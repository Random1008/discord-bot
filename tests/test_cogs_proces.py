from types import SimpleNamespace
from unittest.mock import Mock

import discord

from cogs.proces import ProcesCog, Trial
from config.settings import ADMIN_PERMISSION_ROLE_ID, settings
from services.admin_permission import grant_permission
from services.deepseek_client import judge_trial, judge_turn
from services.proces_config import save_proces_config


class FakeUser:
    def __init__(self, id, display_name, bot=False):
        self.id = id
        self.display_name = display_name
        self.bot = bot
        self.mention = f"<@{id}>"


class FakeMember:
    def __init__(self, id, display_name=None, bot=False):
        self.id = id
        self.display_name = display_name or str(id)
        self.bot = bot
        self.mention = f"<@{id}>"


class FakeRole:
    def __init__(self, id):
        self.id = id


async def make_admin(db_session, id, display_name):
    admin = Mock(spec=discord.Member)
    admin.id = id
    admin.display_name = display_name
    admin.bot = False
    admin.mention = f"<@{id}>"
    admin.roles = [FakeRole(id=ADMIN_PERMISSION_ROLE_ID)]
    await grant_permission(db_session, settings.guild_id, id, granted_by=1)
    return admin


class FakeGuild:
    def __init__(self, id=None):
        self.id = id if id is not None else settings.guild_id


class FakeThread:
    _counter = 0

    def __init__(self, name="thread"):
        FakeThread._counter += 1
        self.id = 900000 + FakeThread._counter
        self.name = name
        self.mention = f"<#{name}>"
        self.sent = []

    async def send(self, content=None, embed=None, view=None, **kwargs):
        self.sent.append({"content": content, "embed": embed, "view": view})
        return None


class FakeMessage:
    def __init__(self):
        self.thread = None

    async def create_thread(self, name):
        self.thread = FakeThread(name=name)
        return self.thread


class FakeChannel:
    def __init__(self):
        self.sent = []

    async def send(self, content=None, embed=None, **kwargs):
        self.sent.append({"content": content, "embed": embed})


class FakeContext:
    def __init__(self, author, guild=None):
        self.author = author
        self.guild = guild if guild is not None else FakeGuild()
        self.message = FakeMessage()
        self.channel = SimpleNamespace(id=123456)
        self.sent = []

    async def send(self, content=None, embed=None, **kwargs):
        self.sent.append({"content": content, "embed": embed})

    def last_text(self) -> str:
        entry = self.sent[-1]
        if entry["embed"] is not None:
            return f"{entry['embed'].title or ''} {entry['embed'].description or ''}"
        return entry["content"] or ""


class FakeBot:
    def __init__(self, session_factory):
        self.session_factory = session_factory


class _FakeSessionContext:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc_info):
        return False


def _cog(db_session):
    return ProcesCog(bot=FakeBot(lambda: _FakeSessionContext(db_session)))


async def _fake_judge_turn(accusation, transcript, api_key, *, opening=False, images=None, reglement=None):
    return {"reponse": "Comment vous défendez-vous ?", "proposer_cloture": False}


async def test_proces_rejects_bot_or_self(db_session, monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-test")
    cog = _cog(db_session)

    # soi-même
    ctx = FakeContext(FakeUser(id=80001, display_name="Moi"))
    await cog.proces.callback(cog, ctx, FakeMember(id=80001, display_name="Moi"))
    assert "Cible invalide" in ctx.last_text()

    # un bot
    ctx2 = FakeContext(FakeUser(id=80001, display_name="Moi"))
    await cog.proces.callback(cog, ctx2, FakeMember(id=999, display_name="Bot", bot=True))
    assert "Cible invalide" in ctx2.last_text()


async def test_proces_requires_api_key(db_session, monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", None)
    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=80001, display_name="Accusateur"))

    await cog.proces.callback(cog, ctx, FakeMember(id=80002, display_name="Criminel"))

    assert "pas configurée" in ctx.last_text()


async def test_proces_opens_thread_and_sets_cooldown(db_session, monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-test")
    monkeypatch.setattr("cogs.proces.judge_turn", _fake_judge_turn)
    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=80001, display_name="Accusateur"))

    await cog.proces.callback(cog, ctx, FakeMember(id=80002, display_name="Criminel"), accusation="il a volé")

    assert "Procès ouvert" in ctx.last_text()
    assert ctx.message.thread is not None
    # le message d'ouverture (annonce + bouton verdict) est le premier posté
    assert len(ctx.message.thread.sent) >= 1
    assert ctx.message.thread.sent[0]["view"] is not None
    # le procès est enregistré
    assert ctx.message.thread.id in cog.trials


