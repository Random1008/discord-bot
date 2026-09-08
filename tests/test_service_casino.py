import random

from config.settings import settings
from models.users import User
from services.casino import (
    add_to_jackpot,
    blackjack_hand_value,
    calc_blackjack_outcome,
    calc_craps,
    calc_dice,
    calc_highlow,
    calc_poker,
    calc_roulette,
    calc_slots,
    calc_wheel,
    draw_poker_hand,
    evaluate_poker_hand,
    get_casino_stats,
    get_jackpot_pool,
    record_casino_result,
    reset_jackpot,
    roll_craps_dice,
    roll_highlow_card,
    roulette_color,
)


def test_calc_slots_triple_seven_pays_15x():
    gain, msg = calc_slots("7️⃣", "7️⃣", "7️⃣", 100)
    assert gain == 1500
    assert "JACKPOT" in msg


def test_calc_slots_two_matching_pays_2x():
    gain, _ = calc_slots("🍒", "🍒", "🍋", 100)
    assert gain == 200


def test_calc_slots_no_match_pays_nothing():
    gain, _ = calc_slots("🍒", "🍋", "💎", 100)
    assert gain == 0


def test_calc_dice_correct_guess_pays_5x():
    gain, _ = calc_dice(3, 3, 100)
    assert gain == 500


def test_calc_dice_wrong_guess_pays_nothing():
    gain, _ = calc_dice(3, 4, 100)
    assert gain == 0


def test_roulette_color_zero_is_green():
    assert roulette_color(0) == "vert"


def test_roulette_color_red_number():
    assert roulette_color(1) == "rouge"


def test_calc_roulette_green_pays_14x():
    gain, _ = calc_roulette("vert", 0, 100)
    assert gain == 1400


def test_calc_roulette_wrong_color_pays_nothing():
    gain, _ = calc_roulette("noir", 1, 100)
    assert gain == 0


def test_blackjack_hand_value_handles_soft_ace():
    assert blackjack_hand_value([11, 9, 5]) == 15


def test_calc_blackjack_outcome_player_bust_loses():
    multiplier, _ = calc_blackjack_outcome(22, 18)
    assert multiplier == 0.0


def test_calc_blackjack_outcome_dealer_bust_pays_2x():
    multiplier, _ = calc_blackjack_outcome(20, 22)
    assert multiplier == 2.0


def test_calc_blackjack_outcome_tie_refunds():
    multiplier, _ = calc_blackjack_outcome(18, 18)
    assert multiplier == 1.0


async def test_jackpot_pool_starts_at_zero(db_session):
    pool = await get_jackpot_pool(db_session, settings.guild_id)
    assert pool == 0


async def test_add_to_jackpot_accumulates(db_session):
    await add_to_jackpot(db_session, settings.guild_id, 100)
    pool = await add_to_jackpot(db_session, settings.guild_id, 50)
    await db_session.commit()

    assert pool == 150


async def test_reset_jackpot_clears_pool(db_session):
    await add_to_jackpot(db_session, settings.guild_id, 200)
    await reset_jackpot(db_session, settings.guild_id)
    await db_session.commit()

    pool = await get_jackpot_pool(db_session, settings.guild_id)
    assert pool == 0


async def test_jackpot_is_scoped_per_guild(db_session):
    other_guild_id = settings.guild_id + 1
    await add_to_jackpot(db_session, settings.guild_id, 300)
    await db_session.commit()

    pool_other = await get_jackpot_pool(db_session, other_guild_id)
    assert pool_other == 0


def test_roll_highlow_card_within_bounds():
    rng = random.Random(1)
    for _ in range(50):
        card = roll_highlow_card(rng)
        assert 1 <= card <= 13


def test_calc_highlow_higher_guess_correct_pays_2x():
    gain, msg = calc_highlow(first_card=5, guess="plus", next_card=10, mise=100)
    assert gain == 200
    assert "deviné" in msg


def test_calc_highlow_wrong_guess_pays_nothing():
    gain, _ = calc_highlow(first_card=5, guess="plus", next_card=2, mise=100)
    assert gain == 0


def test_calc_highlow_thirteen_cannot_go_higher():
    gain, msg = calc_highlow(first_card=13, guess="plus", next_card=5, mise=100)
    assert gain == 0
    assert "13" in msg


def test_calc_highlow_one_cannot_go_lower():
    gain, msg = calc_highlow(first_card=1, guess="moins", next_card=5, mise=100)
    assert gain == 0


def test_calc_highlow_tie_loses():
    gain, msg = calc_highlow(first_card=7, guess="plus", next_card=7, mise=100)
    assert gain == 0
    assert "égalité" in msg


