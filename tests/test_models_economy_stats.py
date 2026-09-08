from datetime import date

from models.economy import Economy
from models.stats import MessageStat, ServerStat, VoiceStat
from models.users import User
from config.settings import settings


async def test_economy_and_daily_stats_roundtrip(db_session):
    user = User(guild_id=settings.guild_id, user_id=3003, username="Talys")
    db_session.add(user)
    await db_session.flush()

    economy = Economy(guild_id=settings.guild_id, user_id=user.user_id, balance=500)
    voice = VoiceStat(guild_id=settings.guild_id, user_id=user.user_id, date=date(2026, 7, 20), seconds=600)
    messages = MessageStat(guild_id=settings.guild_id, user_id=user.user_id, date=date(2026, 7, 20), count=12)
    server = ServerStat(guild_id=settings.guild_id, date=date(2026, 7, 20), total_members=100, active_members=40, messages_count=300, voice_minutes=50, new_members=2)
    db_session.add_all([economy, voice, messages, server])
    await db_session.commit()

    fetched_economy = await db_session.get(Economy, (settings.guild_id, user.user_id))
    assert fetched_economy.balance == 500

    fetched_server = await db_session.get(ServerStat, (settings.guild_id, date(2026, 7, 20)))
    assert fetched_server.total_members == 100
