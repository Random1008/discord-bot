from config.settings import ADMIN_PERMISSION_ROLE_ID
from models.admin_permission import AdminPermission


async def has_permission(session, guild_id: int, user_id: int) -> bool:
    return await session.get(AdminPermission, (guild_id, user_id)) is not None


async def can_bypass(session, guild_id: int, member) -> bool:
    author_roles = getattr(member, "roles", [])
    if not any(role.id == ADMIN_PERMISSION_ROLE_ID for role in author_roles):
        return False
    return await has_permission(session, guild_id, member.id)


async def grant_permission(session, guild_id: int, user_id: int, granted_by: int) -> None:
    existing = await session.get(AdminPermission, (guild_id, user_id))
    if existing is not None:
        return
    session.add(AdminPermission(guild_id=guild_id, user_id=user_id, granted_by=granted_by))
    await session.flush()


async def revoke_permission(session, guild_id: int, user_id: int) -> None:
    existing = await session.get(AdminPermission, (guild_id, user_id))
    if existing is None:
        return
    await session.delete(existing)
    await session.flush()
