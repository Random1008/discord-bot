from models.levels import Level
from models.prestiges import Prestige
from models.users import User
from config.settings import settings


async def test_user_level_and_prestige_roundtrip(db_session):
    user = User(guild_id=settings.guild_id, user_id=1001, username="Ashen")
    db_session.add(user)
    await db_session.flush()

    level = Level(guild_id=settings.guild_id, user_id=user.user_id, xp=250, level=3, prestige=0, message_count=10, voice_seconds=120)
    db_session.add(level)

    prestige = Prestige(guild_id=settings.guild_id, user_id=user.user_id, prestige_level=1)
    db_session.add(prestige)
    await db_session.commit()

    fetched_level = await db_session.get(Level, (settings.guild_id, user.user_id))
    assert fetched_level.xp == 250
    assert fetched_level.level == 3
    assert fetched_level.message_count == 10

    assert prestige.id is not None
    assert prestige.user_id == user.user_id
    assert prestige.prestige_level == 1
