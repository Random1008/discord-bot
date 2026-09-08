from datetime import datetime, timedelta, timezone

from config.settings import settings
from models.users import User
from services import effects as effects_service
from services.effects import (
    consume_one_shot,
    get_active_bonus,
    get_active_multiplier,
    grant_effect,
    has_active,
)

GUILD_ID = settings.guild_id


async def _make_user(db_session, user_id: int) -> None:
    db_session.add(User(guild_id=GUILD_ID, user_id=user_id, username=f"user{user_id}"))
    await db_session.flush()


async def test_get_active_multiplier_defaults_to_one_when_nothing_active(db_session):
    await _make_user(db_session, 60001)

    multiplier = await get_active_multiplier(db_session, GUILD_ID, 60001, "xp_boost")

    assert multiplier == 1.0


async def test_grant_effect_multiplier_is_returned_while_active(db_session):
    await _make_user(db_session, 60002)
    await grant_effect(db_session, GUILD_ID, 60002, "xp_boost", magnitude=2.0, duration_seconds=900)
    await db_session.commit()

    multiplier = await get_active_multiplier(db_session, GUILD_ID, 60002, "xp_boost")

    assert multiplier == 2.0


async def test_expired_effect_no_longer_counts(db_session, monkeypatch):
    await _make_user(db_session, 60003)
    await grant_effect(db_session, GUILD_ID, 60003, "xp_boost", magnitude=3.0, duration_seconds=60)
    await db_session.commit()

    future = datetime.now(timezone.utc) + timedelta(seconds=61)
    monkeypatch.setattr(effects_service, "_now", lambda: future)

    multiplier = await get_active_multiplier(db_session, GUILD_ID, 60003, "xp_boost")

    assert multiplier == 1.0


async def test_get_active_multiplier_takes_the_max_of_several_active_effects(db_session):
    await _make_user(db_session, 60004)
    await grant_effect(db_session, GUILD_ID, 60004, "coins_boost", magnitude=1.2)
    await grant_effect(db_session, GUILD_ID, 60004, "coins_boost", magnitude=1.5)
    await db_session.commit()

    multiplier = await get_active_multiplier(db_session, GUILD_ID, 60004, "coins_boost")

    assert multiplier == 1.5


async def test_get_active_bonus_sums_flat_bonuses(db_session):
    await _make_user(db_session, 60005)
    await grant_effect(db_session, GUILD_ID, 60005, "gacha_rate_boost", magnitude=0.05)
    await grant_effect(db_session, GUILD_ID, 60005, "gacha_rate_boost", magnitude=0.1)
    await db_session.commit()

    bonus = await get_active_bonus(db_session, GUILD_ID, 60005, "gacha_rate_boost")

    assert round(bonus, 4) == 0.15


async def test_has_active_reflects_presence(db_session):
    await _make_user(db_session, 60006)

    assert await has_active(db_session, GUILD_ID, 60006, "casino_insurance") is False

    await grant_effect(db_session, GUILD_ID, 60006, "casino_insurance")
    await db_session.commit()

    assert await has_active(db_session, GUILD_ID, 60006, "casino_insurance") is True


async def test_consume_one_shot_without_uses_removes_after_a_single_consumption(db_session):
    await _make_user(db_session, 60007)
    await grant_effect(db_session, GUILD_ID, 60007, "casino_double_win")
    await db_session.commit()

    consumed_first = await consume_one_shot(db_session, GUILD_ID, 60007, "casino_double_win")
    await db_session.commit()
    consumed_second = await consume_one_shot(db_session, GUILD_ID, 60007, "casino_double_win")

    assert consumed_first is True
    assert consumed_second is False


async def test_consume_one_shot_with_uses_decrements_until_exhausted(db_session):
    await _make_user(db_session, 60008)
    await grant_effect(db_session, GUILD_ID, 60008, "casino_free_bet", uses=2)
    await db_session.commit()

    first = await consume_one_shot(db_session, GUILD_ID, 60008, "casino_free_bet")
    await db_session.commit()
    remaining_after_first = await has_active(db_session, GUILD_ID, 60008, "casino_free_bet")
    second = await consume_one_shot(db_session, GUILD_ID, 60008, "casino_free_bet")
    await db_session.commit()
    third = await consume_one_shot(db_session, GUILD_ID, 60008, "casino_free_bet")

    assert first is True
    assert remaining_after_first is True
    assert second is True
    assert third is False


async def test_consume_one_shot_returns_false_when_nothing_granted(db_session):
    await _make_user(db_session, 60009)

    assert await consume_one_shot(db_session, GUILD_ID, 60009, "casino_insurance") is False


async def test_effects_are_isolated_per_guild(db_session):
    other_guild_id = GUILD_ID + 1
    db_session.add(User(guild_id=other_guild_id, user_id=60010, username="other_guild_user"))
    await _make_user(db_session, 60010)
    await grant_effect(db_session, GUILD_ID, 60010, "xp_boost", magnitude=2.0)
    await db_session.commit()

    multiplier_here = await get_active_multiplier(db_session, GUILD_ID, 60010, "xp_boost")
    multiplier_other_guild = await get_active_multiplier(db_session, other_guild_id, 60010, "xp_boost")

    assert multiplier_here == 2.0
    assert multiplier_other_guild == 1.0