def test_evaluate_poker_hand_royal_flush():
    hand = [(10, "♠"), (11, "♠"), (12, "♠"), (13, "♠"), (14, "♠")]
    assert evaluate_poker_hand(hand) == "quinte_flush_royale"


def test_evaluate_poker_hand_full_house():
    hand = [(5, "♠"), (5, "♥"), (5, "♦"), (9, "♠"), (9, "♥")]
    assert evaluate_poker_hand(hand) == "full"


def test_evaluate_poker_hand_nothing():
    hand = [(2, "♠"), (5, "♥"), (9, "♦"), (11, "♣"), (13, "♠")]
    assert evaluate_poker_hand(hand) == "rien"


def test_draw_poker_hand_returns_five_unique_cards():
    hand = draw_poker_hand(random.Random(1))
    assert len(hand) == 5
    assert len(set(hand)) == 5


def test_calc_poker_pays_by_paytable():
    gain, msg = calc_poker("full", 100)
    assert gain == 900
    assert "full" in msg


def test_calc_poker_losing_hand_pays_nothing():
    gain, msg = calc_poker("rien", 100)
    assert gain == 0
    assert "perdante" in msg


def test_calc_wheel_losing_sector_pays_nothing():
    rng = random.Random(0)
    rng.choice = lambda seq: 0
    gain, msg = calc_wheel(rng, 100)
    assert gain == 0
    assert "perdant" in msg


def test_calc_wheel_winning_sector_pays_multiplier():
    rng = random.Random(0)
    rng.choice = lambda seq: 10
    gain, msg = calc_wheel(rng, 100)
    assert gain == 1000
    assert "x10" in msg


def test_roll_craps_dice_within_bounds():
    rng = random.Random(1)
    for _ in range(50):
        d1, d2 = roll_craps_dice(rng)
        assert 1 <= d1 <= 6
        assert 1 <= d2 <= 6


def test_calc_craps_seven_pays_4x():
    gain, msg = calc_craps(3, 4, "sept", 100)
    assert gain == 400
    assert "sept" in msg


def test_calc_craps_seven_loses_on_other_total():
    gain, _ = calc_craps(2, 2, "sept", 100)
    assert gain == 0


def test_calc_craps_plus_pays_2x_over_seven():
    gain, msg = calc_craps(4, 5, "plus", 100)
    assert gain == 200
    assert "plus" in msg


def test_calc_craps_moins_loses_over_seven():
    gain, _ = calc_craps(4, 5, "moins", 100)
    assert gain == 0


def test_calc_craps_invalid_guess_pays_nothing():
    gain, msg = calc_craps(3, 4, "egal", 100)
    assert gain == 0
    assert "invalide" in msg


async def test_record_casino_result_accumulates_stats(db_session):
    user = User(guild_id=settings.guild_id, user_id=80001, username="Gambler")
    db_session.add(user)
    await db_session.flush()

    await record_casino_result(db_session, settings.guild_id, 80001, wagered=100, won=200, is_win=True, is_jackpot=False)
    await record_casino_result(db_session, settings.guild_id, 80001, wagered=50, won=0, is_win=False, is_jackpot=False)
    await db_session.commit()

    stats = await get_casino_stats(db_session, settings.guild_id, 80001)
    assert stats == {"total_wagered": 150, "total_won": 200, "wins_count": 1, "jackpots_won": 0}


async def test_record_casino_result_tracks_jackpots(db_session):
    user = User(guild_id=settings.guild_id, user_id=80002, username="Lucky")
    db_session.add(user)
    await db_session.flush()

    await record_casino_result(db_session, settings.guild_id, 80002, wagered=100, won=5000, is_win=True, is_jackpot=True)
    await db_session.commit()

    stats = await get_casino_stats(db_session, settings.guild_id, 80002)
    assert stats["jackpots_won"] == 1


async def test_get_casino_stats_defaults_to_zero(db_session):
    stats = await get_casino_stats(db_session, settings.guild_id, 80003)
    assert stats == {"total_wagered": 0, "total_won": 0, "wins_count": 0, "jackpots_won": 0}


async def test_casino_stats_are_isolated_per_guild(db_session):
    other_guild_id = settings.guild_id + 1
    user_here = User(guild_id=settings.guild_id, user_id=80004, username="Traveler")
    user_there = User(guild_id=other_guild_id, user_id=80004, username="Traveler")
    db_session.add_all([user_here, user_there])
    await db_session.flush()

    await record_casino_result(db_session, settings.guild_id, 80004, wagered=100, won=0, is_win=False, is_jackpot=False)
    await db_session.commit()

    stats_other = await get_casino_stats(db_session, other_guild_id, 80004)
    assert stats_other["total_wagered"] == 0
