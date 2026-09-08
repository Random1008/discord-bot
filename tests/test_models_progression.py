from models.keys import UserKey
from models.levels import Level
from models.users import User
from config.settings import settings


async def test_invited_by_and_last_key_drop_level_default(db_session):
    inviter = User(guild_id=settings.guild_id, user_id=5001, username="Inviter")
    invitee = User(guild_id=settings.guild_id, user_id=5002, username="Invitee", invited_by_guild_id=settings.guild_id, invited_by_user_id=5001)
    db_session.add_all([inviter, invitee])
    await db_session.flush()

    level = Level(guild_id=settings.guild_id, user_id=invitee.user_id, xp=0, level=0, prestige=0)
    db_session.add(level)
    await db_session.commit()

    fetched_invitee = await db_session.get(User, (settings.guild_id, 5002))
    fetched_level = await db_session.get(Level, (settings.guild_id, 5002))
    assert fetched_invitee.invited_by_user_id == 5001
    assert fetched_level.last_key_drop_level == 0


async def test_user_key_roundtrip(db_session):
    user = User(guild_id=settings.guild_id, user_id=5003, username="KeyHolder")
    db_session.add(user)
    await db_session.flush()

    key = UserKey(guild_id=settings.guild_id, user_id=user.user_id, rarity="rare", count=1)
    db_session.add(key)
    await db_session.commit()

    fetched = await db_session.get(UserKey, key.id)
    assert fetched.rarity == "rare"
    assert fetched.count == 1
