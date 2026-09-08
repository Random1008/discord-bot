from datetime import date

from models.quests import Quest, UserQuest
from models.users import User
from services.quests import get_daily_quests_status, increment_quest_progress
from config.settings import settings


async def test_increment_quest_progress_creates_row_and_accumulates(db_session):
    user = User(guild_id=settings.guild_id, user_id=9101, username="Grinder")
    quest = Quest(key="messages_25", description="Envoyer 25 messages", target_count=25, xp_reward=100, coins_reward=50)
    db_session.add_all([user, quest])
    await db_session.flush()

    result = await increment_quest_progress(db_session, settings.guild_id, user.user_id, "messages_25", 1, date(2026, 7, 21))
    await db_session.commit()

    assert result.user_quest.progress == 1
    assert result.just_completed is False

    result2 = await increment_quest_progress(db_session, settings.guild_id, user.user_id, "messages_25", 5, date(2026, 7, 21))
    await db_session.commit()

    assert result2.user_quest.progress == 6
    assert result2.just_completed is False


async def test_increment_quest_progress_marks_completed_exactly_once(db_session):
    user = User(guild_id=settings.guild_id, user_id=9102, username="AlmostDone")
    quest = Quest(key="channels_3", description="Écrire dans 3 salons", target_count=3, xp_reward=100, coins_reward=50)
    db_session.add_all([user, quest])
    await db_session.flush()

    r1 = await increment_quest_progress(db_session, settings.guild_id, user.user_id, "channels_3", 1, date(2026, 7, 21))
    r2 = await increment_quest_progress(db_session, settings.guild_id, user.user_id, "channels_3", 1, date(2026, 7, 21))
    r3 = await increment_quest_progress(db_session, settings.guild_id, user.user_id, "channels_3", 1, date(2026, 7, 21))
    await db_session.commit()

    assert [r1.just_completed, r2.just_completed, r3.just_completed] == [False, False, True]
    assert r3.user_quest.completed is True

    r4 = await increment_quest_progress(db_session, settings.guild_id, user.user_id, "channels_3", 1, date(2026, 7, 21))
    await db_session.commit()

    assert r4.just_completed is False
    assert r4.user_quest.progress == 3  # no further increment once completed


async def test_increment_quest_progress_separate_rows_per_day(db_session):
    user = User(guild_id=settings.guild_id, user_id=9103, username="DailyGrinder")
    quest = Quest(key="voice_60min", description="1h vocal", target_count=60, xp_reward=100, coins_reward=50)
    db_session.add_all([user, quest])
    await db_session.flush()

    await increment_quest_progress(db_session, settings.guild_id, user.user_id, "voice_60min", 60, date(2026, 7, 21))
    await db_session.commit()

    result = await increment_quest_progress(db_session, settings.guild_id, user.user_id, "voice_60min", 10, date(2026, 7, 22))
    await db_session.commit()

    assert result.user_quest.progress == 10
    assert result.user_quest.date == date(2026, 7, 22)


async def test_increment_quest_progress_returns_none_for_unknown_quest(db_session):
    user = User(guild_id=settings.guild_id, user_id=9104, username="Nobody")
    db_session.add(user)
    await db_session.flush()

    result = await increment_quest_progress(db_session, settings.guild_id, user.user_id, "does_not_exist", 1, date(2026, 7, 21))

    assert result is None


async def test_get_daily_quests_status_defaults_to_zero_without_row(db_session):
    user = User(guild_id=settings.guild_id, user_id=9103, username="Fresh")
    quest = Quest(key="messages_25", description="Envoyer 25 messages", target_count=25, xp_reward=100, coins_reward=50)
    db_session.add_all([user, quest])
    await db_session.commit()

    statuses = await get_daily_quests_status(db_session, settings.guild_id, user.user_id, date(2026, 7, 21))

    assert len(statuses) == 1
    assert statuses[0].progress == 0
    assert statuses[0].completed is False
    assert statuses[0].target_count == 25
    assert statuses[0].xp_reward == 100


async def test_get_daily_quests_status_reflects_existing_progress(db_session):
    user = User(guild_id=settings.guild_id, user_id=9104, username="InProgress")
    quest = Quest(key="channels_3", description="Écrire dans 3 salons", target_count=3, xp_reward=100, coins_reward=50)
    db_session.add_all([user, quest])
    await db_session.flush()

    await increment_quest_progress(db_session, settings.guild_id, user.user_id, "channels_3", 2, date(2026, 7, 21))
    await db_session.commit()

    statuses = await get_daily_quests_status(db_session, settings.guild_id, user.user_id, date(2026, 7, 21))

    assert statuses[0].progress == 2
    assert statuses[0].completed is False

    # une autre date ne doit pas voir cette progression
    other_day_statuses = await get_daily_quests_status(db_session, settings.guild_id, user.user_id, date(2026, 7, 22))
    assert other_day_statuses[0].progress == 0
