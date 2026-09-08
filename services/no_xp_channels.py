from sqlalchemy import select

from models.no_xp_channels import NoXpChannel


async def add_no_xp_channel(session, guild_id: int, channel_id: int) -> bool:
    """Add a channel to the no-XP list. Returns True if it was already excluded, False if newly added."""
    existing = await session.get(NoXpChannel, (guild_id, channel_id))
    if existing is not None:
        return True
    session.add(NoXpChannel(guild_id=guild_id, channel_id=channel_id))
    await session.flush()
    return False


async def remove_no_xp_channel(session, guild_id: int, channel_id: int) -> bool:
    """Remove a channel from the no-XP list. Returns True if it was removed, False if it wasn't excluded."""
    existing = await session.get(NoXpChannel, (guild_id, channel_id))
    if existing is None:
        return False
    await session.delete(existing)
    await session.flush()
    return True


async def list_no_xp_channels(session, guild_id: int) -> list[int]:
    result = await session.execute(
        select(NoXpChannel.channel_id).where(NoXpChannel.guild_id == guild_id)
    )
    return [row[0] for row in result.all()]


async def is_no_xp_channel(session, guild_id: int, channel_id: int) -> bool:
    return await session.get(NoXpChannel, (guild_id, channel_id)) is not None
