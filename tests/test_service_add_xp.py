from models.levels import Level
from models.rewards import Reward
from models.users import User
from services.leveling import add_xp, get_all_levels, subtract_xp
from config.settings import settings


async def test_add_xp_grants_inviteur_badge_to_inviter_on_invite_validation(db_session):
    import services.leveling as leveling_module
    from sqlalchemy import select

    from models.badges import Badge, UserBadge

    inviter = User(guild_id=settings.guild_id, user_id=10101, username="Inviter")
    invitee = User(guild_id=settings.guild_id, user_id=10102, username="Invitee", invited_by_guild_id=settings.guild_id, invited_by_user_id=10101)
    db_session.add_all([inviter, invitee])
    await db_session.flush()

    badge = Badge(key="inviteur", name="Inviteur", description="d", icon="📨", rarity="rare")
    db_session.add(badge)
    await db_session.flush()

    result = await add_xp(db_session, settings.guild_id, invitee.user_id, leveling_module.xp_for_level(5))
    await db_session.commit()

    assert result.inviter_bonus is not None
    assert result.inviter_bonus.user_id == 10101
    assert any(o.reward_type == "badge" and o.reward_value == "inviteur" for o in result.inviter_bonus.reward_outcomes)

    badge_row = await db_session.execute(
        select(UserBadge).where(UserBadge.user_id == 10101, UserBadge.badge_id == badge.id)
    )
    assert badge_row.scalar_one_or_none() is not None


async def test_add_xp_creates_level_row_and_awards_xp(db_session):
    user = User(guild_id=settings.guild_id, user_id=10001, username="Fresh")
    db_session.add(user)
    await db_session.flush()

    result = await add_xp(db_session, settings.guild_id, user.user_id, 50)
    await db_session.commit()

    assert result.xp == 50
    assert result.level == 0
    assert result.levels_gained == []


async def test_add_xp_crosses_multiple_levels_and_grants_each_rewards(db_session):
    user = User(guild_id=settings.guild_id, user_id=10002, username="Jumper")
    db_session.add(user)
    await db_session.flush()

    db_session.add_all(
        [
            Reward(level=1, reward_type="coins", reward_value="10"),
            Reward(level=2, reward_type="coins", reward_value="20"),
        ]
    )
    await db_session.flush()

    result = await add_xp(db_session, settings.guild_id, user.user_id, 400)  # crosses level 1 and 2
    await db_session.commit()

    assert result.level == 2
    assert result.levels_gained == [1, 2]
    assert [o.detail for o in result.reward_outcomes] == ["10 coins", "20 coins"]


async def test_add_xp_never_lowers_stored_level(db_session):
    from models.levels import Level

    user = User(guild_id=settings.guild_id, user_id=10003, username="Veteran")
    db_session.add(user)
    await db_session.flush()
    db_session.add(Level(guild_id=settings.guild_id, user_id=user.user_id, xp=10000, level=10, prestige=0))
    await db_session.flush()

    result = await add_xp(db_session, settings.guild_id, user.user_id, 1)
    await db_session.commit()

    assert result.level == 10
    assert result.levels_gained == []


async def test_add_xp_applies_prestige_multiplier(db_session):
    from models.levels import Level

    user = User(guild_id=settings.guild_id, user_id=10004, username="Prestiged")
    db_session.add(user)
    await db_session.flush()
    db_session.add(Level(guild_id=settings.guild_id, user_id=user.user_id, xp=0, level=0, prestige=1))
    await db_session.flush()

    result = await add_xp(db_session, settings.guild_id, user.user_id, 100)
    await db_session.commit()
    assert result.xp == 110  # +10% prestige I multiplier


async def test_add_xp_applies_active_xp_boost(db_session):
    from services.effects import grant_effect

    user = User(guild_id=settings.guild_id, user_id=10009, username="Boosted")
    db_session.add(user)
    await db_session.flush()
    await grant_effect(db_session, settings.guild_id, user.user_id, "xp_boost", magnitude=2.0, duration_seconds=900)
    await db_session.commit()

    result = await add_xp(db_session, settings.guild_id, user.user_id, 100)
    await db_session.commit()

    assert result.xp == 200


async def test_add_xp_without_active_boost_is_unaffected(db_session):
    user = User(guild_id=settings.guild_id, user_id=10010, username="Unboosted")
    db_session.add(user)
    await db_session.flush()

    result = await add_xp(db_session, settings.guild_id, user.user_id, 100)
    await db_session.commit()

    assert result.xp == 100


async def test_add_xp_detects_prestige_reached(db_session):
    from models.levels import Level

    user = User(guild_id=settings.guild_id, user_id=10005, username="AlmostHundred")
    db_session.add(user)
    await db_session.flush()
    db_session.add(Level(guild_id=settings.guild_id, user_id=user.user_id, xp=999900, level=99, prestige=0))
    await db_session.flush()

    result = await add_xp(db_session, settings.guild_id, user.user_id, 200)
    await db_session.commit()

    assert result.level == 100
    assert result.prestige_reached == 1


async def test_add_xp_triggers_key_drop_at_five_levels_elapsed(db_session):
    import services.leveling as leveling_module

    class AlwaysDrop:
        def random(self):
            return 0.0

        def uniform(self, low, high):
            return 0.0  # always "commun"

    user = User(guild_id=settings.guild_id, user_id=10006, username="Lucky")
    db_session.add(user)
    await db_session.flush()

    result = await add_xp(db_session, settings.guild_id, user.user_id, leveling_module.xp_for_level(5), rng=AlwaysDrop())
    await db_session.commit()

    assert result.key_drops == [leveling_module.KeyDrop(level=5, rarity="commun")]


async def test_subtract_xp_clamps_at_current_level_floor(db_session):
    from models.levels import Level

    user = User(guild_id=settings.guild_id, user_id=10007, username="Clamped")
    db_session.add(user)
    await db_session.flush()
    db_session.add(Level(guild_id=settings.guild_id, user_id=user.user_id, xp=100, level=1, prestige=0))
    await db_session.flush()

    new_xp = await subtract_xp(db_session, settings.guild_id, user.user_id, 50)
    await db_session.commit()

    assert new_xp == 100  # can't drop below xp_for_level(1) == 100


async def test_get_all_levels_scopes_to_guild(db_session):
    db_session.add_all(
        [
            User(guild_id=settings.guild_id, user_id=10008, username="A"),
            User(guild_id=settings.guild_id, user_id=10009, username="B"),
            User(guild_id=999999, user_id=10008, username="OtherGuildA"),
        ]
    )
    await db_session.flush()
    db_session.add_all(
        [
            Level(guild_id=settings.guild_id, user_id=10008, xp=2500, level=5, prestige=0),
            Level(guild_id=settings.guild_id, user_id=10009, xp=0, level=0, prestige=0),
            Level(guild_id=999999, user_id=10008, xp=999999, level=100, prestige=4),
        ]
    )
    await db_session.commit()

    levels = await get_all_levels(db_session, settings.guild_id)

    assert set(levels) == {(10008, 5, 0), (10009, 0, 0)}
