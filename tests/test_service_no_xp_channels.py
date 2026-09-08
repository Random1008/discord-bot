from config.settings import settings
from services.no_xp_channels import (
    add_no_xp_channel,
    is_no_xp_channel,
    list_no_xp_channels,
    remove_no_xp_channel,
)


async def test_add_no_xp_channel_marks_it_excluded(db_session):
    already_excluded = await add_no_xp_channel(db_session, settings.guild_id, 111)
    await db_session.commit()

    assert already_excluded is False
    assert await is_no_xp_channel(db_session, settings.guild_id, 111) is True


async def test_add_no_xp_channel_is_idempotent(db_session):
    await add_no_xp_channel(db_session, settings.guild_id, 111)
    await db_session.commit()

    already_excluded = await add_no_xp_channel(db_session, settings.guild_id, 111)
    await db_session.commit()

    assert already_excluded is True


async def test_remove_no_xp_channel_clears_exclusion(db_session):
    await add_no_xp_channel(db_session, settings.guild_id, 222)
    await db_session.commit()

    removed = await remove_no_xp_channel(db_session, settings.guild_id, 222)
    await db_session.commit()

    assert removed is True
    assert await is_no_xp_channel(db_session, settings.guild_id, 222) is False


async def test_remove_no_xp_channel_returns_false_when_not_excluded(db_session):
    removed = await remove_no_xp_channel(db_session, settings.guild_id, 333)
    await db_session.commit()

    assert removed is False


async def test_list_no_xp_channels_returns_all_excluded_ids(db_session):
    await add_no_xp_channel(db_session, settings.guild_id, 111)
    await add_no_xp_channel(db_session, settings.guild_id, 222)
    await db_session.commit()

    channel_ids = await list_no_xp_channels(db_session, settings.guild_id)

    assert set(channel_ids) == {111, 222}


async def test_list_no_xp_channels_empty_by_default(db_session):
    assert await list_no_xp_channels(db_session, settings.guild_id) == []
