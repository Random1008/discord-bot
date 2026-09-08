from config.settings import settings
from models.users import User
import services.rpg_db as db


async def _make_user(session, guild_id, user_id, name="Player"):
    user = User(guild_id=guild_id, user_id=user_id, username=name)
    session.add(user)
    await session.flush()
    return user


async def test_get_player_stats_defaults_to_zero(db_session):
    await _make_user(db_session, settings.guild_id, 60001)

    stats = await db.get_player_stats(db_session, settings.guild_id, 60001)

    assert stats.floor_reached_max == 0
    assert stats.monsters_killed == 0


async def test_increment_player_stat_accumulates(db_session):
    await _make_user(db_session, settings.guild_id, 60002)

    await db.increment_player_stat(db_session, settings.guild_id, 60002, "monsters_killed", 3)
    await db.increment_player_stat(db_session, settings.guild_id, 60002, "monsters_killed", 2)
    await db_session.commit()

    stats = await db.get_player_stats(db_session, settings.guild_id, 60002)
    assert stats.monsters_killed == 5


async def test_increment_player_stat_rejects_unknown_field(db_session):
    await _make_user(db_session, settings.guild_id, 60003)

    import pytest

    with pytest.raises(ValueError):
        await db.increment_player_stat(db_session, settings.guild_id, 60003, "not_a_field")


async def test_update_floor_reached_max_only_increases(db_session):
    await _make_user(db_session, settings.guild_id, 60004)

    await db.update_floor_reached_max(db_session, settings.guild_id, 60004, 10)
    await db.update_floor_reached_max(db_session, settings.guild_id, 60004, 5)
    await db_session.commit()

    stats = await db.get_player_stats(db_session, settings.guild_id, 60004)
    assert stats.floor_reached_max == 10


async def test_admin_set_floor_reached_max_can_decrease_the_value(db_session):
    await _make_user(db_session, settings.guild_id, 60006)
    await db.update_floor_reached_max(db_session, settings.guild_id, 60006, 40)
    await db_session.commit()

    new_floor = await db.admin_set_floor_reached_max(db_session, settings.guild_id, 60006, 5)
    await db_session.commit()

    assert new_floor == 5
    stats = await db.get_player_stats(db_session, settings.guild_id, 60006)
    assert stats.floor_reached_max == 5


async def test_admin_set_floor_reached_max_floors_at_zero(db_session):
    await _make_user(db_session, settings.guild_id, 60007)

    new_floor = await db.admin_set_floor_reached_max(db_session, settings.guild_id, 60007, -3)
    await db_session.commit()

    assert new_floor == 0


async def test_admin_adjust_floor_reached_max_adds_and_subtracts(db_session):
    await _make_user(db_session, settings.guild_id, 60008)
    await db.admin_set_floor_reached_max(db_session, settings.guild_id, 60008, 10)
    await db_session.commit()

    after_add = await db.admin_adjust_floor_reached_max(db_session, settings.guild_id, 60008, 5)
    await db_session.commit()
    assert after_add == 15

    after_remove = await db.admin_adjust_floor_reached_max(db_session, settings.guild_id, 60008, -20)
    await db_session.commit()
    assert after_remove == 0  # floored at 0, never negative


async def test_record_death_and_get_legacy(db_session):
    await _make_user(db_session, settings.guild_id, 60005)

    await db.record_death(db_session, settings.guild_id, 60005, floor_reached=12, monsters_killed=7, gold_earned=99)
    await db_session.commit()

    legacy = await db.get_legacy(db_session, settings.guild_id, 60005)
    assert len(legacy.history) == 1
    assert legacy.history[0].floor_reached == 12


async def test_record_codex_visit_returns_incremented_count(db_session):
    await _make_user(db_session, settings.guild_id, 60006)

    first = await db.record_codex_visit(db_session, settings.guild_id, 60006, "salle_des_murmures")
    second = await db.record_codex_visit(db_session, settings.guild_id, 60006, "salle_des_murmures")
    await db_session.commit()

    assert first == 1
    assert second == 2


