from config.settings import settings
from models.users import User
from services.bot_access import block_user, is_blocked, unblock_user

GUILD_ID = settings.guild_id


async def _make_user(db_session, user_id: int) -> None:
    db_session.add(User(guild_id=GUILD_ID, user_id=user_id, username=f"user{user_id}"))
    await db_session.flush()


async def test_user_not_blocked_by_default(db_session):
    await _make_user(db_session, 90001)

    assert await is_blocked(db_session, GUILD_ID, 90001) is False


async def test_block_user_marks_them_blocked(db_session):
    await _make_user(db_session, 90002)
    await _make_user(db_session, 90099)

    await block_user(db_session, GUILD_ID, 90002, blocked_by=90099)

    assert await is_blocked(db_session, GUILD_ID, 90002) is True


async def test_block_user_is_idempotent(db_session):
    await _make_user(db_session, 90003)
    await _make_user(db_session, 90099)

    await block_user(db_session, GUILD_ID, 90003, blocked_by=90099)
    await block_user(db_session, GUILD_ID, 90003, blocked_by=90099)

    assert await is_blocked(db_session, GUILD_ID, 90003) is True


async def test_unblock_user_lifts_the_block(db_session):
    await _make_user(db_session, 90004)
    await _make_user(db_session, 90099)
    await block_user(db_session, GUILD_ID, 90004, blocked_by=90099)

    await unblock_user(db_session, GUILD_ID, 90004)

    assert await is_blocked(db_session, GUILD_ID, 90004) is False


async def test_unblock_user_on_never_blocked_user_is_a_noop(db_session):
    await _make_user(db_session, 90005)

    await unblock_user(db_session, GUILD_ID, 90005)

    assert await is_blocked(db_session, GUILD_ID, 90005) is False


async def test_block_is_scoped_per_guild(db_session):
    other_guild = GUILD_ID + 1
    db_session.add(User(guild_id=other_guild, user_id=90006, username="user90006"))
    await _make_user(db_session, 90006)
    await _make_user(db_session, 90099)
    await db_session.flush()

    await block_user(db_session, GUILD_ID, 90006, blocked_by=90099)

    assert await is_blocked(db_session, GUILD_ID, 90006) is True
    assert await is_blocked(db_session, other_guild, 90006) is False
