import json

import cogs.suggestions as suggestions_module
from cogs.suggestions import (
    SUGGESTION_APPROVER_IDS,
    AcceptRefuseView,
    SuggestionSession,
    SuggestionsCog,
    build_result_embed,
    build_validation_embed,
    build_validation_result_embed,
)
from config.settings import settings
from services.deepseek_client import ClarificationTurn, DeepSeekError


class FakeUser:
    def __init__(self, id, display_name="User", mention=None):
        self.id = id
        self.display_name = display_name
        self.mention = mention or f"<@{id}>"
        self.bot = False

    def __str__(self):
        return self.display_name


class FakeChannel:
    def __init__(self, id, guild=None):
        self.id = id
        self.guild = guild
        self.sent = []

    async def send(self, content=None, embed=None, view=None):
        self.sent.append({"content": content, "embed": embed, "view": view})


class FakeBot:
    def __init__(self, channels=None):
        self._channels = channels or {}

    def get_channel(self, channel_id):
        return self._channels.get(channel_id)


class FakeGuild:
    def __init__(self, id=1, channels=None):
        self.id = id
        self._channels = channels or {}

    def get_channel(self, channel_id):
        return self._channels.get(channel_id)


class FakeDiscordMessageHandle:
    def __init__(self):
        self.edits = []

    async def edit(self, embed=None, view=None):
        self.edits.append({"embed": embed, "view": view})


class FakeResponse:
    def __init__(self):
        self.messages = []
        self.edited = []

    async def send_message(self, content, ephemeral=False):
        self.messages.append((content, ephemeral))

    async def edit_message(self, embed=None, view=None):
        self.edited.append({"embed": embed, "view": view})


class FakeInteraction:
    def __init__(self, user, guild):
        self.user = user
        self.guild = guild
        self.response = FakeResponse()
        self.message = FakeDiscordMessageHandle()


class FakeContext:
    def __init__(self, author, guild, channel):
        self.author = author
        self.guild = guild
        self.channel = channel
        self.sent = []

    async def send(self, content=None, **kwargs):
        self.sent.append(content)


class FakeMessage:
    def __init__(self, author, channel, content):
        self.author = author
        self.channel = channel
        self.content = content


def _cog():
    return SuggestionsCog(bot=object())


def test_build_validation_embed_mentions_requester_and_idea():
    embed = build_validation_embed(FakeUser(1, "Alice"), "je veux une commande musique")

    assert "je veux une commande musique" in embed.description
    assert "<@1>" in embed.description


def test_build_validation_result_embed_reflects_accepted_and_refused():
    accepted = build_validation_result_embed("Alice", "idea", accepted=True, approver=FakeUser(2, "Bob"))
    refused = build_validation_result_embed("Alice", "idea", accepted=False, approver=FakeUser(2, "Bob"))

    assert "acceptée" in accepted.title
    assert "refusée" in refused.title


async def test_suggest_rejects_wrong_channel(monkeypatch):
    monkeypatch.setattr(settings, "suggestion_channel_id", "100")
    cog = _cog()
    ctx = FakeContext(FakeUser(1), FakeGuild(), FakeChannel(id=999))

    await cog.suggest.callback(cog, ctx, idea="je veux une commande musique")

    assert "salon dédié" in ctx.sent[0]


async def test_suggest_warns_when_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "suggestion_channel_id", "100")
    monkeypatch.setattr(settings, "suggestion_validation_channel_id", None)
    cog = _cog()
    ctx = FakeContext(FakeUser(1), FakeGuild(), FakeChannel(id=100))

    await cog.suggest.callback(cog, ctx, idea="idea")

    assert "configuré" in ctx.sent[0]


async def test_suggest_posts_to_validation_channel_and_confirms(monkeypatch):
    monkeypatch.setattr(settings, "suggestion_channel_id", "100")
    monkeypatch.setattr(settings, "suggestion_validation_channel_id", "200")
    monkeypatch.setattr(settings, "deepseek_api_key", "key")
    cog = _cog()
    validation_channel = FakeChannel(id=200)
    guild = FakeGuild(channels={200: validation_channel})
    ctx = FakeContext(FakeUser(1, "Requester"), guild, FakeChannel(id=100))

    await cog.suggest.callback(cog, ctx, idea="je veux une commande musique")

    assert len(validation_channel.sent) == 1
    assert validation_channel.sent[0]["view"] is not None
    assert "transmise pour validation" in ctx.sent[0]
    assert 1 in cog.open_requesters


