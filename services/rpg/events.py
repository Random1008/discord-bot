from dataclasses import dataclass
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from services.rpg.player import PlayerState


@dataclass
class Event:
    key: str
    name: str
    description: str
    # effect is None for events whose choice is handled by the Discord UI
    # (prisonnier / voix_dans_le_mur in cogs/tour.py).
    effect: Callable[["PlayerState", object], str] | None = None


def resolve_autel_ancien(player: "PlayerState", rng) -> str:
    cost = max(1, round(player.max_hp * 0.2))
    dealt = player.take_damage(cost)
    gained = rng.randint(30, 60)
    player.add_gold(gained)
    return f"Vous sacrifiez {dealt} PV sur l'autel ancien et recevez {gained} or."


def resolve_coffre_piege(player: "PlayerState", rng) -> str:
    if rng.random() < 0.6:
        gained = rng.randint(25, 45)
        player.add_gold(gained)
        return f"Le coffre était sûr : {gained} or."
    dealt = player.take_damage(rng.randint(10, 20))
    return f"Le coffre était piégé : {dealt} dégâts."


def resolve_prisonnier(player: "PlayerState", choice: bool, rng) -> str:
    if choice:
        player.atk += 5
        return "Vous libérez le prisonnier, reconnaissant, qui vous enseigne une technique (+5 ATK)."
    gained = rng.randint(20, 40)
    player.add_gold(gained)
    return f"Vous laissez le prisonnier enchaîné et fouillez sa cellule ({gained} or)."


def resolve_potion_mysterieuse(player: "PlayerState", rng) -> str:
    roll = rng.random()
    if roll < 0.4:
        healed = player.heal(25)
        return f"La potion vous soigne de {healed} PV."
    if roll < 0.7:
        player.atk += 2
        return "La potion renforce durablement votre attaque."
    dealt = player.take_damage(10)
    return f"La potion était toxique : {dealt} dégâts."


def resolve_vision(player: "PlayerState", rng) -> str:
    player.crit_chance += 0.05
    return "Une vision fugace aiguise votre instinct."


def resolve_voix_dans_le_mur(player: "PlayerState", choice: bool, rng) -> str:
    if choice:
        player.xp += 20
        return "Vous écoutez la voix murmurer un secret oublié (+20 XP)."
    gained = rng.randint(10, 20)
    player.add_gold(gained)
    return f"Vous ignorez la voix et trouvez {gained} or par terre."


EVENTS = [
    Event("autel_ancien", "Autel Ancien", "Un autel de pierre attend une offrande.", resolve_autel_ancien),
    Event("coffre_piege", "Coffre Piégé", "Un coffre suspect repose au centre de la salle.", resolve_coffre_piege),
    Event("prisonnier", "Prisonnier", "Un prisonnier enchaîné vous supplie du regard."),
    Event("potion_mysterieuse", "Potion Mystérieuse", "Une fiole d'origine inconnue brille faiblement.",
          resolve_potion_mysterieuse),
    Event("vision", "Vision", "Une vision traverse votre esprit sans prévenir.", resolve_vision),
    Event("voix_dans_le_mur", "Voix dans le Mur", "Une voix murmure depuis les pierres."),
]


def draw_event(rng) -> Event:
    return rng.choice(EVENTS)
