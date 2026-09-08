import random
from unittest.mock import Mock

import discord

from cogs.underworld import MafiaMarketView, UnderworldCog
from config.settings import ADMIN_PERMISSION_ROLE_ID, settings
from models.economy import Economy
from services.admin_permission import grant_permission
from services.economy import add_balance
from services.market import add_generic_item
from services.users import get_or_create_user


class FakeUser:
    def __init__(self, id, display_name, bot=False):
        self.id = id
        self.display_name = display_name
        self.bot = bot


class FakeMember:
    def __init__(self, id, display_name=None, name=None, bot=False):
        self.id = id
        self.display_name = display_name or str(id)
        self.name = name or self.display_name
        self.bot = bot


class FakeChannel:
    def __init__(self, id=1, guild=None):
        self.id = id
        self.guild = guild
        self.mention = f"<#{id}>"
        self.sent = []
        self.permission_overwrites = []

    async def send(self, content=None, embed=None, **kwargs):
        self.sent.append({"content": content, "embed": embed})
        return None

    async def set_permissions(self, target, **kwargs):
        self.permission_overwrites.append((target, kwargs))


class FakeRole:
    def __init__(self, id):
        self.id = id


async def make_admin(db_session, id, display_name, guild_id=None):
    admin = Mock(spec=discord.Member)
    admin.id = id
    admin.display_name = display_name
    admin.bot = False
    admin.roles = [FakeRole(id=ADMIN_PERMISSION_ROLE_ID)]
    await grant_permission(db_session, guild_id if guild_id is not None else settings.guild_id, id, granted_by=1)
    return admin


class FakeGuild:
    def __init__(self, id=None, members=None):
        self.id = id if id is not None else settings.guild_id
        self.members = members or []
        self.channels = {}

    def get_member(self, user_id):
        for m in self.members:
            if m.id == user_id:
                return m
        return None

    async def fetch_member(self, user_id):
        return self.get_member(user_id)

    def get_channel(self, channel_id):
        return self.channels.get(channel_id)


class FakeContext:
    def __init__(self, author, guild=None, channel=None):
        self.author = author
        self.guild = guild if guild is not None else FakeGuild()
        self.channel = channel if channel is not None else FakeChannel()
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
    return UnderworldCog(bot=FakeBot(lambda: _FakeSessionContext(db_session)))


def _ctx_with_victim(author_id, author_name, victim_id, victim_name, victim_balance):
    """Construit un contexte dont la guilde connaît la victime (pour résoudre une cible)."""
    guild = FakeGuild(members=[FakeMember(id=victim_id, display_name=victim_name)])
    return FakeContext(FakeUser(id=author_id, display_name=author_name), guild=guild)


def _mafia_ctx(author_id, author_name, channel_id=12345):
    """Construit un contexte + un salon mafia fictif (guild.get_channel résout le salon)."""
    guild = FakeGuild()
    guild.members.append(FakeMember(id=author_id, display_name=author_name))
    channel = FakeChannel(id=channel_id, guild=guild)
    guild.channels[channel_id] = channel
    ctx = FakeContext(FakeUser(id=author_id, display_name=author_name), guild=guild)
    return ctx, channel


async def test_hack_success_credits_coins(db_session, monkeypatch):
    monkeypatch.setattr(random, "random", lambda: 0.0)
    monkeypatch.setattr(random, "randint", lambda a, b: 250)

    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=50001, display_name="Hacker"))

    await cog.hack.callback(cog, ctx)

    economy = await db_session.get(Economy, (settings.guild_id, 50001))
    assert economy.balance == 250
    assert "réussi" in ctx.last_text()


async def test_hack_no_target_always_succeeds(db_session, monkeypatch):
    monkeypatch.setattr(random, "random", lambda: 0.99)
    monkeypatch.setattr(random, "randint", lambda a, b: 250)

    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=50009, display_name="Solo"))

    await cog.hack.callback(cog, ctx)

    economy = await db_session.get(Economy, (settings.guild_id, 50009))
    assert economy.balance == 250
    assert "réussi" in ctx.last_text()


async def test_hack_target_success_steals_from_victim(db_session, monkeypatch):
    await get_or_create_user(db_session, settings.guild_id, 60001, "Victime")
    await add_balance(db_session, settings.guild_id, 60001, 10000)
    await db_session.commit()

    monkeypatch.setattr(random, "random", lambda: 0.0)
    monkeypatch.setattr(random, "randint", lambda a, b: 250)

    cog = _cog(db_session)
    ctx = _ctx_with_victim(50001, "Hacker", 60001, "Victime", 10000)

    await cog.hack.callback(cog, ctx, "60001")

    attacker = await db_session.get(Economy, (settings.guild_id, 50001))
    victim = await db_session.get(Economy, (settings.guild_id, 60001))
    assert attacker.balance == 500
    assert victim.balance == 9500
    assert "volé" in ctx.last_text()