async def test_suggest_blocks_a_second_submission_while_one_is_open(monkeypatch):
    monkeypatch.setattr(settings, "suggestion_channel_id", "100")
    monkeypatch.setattr(settings, "suggestion_validation_channel_id", "200")
    monkeypatch.setattr(settings, "deepseek_api_key", "key")
    cog = _cog()
    validation_channel = FakeChannel(id=200)
    guild = FakeGuild(channels={200: validation_channel})
    ctx = FakeContext(FakeUser(1, "Requester"), guild, FakeChannel(id=100))

    await cog.suggest.callback(cog, ctx, idea="idée 1")
    await cog.suggest.callback(cog, ctx, idea="idée 2")

    assert len(validation_channel.sent) == 1
    assert "en cours" in ctx.sent[-1]


async def test_interaction_check_blocks_unauthorized_users():
    cog = _cog()
    view = AcceptRefuseView(cog, 1, "Requester", "idea", 100, 1)
    interaction = FakeInteraction(FakeUser(999, "Intruder"), FakeGuild())

    allowed = await view.interaction_check(interaction)

    assert allowed is False
    assert interaction.response.messages


async def test_interaction_check_allows_the_two_designated_approvers():
    cog = _cog()
    view = AcceptRefuseView(cog, 1, "Requester", "idea", 100, 1)
    for approver_id in SUGGESTION_APPROVER_IDS:
        interaction = FakeInteraction(FakeUser(approver_id, "Approver"), FakeGuild())
        assert await view.interaction_check(interaction) is True


async def test_handle_refuse_edits_embed_logs_and_notifies_requester(monkeypatch):
    monkeypatch.setattr(settings, "admin_log_channel_id", "42")
    cog = _cog()
    approver_id = next(iter(SUGGESTION_APPROVER_IDS))
    suggestion_channel = FakeChannel(id=100)
    log_channel = FakeChannel(id=42)
    guild = FakeGuild(channels={100: suggestion_channel, 42: log_channel})
    cog.open_requesters.add(1)
    view = AcceptRefuseView(cog, 1, "Requester", "idea", 100, guild.id)
    interaction = FakeInteraction(FakeUser(approver_id, "Approver"), guild)

    await cog.handle_refuse(interaction, view)

    assert interaction.response.edited
    assert all(item.disabled for item in view.children)
    assert 1 not in cog.open_requesters
    assert len(log_channel.sent) == 1
    assert len(suggestion_channel.sent) == 1
    assert "<@1>" in suggestion_channel.sent[0]["content"]


async def test_handle_accept_finalizes_immediately_when_deepseek_needs_no_questions(monkeypatch):
    monkeypatch.setattr(settings, "admin_log_channel_id", "42")
    monkeypatch.setattr(settings, "deepseek_api_key", "key")

    async def fake_turn(idea, history, api_key, force_done=False):
        return ClarificationTurn(done=True, final_prompt="Prompt final")

    monkeypatch.setattr(suggestions_module, "conduct_clarification_turn", fake_turn)

    written = {}

    def fake_write(**kwargs):
        written.update(kwargs)
        return "job-id-1234"

    monkeypatch.setattr(suggestions_module, "write_suggestion_job", fake_write)

    cog = _cog()
    approver_id = next(iter(SUGGESTION_APPROVER_IDS))
    suggestion_channel = FakeChannel(id=100)
    log_channel = FakeChannel(id=42)
    guild = FakeGuild(channels={100: suggestion_channel, 42: log_channel})
    cog.open_requesters.add(1)
    view = AcceptRefuseView(cog, 1, "Requester", "idea", 100, guild.id)
    interaction = FakeInteraction(FakeUser(approver_id, "Approver"), guild)

    await cog.handle_accept(interaction, view)

    assert written["final_prompt"] == "Prompt final"
    assert 1 not in cog.open_requesters
    assert 1 not in cog.active_sessions
    assert any("job-id" in (m["content"] or "") for m in suggestion_channel.sent)


async def test_handle_accept_starts_interview_when_deepseek_has_a_question(monkeypatch):
    monkeypatch.setattr(settings, "admin_log_channel_id", "42")
    monkeypatch.setattr(settings, "deepseek_api_key", "key")

    async def fake_turn(idea, history, api_key, force_done=False):
        return ClarificationTurn(done=False, question="Quel préfixe veux-tu ?")

    monkeypatch.setattr(suggestions_module, "conduct_clarification_turn", fake_turn)

    cog = _cog()
    approver_id = next(iter(SUGGESTION_APPROVER_IDS))
    suggestion_channel = FakeChannel(id=100)
    guild = FakeGuild(channels={100: suggestion_channel})
    view = AcceptRefuseView(cog, 1, "Requester", "idea", 100, guild.id)
    interaction = FakeInteraction(FakeUser(approver_id, "Approver"), guild)

    await cog.handle_accept(interaction, view)

    assert 1 in cog.active_sessions
    assert cog.active_sessions[1].pending_question == "Quel préfixe veux-tu ?"
    assert "Quel préfixe" in suggestion_channel.sent[-1]["content"]


