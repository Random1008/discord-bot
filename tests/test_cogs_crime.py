import random
from unittest.mock import Mock

import discord

from cogs.crime import CrimeCog
from config.settings import ADMIN_PERMISSION_ROLE_ID, settings
from models.economy import Economy
from services.admin_permission import grant_permission
from services.economy import add_balance
from services.users import get_or_create_user


class FakeUser:
    def __init__(self, id, display_name, bot=False):
        self.id = id
        self.display_name = display_name
        self.bot = bot


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
    def __init__(self, id=None):
        self.id = id if id is not None else settings.guild_id


class FakeContext:
    def __init__(self, author, guild=None):
        self.author = author
        self.guild = guild if guild is not None else FakeGuild()
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
    return CrimeCog(bot=FakeBot(lambda: _FakeSessionContext(db_session)))


async def test_crime_success_credits_coins(db_session, monkeypatch):
    monkeypatch.setattr(random, "random", lambda: 0.0)
    monkeypatch.setattr(random, "randint", lambda a, b: 100)

    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=40001, display_name="Criminal"))

    await cog.crime.callback(cog, ctx)

    economy = await db_session.get(Economy, (settings.guild_id, 40001))
    assert economy.balance == 100
    assert "réussi" in ctx.last_text()


async def test_crime_failure_pays_fine(db_session, monkeypatch):
    await get_or_create_user(db_session, settings.guild_id, 40002, "Unlucky")
    await add_balance(db_session, settings.guild_id, 40002, 100)
    await db_session.commit()

    monkeypatch.setattr(random, "random", lambda: 0.99)

    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=40002, display_name="Unlucky"))

    await cog.crime.callback(cog, ctx)

    economy = await db_session.get(Economy, (settings.guild_id, 40002))
    assert economy.balance == 50


async def test_crime_rejects_second_attempt_within_cooldown(db_session, monkeypatch):
    monkeypatch.setattr(random, "random", lambda: 0.0)
    monkeypatch.setattr(random, "randint", lambda a, b: 50)

    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=40003, display_name="Impatient"))

    await cog.crime.callback(cog, ctx)
    await cog.crime.callback(cog, ctx)

    assert "Cooldown" in ctx.last_text()


async def test_rob_rejects_self_target(db_session):
    cog = _cog(db_session)
    author = FakeUser(id=40004, display_name="Self")
    ctx = FakeContext(author)

    await cog.rob.callback(cog, ctx, author)

    assert "invalide" in ctx.last_text()


async def test_rob_rejects_target_below_minimum_balance(db_session):
    await get_or_create_user(db_session, settings.guild_id, 40006, "PoorTarget")
    await db_session.commit()

    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=40005, display_name="Robber"))
    target = FakeUser(id=40006, display_name="PoorTarget")

    await cog.rob.callback(cog, ctx, target)

    assert "assez de credits" in ctx.last_text()


async def test_rob_success_transfers_percentage(db_session, monkeypatch):
    await get_or_create_user(db_session, settings.guild_id, 40008, "RichTarget")
    await add_balance(db_session, settings.guild_id, 40008, 1000)
    await db_session.commit()

    monkeypatch.setattr(random, "random", lambda: 0.0)
    monkeypatch.setattr(random, "uniform", lambda a, b: 0.2)

    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=40007, display_name="Robber2"))
    target = FakeUser(id=40008, display_name="RichTarget")

    await cog.rob.callback(cog, ctx, target)

    robber_economy = await db_session.get(Economy, (settings.guild_id, 40007))
    target_economy = await db_session.get(Economy, (settings.guild_id, 40008))
    assert robber_economy.balance == 200
    assert target_economy.balance == 800


async def test_rob_failure_fines_and_jails_robber(db_session, monkeypatch):
    await get_or_create_user(db_session, settings.guild_id, 40010, "RichTarget2")
    await add_balance(db_session, settings.guild_id, 40010, 1000)
    await get_or_create_user(db_session, settings.guild_id, 40009, "Robber3")
    await add_balance(db_session, settings.guild_id, 40009, 200)
    await db_session.commit()

    monkeypatch.setattr(random, "random", lambda: 0.99)

    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=40009, display_name="Robber3"))
    target = FakeUser(id=40010, display_name="RichTarget2")

    await cog.rob.callback(cog, ctx, target)

    robber_economy = await db_session.get(Economy, (settings.guild_id, 40009))
    assert robber_economy.balance == 100
    assert "prison" in ctx.last_text()

    ctx2 = FakeContext(FakeUser(id=40009, display_name="Robber3"))
    await cog.rob.callback(cog, ctx2, target)
    assert "prison" in ctx2.last_text().lower()


async def test_crime_bypass_skips_cooldown_for_admin(db_session, monkeypatch):
    monkeypatch.setattr(random, "random", lambda: 0.0)
    monkeypatch.setattr(random, "randint", lambda a, b: 50)

    cog = _cog(db_session)
    ctx = FakeContext(await make_admin(db_session, id=40011, display_name="AdminCriminal"))

    await cog.crime.callback(cog, ctx, "bypass")
    await cog.crime.callback(cog, ctx, "bypass")

    assert "réussi" in ctx.last_text()
    assert "bypass" in ctx.last_text()


async def test_crime_bypass_ignored_for_non_admin(db_session, monkeypatch):
    monkeypatch.setattr(random, "random", lambda: 0.0)
    monkeypatch.setattr(random, "randint", lambda a, b: 50)

    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=40012, display_name="RegularCriminal"))

    await cog.crime.callback(cog, ctx, "bypass")
    await cog.crime.callback(cog, ctx, "bypass")

    assert "Cooldown" in ctx.last_text()


async def test_rob_bypass_skips_cooldown_and_prison_for_admin(db_session, monkeypatch):
    await get_or_create_user(db_session, settings.guild_id, 40014, "RichTarget3")
    await add_balance(db_session, settings.guild_id, 40014, 1000)
    await db_session.commit()

    monkeypatch.setattr(random, "random", lambda: 0.99)  # rob fails -> prison

    cog = _cog(db_session)
    admin = await make_admin(db_session, id=40013, display_name="AdminRobber")
    ctx = FakeContext(admin)
    target = FakeUser(id=40014, display_name="RichTarget3")

    await cog.rob.callback(cog, ctx, target, "bypass")
    assert "prison" in ctx.last_text()

    ctx2 = FakeContext(admin, guild=ctx.guild)
    await cog.rob.callback(cog, ctx2, target, "bypass")

    # The gate message ("Libéré dans") would appear if bypass didn't skip the prison/cooldown
    # check; instead we should reach the (still-failing, per the patched roll) outcome embed.
    assert "bypass" in ctx2.last_text()
    assert "Libéré dans" not in ctx2.last_text()
    assert "Vol raté" in ctx2.last_text()
