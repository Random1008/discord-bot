import random

from config.settings import settings
from models.users import User
from services.invest import (
    INVEST_LOSS_CHANCE,
    INVEST_WIN_MAX_MULTIPLIER,
    INVEST_WIN_MIN_MULTIPLIER,
    MARKET_INDEX_MAX,
    MARKET_INDEX_MIN,
    calculate_return,
    get_invest_usage,
    get_market_index,
    register_invest,
    set_market_index,
    update_market_index,
)


class _FakeRng:
    def __init__(self, random_value: float, uniform_value: float = 2.0):
        self._random_value = random_value
        self._uniform_value = uniform_value

    def random(self) -> float:
        return self._random_value

    def uniform(self, a: float, b: float) -> float:
        return self._uniform_value


def test_calculate_return_loss_returns_zero():
    rng = _FakeRng(0.0)  # < 0.75 → perte
    assert calculate_return(1000, rng) == 0


def test_calculate_return_win_pays_min_multiplier():
    rng = _FakeRng(0.9, uniform_value=INVEST_WIN_MIN_MULTIPLIER)  # >= 0.75 → gain x2
    assert calculate_return(1000, rng) == 2000


def test_calculate_return_win_pays_max_multiplier():
    rng = _FakeRng(0.99, uniform_value=INVEST_WIN_MAX_MULTIPLIER)  # gain x2.5
    assert calculate_return(1000, rng) == 2500


def test_calculate_return_respects_loss_chance_boundary():
    assert INVEST_LOSS_CHANCE == 0.75
    assert calculate_return(1000, _FakeRng(0.7499)) == 0
    assert calculate_return(1000, _FakeRng(0.7501, 2.0)) > 0


def test_update_market_index_stays_within_bounds():
    rng = random.Random(7)
    index = 1.0
    for _ in range(1000):
        index = update_market_index(index, rng)
    assert MARKET_INDEX_MIN <= index <= MARKET_INDEX_MAX


async def test_get_market_index_defaults_to_one(db_session):
    index = await get_market_index(db_session, settings.guild_id)
    assert index == 1.0


async def test_set_market_index_persists_value(db_session):
    await set_market_index(db_session, settings.guild_id, 1.25)
    await db_session.commit()

    index = await get_market_index(db_session, settings.guild_id)
    assert index == 1.25


async def test_market_index_is_scoped_per_guild(db_session):
    other_guild_id = settings.guild_id + 1
    await set_market_index(db_session, settings.guild_id, 1.4)
    await db_session.commit()

    index_other = await get_market_index(db_session, other_guild_id)
    assert index_other == 1.0


async def test_invest_usage_defaults_to_zero(db_session):
    assert await get_invest_usage(db_session, settings.guild_id, 90001) == 0


async def test_register_invest_increments_today(db_session):
    db_session.add(User(guild_id=settings.guild_id, user_id=90002, username="Investor"))
    await db_session.flush()

    assert await register_invest(db_session, settings.guild_id, 90002) == 1
    assert await register_invest(db_session, settings.guild_id, 90002) == 2
    await db_session.commit()

    assert await get_invest_usage(db_session, settings.guild_id, 90002) == 2


async def test_invest_usage_is_scoped_per_guild(db_session):
    other_guild_id = settings.guild_id + 1
    db_session.add(User(guild_id=settings.guild_id, user_id=90003, username="A"))
    db_session.add(User(guild_id=other_guild_id, user_id=90003, username="A"))
    await db_session.flush()

    await register_invest(db_session, settings.guild_id, 90003)
    await db_session.commit()

    assert await get_invest_usage(db_session, settings.guild_id, 90003) == 1
    assert await get_invest_usage(db_session, other_guild_id, 90003) == 0