async def test_hack_mention_target_steals_from_victim(db_session, monkeypatch):
    await get_or_create_user(db_session, settings.guild_id, 60004, "Mention")
    await add_balance(db_session, settings.guild_id, 60004, 1000)
    await db_session.commit()

    monkeypatch.setattr(random, "random", lambda: 0.0)
    monkeypatch.setattr(random, "randint", lambda a, b: 100)

    cog = _cog(db_session)
    ctx = _ctx_with_victim(50001, "Hacker", 60004, "Mention", 1000)

    await cog.hack.callback(cog, ctx, "<@60004>")

    attacker = await db_session.get(Economy, (settings.guild_id, 50001))
    victim = await db_session.get(Economy, (settings.guild_id, 60004))
    assert attacker.balance == 200
    assert victim.balance == 800


async def test_hack_target_failure_pays_fine(db_session, monkeypatch):
    await get_or_create_user(db_session, settings.guild_id, 60002, "Victime")
    await add_balance(db_session, settings.guild_id, 60002, 10000)
    await db_session.commit()

    monkeypatch.setattr(random, "random", lambda: 0.99)

    cog = _cog(db_session)
    ctx = _ctx_with_victim(50002, "ScriptKiddie", 60002, "Victime", 10000)

    await cog.hack.callback(cog, ctx, "60002")

    attacker = await db_session.get(Economy, (settings.guild_id, 50002))
    victim = await db_session.get(Economy, (settings.guild_id, 60002))
    assert attacker.balance == -100
    assert victim.balance == 10000
    assert "raté" in ctx.last_text()


async def test_hack_target_with_nothing_to_steal_rejected(db_session, monkeypatch):
    await get_or_create_user(db_session, settings.guild_id, 60005, "Pauvre")
    await db_session.commit()

    cog = _cog(db_session)
    ctx = _ctx_with_victim(50002, "ScriptKiddie", 60005, "Pauvre", 0)

    await cog.hack.callback(cog, ctx, "60005")

    assert "rien à voler" in ctx.last_text()


async def test_hack_cooldown_blocks_second_attempt(db_session, monkeypatch):
    monkeypatch.setattr(random, "random", lambda: 0.0)
    monkeypatch.setattr(random, "randint", lambda a, b: 100)

    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=50003, display_name="Impatient"))

    await cog.hack.callback(cog, ctx)
    await cog.hack.callback(cog, ctx)

    assert "Cooldown" in ctx.last_text()


async def test_braquage_failure_jails(db_session, monkeypatch):
    monkeypatch.setattr(random, "random", lambda: 0.99)

    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=50004, display_name="Braqueur"))

    await cog.braquage.callback(cog, ctx)
    assert "prison" in ctx.last_text().lower()

    ctx2 = FakeContext(FakeUser(id=50004, display_name="Braqueur"))
    await cog.braquage.callback(cog, ctx2)
    assert "prison" in ctx2.last_text().lower()


async def test_braquage_ignores_target_token(db_session, monkeypatch):
    await get_or_create_user(db_session, settings.guild_id, 60006, "Riche")
    await add_balance(db_session, settings.guild_id, 60006, 100000)
    await db_session.commit()

    monkeypatch.setattr(random, "random", lambda: 0.0)
    monkeypatch.setattr(random, "randint", lambda a, b: 5000)

    cog = _cog(db_session)
    ctx = _ctx_with_victim(50001, "Braqueur", 60006, "Riche", 100000)

    await cog.braquage.callback(cog, ctx, "60006")

    attacker = await db_session.get(Economy, (settings.guild_id, 50001))
    victim = await db_session.get(Economy, (settings.guild_id, 60006))
    assert attacker.balance == 5000
    assert victim.balance == 100000


async def test_falsifier_success_applies_multiplier(db_session, monkeypatch):
    monkeypatch.setattr(random, "random", lambda: 0.0)
    monkeypatch.setattr(random, "randint", lambda a, b: 200)
    monkeypatch.setattr(random, "uniform", lambda a, b: 2.0)

    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=50005, display_name="Faussaire"))

    await cog.falsifier.callback(cog, ctx)

    economy = await db_session.get(Economy, (settings.guild_id, 50005))
    assert economy.balance == 400
    assert "bonus" in ctx.last_text()


async def test_blanchir_success_multiplies(db_session, monkeypatch):
    await get_or_create_user(db_session, settings.guild_id, 50006, "Blanchisseur")
    await add_balance(db_session, settings.guild_id, 50006, 1000)
    await db_session.commit()

    monkeypatch.setattr(random, "random", lambda: 0.0)
    monkeypatch.setattr(random, "uniform", lambda a, b: 1.5)

    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=50006, display_name="Blanchisseur"))

    await cog.blanchir.callback(cog, ctx, "500")

    economy = await db_session.get(Economy, (settings.guild_id, 50006))
    assert economy.balance == 1250