async def test_handle_accept_reports_deepseek_error_gracefully(monkeypatch):
    monkeypatch.setattr(settings, "admin_log_channel_id", None)
    monkeypatch.setattr(settings, "deepseek_api_key", "key")

    async def fake_turn(*args, **kwargs):
        raise DeepSeekError("boom")

    monkeypatch.setattr(suggestions_module, "conduct_clarification_turn", fake_turn)

    cog = _cog()
    approver_id = next(iter(SUGGESTION_APPROVER_IDS))
    suggestion_channel = FakeChannel(id=100)
    guild = FakeGuild(channels={100: suggestion_channel})
    cog.open_requesters.add(1)
    view = AcceptRefuseView(cog, 1, "Requester", "idea", 100, guild.id)
    interaction = FakeInteraction(FakeUser(approver_id, "Approver"), guild)

    await cog.handle_accept(interaction, view)

    assert 1 not in cog.open_requesters
    assert "Erreur" in suggestion_channel.sent[-1]["content"]


async def test_on_message_ignores_users_without_an_active_session():
    cog = _cog()
    channel = FakeChannel(id=100)
    message = FakeMessage(FakeUser(1), channel, "salut")

    await cog.on_message(message)  # must not raise, nothing to do


async def test_on_message_ignores_bot_authors():
    cog = _cog()
    author = FakeUser(1)
    author.bot = True
    session = SuggestionSession(1, "Requester", 1, 100, "idea", pending_question="Q ?")
    cog.active_sessions[1] = session
    channel = FakeChannel(id=100)
    message = FakeMessage(author, channel, "réponse")

    await cog.on_message(message)

    assert session.history == []


async def test_on_message_ignores_command_prefixed_replies(monkeypatch):
    called = False

    async def fake_turn(*args, **kwargs):
        nonlocal called
        called = True
        return ClarificationTurn(done=False, question="x")

    monkeypatch.setattr(suggestions_module, "conduct_clarification_turn", fake_turn)

    cog = _cog()
    session = SuggestionSession(1, "Requester", 1, 100, "idea", pending_question="Q ?")
    cog.active_sessions[1] = session
    channel = FakeChannel(id=100)
    message = FakeMessage(FakeUser(1), channel, "!bal")

    await cog.on_message(message)

    assert called is False
    assert session.history == []


async def test_on_message_answers_are_forwarded_to_deepseek_and_advance_the_session(monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "key")
    calls = []

    async def fake_turn(idea, history, api_key, force_done=False):
        calls.append((idea, list(history), force_done))
        return ClarificationTurn(done=False, question="Question suivante ?")

    monkeypatch.setattr(suggestions_module, "conduct_clarification_turn", fake_turn)

    cog = _cog()
    session = SuggestionSession(1, "Requester", 1, 100, "idea", pending_question="Quel préfixe ?")
    cog.active_sessions[1] = session
    channel = FakeChannel(id=100)
    message = FakeMessage(FakeUser(1), channel, "oui")

    await cog.on_message(message)

    assert calls[0][1] == [("Quel préfixe ?", "oui")]
    assert session.history == [("Quel préfixe ?", "oui")]
    assert session.pending_question == "Question suivante ?"
    assert "Question suivante" in channel.sent[-1]["content"]


async def test_on_message_forces_done_after_max_questions(monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "key")

    async def fake_turn(idea, history, api_key, force_done=False):
        assert force_done is True
        return ClarificationTurn(done=True, final_prompt="Prompt final")

    monkeypatch.setattr(suggestions_module, "conduct_clarification_turn", fake_turn)

    written = {}
    monkeypatch.setattr(
        suggestions_module, "write_suggestion_job", lambda **kw: (written.update(kw), "job-id")[1]
    )

    cog = _cog()
    history = [(f"Q{i}", f"R{i}") for i in range(suggestions_module.MAX_CLARIFICATION_QUESTIONS - 1)]
    session = SuggestionSession(1, "Requester", 1, 100, "idea", history=history, pending_question="Dernière ?")
    cog.active_sessions[1] = session
    channel = FakeChannel(id=100)
    message = FakeMessage(FakeUser(1), channel, "réponse finale")

    await cog.on_message(message)

    assert 1 not in cog.active_sessions
    assert written["final_prompt"] == "Prompt final"


