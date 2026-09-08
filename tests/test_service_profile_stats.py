from datetime import date

from models.keys import UserKey
from models.quests import Quest, UserQuest
from models.stats import MessageStat, VoiceStat
from models.users import User
from services.profile_stats import gather_profile_stats
from config.settings import settings


async def test_gather_profile_stats_sums_messages_and_voice_across_dates(db_session):
    user = User(guild_id=settings.guild_id, user_id=32001, username="Statful")
    db_session.add(user)
    await db_session.flush()
    db_session.add_all(
        [
            MessageStat(guild_id=settings.guild_id, user_id=32001, date=date(2026, 7, 20), count=10),
            MessageStat(guild_id=settings.guild_id, user_id=32001, date=date(2026, 7, 21), count=5),
            VoiceStat(guild_id=settings.guild_id, user_id=32001, date=date(2026, 7, 20), seconds=600),
            VoiceStat(guild_id=settings.guild_id, user_id=32001, date=date(2026, 7, 21), seconds=1200),
        ]
    )
    await db_session.commit()

    stats = await gather_profile_stats(db_session, settings.guild_id, 32001, date(2026, 7, 21))

    assert stats.total_messages == 15
    assert stats.total_voice_seconds == 1800


async def test_gather_profile_stats_returns_zero_for_new_user(db_session):
    user = User(guild_id=settings.guild_id, user_id=32002, username="Fresh")
    db_session.add(user)
    await db_session.commit()

    stats = await gather_profile_stats(db_session, settings.guild_id, 32002, date(2026, 7, 21))

    assert stats.total_messages == 0
    assert stats.total_voice_seconds == 0
    assert stats.quests_today == []
    assert stats.keys_by_rarity == {}


async def test_gather_profile_stats_includes_only_todays_quests(db_session):
    user = User(guild_id=settings.guild_id, user_id=32003, username="Grinder")
    quest = Quest(key="messages_25", description="Envoyer 25 messages", target_count=25, xp_reward=100, coins_reward=50)
    db_session.add_all([user, quest])
    await db_session.flush()
    db_session.add_all(
        [
            UserQuest(guild_id=settings.guild_id, user_id=32003, quest_id=quest.id, date=date(2026, 7, 21), progress=10, completed=False),
            UserQuest(guild_id=settings.guild_id, user_id=32003, quest_id=quest.id, date=date(2026, 7, 20), progress=25, completed=True),
        ]
    )
    await db_session.commit()

    stats = await gather_profile_stats(db_session, settings.guild_id, 32003, date(2026, 7, 21))

    assert len(stats.quests_today) == 1
    assert stats.quests_today[0].description == "Envoyer 25 messages"
    assert stats.quests_today[0].progress == 10
    assert stats.quests_today[0].target_count == 25
    assert stats.quests_today[0].completed is False


async def test_gather_profile_stats_includes_keys_by_rarity(db_session):
    user = User(guild_id=settings.guild_id, user_id=32004, username="KeyHolder")
    db_session.add(user)
    await db_session.flush()
    db_session.add_all(
        [
            UserKey(guild_id=settings.guild_id, user_id=32004, rarity="commun", count=3),
            UserKey(guild_id=settings.guild_id, user_id=32004, rarity="rare", count=1),
        ]
    )
    await db_session.commit()

    stats = await gather_profile_stats(db_session, settings.guild_id, 32004, date(2026, 7, 21))

    assert stats.keys_by_rarity == {"commun": 3, "rare": 1}
