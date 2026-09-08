from models.badges import Badge, UserBadge
from models.users import User
from config.settings import settings


async def test_badge_and_user_badge_roundtrip(db_session):
    user = User(guild_id=settings.guild_id, user_id=2002, username="Wren")
    badge = Badge(key="debutant", name="Débutant", description="Niveau 1 atteint", icon="🔰", rarity="commun")
    db_session.add_all([user, badge])
    await db_session.flush()

    user_badge = UserBadge(guild_id=settings.guild_id, user_id=user.user_id, badge_id=badge.id)
    db_session.add(user_badge)
    await db_session.commit()

    fetched = await db_session.get(
        UserBadge, {"guild_id": settings.guild_id, "user_id": user.user_id, "badge_id": badge.id}
    )
    assert fetched is not None
    assert fetched.earned_at is not None
