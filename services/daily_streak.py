from datetime import datetime, timedelta

from models.daily_streak import DailyStreak

STREAK_WINDOW = timedelta(hours=48)
STREAK_BONUS_PER_DAY = 20
STREAK_BONUS_CAP = 500


def streak_bonus(streak_count: int) -> int:
    return min(streak_count * STREAK_BONUS_PER_DAY, STREAK_BONUS_CAP)


async def get_or_create_streak(session, guild_id: int, user_id: int) -> DailyStreak:
    streak = await session.get(DailyStreak, (guild_id, user_id))
    if streak is None:
        streak = DailyStreak(guild_id=guild_id, user_id=user_id, streak_count=0)
        session.add(streak)
        await session.flush()
    return streak


async def register_daily_claim(
    session,
    guild_id: int,
    user_id: int,
    previous_claim_at: datetime | None,
    now: datetime,
    protected: bool = False,
) -> DailyStreak:
    streak = await get_or_create_streak(session, guild_id, user_id)
    continues = previous_claim_at is not None and (now - previous_claim_at) < STREAK_WINDOW
    if continues or protected:
        streak.streak_count += 1
    else:
        streak.streak_count = 1
    await session.flush()
    return streak
