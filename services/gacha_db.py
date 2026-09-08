from sqlalchemy import select, update

from models.gacha import GachaCharacter, GachaHistoryEntry, GachaState, GachaWishlist


async def _get_or_create_gacha_state(session, guild_id: int, user_id: int) -> GachaState:
    row = await session.get(GachaState, (guild_id, user_id))
    if row is None:
        row = GachaState(guild_id=guild_id, user_id=user_id)
        session.add(row)
        await session.flush()
    return row


async def get_gacha_state(session, guild_id: int, user_id: int) -> dict:
    row = await _get_or_create_gacha_state(session, guild_id, user_id)
    return {
        "pulls_since_epique": row.pulls_since_epique,
        "pulls_since_legendaire": row.pulls_since_legendaire,
        "pulls_since_mythique": row.pulls_since_mythique,
        "fragments": row.fragments,
        "secret_rolls": row.secret_rolls,
    }


async def update_gacha_pity(
    session,
    guild_id: int,
    user_id: int,
    pulls_since_epique: int,
    pulls_since_legendaire: int,
    pulls_since_mythique: int,
) -> None:
    row = await _get_or_create_gacha_state(session, guild_id, user_id)
    row.pulls_since_epique = pulls_since_epique
    row.pulls_since_legendaire = pulls_since_legendaire
    row.pulls_since_mythique = pulls_since_mythique
    await session.flush()


async def add_fragments(session, guild_id: int, user_id: int, delta: int) -> int:
    row = await _get_or_create_gacha_state(session, guild_id, user_id)
    row.fragments = max(0, row.fragments + delta)
    await session.flush()
    return row.fragments


async def spend_fragments(session, guild_id: int, user_id: int, amount: int) -> tuple[bool, int]:
    row = await _get_or_create_gacha_state(session, guild_id, user_id)
    if row.fragments < amount:
        return False, row.fragments
    result = await session.execute(
        update(GachaState)
        .where(
            GachaState.guild_id == guild_id,
            GachaState.user_id == user_id,
            GachaState.fragments >= amount,
        )
        .values(fragments=GachaState.fragments - amount)
    )
    await session.flush()
    row = await session.get(GachaState, (guild_id, user_id))
    return (result.rowcount == 1), row.fragments


async def increment_secret_rolls(session, guild_id: int, user_id: int) -> int:
    row = await _get_or_create_gacha_state(session, guild_id, user_id)
    row.secret_rolls += 1
    await session.flush()
    return row.secret_rolls


async def add_character(session, guild_id: int, user_id: int, character_name: str) -> None:
    row = await session.get(GachaCharacter, (guild_id, user_id, character_name))
    if row is None:
        session.add(GachaCharacter(guild_id=guild_id, user_id=user_id, character_name=character_name, count=1))
    else:
        row.count += 1
    await session.flush()


async def remove_character(session, guild_id: int, user_id: int, character_name: str) -> bool:
    row = await session.get(GachaCharacter, (guild_id, user_id, character_name))
    if row is None or row.count <= 0:
        return False
    row.count -= 1
    if row.count <= 0:
        await session.delete(row)
    await session.flush()
    return True


async def get_characters(session, guild_id: int, user_id: int) -> list[dict]:
    result = await session.execute(
        select(GachaCharacter)
        .where(GachaCharacter.guild_id == guild_id, GachaCharacter.user_id == user_id)
        .order_by(GachaCharacter.character_name)
    )
    return [{"character_name": c.character_name, "count": c.count} for c in result.scalars().all()]


async def record_gacha_pull(session, guild_id: int, user_id: int, rarity: str, character_name: str | None) -> None:
    session.add(GachaHistoryEntry(guild_id=guild_id, user_id=user_id, rarity=rarity, character_name=character_name))
    await session.flush()


async def get_gacha_history(session, guild_id: int, user_id: int, limit: int = 10) -> list[dict]:
    result = await session.execute(
        select(GachaHistoryEntry)
        .where(GachaHistoryEntry.guild_id == guild_id, GachaHistoryEntry.user_id == user_id)
        .order_by(GachaHistoryEntry.id.desc())
        .limit(limit)
    )
    return [{"rarity": h.rarity, "character_name": h.character_name} for h in result.scalars().all()]


async def set_wishlist_character(session, guild_id: int, user_id: int, character_name: str | None) -> None:
    row = await session.get(GachaWishlist, (guild_id, user_id))
    if character_name is None:
        if row is not None:
            await session.delete(row)
    elif row is None:
        session.add(GachaWishlist(guild_id=guild_id, user_id=user_id, character_name=character_name))
    else:
        row.character_name = character_name
    await session.flush()


async def get_wishlist_character(session, guild_id: int, user_id: int) -> str | None:
    row = await session.get(GachaWishlist, (guild_id, user_id))
    return row.character_name if row is not None else None
