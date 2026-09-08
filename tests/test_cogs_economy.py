from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import discord

from cogs.economy import EconomyCog
from config.settings import ADMIN_PERMISSION_ROLE_ID, settings
from services.admin_permission import grant_permission


class FakeUser:
    def __init__(self, id, display_name):
        self.id = id
        self.display_name = display_name


class FakeGuild:
    def __init__(self, id=None):
        self.id = id if id is not None else settings.guild_id


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


class FakeContext:
    def __init__(self, author, guild=None):
        self.author = author
        self.guild = guild if guild is not None else FakeGuild()
        self.messages = []

    async def send(self, content=None, **kwargs):
        self.messages.append(content)


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


async def test_balance_reports_zero_for_new_user(db_session):
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = EconomyCog(bot=FakeBot(session_factory))
    ctx = FakeContext(FakeUser(id=20001, display_name="Newcomer"))

    await cog.balance.callback(cog, ctx)

    assert "0" in ctx.messages[0]


async def test_pay_transfers_coins_between_members(db_session):
    from services.economy import add_balance
    from services.users import get_or_create_user

    await get_or_create_user(db_session, settings.guild_id, 20002, "Payer")
    await add_balance(db_session, settings.guild_id, 20002, 500)
    await db_session.commit()

    session_factory = lambda: _FakeSessionContext(db_session)
    cog = EconomyCog(bot=FakeBot(session_factory))
    ctx = FakeContext(FakeUser(id=20002, display_name="Payer"))
    member = FakeUser(id=20003, display_name="Payee")

    await cog.pay.callback(cog, ctx, member, 200)

    from models.economy import Economy

    payer_economy = await db_session.get(Economy, (settings.guild_id, 20002))
    payee_economy = await db_session.get(Economy, (settings.guild_id, 20003))
    assert payer_economy.balance == 300
    assert payee_economy.balance == 200


async def test_pay_rejects_non_positive_amount(db_session):
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = EconomyCog(bot=FakeBot(session_factory))
    ctx = FakeContext(FakeUser(id=20004, display_name="Payer2"))
    member = FakeUser(id=20005, display_name="Payee2")

    await cog.pay.callback(cog, ctx, member, 0)

    assert "positif" in ctx.messages[0]


async def test_daily_grants_coins_on_first_claim(db_session):
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = EconomyCog(bot=FakeBot(session_factory))
    ctx = FakeContext(FakeUser(id=20006, display_name="Claimer"))

    await cog.daily.callback(cog, ctx)

    from models.economy import Economy

    economy = await db_session.get(Economy, (settings.guild_id, 20006))
    assert economy.balance == 120  # 100 base + 20 streak bonus for day 1
    assert economy.last_daily_at is not None
    assert "Série" in ctx.messages[0]


async def test_pay_bypass_admin_credits_without_debit(db_session):
    from services.users import get_or_create_user

    await get_or_create_user(db_session, settings.guild_id, 20010, "AdminPayer")
    await db_session.commit()

    session_factory = lambda: _FakeSessionContext(db_session)
    cog = EconomyCog(bot=FakeBot(session_factory))
    admin = await make_admin(db_session, id=20010, display_name="AdminPayer")
    ctx = FakeContext(admin)
    member = FakeUser(id=20011, display_name="Receiver")

    await cog.pay.callback(cog, ctx, member, "bypass", "300")

    from models.economy import Economy

    payer_economy = await db_session.get(Economy, (settings.guild_id, 20010))
    payee_economy = await db_session.get(Economy, (settings.guild_id, 20011))
    assert payer_economy is None or payer_economy.balance == 0
    assert payee_economy.balance == 300
    assert "Bypass" in ctx.messages[0]


async def test_pay_bypass_ignored_for_non_admin(db_session):
    from services.economy import add_balance
    from services.users import get_or_create_user

    await get_or_create_user(db_session, settings.guild_id, 20012, "RegularPayer")
    await add_balance(db_session, settings.guild_id, 20012, 500)
    await db_session.commit()

    session_factory = lambda: _FakeSessionContext(db_session)
    cog = EconomyCog(bot=FakeBot(session_factory))
    ctx = FakeContext(FakeUser(id=20012, display_name="RegularPayer"))
    member = FakeUser(id=20013, display_name="Receiver2")

    await cog.pay.callback(cog, ctx, member, "bypass", "200")

    from models.economy import Economy

    payer_economy = await db_session.get(Economy, (settings.guild_id, 20012))
    assert payer_economy.balance == 300


