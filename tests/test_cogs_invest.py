import random
from unittest.mock import Mock

import discord

from cogs.invest import InvestCog
from config.settings import ADMIN_PERMISSION_ROLE_ID, settings
from models.economy import Economy
from services.admin_permission import grant_permission
from services.economy import add_balance
from services.invest import set_market_index
from services.users import get_or_create_user


class FakeUser:
    def __init__(self, id, display_name):
        self.id = id
        self.display_name = display_name


class FakeRole:
    def __init__(self, id):
        self.id = id


async def make_admin(db_session, id, display_name, guild_id=None):
    admin = Mock(spec=discord.Member)
    admin.id = id
    admin.display_name = display_name
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
    return InvestCog(bot=FakeBot(lambda: _FakeSessionContext(db_session)))


async def test_weekly_grants_flat_amount(db_session):
    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=50001, display_name="Weekler"))

    await cog.weekly.callback(cog, ctx)

    economy = await db_session.get(Economy, (settings.guild_id, 50001))
    assert economy.balance == 2000


async def test_weekly_applies_active_coins_boost(db_session):
    from services.effects import grant_effect

    await get_or_create_user(db_session, settings.guild_id, 50012, "BoostedWeekler")
    await grant_effect(db_session, settings.guild_id, 50012, "coins_boost", magnitude=1.5)
    await db_session.commit()

    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=50012, display_name="BoostedWeekler"))

    await cog.weekly.callback(cog, ctx)

    economy = await db_session.get(Economy, (settings.guild_id, 50012))
    assert economy.balance == 3000


async def test_weekly_rejects_second_claim_within_cooldown(db_session):
    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=50002, display_name="Weekler2"))

    await cog.weekly.callback(cog, ctx)
    await cog.weekly.callback(cog, ctx)

    economy = await db_session.get(Economy, (settings.guild_id, 50002))
    assert economy.balance == 2000
    assert "déjà récupéré" in ctx.last_text()


async def test_monthly_grants_flat_amount(db_session):
    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=50003, display_name="Monthler"))

    await cog.monthly.callback(cog, ctx)

    economy = await db_session.get(Economy, (settings.guild_id, 50003))
    assert economy.balance == 8000


async def test_monthly_applies_active_coins_boost(db_session):
    from services.effects import grant_effect

    await get_or_create_user(db_session, settings.guild_id, 50013, "BoostedMonthler")
    await grant_effect(db_session, settings.guild_id, 50013, "coins_boost", magnitude=1.5)
    await db_session.commit()

    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=50013, display_name="BoostedMonthler"))

    await cog.monthly.callback(cog, ctx)

    economy = await db_session.get(Economy, (settings.guild_id, 50013))
    assert economy.balance == 12000


async def test_invest_rejects_non_positive_amount(db_session):
    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=50004, display_name="Investor"))

    await cog.invest.callback(cog, ctx, 0)

    assert "positif" in ctx.last_text()


async def test_invest_rejects_insufficient_balance(db_session):
    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=50005, display_name="Poor"))

    await cog.invest.callback(cog, ctx, 500)

    assert "insuffisant" in ctx.last_text()


async def test_invest_win_pays_between_2x_and_2_5x(db_session, monkeypatch):
    await get_or_create_user(db_session, settings.guild_id, 50006, "Investor2")
    await add_balance(db_session, settings.guild_id, 50006, 1000)
    await set_market_index(db_session, settings.guild_id, 1.0)
    await db_session.commit()

    fixed_rng = random.Random()
    monkeypatch.setattr(random, "Random", lambda: fixed_rng)
    monkeypatch.setattr(fixed_rng, "random", lambda: 0.9)  # >= 0.75 → gain
    monkeypatch.setattr(fixed_rng, "uniform", lambda a, b: 2.0)  # x2

    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=50006, display_name="Investor2"))

    await cog.invest.callback(cog, ctx, 1000)

    economy = await db_session.get(Economy, (settings.guild_id, 50006))
    assert economy.balance == 1000 - 1000 + 2000  # mise + retour x2


