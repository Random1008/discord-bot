from datetime import datetime, timedelta, timezone

from models.badges import Badge, UserBadge
from models.levels import Level
from models.stats import MessageStat, VoiceStat
from models.users import User
from services.classement_badges import sweep_classement_badges
from config.settings import settings


async def _seed_badges(db_session):
    db_session.add_all(
        [
            Badge(key="roi_du_chat", name="Roi du Chat", description="d", icon="💬", rarity="epique"),
            Badge(key="maitre_vocal", name="Maître Vocal", description="d", icon="🎙️", rarity="epique"),
            Badge(key="top_10", name="Top 10", description="d", icon="🔟", rarity="rare"),
            Badge(key="ancien", name="Ancien", description="d", icon="⏳", rarity="epique"),
        ]
    )
    await db_session.commit()


async def test_sweep_grants_roi_du_chat_to_message_leader(db_session):
    await _seed_badges(db_session)
    now = datetime(2026, 7, 21, tzinfo=timezone.utc)
    db_session.add(User(guild_id=settings.guild_id, user_id=31001, username="Chatty", created_at=now))
    await db_session.flush()
    db_session.add(MessageStat(guild_id=settings.guild_id, user_id=31001, date=now.date(), count=100))
    await db_session.commit()

    outcomes = await sweep_classement_badges(db_session, settings.guild_id, now)
    await db_session.commit()

    assert any(user_id == 31001 and outcome.reward_value == "roi_du_chat" for user_id, outcome in outcomes)

    from sqlalchemy import select

    result = await db_session.execute(select(UserBadge).where(UserBadge.user_id == 31001))
    badge_ids = {row.badge_id for row in result.scalars().all()}
    badge_result = await db_session.execute(select(Badge).where(Badge.key == "roi_du_chat"))
    assert badge_result.scalar_one().id in badge_ids


async def test_sweep_grants_maitre_vocal_to_voice_leader(db_session):
    await _seed_badges(db_session)
    now = datetime(2026, 7, 21, tzinfo=timezone.utc)
    db_session.add(User(guild_id=settings.guild_id, user_id=31002, username="Talker", created_at=now))
    await db_session.flush()
    db_session.add(VoiceStat(guild_id=settings.guild_id, user_id=31002, date=now.date(), seconds=3600))
    await db_session.commit()

    outcomes = await sweep_classement_badges(db_session, settings.guild_id, now)
    await db_session.commit()

    assert any(user_id == 31002 and outcome.reward_value == "maitre_vocal" for user_id, outcome in outcomes)


async def test_sweep_grants_top_10_to_everyone_in_xp_top_ten(db_session):
    await _seed_badges(db_session)
    now = datetime(2026, 7, 21, tzinfo=timezone.utc)
    users = [User(guild_id=settings.guild_id, user_id=31100 + i, username=f"U{i}", created_at=now) for i in range(12)]
    db_session.add_all(users)
    await db_session.flush()
    db_session.add_all([Level(guild_id=settings.guild_id, user_id=31100 + i, xp=i * 100, level=0, prestige=0) for i in range(12)])
    await db_session.commit()

    outcomes = await sweep_classement_badges(db_session, settings.guild_id, now)
    await db_session.commit()

    top_10_grantees = {user_id for user_id, outcome in outcomes if outcome.reward_value == "top_10"}
    assert len(top_10_grantees) == 10
    assert 31100 not in top_10_grantees  # lowest XP, rank 12, not in top 10
    assert 31101 not in top_10_grantees  # rank 11, not in top 10


async def test_sweep_grants_ancien_to_tenured_users_only(db_session):
    await _seed_badges(db_session)
    now = datetime(2026, 7, 21, tzinfo=timezone.utc)
    db_session.add_all(
        [
            User(guild_id=settings.guild_id, user_id=31003, username="OldTimer", created_at=now - timedelta(days=400)),
            User(guild_id=settings.guild_id, user_id=31004, username="Newbie", created_at=now - timedelta(days=10)),
        ]
    )
    await db_session.commit()

    outcomes = await sweep_classement_badges(db_session, settings.guild_id, now)
    await db_session.commit()

    ancien_grantees = {user_id for user_id, outcome in outcomes if outcome.reward_value == "ancien"}
    assert ancien_grantees == {31003}


async def test_sweep_does_not_re_announce_already_held_badges(db_session):
    await _seed_badges(db_session)
    now = datetime(2026, 7, 21, tzinfo=timezone.utc)
    db_session.add(User(guild_id=settings.guild_id, user_id=31005, username="Chatty2", created_at=now))
    await db_session.flush()
    db_session.add(MessageStat(guild_id=settings.guild_id, user_id=31005, date=now.date(), count=100))
    await db_session.commit()

    first_outcomes = await sweep_classement_badges(db_session, settings.guild_id, now)
    await db_session.commit()
    assert any(user_id == 31005 for user_id, _ in first_outcomes)

    second_outcomes = await sweep_classement_badges(db_session, settings.guild_id, now)
    await db_session.commit()
    assert not any(user_id == 31005 for user_id, _ in second_outcomes)