async def test_daily_applies_active_coins_boost(db_session):
    from services.effects import grant_effect
    from services.users import get_or_create_user

    await get_or_create_user(db_session, settings.guild_id, 20007, "BoostedClaimer")
    await grant_effect(db_session, settings.guild_id, 20007, "coins_boost", magnitude=2.0)
    await db_session.commit()

    session_factory = lambda: _FakeSessionContext(db_session)
    cog = EconomyCog(bot=FakeBot(session_factory))
    ctx = FakeContext(FakeUser(id=20007, display_name="BoostedClaimer"))

    await cog.daily.callback(cog, ctx)

    from models.economy import Economy

    economy = await db_session.get(Economy, (settings.guild_id, 20007))
    assert economy.balance == 240  # (100 base + 20 streak bonus) * 2.0 coins_boost
    assert "240" in ctx.messages[0]


async def test_daily_bypass_admin_ignores_cooldown(db_session):
    from models.economy import Economy
    from services.users import get_or_create_user

    await get_or_create_user(db_session, settings.guild_id, 20014, "AdminClaimer")
    db_session.add(Economy(guild_id=settings.guild_id, user_id=20014, balance=0, last_daily_at=datetime.now(timezone.utc) - timedelta(hours=1)))
    await db_session.commit()

    session_factory = lambda: _FakeSessionContext(db_session)
    cog = EconomyCog(bot=FakeBot(session_factory))
    admin = await make_admin(db_session, id=20014, display_name="AdminClaimer")
    ctx = FakeContext(admin)

    await cog.daily.callback(cog, ctx, "bypass")

    economy = await db_session.get(Economy, (settings.guild_id, 20014))
    assert economy.balance == 120  # 100 base + 20 streak bonus for day 1
    assert "bypass" in ctx.messages[0].lower()


async def test_daily_streak_continues_on_a_consecutive_claim(db_session):
    from models.economy import Economy
    from services.users import get_or_create_user

    await get_or_create_user(db_session, settings.guild_id, 20019, "Streaker")
    db_session.add(
        Economy(
            guild_id=settings.guild_id,
            user_id=20019,
            balance=0,
            last_daily_at=datetime.now(timezone.utc) - timedelta(hours=30),
        )
    )
    await db_session.commit()

    from services.daily_streak import get_or_create_streak

    streak = await get_or_create_streak(db_session, settings.guild_id, 20019)
    streak.streak_count = 1
    await db_session.commit()

    session_factory = lambda: _FakeSessionContext(db_session)
    cog = EconomyCog(bot=FakeBot(session_factory))
    ctx = FakeContext(FakeUser(id=20019, display_name="Streaker"))

    await cog.daily.callback(cog, ctx)

    economy = await db_session.get(Economy, (settings.guild_id, 20019))
    assert economy.balance == 140  # 100 base + 40 streak bonus for day 2
    assert "Série" in ctx.messages[0] and "2" in ctx.messages[0]


async def test_daily_streak_resets_after_missing_the_window(db_session):
    from models.economy import Economy
    from services.users import get_or_create_user

    await get_or_create_user(db_session, settings.guild_id, 20020, "LapsedStreaker")
    db_session.add(
        Economy(
            guild_id=settings.guild_id,
            user_id=20020,
            balance=0,
            last_daily_at=datetime.now(timezone.utc) - timedelta(hours=72),
        )
    )
    await db_session.commit()

    from services.daily_streak import get_or_create_streak

    streak = await get_or_create_streak(db_session, settings.guild_id, 20020)
    streak.streak_count = 5
    await db_session.commit()

    session_factory = lambda: _FakeSessionContext(db_session)
    cog = EconomyCog(bot=FakeBot(session_factory))
    ctx = FakeContext(FakeUser(id=20020, display_name="LapsedStreaker"))

    await cog.daily.callback(cog, ctx)

    economy = await db_session.get(Economy, (settings.guild_id, 20020))
    assert economy.balance == 120  # reset to day 1 (100 base + 20 bonus)


