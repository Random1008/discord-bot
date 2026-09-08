from dataclasses import dataclass, field
from datetime import date as Date

from sqlalchemy import func, select

from models.keys import UserKey
from models.quests import Quest, UserQuest
from models.stats import MessageStat, VoiceStat


@dataclass
class QuestProgressView:
    description: str
    progress: int
    target_count: int
    completed: bool


@dataclass
class ProfileStats:
    total_messages: int
    total_voice_seconds: int
    quests_today: list[QuestProgressView] = field(default_factory=list)
    keys_by_rarity: dict[str, int] = field(default_factory=dict)


async def gather_profile_stats(session, guild_id: int, user_id: int, today: Date) -> ProfileStats:
    total_messages_result = await session.execute(
        select(func.sum(MessageStat.count)).where(
            MessageStat.guild_id == guild_id, MessageStat.user_id == user_id
        )
    )
    total_messages = total_messages_result.scalar_one_or_none() or 0

    total_voice_result = await session.execute(
        select(func.sum(VoiceStat.seconds)).where(
            VoiceStat.guild_id == guild_id, VoiceStat.user_id == user_id
        )
    )
    total_voice_seconds = total_voice_result.scalar_one_or_none() or 0

    quests_result = await session.execute(
        select(UserQuest, Quest)
        .join(Quest, Quest.id == UserQuest.quest_id)
        .where(UserQuest.guild_id == guild_id, UserQuest.user_id == user_id, UserQuest.date == today)
    )
    quests_today = [
        QuestProgressView(
            description=quest.description,
            progress=user_quest.progress,
            target_count=quest.target_count,
            completed=user_quest.completed,
        )
        for user_quest, quest in quests_result.all()
    ]

    keys_result = await session.execute(
        select(UserKey.rarity, UserKey.count).where(
            UserKey.guild_id == guild_id, UserKey.user_id == user_id
        )
    )
    keys_by_rarity = {rarity: count for rarity, count in keys_result.all()}

    return ProfileStats(
        total_messages=total_messages,
        total_voice_seconds=total_voice_seconds,
        quests_today=quests_today,
        keys_by_rarity=keys_by_rarity,
    )
