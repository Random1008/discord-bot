import unicodedata
import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.rpg.player import PlayerState

TREASURE_GOLD_MIN = 10
TREASURE_GOLD_MAX = 20
REPOS_HEAL_RATIO = 0.3
PIEGE_DAMAGE_MIN = 5
PIEGE_DAMAGE_MAX = 15
SALLE_MAUDITE_DAMAGE_MIN = 10
SALLE_MAUDITE_DAMAGE_MAX = 25
SALLE_MAUDITE_GOLD_MIN = 30
SALLE_MAUDITE_GOLD_MAX = 50


def resolve_treasure(player: "PlayerState", rng: random.Random) -> int:
    gained = rng.randint(TREASURE_GOLD_MIN, TREASURE_GOLD_MAX)
    player.add_gold(gained)
    return gained


def resolve_repos(player: "PlayerState") -> int:
    if player.no_potions:
        return 0
    return player.heal(round(player.max_hp * REPOS_HEAL_RATIO))


def resolve_piege(player: "PlayerState", rng: random.Random) -> int:
    amount = rng.randint(PIEGE_DAMAGE_MIN, PIEGE_DAMAGE_MAX)
    return player.take_damage(amount)


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.strip().lower()


def resolve_enigme(answer: str, correct: str) -> bool:
    return _normalize(answer) == _normalize(correct)


def resolve_casino(player: "PlayerState", bet: int, rng: random.Random) -> int:
    # A bet is a fair coin flip, not "earned" gold: the gold_multiplier
    # (meant for treasure/rewards) must not skew it positive-EV.
    if rng.random() < 0.5:
        player.add_gold(bet, apply_multiplier=False)
        return bet
    player.add_gold(-bet)
    return -bet


def resolve_salle_maudite(player: "PlayerState", rng: random.Random) -> tuple[int, int]:
    dealt = player.take_damage(rng.randint(SALLE_MAUDITE_DAMAGE_MIN, SALLE_MAUDITE_DAMAGE_MAX))
    gained = rng.randint(SALLE_MAUDITE_GOLD_MIN, SALLE_MAUDITE_GOLD_MAX)
    player.add_gold(gained)
    return dealt, gained
