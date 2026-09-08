import math
import random
from dataclasses import dataclass, field

from sqlalchemy import select

from models.levels import Level
from models.rewards import Reward
from services.effects import get_active_multiplier
from services.keys import add_key, roll_key_rarity, should_drop_key
from services.prestige import multiplier_for_prestige, prestige_for_level
from services.rewards import RewardOutcome, grant_badge_by_key, grant_reward


def xp_for_level(level: int) -> int:
    """Total XP required to reach `level` (formula: 100 * level^2)."""
    return 100 * level * level


def level_for_xp(xp: int) -> int:
    """Current level for a total XP amount (formula: floor(sqrt(xp / 100)))."""
    return math.isqrt(xp // 100)


@dataclass
class KeyDrop:
    level: int
    rarity: str


@dataclass
class LevelUpResult:
    user_id: int
    xp: int
    level: int
    levels_gained: list[int] = field(default_factory=list)
    reward_outcomes: list[RewardOutcome] = field(default_factory=list)
    key_drops: list[KeyDrop] = field(default_factory=list)
    prestige_reached: int | None = None
    inviter_bonus: "LevelUpResult | None" = None


async def get_or_create_level(session, guild_id: int, user_id: int) -> Level:
    level_row = await session.get(Level, (guild_id, user_id))
    if level_row is None:
        level_row = Level(
            guild_id=guild_id, user_id=user_id, xp=0, level=0, prestige=0, last_key_drop_level=0
        )
        session.add(level_row)
        await session.flush()
    return level_row


async def add_xp(session, guild_id: int, user_id: int, base_amount: int, rng=random) -> LevelUpResult:
    level_row = await get_or_create_level(session, guild_id, user_id)

    multiplier = multiplier_for_prestige(level_row.prestige)
    xp_boost = await get_active_multiplier(session, guild_id, user_id, "xp_boost")
    actual_amount = round(base_amount * multiplier * xp_boost)

    old_level = level_row.level
    level_row.xp += actual_amount
    computed_level = level_for_xp(level_row.xp)
    new_level = max(old_level, computed_level)
    levels_gained = list(range(old_level + 1, new_level + 1))
    level_row.level = new_level

    reward_outcomes: list[RewardOutcome] = []
    key_drops: list[KeyDrop] = []
    inviter_bonus: LevelUpResult | None = None

    for crossed_level in levels_gained:
        reward_result = await session.execute(select(Reward).where(Reward.level == crossed_level))
        for reward in reward_result.scalars().all():
            reward_outcomes.append(await grant_reward(session, guild_id, user_id, reward, rng=rng))

        levels_elapsed = crossed_level - level_row.last_key_drop_level
        if should_drop_key(levels_elapsed, rng=rng):
            rarity = roll_key_rarity(rng=rng)
            await add_key(session, guild_id, user_id, rarity)
            level_row.last_key_drop_level = crossed_level
            key_drops.append(KeyDrop(level=crossed_level, rarity=rarity))

        if crossed_level == 5:
            inviter_bonus = await _maybe_reward_inviter(session, guild_id, user_id, rng=rng)

    new_prestige = prestige_for_level(new_level)
    prestige_reached = new_prestige if new_prestige > level_row.prestige else None
    level_row.prestige = max(level_row.prestige, new_prestige)

    await session.flush()

    return LevelUpResult(
        user_id=user_id,
        xp=level_row.xp,
        level=level_row.level,
        levels_gained=levels_gained,
        reward_outcomes=reward_outcomes,
        key_drops=key_drops,
        prestige_reached=prestige_reached,
        inviter_bonus=inviter_bonus,
    )


async def _maybe_reward_inviter(session, guild_id: int, invitee_user_id: int, rng=random) -> "LevelUpResult | None":
    from models.users import User
    from services.xp import INVITE_VALIDATION_XP

    invitee = await session.get(User, (guild_id, invitee_user_id))
    if invitee is None or invitee.invited_by_user_id is None:
        return None
    inviter_guild_id = invitee.invited_by_guild_id
    inviter_id = invitee.invited_by_user_id
    result = await add_xp(session, inviter_guild_id, inviter_id, INVITE_VALIDATION_XP, rng=rng)
    badge_outcome = await grant_badge_by_key(session, inviter_guild_id, inviter_id, "inviteur")
    result.reward_outcomes.append(badge_outcome)
    return result


async def get_all_levels(session, guild_id: int) -> list[tuple[int, int, int]]:
    """Returns (user_id, level, prestige) for every member with a Level row in this guild."""
    result = await session.execute(
        select(Level.user_id, Level.level, Level.prestige).where(Level.guild_id == guild_id)
    )
    return result.all()


async def subtract_xp(session, guild_id: int, user_id: int, amount: int) -> int:
    level_row = await get_or_create_level(session, guild_id, user_id)
    floor_xp = xp_for_level(level_row.level)
    level_row.xp = max(floor_xp, level_row.xp - amount)
    await session.flush()
    return level_row.xp
