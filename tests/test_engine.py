from sqlalchemy import text

from database.engine import create_engine_and_session


async def test_create_engine_and_session_executes_query():
    engine, session_factory = create_engine_and_session("sqlite+aiosqlite:///:memory:")

    async with session_factory() as session:
        result = await session.execute(text("SELECT 1"))
        assert result.scalar_one() == 1

    await engine.dispose()