async def test_get_all_codex_visits_excludes_event_keys(db_session):
    await _make_user(db_session, settings.guild_id, 60007)

    await db.record_codex_visit(db_session, settings.guild_id, 60007, "salle_des_murmures")
    await db.record_codex_visit(db_session, settings.guild_id, 60007, "event:autel_ancien")
    await db_session.commit()

    visits = await db.get_all_codex_visits(db_session, settings.guild_id, 60007)
    assert visits == {"salle_des_murmures": 1}


async def test_unlock_achievement_is_idempotent(db_session):
    await _make_user(db_session, settings.guild_id, 60008)

    first = await db.unlock_achievement(db_session, settings.guild_id, 60008, "etage_10")
    second = await db.unlock_achievement(db_session, settings.guild_id, 60008, "etage_10")
    await db_session.commit()

    assert first is True
    assert second is False
    assert await db.get_unlocked_achievements(db_session, settings.guild_id, 60008) == {"etage_10"}


async def test_ng_plus_defaults_to_zero_and_can_be_set(db_session):
    await _make_user(db_session, settings.guild_id, 60009)

    assert await db.get_ng_plus(db_session, settings.guild_id, 60009) == 0

    await db.set_ng_plus(db_session, settings.guild_id, 60009, 2)
    await db_session.commit()

    assert await db.get_ng_plus(db_session, settings.guild_id, 60009) == 2


async def test_or_balance_add_and_spend(db_session):
    await _make_user(db_session, settings.guild_id, 60010)

    await db.add_or_balance(db_session, settings.guild_id, 60010, 500)
    await db_session.commit()
    assert await db.get_or_balance(db_session, settings.guild_id, 60010) == 500

    ok, balance = await db.spend_or_balance(db_session, settings.guild_id, 60010, 200)
    await db_session.commit()
    assert ok is True
    assert balance == 300


async def test_spend_or_balance_rejects_insufficient_funds(db_session):
    await _make_user(db_session, settings.guild_id, 60011)
    await db.add_or_balance(db_session, settings.guild_id, 60011, 50)
    await db_session.commit()

    ok, balance = await db.spend_or_balance(db_session, settings.guild_id, 60011, 100)

    assert ok is False
    assert balance == 50


async def test_convert_or_to_credits_moves_balance(db_session):
    from models.economy import Economy

    await _make_user(db_session, settings.guild_id, 60012)
    await db.add_or_balance(db_session, settings.guild_id, 60012, 400)
    await db_session.commit()

    success, reason = await db.convert_or_to_credits(db_session, settings.guild_id, 60012, 150)
    await db_session.commit()

    assert success is True
    assert reason == "ok"
    assert await db.get_or_balance(db_session, settings.guild_id, 60012) == 250
    economy = await db_session.get(Economy, (settings.guild_id, 60012))
    assert economy.balance == 150


async def test_convert_or_to_credits_rejects_non_positive_amount(db_session):
    await _make_user(db_session, settings.guild_id, 60013)

    success, reason = await db.convert_or_to_credits(db_session, settings.guild_id, 60013, 0)

    assert success is False
    assert reason == "invalid_amount"


async def test_or_balance_is_isolated_per_guild(db_session):
    other_guild_id = settings.guild_id + 1
    await _make_user(db_session, settings.guild_id, 60014)
    await _make_user(db_session, other_guild_id, 60014)

    await db.add_or_balance(db_session, settings.guild_id, 60014, 300)
    await db_session.commit()

    assert await db.get_or_balance(db_session, settings.guild_id, 60014) == 300
    assert await db.get_or_balance(db_session, other_guild_id, 60014) == 0


async def test_player_stats_are_isolated_per_guild(db_session):
    other_guild_id = settings.guild_id + 1
    await _make_user(db_session, settings.guild_id, 60015)
    await _make_user(db_session, other_guild_id, 60015)

    await db.increment_player_stat(db_session, settings.guild_id, 60015, "monsters_killed", 10)
    await db_session.commit()

    stats_here = await db.get_player_stats(db_session, settings.guild_id, 60015)
    stats_other = await db.get_player_stats(db_session, other_guild_id, 60015)
    assert stats_here.monsters_killed == 10
    assert stats_other.monsters_killed == 0
