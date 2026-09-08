from sqlalchemy import select

from models.inventory import UserItem


async def add_to_inventory(session, guild_id: int, user_id: int, item_id: int) -> None:
    result = await session.execute(
        select(UserItem).where(
            UserItem.guild_id == guild_id, UserItem.user_id == user_id, UserItem.item_id == item_id
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = UserItem(guild_id=guild_id, user_id=user_id, item_id=item_id, count=0)
        session.add(row)
    row.count += 1
    await session.flush()


async def get_inventory_count(session, guild_id: int, user_id: int, item_id: int) -> int:
    result = await session.execute(
        select(UserItem).where(
            UserItem.guild_id == guild_id, UserItem.user_id == user_id, UserItem.item_id == item_id
        )
    )
    row = result.scalar_one_or_none()
    return row.count if row is not None else 0


async def remove_from_inventory(session, guild_id: int, user_id: int, item_id: int) -> bool:
    result = await session.execute(
        select(UserItem).where(
            UserItem.guild_id == guild_id, UserItem.user_id == user_id, UserItem.item_id == item_id
        )
    )
    row = result.scalar_one_or_none()
    if row is None or row.count <= 0:
        return False
    row.count -= 1
    await session.flush()
    return True


async def list_inventory(session, guild_id: int, user_id: int) -> list[UserItem]:
    result = await session.execute(
        select(UserItem).where(
            UserItem.guild_id == guild_id, UserItem.user_id == user_id, UserItem.count > 0
        )
    )
    return list(result.scalars().all())
