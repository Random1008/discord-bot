from datetime import date

from models.economy import Economy
from models.levels import Level
from models.stats import MessageStat, VoiceStat
from models.users import User
from services.leaderboard import (
    get_coins_leaderboard,
    get_message_leaderboard,
    get_voice_leaderboard,
    get_xp_leaderboard,
    get_xp_rank,
)
from config.settings import settings


async def test_get_xp_leaderboard_orders_by_xp_desc(db_session):
    db_session.add_all(
        [
            User(guild_id=settings.guild_id, user_id=30001, username="Low"),
            User(guild_id=settings.guild_id, user_id=30002, username="High"),
        ]
    )
    await db_session.flush()
    db_session.add_all(
        [
            Level(guild_id=settings.guild_id, user_id=30001, xp=100, level=1, prestige=0),
            Level(guild_id=settings.guild_id, user_id=30002, xp=500, level=2, prestige=0),
        ]
    )
    await db_session.commit()

    entries = await get_xp_leaderboard(db_session, settings.guild_id, limit=10)

    assert [e.username for e in entries] == ["High", "Low"]
    assert entries[0].score == 500


async def test_get_xp_leaderboard_respects_limit(db_session):
    users = [User(guild_id=settings.guild_id, user_id=30100 + i, username=f"U{i}") for i in range(15)]
    db_session.add_all(users)
    await db_session.flush()
    db_session.add_all([Level(guild_id=settings.guild_id, user_id=30100 + i, xp=i * 10, level=0, prestige=0) for i in range(15)])
    await db_session.commit()

    entries = await get_xp_leaderboard(db_session, settings.guild_id, limit=10)

    assert len(entries) == 10
    assert entries[0].score == 140


async def test_get_message_leaderboard_sums_across_dates(db_session):
    db_session.add(User(guild_id=settings.guild_id, user_id=30002, username="Chatty"))
    await db_session.flush()
    db_session.add_all(
        [
            MessageStat(guild_id=settings.guild_id, user_id=30002, date=date(2026, 7, 20), count=10),
            MessageStat(guild_id=settings.guild_id, user_id=30002, date=date(2026, 7, 21), count=15),
        ]
    )
    await db_session.commit()

    entries = await get_message_leaderboard(db_session, settings.guild_id, limit=10)

    assert entries[0].username == "Chatty"
    assert entries[0].score == 25


async def test_get_voice_leaderboard_sums_across_dates(db_session):
    db_session.add(User(guild_id=settings.guild_id, user_id=30003, username="Talker"))
    await db_session.flush()
    db_session.add_all(
        [
            VoiceStat(guild_id=settings.guild_id, user_id=30003, date=date(2026, 7, 20), seconds=600),
            VoiceStat(guild_id=settings.guild_id, user_id=30003, date=date(2026, 7, 21), seconds=1200),
        ]
    )
    await db_session.commit()

    entries = await get_voice_leaderboard(db_session, settings.guild_id, limit=10)

    assert entries[0].username == "Talker"
    assert entries[0].score == 1800


async def test_get_coins_leaderboard_orders_by_balance_desc(db_session):
    db_session.add_all(
        [
            User(guild_id=settings.guild_id, user_id=30004, username="Poor"),
            User(guild_id=settings.guild_id, user_id=30005, username="Rich"),
        ]
    )
    await db_session.flush()
    db_session.add_all(
        [
            Economy(guild_id=settings.guild_id, user_id=30004, balance=50),
            Economy(guild_id=settings.guild_id, user_id=30005, balance=5000),
        ]
    )
    await db_session.commit()

    entries = await get_coins_leaderboard(db_session, settings.guild_id, limit=10)

    assert [e.username for e in entries] == ["Rich", "Poor"]
    assert entries[0].score == 5000


async def test_leaderboards_return_empty_list_when_no_data(db_session):
    assert await get_xp_leaderboard(db_session, settings.guild_id) == []
    assert await get_message_leaderboard(db_session, settings.guild_id) == []
    assert await get_voice_leaderboard(db_session, settings.guild_id) == []
    assert await get_coins_leaderboard(db_session, settings.guild_id) == []


async def test_get_xp_rank_orders_by_xp_desc(db_session):
    db_session.add_all(
        [
            User(guild_id=settings.guild_id, user_id=31001, username="Low"),
            User(guild_id=settings.guild_id, user_id=31002, username="Mid"),
            User(guild_id=settings.guild_id, user_id=31003, username="High"),
        ]
    )
    await db_session.flush()
    db_session.add_all(
        [
            Level(guild_id=settings.guild_id, user_id=31001, xp=100, level=1, prestige=0),
            Level(guild_id=settings.guild_id, user_id=31002, xp=500, level=2, prestige=0),
            Level(guild_id=settings.guild_id, user_id=31003, xp=900, level=3, prestige=0),
        ]
    )
    await db_session.commit()

    assert await get_xp_rank(db_session, settings.guild_id, 31003) == 1
    assert await get_xp_rank(db_session, settings.guild_id, 31002) == 2
    assert await get_xp_rank(db_session, settings.guild_id, 31001) == 3


async def test_get_xp_rank_treats_missing_level_row_as_zero_xp(db_session):
    db_session.add(User(guild_id=settings.guild_id, user_id=31004, username="NoXP"))
    await db_session.flush()
    db_session.add(Level(guild_id=settings.guild_id, user_id=31005, xp=50, level=1, prestige=0))
    await db_session.commit()

    assert await get_xp_rank(db_session, settings.guild_id, 31004) == 2
