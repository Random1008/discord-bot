from models.bot_access import BlockedUser


async def is_blocked(session, guild_id: int, user_id: int) -> bool:
    return await session.get(BlockedUser, (guild_id, user_id)) is not None


async def block_user(session, guild_id: int, user_id: int, blocked_by: int) -> None:
    existing = await session.get(BlockedUser, (guild_id, user_id))
    if existing is not None:
        return
    session.add(BlockedUser(guild_id=guild_id, user_id=user_id, blocked_by=blocked_by))
    await session.flush()


async def unblock_user(session, guild_id: int, user_id: int) -> None:
    existing = await session.get(BlockedUser, (guild_id, user_id))
    if existing is None:
        return
    await session.delete(existing)
    await session.flush()
