from models.users import User
from shared.db import services as shared_services


async def get_or_create_user(session, guild_id: int, discord_id: int, username: str) -> User:
    return await shared_services.get_or_create_user(session, guild_id, discord_id, username)
