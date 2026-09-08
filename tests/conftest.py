import os

os.environ.setdefault("DISCORD_TOKEN", "test-token")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from database.base import Base
from database.engine import create_engine_and_session


@pytest_asyncio.fixture
async def db_session():
    engine, _ = create_engine_and_session("sqlite+aiosqlite:///:memory:")
    engine = engine.execution_options(schema_translate_map={"shared": None})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()
