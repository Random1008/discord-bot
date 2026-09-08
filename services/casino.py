import random

from models.casino import CasinoJackpot, CasinoStats

SYMBOLS = ["🍒", "🍊", "🍋", "💎", "7️⃣"]
WEIGHTS = [35, 30, 25, 7, 3]

ROULETTE_RED_NUMBERS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}

BLACKJACK_CARD_VALUES = [2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 10, 10, 11]
BLACKJACK_DEALER_STOP = 17
JACKPOT_WIN_CHANCE = 0.01

RANKS = list(range(2, 15))
SUITS = ["♠", "♥", "♦", "♣"]

POKER_PAYTABLE = {
    "quinte_flush_royale": 250,
    "quinte_flush": 50,
    "carre": 25,
    "full": 9,
    "couleur": 6,
    "quinte": 4,
    "brelan": 3,
    "deux_paires": 2,
    "paire_valets_ou_mieux": 1,
    "rien": 0,
}


def calc_slots(s1: str, s2: str, s3: str, mise: int) -> tuple[int, str]:
    if s1 == s2 == s3:
        if s1 == "7️⃣":
            return mise * 15, "JACKPOT x15 !"
        if s1 == "💎":
            return mise * 10, "Diamant x10 !"
        return mise * 5, "Triple x5 !"
    if s1 == s2 or s2 == s3 or s1 == s3:
        return mise * 2, "Deux identiques — x2 !"
    return 0, "Rien..."


def calc_dice(guess: int, rolled: int, mise: int) -> tuple[int, str]:
    if guess == rolled:
        return mise * 5, f"Le dé tombe sur {rolled} — deviné !"
    return 0, f"Le dé tombe sur {rolled} — perdu."


def roulette_color(number: int) -> str:
    if number == 0:
        return "vert"
    return "rouge" if number in ROULETTE_RED_NUMBERS else "noir"


def calc_roulette(color_guess: str, rolled_number: int, mise: int) -> tuple[int, str]:
    color = roulette_color(rolled_number)
    if color_guess != color:
        return 0, f"La bille tombe sur {rolled_number} ({color}) — perdu."
    payout = mise * 14 if color == "vert" else mise * 2
    return payout, f"La bille tombe sur {rolled_number} ({color}) — gagné !"


def draw_card(rng: random.Random) -> int:
    return rng.choice(BLACKJACK_CARD_VALUES)


def blackjack_hand_value(cards: list[int]) -> int:
    total = sum(cards)
    aces = cards.count(11)
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    return total


def calc_blackjack_outcome(player_total: int, dealer_total: int) -> tuple[float, str]:
    if player_total > 21:
        return 0.0, "Tu dépasses 21 — perdu."
    if dealer_total > 21:
        return 2.0, "Le croupier dépasse 21 — tu gagnes !"
    if player_total > dealer_total:
        return 2.0, "Tu gagnes !"
    if player_total == dealer_total:
        return 1.0, "Égalité — mise remboursée."
    return 0.0, "Le croupier gagne."


def roll_highlow_card(rng: random.Random) -> int:
    return rng.randint(1, 13)


def calc_highlow(first_card: int, guess: str, next_card: int, mise: int) -> tuple[int, str]:
    if guess == "plus" and first_card == 13:
        return 0, "13 ne peut pas être dépassé — perdu automatiquement."
    if guess == "moins" and first_card == 1:
        return 0, "1 ne peut pas être plus bas — perdu automatiquement."
    if next_card == first_card:
        return 0, f"Carte suivante : {next_card} — égalité, perdu."
    won = (next_card > first_card) if guess == "plus" else (next_card < first_card)
    if won:
        return mise * 2, f"Carte suivante : {next_card} — deviné !"
    return 0, f"Carte suivante : {next_card} — perdu."


def draw_poker_hand(rng: random.Random) -> list[tuple[int, str]]:
    deck = [(r, s) for r in RANKS for s in SUITS]
    return rng.sample(deck, 5)


