from dataclasses import dataclass

from sqlalchemy import and_, func, select

from models.economy import Economy
from models.levels import Level
from models.stats import MessageStat, VoiceStat
from models.users import User


@dataclass
class LeaderboardEntry:
    user_id: int
    username: str
    score: int


async def get_xp_leaderboard(session, guild_id: int, limit: int = 10) -> list[LeaderboardEntry]:
    result = await session.execute(
        select(User.user_id, User.username, Level.xp)
        .join(Level, and_(Level.user_id == User.user_id, Level.guild_id == User.guild_id))
        .where(User.guild_id == guild_id)
        .order_by(Level.xp.desc())
        .limit(limit)
    )
    return [LeaderboardEntry(user_id=row[0], username=row[1], score=row[2]) for row in result.all()]


async def get_message_leaderboard(session, guild_id: int, limit: int = 10) -> list[LeaderboardEntry]:
    result = await session.execute(
        select(User.user_id, User.username, func.sum(MessageStat.count).label("total"))
        .join(MessageStat, and_(MessageStat.user_id == User.user_id, MessageStat.guild_id == User.guild_id))
        .where(User.guild_id == guild_id)
        .group_by(User.user_id, User.username)
        .order_by(func.sum(MessageStat.count).desc())
        .limit(limit)
    )
    return [LeaderboardEntry(user_id=row[0], username=row[1], score=int(row[2])) for row in result.all()]


async def get_coins_leaderboard(session, guild_id: int, limit: int = 10) -> list[LeaderboardEntry]:
    result = await session.execute(
        select(User.user_id, User.username, Economy.balance)
        .join(Economy, and_(Economy.user_id == User.user_id, Economy.guild_id == User.guild_id))
        .where(User.guild_id == guild_id)
        .order_by(Economy.balance.desc())
        .limit(limit)
    )
    return [LeaderboardEntry(user_id=row[0], username=row[1], score=row[2]) for row in result.all()]


async def get_xp_rank(session, guild_id: int, user_id: int) -> int:
    level_row = await session.get(Level, (guild_id, user_id))
    xp = level_row.xp if level_row is not None else 0
    result = await session.execute(
        select(func.count()).select_from(Level).where(Level.guild_id == guild_id, Level.xp > xp)
    )
    higher_count = result.scalar_one()
    return higher_count + 1


async def get_voice_leaderboard(session, guild_id: int, limit: int = 10) -> list[LeaderboardEntry]:
    result = await session.execute(
        select(User.user_id, User.username, func.sum(VoiceStat.seconds).label("total"))
        .join(VoiceStat, and_(VoiceStat.user_id == User.user_id, VoiceStat.guild_id == User.guild_id))
        .where(User.guild_id == guild_id)
        .group_by(User.user_id, User.username)
        .order_by(func.sum(VoiceStat.seconds).desc())
        .limit(limit)
    )
    return [LeaderboardEntry(user_id=row[0], username=row[1], score=int(row[2])) for row in result.all()]
