from models.users import User
from services.keys import add_key, get_key_count, roll_key_rarity, should_drop_key, upgrade_key
from config.settings import settings


class FixedRng:
    def __init__(self, uniform_value=None, random_value=None):
        self.uniform_value = uniform_value
        self.random_value = random_value

    def uniform(self, low, high):
        return self.uniform_value

    def random(self):
        return self.random_value


def test_roll_key_rarity_boundaries():
    assert roll_key_rarity(rng=FixedRng(uniform_value=10.0)) == "commun"
    assert roll_key_rarity(rng=FixedRng(uniform_value=70.0)) == "rare"
    assert roll_key_rarity(rng=FixedRng(uniform_value=90.0)) == "epique"
    assert roll_key_rarity(rng=FixedRng(uniform_value=96.0)) == "legendaire"
    assert roll_key_rarity(rng=FixedRng(uniform_value=98.6)) == "mythique"
    assert roll_key_rarity(rng=FixedRng(uniform_value=99.9)) == "divin"


def test_should_drop_key_only_fires_on_known_thresholds():
    assert should_drop_key(1, rng=FixedRng(random_value=0.0)) is False
    assert should_drop_key(7, rng=FixedRng(random_value=0.0)) is False


def test_should_drop_key_respects_chance_table():
    assert should_drop_key(5, rng=FixedRng(random_value=0.10)) is True
    assert should_drop_key(5, rng=FixedRng(random_value=0.20)) is False
    assert should_drop_key(25, rng=FixedRng(random_value=0.999)) is True


async def test_add_key_creates_then_increments(db_session):
    user = User(guild_id=settings.guild_id, user_id=6001, username="Keyed")
    db_session.add(user)
    await db_session.flush()

    await add_key(db_session, settings.guild_id, user.user_id, "rare")
    await add_key(db_session, settings.guild_id, user.user_id, "rare")
    await db_session.commit()

    from sqlalchemy import select
    from models.keys import UserKey

    result = await db_session.execute(
        select(UserKey).where(UserKey.user_id == user.user_id, UserKey.rarity == "rare")
    )
    fetched = result.scalar_one()
    assert fetched.count == 2


async def test_upgrade_key_with_explicit_rarity_consumes_one_and_grants_the_next_tier(db_session):
    user = User(guild_id=settings.guild_id, user_id=6002, username="Upgrader")
    db_session.add(user)
    await db_session.flush()
    await add_key(db_session, settings.guild_id, user.user_id, "rare")
    await db_session.commit()

    new_rarity = await upgrade_key(db_session, settings.guild_id, user.user_id, from_rarity="rare")
    await db_session.commit()

    assert new_rarity == "epique"
    assert await get_key_count(db_session, settings.guild_id, user.user_id, "rare") == 0
    assert await get_key_count(db_session, settings.guild_id, user.user_id, "epique") == 1


async def test_upgrade_key_returns_none_when_none_owned(db_session):
    user = User(guild_id=settings.guild_id, user_id=6003, username="Empty")
    db_session.add(user)
    await db_session.flush()
    await db_session.commit()

    new_rarity = await upgrade_key(db_session, settings.guild_id, user.user_id, from_rarity="commun")

    assert new_rarity is None


async def test_upgrade_key_returns_none_at_the_top_tier(db_session):
    user = User(guild_id=settings.guild_id, user_id=6004, username="Maxed")
    db_session.add(user)
    await db_session.flush()
    await add_key(db_session, settings.guild_id, user.user_id, "divin")
    await db_session.commit()

    new_rarity = await upgrade_key(db_session, settings.guild_id, user.user_id, from_rarity="divin")

    assert new_rarity is None
    assert await get_key_count(db_session, settings.guild_id, user.user_id, "divin") == 1  # untouched


async def test_upgrade_key_without_rarity_picks_among_owned_keys(db_session):
    user = User(guild_id=settings.guild_id, user_id=6005, username="RandomUpgrader")
    db_session.add(user)
    await db_session.flush()
    await add_key(db_session, settings.guild_id, user.user_id, "epique")
    await db_session.commit()

    class FixedChoiceRng:
        def choice(self, seq):
            return seq[0]

    new_rarity = await upgrade_key(db_session, settings.guild_id, user.user_id, rng=FixedChoiceRng())

    assert new_rarity == "legendaire"
    assert await get_key_count(db_session, settings.guild_id, user.user_id, "epique") == 0