async def test_invest_loss_loses_the_stake(db_session, monkeypatch):
    await get_or_create_user(db_session, settings.guild_id, 50015, "Loser")
    await add_balance(db_session, settings.guild_id, 50015, 1000)
    await db_session.commit()

    fixed_rng = random.Random()
    monkeypatch.setattr(random, "Random", lambda: fixed_rng)
    monkeypatch.setattr(fixed_rng, "random", lambda: 0.1)  # < 0.75 → perte

    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=50015, display_name="Loser"))

    await cog.invest.callback(cog, ctx, 1000)

    economy = await db_session.get(Economy, (settings.guild_id, 50015))
    assert economy.balance == 0  # mise perdue


async def test_invest_caps_at_100k(db_session):
    await get_or_create_user(db_session, settings.guild_id, 50016, "Whale")
    await add_balance(db_session, settings.guild_id, 50016, 500000)
    await db_session.commit()

    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=50016, display_name="Whale"))

    await cog.invest.callback(cog, ctx, 100001)

    assert "plafonné" in ctx.last_text()


async def test_invest_daily_limit_of_five(db_session):
    from services.invest import register_invest

    await get_or_create_user(db_session, settings.guild_id, 50017, "Daily")
    await add_balance(db_session, settings.guild_id, 50017, 100000)
    for _ in range(5):
        await register_invest(db_session, settings.guild_id, 50017)
    await db_session.commit()

    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=50017, display_name="Daily"))

    await cog.invest.callback(cog, ctx, 100)

    assert "limite" in ctx.last_text()


async def test_stocks_reports_current_index(db_session, monkeypatch):
    await set_market_index(db_session, settings.guild_id, 1.3)
    await db_session.commit()

    # Force une lecture exacte (pas d'« estimation incertaine » à 30%).
    monkeypatch.setattr(random, "random", lambda: 0.5)

    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=50007, display_name="Watcher"))

    await cog.stocks.callback(cog, ctx)

    assert "1.30" in ctx.last_text()
    assert "hausse" in ctx.last_text()


async def test_weekly_bypass_skips_cooldown_for_admin(db_session):
    cog = _cog(db_session)
    ctx = FakeContext(await make_admin(db_session, id=50008, display_name="AdminWeekler"))

    await cog.weekly.callback(cog, ctx, "bypass")
    await cog.weekly.callback(cog, ctx, "bypass")

    economy = await db_session.get(Economy, (settings.guild_id, 50008))
    assert economy.balance == 4000
    assert "bypass" in ctx.last_text()


async def test_monthly_bypass_ignored_for_non_admin(db_session):
    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=50009, display_name="RegularMonthler"))

    await cog.monthly.callback(cog, ctx, "bypass")
    await cog.monthly.callback(cog, ctx, "bypass")

    economy = await db_session.get(Economy, (settings.guild_id, 50009))
    assert economy.balance == 8000
    assert "déjà récupéré" in ctx.last_text()


async def test_invest_bypass_allows_zero_balance_and_keeps_full_proceeds(db_session, monkeypatch):
    await set_market_index(db_session, settings.guild_id, 1.0)
    await db_session.commit()

    fixed_rng = random.Random()
    monkeypatch.setattr(random, "Random", lambda: fixed_rng)
    monkeypatch.setattr(fixed_rng, "random", lambda: 0.9)  # >= 0.75 → gain
    monkeypatch.setattr(fixed_rng, "uniform", lambda a, b: 2.0)  # x2

    cog = _cog(db_session)
    ctx = FakeContext(await make_admin(db_session, id=50010, display_name="AdminInvestor"))

    await cog.invest.callback(cog, ctx, 1000, "bypass")

    economy = await db_session.get(Economy, (settings.guild_id, 50010))
    assert economy.balance == 2000  # stake never debited, full x2 proceeds
    assert "bypass" in ctx.last_text()