async def test_on_message_reports_deepseek_error_and_preserves_session(monkeypatch):
    async def fake_turn(*args, **kwargs):
        raise DeepSeekError("boom")

    monkeypatch.setattr(suggestions_module, "conduct_clarification_turn", fake_turn)

    cog = _cog()
    session = SuggestionSession(1, "Requester", 1, 100, "idea", pending_question="Q ?")
    cog.active_sessions[1] = session
    channel = FakeChannel(id=100)
    message = FakeMessage(FakeUser(1), channel, "réponse")

    await cog.on_message(message)

    assert 1 in cog.active_sessions
    assert session.history == []
    assert "Erreur" in channel.sent[-1]["content"]


def test_build_result_embed_success_mentions_the_idea():
    embed = build_result_embed({"idea": "musique", "requester_display": "Alice"}, success=True)

    assert "implémentée" in embed.title
    assert embed.description == "musique"


def test_build_result_embed_failure_includes_stage_and_log_tail():
    embed = build_result_embed(
        {"idea": "musique", "requester_display": "Alice", "stage": "tests", "test_output": "2 failed"},
        success=False,
    )

    assert "tests" in embed.title
    field_values = {f.name: f.value for f in embed.fields}
    assert "2 failed" in field_values["Détail (fin du log)"]


async def test_poll_once_reports_a_done_result_and_removes_the_file(tmp_path, monkeypatch):
    done_dir = tmp_path / "done"
    monkeypatch.setattr(suggestions_module, "DONE_DIR", done_dir)
    monkeypatch.setattr(suggestions_module, "FAILED_DIR", tmp_path / "failed")
    done_dir.mkdir(parents=True)
    result = {
        "id": "job-1",
        "requester_id": 1,
        "requester_display": "Requester",
        "guild_id": 1,
        "channel_id": 100,
        "idea": "musique",
        "success": True,
        "stage": "done",
    }
    (done_dir / "job-1.json").write_text(json.dumps(result), encoding="utf-8")

    channel = FakeChannel(id=100)
    cog = SuggestionsCog(bot=FakeBot(channels={100: channel}))

    await cog._poll_once()

    assert len(channel.sent) == 1
    assert "<@1>" in channel.sent[0]["content"]
    assert not (done_dir / "job-1.json").exists()


async def test_poll_once_reports_a_failed_result(tmp_path, monkeypatch):
    failed_dir = tmp_path / "failed"
    monkeypatch.setattr(suggestions_module, "DONE_DIR", tmp_path / "done")
    monkeypatch.setattr(suggestions_module, "FAILED_DIR", failed_dir)
    failed_dir.mkdir(parents=True)
    result = {
        "id": "job-2",
        "requester_id": 2,
        "requester_display": "Requester",
        "guild_id": 1,
        "channel_id": 100,
        "idea": "musique",
        "success": False,
        "stage": "tests",
        "test_output": "2 failed",
    }
    (failed_dir / "job-2.json").write_text(json.dumps(result), encoding="utf-8")

    channel = FakeChannel(id=100)
    cog = SuggestionsCog(bot=FakeBot(channels={100: channel}))

    await cog._poll_once()

    assert len(channel.sent) == 1
    assert "Échec" in channel.sent[0]["embed"].title
    assert not (failed_dir / "job-2.json").exists()


async def test_poll_once_skips_missing_directories(tmp_path, monkeypatch):
    monkeypatch.setattr(suggestions_module, "DONE_DIR", tmp_path / "nope-done")
    monkeypatch.setattr(suggestions_module, "FAILED_DIR", tmp_path / "nope-failed")

    cog = SuggestionsCog(bot=FakeBot())

    await cog._poll_once()  # must not raise


async def test_poll_once_removes_the_file_even_if_no_channel_is_found(tmp_path, monkeypatch):
    done_dir = tmp_path / "done"
    monkeypatch.setattr(suggestions_module, "DONE_DIR", done_dir)
    monkeypatch.setattr(suggestions_module, "FAILED_DIR", tmp_path / "failed")
    done_dir.mkdir(parents=True)
    result = {
        "id": "job-3",
        "requester_id": 3,
        "requester_display": "Requester",
        "guild_id": 1,
        "channel_id": 999,
        "idea": "musique",
        "success": True,
        "stage": "done",
    }
    (done_dir / "job-3.json").write_text(json.dumps(result), encoding="utf-8")

    cog = SuggestionsCog(bot=FakeBot(channels={}))

    await cog._poll_once()

    assert not (done_dir / "job-3.json").exists()
