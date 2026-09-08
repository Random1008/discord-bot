import random

from sqlalchemy import select

from models.keys import UserKey

KEY_RARITY_WEIGHTS = {
    "commun": 60.0,
    "rare": 25.0,
    "epique": 10.0,
    "legendaire": 3.5,
    "mythique": 1.0,
    "divin": 0.5,
}

KEY_DROP_CHANCES = {5: 0.15, 10: 0.25, 15: 0.5, 20: 0.75, 25: 1.0}

KEY_RARITY_ORDER = ["commun", "rare", "epique", "legendaire", "mythique", "divin"]


def roll_key_rarity(rng=random) -> str:
    roll = rng.uniform(0.0, 100.0)
    cumulative = 0.0
    for rarity, weight in KEY_RARITY_WEIGHTS.items():
        cumulative += weight
        if roll < cumulative:
            return rarity
    return "divin"


def should_drop_key(levels_elapsed: int, rng=random) -> bool:
    chance = KEY_DROP_CHANCES.get(levels_elapsed)
    if chance is None:
        return False
    return rng.random() < chance


async def add_key(session, guild_id: int, user_id: int, rarity: str) -> None:
    result = await session.execute(
        select(UserKey).where(
            UserKey.guild_id == guild_id, UserKey.user_id == user_id, UserKey.rarity == rarity
        )
    )
    key = result.scalar_one_or_none()
    if key is None:
        key = UserKey(guild_id=guild_id, user_id=user_id, rarity=rarity, count=0)
        session.add(key)
    key.count += 1
    await session.flush()


async def get_key_count(session, guild_id: int, user_id: int, rarity: str) -> int:
    result = await session.execute(
        select(UserKey).where(
            UserKey.guild_id == guild_id, UserKey.user_id == user_id, UserKey.rarity == rarity
        )
    )
    key = result.scalar_one_or_none()
    return key.count if key is not None else 0


async def remove_key(session, guild_id: int, user_id: int, rarity: str) -> bool:
    result = await session.execute(
        select(UserKey).where(
            UserKey.guild_id == guild_id, UserKey.user_id == user_id, UserKey.rarity == rarity
        )
    )
    key = result.scalar_one_or_none()
    if key is None or key.count <= 0:
        return False
    key.count -= 1
    await session.flush()
    return True


async def upgrade_key(session, guild_id: int, user_id: int, from_rarity: str | None = None, rng=random) -> str | None:
    """Consumes one key and grants one of the next rarity up. Returns the new rarity, or
    None if there was nothing eligible to upgrade (no key owned, or already at the top tier)."""
    if from_rarity is None:
        owned = []
        for rarity in KEY_RARITY_ORDER[:-1]:
            if await get_key_count(session, guild_id, user_id, rarity) > 0:
                owned.append(rarity)
        if not owned:
            return None
        from_rarity = rng.choice(owned)

    index = KEY_RARITY_ORDER.index(from_rarity)
    if index >= len(KEY_RARITY_ORDER) - 1:
        return None

    removed = await remove_key(session, guild_id, user_id, from_rarity)
    if not removed:
        return None

    to_rarity = KEY_RARITY_ORDER[index + 1]
    await add_key(session, guild_id, user_id, to_rarity)
    return to_rarity
