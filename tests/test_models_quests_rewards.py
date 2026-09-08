from datetime import date

from models.quests import Quest, UserQuest
from models.rewards import Reward
from models.users import User
from config.settings import settings


async def test_quest_progress_and_reward_roundtrip(db_session):
    user = User(guild_id=settings.guild_id, user_id=4004, username="Odile")
    quest = Quest(key="messages_25", description="Envoyer 25 messages", target_count=25, xp_reward=100, coins_reward=50)
    db_session.add_all([user, quest])
    await db_session.flush()

    user_quest = UserQuest(guild_id=settings.guild_id, user_id=user.user_id, quest_id=quest.id, date=date(2026, 7, 20), progress=10, completed=False)
    reward = Reward(level=10, reward_type="coins", reward_value="1000")
    db_session.add_all([user_quest, reward])
    await db_session.commit()

    fetched_quest_progress = await db_session.get(UserQuest, user_quest.id)
    assert fetched_quest_progress.progress == 10
    assert fetched_quest_progress.completed is False

    assert reward.id is not None
    assert reward.reward_value == "1000"
