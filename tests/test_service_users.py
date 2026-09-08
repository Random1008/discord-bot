from config.settings import settings
from services.users import get_or_create_user


async def test_get_or_create_user_creates_new_row(db_session):
    user = await get_or_create_user(db_session, settings.guild_id, 8001, "Newcomer")
    await db_session.commit()

    assert user.user_id == 8001
    assert user.username == "Newcomer"


async def test_get_or_create_user_returns_existing_row_unchanged(db_session):
    first = await get_or_create_user(db_session, settings.guild_id, 8002, "Original")
    await db_session.commit()

    second = await get_or_create_user(db_session, settings.guild_id, 8002, "RenamedElsewhere")
    await db_session.commit()

    assert second.user_id == first.user_id
    assert second.username == "Original"
