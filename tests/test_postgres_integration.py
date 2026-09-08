import os
import uuid

from sqlalchemy import select

from database.engine import create_engine_and_session
from models.users import User
from config.settings import settings


async def test_user_roundtrip_against_real_postgres():
    engine, session_factory = create_engine_and_session(os.environ["DATABASE_URL"])

    discord_id = int(uuid.uuid4().int % 1_000_000_000_000)

    async with session_factory() as session:
        session.add(User(guild_id=settings.guild_id, user_id=discord_id, username="pg-integration-check"))
        await session.commit()

    async with session_factory() as session:
        fetched = await session.get(User, (settings.guild_id, discord_id))
        assert fetched is not None
        assert fetched.username == "pg-integration-check"

        await session.delete(fetched)
        await session.commit()

    await engine.dispose()
