from services.rpg.classes import CharacterClass, apply_class
from services.rpg.player import PlayerState
from services.rpg.traits import Trait, apply_trait, random_trait

BASE_HP = 100
BASE_ATK = 10
BASE_DEFENSE = 5


def create_player(character_class: CharacterClass, rng, tower_level: int = 1) -> tuple[PlayerState, Trait]:
    """Crée un joueur pour une run : stats de base, puis trait aléatoire
    (pondéré par rareté, gated par le niveau de Tour) et classe choisie."""
    player = PlayerState(hp=BASE_HP, max_hp=BASE_HP, atk=BASE_ATK, defense=BASE_DEFENSE)
    trait = random_trait(rng, tower_level=tower_level)
    apply_trait(player, trait)
    apply_class(player, character_class)
    return player, trait