async def test_proces_cooldown_blocks_second_attempt(db_session, monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-test")
    monkeypatch.setattr("cogs.proces.judge_turn", _fake_judge_turn)
    cog = _cog(db_session)
    accused = FakeMember(id=80002, display_name="Criminel")

    ctx = FakeContext(FakeUser(id=80001, display_name="Accusateur"))
    await cog.proces.callback(cog, ctx, accused, accusation="vol")
    assert "Procès ouvert" in ctx.last_text()

    ctx2 = FakeContext(FakeUser(id=80001, display_name="Accusateur"))
    await cog.proces.callback(cog, ctx2, accused, accusation="vol")
    assert "Cooldown" in ctx2.last_text()


async def test_proces_bypass_skips_cooldown(db_session, monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-test")
    monkeypatch.setattr("cogs.proces.judge_turn", _fake_judge_turn)
    cog = _cog(db_session)
    admin = await make_admin(db_session, 80001, "Admin")
    accused = FakeMember(id=80002, display_name="Criminel")

    ctx = FakeContext(admin)
    await cog.proces.callback(cog, ctx, accused, accusation="bypass")
    assert "Procès ouvert" in ctx.last_text()

    ctx2 = FakeContext(admin)
    await cog.proces.callback(cog, ctx2, accused, accusation="bypass")
    assert "Procès ouvert" in ctx2.last_text()  # pas de cooldown en bypass


async def test_proces_non_admin_bypass_still_hits_cooldown(db_session, monkeypatch):
    # "bypass" sans être admin est ignoré : le cooldown s'applique normalement.
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-test")
    monkeypatch.setattr("cogs.proces.judge_turn", _fake_judge_turn)
    cog = _cog(db_session)
    accused = FakeMember(id=80002, display_name="Criminel")

    ctx = FakeContext(FakeUser(id=80001, display_name="Accusateur"))
    await cog.proces.callback(cog, ctx, accused, accusation="bypass")
    assert "Procès ouvert" in ctx.last_text()

    ctx2 = FakeContext(FakeUser(id=80001, display_name="Accusateur"))
    await cog.proces.callback(cog, ctx2, accused, accusation="bypass")
    assert "Cooldown" in ctx2.last_text()


async def test_proces_trailing_bypass_keeps_accusation(db_session, monkeypatch):
    # `$proces @joueur2 il a volé bypass` -> bypass activé, accusation conservée.
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-test")
    monkeypatch.setattr("cogs.proces.judge_turn", _fake_judge_turn)
    cog = _cog(db_session)
    admin = await make_admin(db_session, 80001, "Admin")
    accused = FakeMember(id=80002, display_name="Criminel")

    ctx = FakeContext(admin)
    await cog.proces.callback(cog, ctx, accused, accusation="il a volé bypass")
    assert "Procès ouvert" in ctx.last_text()
    thread = ctx.message.thread
    assert thread is not None and len(thread.sent) >= 1
    embed = thread.sent[0]["embed"]
    assert "il a volé" in embed.description
    assert "bypass" not in embed.description


async def test_complice_outside_trial_rejected(db_session, monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-test")
    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=80001, display_name="Accusateur"))
    await cog.complice.callback(cog, ctx)
    assert "uniquement dans un procès" in ctx.last_text()


class _FakeGuildMembers:
    """FakeGuild avec get_member/fetch_member pour les ajouts directs."""

    def __init__(self, members):
        self.id = settings.guild_id
        self.members = list(members)
        self._by_id = {m.id: m for m in members}

    def get_member(self, user_id):
        return self._by_id.get(user_id)

    async def fetch_member(self, user_id):
        member = self._by_id.get(user_id)
        if member is None:
            raise discord.NotFound(Mock(), "membre inconnu")
        return member


def _active_trial(thread_id=123456):
    return Trial(
        guild_id=settings.guild_id,
        thread_id=thread_id,
        accuser_id=80001,
        accused_id=80002,
        accusation="il a volé",
        participants={80001: "Accusateur", 80002: "Accusé"},
    )


async def test_complice_direct_add_by_mention(db_session, monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-test")
    cog = _cog(db_session)
    guild = _FakeGuildMembers(
        [FakeUser(80001, "Accusateur"), FakeUser(80002, "Accusé"), FakeUser(80003, "Témoin")]
    )
    trial = _active_trial()
    cog.trials[trial.thread_id] = trial
    ctx = FakeContext(FakeUser(80001, "Accusateur"), guild=guild)
    await cog.complice.callback(cog, ctx, cible="<@80003>")
    assert 80003 in trial.complices
    assert trial.participants[80003] == "Témoin"
    assert "complice" in ctx.last_text()


async def test_complice_direct_add_by_raw_id(db_session, monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-test")
    cog = _cog(db_session)
    guild = _FakeGuildMembers(
        [FakeUser(80001, "Accusateur"), FakeUser(80002, "Accusé"), FakeUser(80003, "Témoin")]
    )
    trial = _active_trial()
    cog.trials[trial.thread_id] = trial
    ctx = FakeContext(FakeUser(80001, "Accusateur"), guild=guild)
    await cog.complice.callback(cog, ctx, cible="80003")
    assert 80003 in trial.complices


async def test_complice_direct_add_unknown_member_rejected(db_session, monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-test")
    cog = _cog(db_session)
    guild = _FakeGuildMembers([FakeUser(80001, "Accusateur"), FakeUser(80002, "Accusé")])
    trial = _active_trial()
    cog.trials[trial.thread_id] = trial
    ctx = FakeContext(FakeUser(80001, "Accusateur"), guild=guild)
    await cog.complice.callback(cog, ctx, cible="<@99999>")
    assert "introuvable" in ctx.last_text()
    assert trial.complices == []


async def test_complice_direct_add_already_participant_rejected(db_session, monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-test")
    cog = _cog(db_session)
    guild = _FakeGuildMembers(
        [FakeUser(80001, "Accusateur"), FakeUser(80002, "Accusé"), FakeUser(80003, "Témoin")]
    )
    trial = _active_trial()
    cog.trials[trial.thread_id] = trial
    ctx = FakeContext(FakeUser(80001, "Accusateur"), guild=guild)
    await cog.complice.callback(cog, ctx, cible="<@80002>")
    assert "déjà dans le procès" in ctx.last_text()
    assert trial.complices == []


async def test_complice_direct_add_bot_rejected(db_session, monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-test")
    cog = _cog(db_session)
    guild = _FakeGuildMembers(
        [FakeUser(80001, "Accusateur"), FakeUser(80002, "Accusé"), FakeUser(80004, "Robot", bot=True)]
    )
    trial = _active_trial()
    cog.trials[trial.thread_id] = trial
    ctx = FakeContext(FakeUser(80001, "Accusateur"), guild=guild)
    await cog.complice.callback(cog, ctx, cible="<@80004>")
    assert "introuvable" in ctx.last_text()
    assert trial.complices == []


async def test_judge_trial_parses_verdict(monkeypatch):
    async def fake_call(messages, api_key):
        return '{"verdict": "coupable", "raison": "preuves accablantes"}'

    monkeypatch.setattr("services.deepseek_client._call_deepseek", fake_call)

    result = await judge_trial("il a volé", "Accusateur: il a volé\nCriminel: non", "sk-test")

    assert result["verdict"] == "coupable"
    assert "accablantes" in result["raison"]


async def test_judge_turn_parses(monkeypatch):
    async def fake_call(messages, api_key):
        return '{"reponse": "Comment vous défendez-vous ?", "proposer_cloture": false}'

    monkeypatch.setattr("services.deepseek_client._call_deepseek", fake_call)

    result = await judge_turn("il a volé", "Accusateur: il a volé", "sk-test")

    assert result["reponse"] == "Comment vous défendez-vous ?"
    assert result["proposer_cloture"] is False


async def test_render_verdict_bypass_does_not_debit(db_session, monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-test")

    async def fake_judge_trial(accusation, transcript, api_key, *, images=None, reglement=None):
        return {"verdict": "coupable", "raison": "preuves accablantes"}

    monkeypatch.setattr("cogs.proces.judge_trial", fake_judge_trial)

    calls = []

    async def spy_add_balance(session, guild_id, user_id, amount):
        calls.append((user_id, amount))
        return 0

    monkeypatch.setattr("cogs.proces.add_balance", spy_add_balance)

    cog = _cog(db_session)
    trial = Trial(
        guild_id=settings.guild_id,
        thread_id=999999,
        accuser_id=80001,
        accused_id=80002,
        accusation="vol",
        bypass=True,
        participants={80001: "A", 80002: "B"},
    )
    trial.participant_messages = 3
    channel = FakeChannel()
    await cog._render_final_verdict(trial, channel)

    assert calls == []  # aucun débit en mode bypass
    assert channel.sent
    assert "bypass" in (channel.sent[-1]["embed"].description or "")


async def test_judge_receives_configured_reglement(db_session, monkeypatch, tmp_path):
    # Le règlement stocké dans proces_config.json doit être transmis au juge IA
    # à l'ouverture d'un procès.
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-test")
    cfg_path = tmp_path / "proces_config.json"
    save_proces_config(cfg_path, "Titre", "Texte", reglement="Article test : pas d'insultes.")
    monkeypatch.setattr("cogs.proces.DEFAULT_PROCES_CONFIG_PATH", cfg_path)

    seen = {}

    async def spy_judge_turn(accusation, transcript, api_key, *, opening=False, images=None, reglement=None):
        seen["reglement"] = reglement
        return {"reponse": "Bonjour, présentez-vous.", "proposer_cloture": False}

    monkeypatch.setattr("cogs.proces.judge_turn", spy_judge_turn)
    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=80001, display_name="Accusateur"))

    await cog.proces.callback(
        cog, ctx, FakeMember(id=80002, display_name="Criminel"), accusation="il m'a insulté"
    )

    assert seen.get("reglement") == "Article test : pas d'insultes."


async def test_judge_sovereign_closure_closes_and_sentences(db_session, monkeypatch):
    # Parole absolue du juge : quand le juge décide de clore (proposer_cloture),
    # le procès se ferme et la sentence est rendue immédiatement — plus de
    # « Proposition de clôture » soumise au vote des participants.
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-test")
    cog = _cog(db_session)
    trial = _active_trial()
    cog.trials[trial.thread_id] = trial

    async def fake_judge_turn(accusation, transcript, api_key, *, opening=False, images=None, reglement=None):
        return {"reponse": "J'ai entendu les deux parties. Les débats sont clos.", "proposer_cloture": True}

    async def fake_judge_trial(accusation, transcript, api_key, *, images=None, reglement=None):
        return {"verdict": "innocent", "raison": "accusation non étayée"}

    monkeypatch.setattr("cogs.proces.judge_turn", fake_judge_turn)
    monkeypatch.setattr("cogs.proces.judge_trial", fake_judge_trial)

    class _Typing:
        async def __aenter__(self):
            return None

        async def __aexit__(self, *exc_info):
            return False

    class _TrialChannel(FakeChannel):
        def __init__(self, channel_id):
            super().__init__()
            self.id = channel_id

        def typing(self):
            return _Typing()

    channel = _TrialChannel(trial.thread_id)
    message = SimpleNamespace(
        author=FakeUser(80002, "Accusé"),
        guild=FakeGuild(),
        channel=channel,
        content="Je n'ai rien fait !",
        attachments=[],
        embeds=[],
    )

    await cog.on_message(message)

    assert trial.closure_proposed is True
    assert trial.closed is True
    assert trial.thread_id not in cog.trials
    titles = [entry["embed"].title or "" for entry in channel.sent if entry["embed"] is not None]
    assert "⚖️ Le Juge" in titles  # l'annonce de clôture du juge a été postée
    assert any(t.startswith("⚖️ Verdict") for t in titles)  # la sentence est rendue
    assert "🔨 Proposition de clôture" not in titles  # plus de vote des participants
    assert all("view" not in entry for entry in channel.sent)  # aucun bouton de vote

    # Après la clôture, les messages des participants sont ignorés.
    sent_before = len(channel.sent)
    await cog.on_message(message)
    assert len(channel.sent) == sent_before


async def test_judge_opening_can_close_immediately(db_session, monkeypatch):
    # Même à l'ouverture, si le juge estime pouvoir trancher, il clôt les débats
    # et rend la sentence directement (parole absolue).
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-test")
    cog = _cog(db_session)
    trial = _active_trial()

    async def fake_judge_turn(accusation, transcript, api_key, *, opening=False, images=None, reglement=None):
        assert opening is True
        return {"reponse": "Les faits sont clairs. Je clos les débats.", "proposer_cloture": True}

    async def fake_judge_trial(accusation, transcript, api_key, *, images=None, reglement=None):
        return {"verdict": "innocent", "raison": "accusation non étayée"}

    monkeypatch.setattr("cogs.proces.judge_turn", fake_judge_turn)
    monkeypatch.setattr("cogs.proces.judge_trial", fake_judge_trial)

    channel = FakeChannel()
    await cog._judge_opening(trial, channel)

    assert trial.closed is True
    titles = [entry["embed"].title or "" for entry in channel.sent if entry["embed"] is not None]
    assert "⚖️ Le Juge" in titles
    assert any(t.startswith("⚖️ Verdict") for t in titles)
    assert "🔨 Proposition de clôture" not in titles


async def test_verdict_guilty_can_leave_accused_in_unlimited_debt(db_session, monkeypatch):
    # Sentence souveraine : si le condamné n'a pas de quoi payer, son solde peut
    # devenir négatif SANS le plancher habituel de -5000 (dette illimitée).
    from models.economy import Economy

    monkeypatch.setattr(settings, "deepseek_api_key", "sk-test")

    async def fake_judge_trial(accusation, transcript, api_key, *, images=None, reglement=None):
        return {"verdict": "coupable", "raison": "preuves accablantes"}

    monkeypatch.setattr("cogs.proces.judge_trial", fake_judge_trial)

    cog = _cog(db_session)
    trial = Trial(
        guild_id=settings.guild_id,
        thread_id=999998,
        accuser_id=80001,
        accused_id=80002,
        accusation="vol",
        participants={80001: "A", 80002: "B"},
    )
    trial.participant_messages = 60  # 60 × 100 = 6000 credits demandés

    channel = FakeChannel()
    await cog._render_final_verdict(trial, channel)

    accuser = await db_session.get(Economy, (settings.guild_id, 80001))
    accused = await db_session.get(Economy, (settings.guild_id, 80002))
    assert accuser is not None and accuser.balance == 6000
    assert accused is not None and accused.balance == -6000  # sous -5000 : plancher levé


async def test_proces_end_renders_judgment_on_current_information(db_session, monkeypatch):
    # `.proces end` (admin) : le juge rend immédiatement son jugement sur la
    # base des éléments déjà présentés — sans attendre sa décision de clore.
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-test")
    cog = _cog(db_session)
    trial = _active_trial()
    trial.history = [
        ("Accusé", "je n'ai rien fait"),
        ("Accusateur", "il m'a volé 1000 credits"),
    ]
    trial.participant_messages = 2
    cog.trials[trial.thread_id] = trial

    seen = {}

    async def fake_judge_trial(accusation, transcript, api_key, *, images=None, reglement=None):
        seen["transcript"] = transcript
        return {"verdict": "innocent", "raison": "accusation non étayée"}

    monkeypatch.setattr("cogs.proces.judge_trial", fake_judge_trial)

    class _Channel(FakeChannel):
        def __init__(self, channel_id):
            super().__init__()
            self.id = channel_id

    channel = _Channel(trial.thread_id)
    ctx = FakeContext(FakeUser(80001, "Admin"))
    ctx.channel = channel

    await cog.proces_end.callback(cog, ctx)

    assert trial.closed is True
    assert trial.thread_id not in cog.trials
    # l'annonce de clôture du juge a été postée…
    titles_ctx = [entry["embed"].title or "" for entry in ctx.sent if entry["embed"] is not None]
    assert "⚖️ Le Juge" in titles_ctx
    # … et la sentence rendue dans le fil, sur la base du débat déjà tenu.
    titles = [entry["embed"].title or "" for entry in channel.sent if entry["embed"] is not None]
    assert any(t.startswith("⚖️ Verdict") for t in titles)
    assert "je n'ai rien fait" in seen["transcript"]
    assert "il m'a volé 1000 credits" in seen["transcript"]


async def test_proces_end_outside_trial_rejected(db_session, monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-test")
    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(80001, "Admin"))
    await cog.proces_end.callback(cog, ctx)
    assert "Aucun procès" in ctx.last_text()