async def test_blanchir_failure_seizes(db_session, monkeypatch):
    await get_or_create_user(db_session, settings.guild_id, 50007, "Saisi")
    await add_balance(db_session, settings.guild_id, 50007, 1000)
    await db_session.commit()

    monkeypatch.setattr(random, "random", lambda: 0.99)

    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=50007, display_name="Saisi"))

    await cog.blanchir.callback(cog, ctx, "500")

    economy = await db_session.get(Economy, (settings.guild_id, 50007))
    assert economy.balance == 500


async def test_hack_bypass_skips_cooldown_for_admin(db_session, monkeypatch):
    monkeypatch.setattr(random, "random", lambda: 0.0)
    monkeypatch.setattr(random, "randint", lambda a, b: 100)

    cog = _cog(db_session)
    ctx = FakeContext(await make_admin(db_session, id=50008, display_name="AdminHacker"))

    await cog.hack.callback(cog, ctx, "bypass")
    await cog.hack.callback(cog, ctx, "bypass")

    assert "réussi" in ctx.last_text()
    assert "bypass" in ctx.last_text()


# --- Marché de la mafia ---

async def test_mafia_requires_configured_channel(db_session, monkeypatch):
    monkeypatch.setattr(settings, "mafia_channel_id", None)

    cog = _cog(db_session)
    ctx, _ = _mafia_ctx(70003, "Mafioso")

    await cog.mafia.callback(cog, ctx)

    assert "pas configuré" in ctx.last_text()


async def test_mafia_failure_jails(db_session, monkeypatch):
    await get_or_create_user(db_session, settings.guild_id, 70001, "Mafioso")
    await add_balance(db_session, settings.guild_id, 70001, 10000)
    await db_session.commit()

    monkeypatch.setattr(settings, "mafia_channel_id", "12345")
    monkeypatch.setattr(random, "random", lambda: 0.99)  # échec (>= 0.35)

    cog = _cog(db_session)
    ctx, _ = _mafia_ctx(70001, "Mafioso")

    await cog.mafia.callback(cog, ctx)

    assert "prison" in ctx.last_text().lower()


async def test_mafia_success_opens_market_and_grants_access(db_session, monkeypatch):
    await add_generic_item(db_session, name="Objet Mafia", price=1000, description="x", guild_id=None)
    await db_session.commit()

    monkeypatch.setattr(settings, "mafia_channel_id", "12345")
    monkeypatch.setattr(random, "random", lambda: 0.0)       # réussite
    monkeypatch.setattr(random, "uniform", lambda a, b: 0.45)  # remise 45%

    cog = _cog(db_session)
    ctx, channel = _mafia_ctx(70002, "Mafioso")

    await cog.mafia.callback(cog, ctx)

    # le marché est posté dans le salon mafia
    market_embeds = [m["embed"] for m in channel.sent if m["embed"] is not None]
    assert any("Marché de la mafia" in (e.title or "") for e in market_embeds)
    assert any("-45%" in (e.description or "") for e in market_embeds)

    # accès accordé (read_messages=True)
    assert any(kw.get("read_messages") is True for _, kw in channel.permission_overwrites)

    # confirmation envoyée à l'auteur
    assert "portes" in ctx.last_text().lower()


async def test_mafia_purchase_discount(db_session, monkeypatch):
    await get_or_create_user(db_session, settings.guild_id, 70005, "Acheteur")
    await add_balance(db_session, settings.guild_id, 70005, 10000)
    item = await add_generic_item(db_session, name="Objet Soldé", price=1000, description="x", guild_id=None)
    await db_session.flush()
    item_id = item.id
    await db_session.commit()

    cog = _cog(db_session)
    async with cog._session() as session:
        name, discounted, new_bal = await cog._mafia_purchase(
            session, settings.guild_id, 70005, item_id, 0.50
        )

    assert name == "Objet Soldé"
    assert discounted == 500
    assert new_bal == 9500


async def test_mafia_purchase_insufficient_balance(db_session, monkeypatch):
    await get_or_create_user(db_session, settings.guild_id, 70006, "Pauvre")
    item = await add_generic_item(db_session, name="Objet Cher", price=1000, description="x", guild_id=None)
    await db_session.flush()
    item_id = item.id
    await db_session.commit()

    cog = _cog(db_session)
    async with cog._session() as session:
        try:
            await cog._mafia_purchase(session, settings.guild_id, 70006, item_id, 0.30)
            raised = False
        except ValueError:
            raised = True

    assert raised


async def test_mafia_revoke_access_after_purchase(db_session):
    cog = _cog(db_session)
    ctx, channel = _mafia_ctx(70002, "Mafioso")

    view = MafiaMarketView(cog, ctx.author, channel, [(1, "Objet", 100)], 0.40)
    await view.revoke_access()

    assert any(kw.get("overwrite") is None for _, kw in channel.permission_overwrites)
