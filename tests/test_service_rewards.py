import random

from models.badges import Badge
from models.rewards import Reward
from models.users import User
from services.rewards import get_role_reward_thresholds, grant_reward
from config.settings import settings


class FixedRng(random.Random):
    def uniform(self, low, high):
        return 10.0  # always rolls "commun"


async def test_grant_badge_reward_inserts_user_badge(db_session):
    user = User(guild_id=settings.guild_id, user_id=9001, username="Badged")
    badge = Badge(key="debutant", name="Débutant", description="d", icon="🔰", rarity="commun")
    db_session.add_all([user, badge])
    await db_session.flush()

    reward = Reward(level=1, reward_type="badge", reward_value="debutant")
    db_session.add(reward)
    await db_session.flush()

    outcome = await grant_reward(db_session, settings.guild_id, user.user_id, reward)
    await db_session.commit()

    assert outcome.reward_type == "badge"
    assert outcome.reward_value == "debutant"

    from sqlalchemy import select
    from models.badges import UserBadge

    result = await db_session.execute(
        select(UserBadge).where(UserBadge.user_id == user.user_id, UserBadge.badge_id == badge.id)
    )
    assert result.scalar_one_or_none() is not None


async def test_grant_badge_reward_is_idempotent(db_session):
    user = User(guild_id=settings.guild_id, user_id=9002, username="BadgedTwice")
    badge = Badge(key="actif", name="Actif", description="d", icon="⭐", rarity="commun")
    db_session.add_all([user, badge])
    await db_session.flush()

    reward = Reward(level=5, reward_type="badge", reward_value="actif")
    db_session.add(reward)
    await db_session.flush()

    await grant_reward(db_session, settings.guild_id, user.user_id, reward)
    await grant_reward(db_session, settings.guild_id, user.user_id, reward)
    await db_session.commit()

    from sqlalchemy import select
    from models.badges import UserBadge

    result = await db_session.execute(
        select(UserBadge).where(UserBadge.user_id == user.user_id, UserBadge.badge_id == badge.id)
    )
    assert len(result.scalars().all()) == 1


async def test_grant_coins_reward_credits_economy(db_session):
    user = User(guild_id=settings.guild_id, user_id=9003, username="Coined")
    db_session.add(user)
    await db_session.flush()

    reward = Reward(level=10, reward_type="coins", reward_value="1000")
    db_session.add(reward)
    await db_session.flush()

    outcome = await grant_reward(db_session, settings.guild_id, user.user_id, reward)
    await db_session.commit()

    from models.economy import Economy

    economy = await db_session.get(Economy, (settings.guild_id, user.user_id))
    assert economy.balance == 1000
    assert outcome.detail == "1000 coins"


async def test_grant_item_reward_grants_a_key(db_session):
    user = User(guild_id=settings.guild_id, user_id=9004, username="Chested")
    db_session.add(user)
    await db_session.flush()

    reward = Reward(level=90, reward_type="item", reward_value="coffre_mystere")
    db_session.add(reward)
    await db_session.flush()

    outcome = await grant_reward(db_session, settings.guild_id, user.user_id, reward, rng=FixedRng())
    await db_session.commit()

    from sqlalchemy import select
    from models.keys import UserKey

    result = await db_session.execute(
        select(UserKey).where(UserKey.user_id == user.user_id, UserKey.rarity == "commun")
    )
    assert result.scalar_one().count == 1
    assert outcome.reward_type == "item"


async def test_grant_role_reward_has_no_db_side_effect(db_session):
    user = User(guild_id=settings.guild_id, user_id=9005, username="RoleWaiting")
    db_session.add(user)
    await db_session.flush()

    reward = Reward(level=5, reward_type="role", reward_value="role_actif")
    db_session.add(reward)
    await db_session.flush()

    outcome = await grant_reward(db_session, settings.guild_id, user.user_id, reward)

    assert outcome.reward_type == "role"
    assert outcome.reward_value == "role_actif"


async def test_get_role_reward_thresholds_includes_role_and_access_only(db_session):
    db_session.add_all(
        [
            Reward(level=5, reward_type="role", reward_value="role_actif"),
            Reward(level=60, reward_type="access", reward_value="vip_argent"),
            Reward(level=1, reward_type="badge", reward_value="debutant"),
            Reward(level=25, reward_type="coins", reward_value="2500"),
        ]
    )
    await db_session.commit()

    thresholds = await get_role_reward_thresholds(db_session)

    assert thresholds == {"role_actif": 5, "vip_argent": 60}