def evaluate_poker_hand(cards: list[tuple[int, str]]) -> str:
    ranks = sorted(r for r, s in cards)
    suits = [s for r, s in cards]
    rank_counts: dict[int, int] = {}
    for r in ranks:
        rank_counts[r] = rank_counts.get(r, 0) + 1
    counts = sorted(rank_counts.values(), reverse=True)
    is_flush = len(set(suits)) == 1
    is_straight = ranks == list(range(ranks[0], ranks[0] + 5)) or ranks == [2, 3, 4, 5, 14]

    if is_straight and is_flush and ranks[0] == 10:
        return "quinte_flush_royale"
    if is_straight and is_flush:
        return "quinte_flush"
    if counts == [4, 1]:
        return "carre"
    if counts == [3, 2]:
        return "full"
    if is_flush:
        return "couleur"
    if is_straight:
        return "quinte"
    if counts == [3, 1, 1]:
        return "brelan"
    if counts == [2, 2, 1]:
        return "deux_paires"
    if counts == [2, 1, 1, 1]:
        pair_rank = [r for r, c in rank_counts.items() if c == 2][0]
        if pair_rank >= 11:
            return "paire_valets_ou_mieux"
        return "rien"
    return "rien"


def calc_poker(hand_category: str, mise: int) -> tuple[int, str]:
    multiplier = POKER_PAYTABLE[hand_category]
    if multiplier == 0:
        return 0, "Main perdante."
    return mise * multiplier, f"Main : {hand_category.replace('_', ' ')} — x{multiplier} !"


WHEEL_MULTIPLIERS = [0, 0, 0, 2, 2, 3, 5, 10]


def calc_wheel(rng: random.Random, mise: int) -> tuple[int, str]:
    """Roue de la Fortune : la roue s'arrête sur un secteur multiplicateur."""
    multiplier = rng.choice(WHEEL_MULTIPLIERS)
    if multiplier == 0:
        return 0, "La roue s'arrête sur un secteur perdant — rien."
    return mise * multiplier, f"La roue s'arrête sur un secteur **x{multiplier}** !"


def roll_craps_dice(rng: random.Random) -> tuple[int, int]:
    return rng.randint(1, 6), rng.randint(1, 6)


def calc_craps(d1: int, d2: int, guess: str, mise: int) -> tuple[int, str]:
    """Craps simplifié : parie que la somme des deux dés est 7, plus que 7 ou moins que 7."""
    total = d1 + d2
    if guess == "sept":
        if total == 7:
            return mise * 4, f"Dés : {d1}+{d2} = **7** — sept deviné !"
        return 0, f"Dés : {d1}+{d2} = {total} — perdu."
    if guess == "plus":
        if total > 7:
            return mise * 2, f"Dés : {d1}+{d2} = {total} (plus que 7) — gagné !"
        return 0, f"Dés : {d1}+{d2} = {total} — perdu."
    if guess == "moins":
        if total < 7:
            return mise * 2, f"Dés : {d1}+{d2} = {total} (moins que 7) — gagné !"
        return 0, f"Dés : {d1}+{d2} = {total} — perdu."
    return 0, "Pari invalide."


async def record_casino_result(
    session, guild_id: int, user_id: int, wagered: int, won: int, is_win: bool, is_jackpot: bool
) -> None:
    row = await session.get(CasinoStats, (guild_id, user_id))
    if row is None:
        row = CasinoStats(guild_id=guild_id, user_id=user_id)
        session.add(row)
        await session.flush()
    row.total_wagered += wagered
    row.total_won += won
    row.wins_count += 1 if is_win else 0
    row.jackpots_won += 1 if is_jackpot else 0
    await session.flush()


async def get_casino_stats(session, guild_id: int, user_id: int) -> dict:
    row = await session.get(CasinoStats, (guild_id, user_id))
    if row is None:
        return {"total_wagered": 0, "total_won": 0, "wins_count": 0, "jackpots_won": 0}
    return {
        "total_wagered": row.total_wagered,
        "total_won": row.total_won,
        "wins_count": row.wins_count,
        "jackpots_won": row.jackpots_won,
    }


async def get_jackpot_pool(session, guild_id: int) -> int:
    row = await session.get(CasinoJackpot, guild_id)
    return row.pool if row is not None else 0


async def add_to_jackpot(session, guild_id: int, amount: int) -> int:
    row = await session.get(CasinoJackpot, guild_id)
    if row is None:
        row = CasinoJackpot(guild_id=guild_id, pool=amount)
        session.add(row)
    else:
        row.pool += amount
    await session.flush()
    return row.pool


async def reset_jackpot(session, guild_id: int) -> None:
    row = await session.get(CasinoJackpot, guild_id)
    if row is None:
        row = CasinoJackpot(guild_id=guild_id, pool=0)
        session.add(row)
    else:
        row.pool = 0
    await session.flush()