async def test_daily_streak_protection_preserves_a_missed_streak(db_session):
    from models.economy import Economy
    from services.effects import grant_effect
    from services.users import get_or_create_user

    await get_or_create_user(db_session, settings.guild_id, 20021, "ProtectedStreaker")
    db_session.add(
        Economy(
            guild_id=settings.guild_id,
            user_id=20021,
            balance=0,
            last_daily_at=datetime.now(timezone.utc) - timedelta(hours=72),
        )
    )
    await db_session.commit()

    from services.daily_streak import get_or_create_streak

    streak = await get_or_create_streak(db_session, settings.guild_id, 20021)
    streak.streak_count = 5
    await grant_effect(db_session, settings.guild_id, 20021, "streak_protection", uses=1)
    await db_session.commit()

    session_factory = lambda: _FakeSessionContext(db_session)
    cog = EconomyCog(bot=FakeBot(session_factory))
    ctx = FakeContext(FakeUser(id=20021, display_name="ProtectedStreaker"))

    await cog.daily.callback(cog, ctx)

    economy = await db_session.get(Economy, (settings.guild_id, 20021))
    assert economy.balance == 220  # 100 base + 120 streak bonus for day 6
    assert "protégée" in ctx.messages[0].lower()


async def test_daily_rejects_second_claim_within_cooldown(db_session):
    from models.economy import Economy
    from services.users import get_or_create_user

    await get_or_create_user(db_session, settings.guild_id, 20007, "Impatient")
    db_session.add(Economy(guild_id=settings.guild_id, user_id=20007, balance=0, last_daily_at=datetime.now(timezone.utc) - timedelta(hours=1)))
    await db_session.commit()

    session_factory = lambda: _FakeSessionContext(db_session)
    cog = EconomyCog(bot=FakeBot(session_factory))
    ctx = FakeContext(FakeUser(id=20007, display_name="Impatient"))

    await cog.daily.callback(cog, ctx)

    economy = await db_session.get(Economy, (settings.guild_id, 20007))
    assert economy.balance == 0
    assert "Reviens" in ctx.messages[0]


async def test_work_grants_the_configured_fixed_amount(db_session):
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = EconomyCog(bot=FakeBot(session_factory))
    ctx = FakeContext(FakeUser(id=20015, display_name="Worker"))

    await cog.work.callback(cog, ctx)

    from models.economy import Economy

    economy = await db_session.get(Economy, (settings.guild_id, 20015))
    assert economy.balance == settings.work_amount


async def test_work_applies_active_coins_boost(db_session):
    from services.effects import grant_effect
    from services.users import get_or_create_user

    await get_or_create_user(db_session, settings.guild_id, 20018, "BoostedWorker")
    await grant_effect(db_session, settings.guild_id, 20018, "coins_boost", magnitude=2.0)
    await db_session.commit()

    session_factory = lambda: _FakeSessionContext(db_session)
    cog = EconomyCog(bot=FakeBot(session_factory))
    ctx = FakeContext(FakeUser(id=20018, display_name="BoostedWorker"))

    await cog.work.callback(cog, ctx)

    from models.economy import Economy

    economy = await db_session.get(Economy, (settings.guild_id, 20018))
    assert economy.balance == round(settings.work_amount * 2.0)


async def test_work_rejects_second_attempt_within_cooldown(db_session):
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = EconomyCog(bot=FakeBot(session_factory))
    ctx = FakeContext(FakeUser(id=20016, display_name="Worker2"))

    from models.economy import Economy

    await cog.work.callback(cog, ctx)
    first_balance = (await db_session.get(Economy, (settings.guild_id, 20016))).balance
    await cog.work.callback(cog, ctx)

    economy = await db_session.get(Economy, (settings.guild_id, 20016))
    assert economy.balance == first_balance
    assert "viens de travailler" in ctx.messages[-1]


async def test_work_bypass_admin_ignores_cooldown(db_session):
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = EconomyCog(bot=FakeBot(session_factory))
    admin = await make_admin(db_session, id=20017, display_name="AdminWorker")
    ctx = FakeContext(admin)

    await cog.work.callback(cog, ctx)
    await cog.work.callback(cog, ctx, "bypass")

    from models.economy import Economy

    economy = await db_session.get(Economy, (settings.guild_id, 20017))
    assert economy.balance >= 100
    assert "bypass" in ctx.messages[-1].lower()
