from datetime import datetime, timedelta

from sqlalchemy import select

from models.badges import Badge, UserBadge
from models.users import User
from services.leaderboard import get_message_leaderboard, get_voice_leaderboard, get_xp_leaderboard
from services.rewards import RewardOutcome, grant_badge_by_key

ANCIEN_THRESHOLD_DAYS = 365


async def sweep_classement_badges(session, guild_id: int, now: datetime) -> list[tuple[int, RewardOutcome]]:
    outcomes: list[tuple[int, RewardOutcome]] = []

    message_leaderboard = await get_message_leaderboard(session, guild_id, limit=1)
    if message_leaderboard:
        outcome = await _grant_if_new(session, guild_id, message_leaderboard[0].user_id, "roi_du_chat")
        if outcome is not None:
            outcomes.append((message_leaderboard[0].user_id, outcome))

    voice_leaderboard = await get_voice_leaderboard(session, guild_id, limit=1)
    if voice_leaderboard:
        outcome = await _grant_if_new(session, guild_id, voice_leaderboard[0].user_id, "maitre_vocal")
        if outcome is not None:
            outcomes.append((voice_leaderboard[0].user_id, outcome))

    xp_leaderboard = await get_xp_leaderboard(session, guild_id, limit=10)
    for entry in xp_leaderboard:
        outcome = await _grant_if_new(session, guild_id, entry.user_id, "top_10")
        if outcome is not None:
            outcomes.append((entry.user_id, outcome))

    cutoff = now - timedelta(days=ANCIEN_THRESHOLD_DAYS)
    tenured_result = await session.execute(
        select(User.user_id).where(User.guild_id == guild_id, User.created_at <= cutoff)
    )
    for (user_id,) in tenured_result.all():
        outcome = await _grant_if_new(session, guild_id, user_id, "ancien")
        if outcome is not None:
            outcomes.append((user_id, outcome))

    return outcomes


async def _grant_if_new(session, guild_id: int, user_id: int, badge_key: str) -> RewardOutcome | None:
    badge_result = await session.execute(select(Badge).where(Badge.key == badge_key))
    badge = badge_result.scalar_one()

    existing = await session.execute(
        select(UserBadge).where(
            UserBadge.guild_id == guild_id, UserBadge.user_id == user_id, UserBadge.badge_id == badge.id
        )
    )
    already_had = existing.scalar_one_or_none() is not None

    outcome = await grant_badge_by_key(session, guild_id, user_id, badge_key)

    return None if already_had else outcome
