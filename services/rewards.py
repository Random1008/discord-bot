import random
from dataclasses import dataclass

from sqlalchemy import select

from models.badges import Badge, UserBadge
from models.rewards import Reward
from services.economy import add_balance
from services.keys import add_key, roll_key_rarity


@dataclass
class RewardOutcome:
    reward_type: str
    reward_value: str
    detail: str


async def grant_reward(session, guild_id: int, user_id: int, reward: Reward, rng=random) -> RewardOutcome:
    if reward.reward_type == "badge":
        outcome = await grant_badge_by_key(session, guild_id, user_id, reward.reward_value)
        return RewardOutcome(reward_type="badge", reward_value=reward.reward_value, detail=outcome.detail)
    elif reward.reward_type == "coins":
        amount = int(reward.reward_value)
        await add_balance(session, guild_id, user_id, amount)
        detail = f"{amount} coins"
    elif reward.reward_type == "item":
        rarity = roll_key_rarity(rng=rng)
        await add_key(session, guild_id, user_id, rarity)
        detail = f"clé {rarity}"
    else:
        # role, access, title: no DB-side effect here — the caller (cogs/_xp_common.py)
        # resolves reward_value to a Discord role via config, or is announce-only (title).
        detail = reward.reward_value

    return RewardOutcome(reward_type=reward.reward_type, reward_value=reward.reward_value, detail=detail)


async def get_role_reward_thresholds(session) -> dict[str, int]:
    """Maps reward_value -> level for every role/access reward row.

    Used to reconcile a member's currently-held roles against the level they've
    reached, independent of whether the level-up event that would normally grant
    the role ever fired for them (e.g. after a `.resetuser`/`.setlevel`, or if a
    role was assigned/removed manually).
    """
    result = await session.execute(
        select(Reward.reward_value, Reward.level).where(Reward.reward_type.in_(("role", "access")))
    )
    return {reward_value: level for reward_value, level in result.all()}


async def grant_badge_by_key(session, guild_id: int, user_id: int, badge_key: str) -> RewardOutcome:
    """Idempotently grant a badge by its `key`, independent of the level/reward table.

    Used both by the level-crossing reward path (`grant_reward`) and by event-keyed
    badge grants (e.g. the "inviteur" badge, granted on invite validation rather than
    on a level crossing).
    """
    badge_result = await session.execute(select(Badge).where(Badge.key == badge_key))
    badge = badge_result.scalar_one()

    existing = await session.execute(
        select(UserBadge).where(
            UserBadge.guild_id == guild_id, UserBadge.user_id == user_id, UserBadge.badge_id == badge.id
        )
    )
    if existing.scalar_one_or_none() is None:
        session.add(UserBadge(guild_id=guild_id, user_id=user_id, badge_id=badge.id))
        await session.flush()

    return RewardOutcome(reward_type="badge", reward_value=badge_key, detail=badge_key)
