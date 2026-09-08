from dataclasses import dataclass
from datetime import date as Date

from sqlalchemy import select

from models.quests import Quest, UserQuest


@dataclass
class QuestProgressResult:
    user_quest: UserQuest
    quest: Quest
    just_completed: bool


@dataclass
class QuestStatus:
    description: str
    progress: int
    target_count: int
    completed: bool
    xp_reward: int
    coins_reward: int


async def get_daily_quests_status(session, guild_id: int, user_id: int, today: Date) -> list[QuestStatus]:
    result = await session.execute(
        select(Quest, UserQuest)
        .outerjoin(
            UserQuest,
            (UserQuest.quest_id == Quest.id)
            & (UserQuest.guild_id == guild_id)
            & (UserQuest.user_id == user_id)
            & (UserQuest.date == today),
        )
        .order_by(Quest.id)
    )
    return [
        QuestStatus(
            description=quest.description,
            progress=user_quest.progress if user_quest is not None else 0,
            target_count=quest.target_count,
            completed=user_quest.completed if user_quest is not None else False,
            xp_reward=quest.xp_reward,
            coins_reward=quest.coins_reward,
        )
        for quest, user_quest in result.all()
    ]


async def increment_quest_progress(
    session, guild_id: int, user_id: int, quest_key: str, amount: int, today: Date
) -> QuestProgressResult | None:
    quest_result = await session.execute(select(Quest).where(Quest.key == quest_key))
    quest = quest_result.scalar_one_or_none()
    if quest is None:
        return None

    row_result = await session.execute(
        select(UserQuest).where(
            UserQuest.guild_id == guild_id,
            UserQuest.user_id == user_id,
            UserQuest.quest_id == quest.id,
            UserQuest.date == today,
        )
    )
    user_quest = row_result.scalar_one_or_none()
    if user_quest is None:
        user_quest = UserQuest(
            guild_id=guild_id, user_id=user_id, quest_id=quest.id, date=today, progress=0, completed=False
        )
        session.add(user_quest)
        await session.flush()

    if user_quest.completed:
        return QuestProgressResult(user_quest=user_quest, quest=quest, just_completed=False)

    user_quest.progress += amount
    just_completed = False
    if user_quest.progress >= quest.target_count:
        user_quest.completed = True
        just_completed = True
    await session.flush()

    return QuestProgressResult(user_quest=user_quest, quest=quest, just_completed=just_completed)
