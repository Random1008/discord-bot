from datetime import datetime, timedelta, timezone

from config.settings import settings
from models.users import User
from services.daily_streak import get_or_create_streak, register_daily_claim, streak_bonus

GUILD_ID = settings.guild_id


async def _make_user(db_session, user_id: int) -> None:
    db_session.add(User(guild_id=GUILD_ID, user_id=user_id, username=f"user{user_id}"))
    await db_session.flush()


def test_streak_bonus_scales_and_caps():
    assert streak_bonus(0) == 0
    assert streak_bonus(1) == 20
    assert streak_bonus(10) == 200
    assert streak_bonus(100) == 500  # capped


async def test_get_or_create_streak_defaults_to_zero(db_session):
    await _make_user(db_session, 80001)

    streak = await get_or_create_streak(db_session, GUILD_ID, 80001)

    assert streak.streak_count == 0


async def test_register_daily_claim_starts_a_new_streak_at_one_when_no_previous_claim(db_session):
    await _make_user(db_session, 80002)
    now = datetime.now(timezone.utc)

    streak = await register_daily_claim(db_session, GUILD_ID, 80002, previous_claim_at=None, now=now)

    assert streak.streak_count == 1


async def test_register_daily_claim_continues_the_streak_within_the_window(db_session):
    await _make_user(db_session, 80003)
    previous = datetime.now(timezone.utc) - timedelta(hours=30)
    now = datetime.now(timezone.utc)
    await register_daily_claim(db_session, GUILD_ID, 80003, previous_claim_at=None, now=previous)
    await db_session.commit()

    streak = await register_daily_claim(db_session, GUILD_ID, 80003, previous_claim_at=previous, now=now)

    assert streak.streak_count == 2


async def test_register_daily_claim_resets_after_missing_the_window(db_session):
    await _make_user(db_session, 80004)
    previous = datetime.now(timezone.utc) - timedelta(hours=72)
    now = datetime.now(timezone.utc)
    streak = await get_or_create_streak(db_session, GUILD_ID, 80004)
    streak.streak_count = 5
    await db_session.commit()

    result = await register_daily_claim(db_session, GUILD_ID, 80004, previous_claim_at=previous, now=now)

    assert result.streak_count == 1


async def test_register_daily_claim_protected_preserves_streak_despite_missed_window(db_session):
    await _make_user(db_session, 80005)
    previous = datetime.now(timezone.utc) - timedelta(hours=72)
    now = datetime.now(timezone.utc)
    streak = await get_or_create_streak(db_session, GUILD_ID, 80005)
    streak.streak_count = 5
    await db_session.commit()

    result = await register_daily_claim(
        db_session, GUILD_ID, 80005, previous_claim_at=previous, now=now, protected=True
    )

    assert result.streak_count == 6
