from enum import Enum
from typing import TYPE_CHECKING

from services.rpg.rarity import Rarity, RARITY_WEIGHTS, UNLOCK_TOWER_LEVEL

if TYPE_CHECKING:
    from services.rpg.player import PlayerState


class CharacterClass(Enum):
    BERSERKER = "berserker"
    GARDIEN = "gardien"
    ASSASSIN = "assassin"
    MAGE_INSTABLE = "mage_instable"
    LAME_SANGUINE = "lame_sanguine"
    AVENTURIER_CHANCEUX = "aventurier_chanceux"
    OCCULTISTE = "occultiste"
    ALCHIMISTE = "alchimiste"
    PALADIN = "paladin"
    CHASSEUR = "chasseur"
    INVOCATEUR = "invocateur"
    DUELISTE = "dueliste"
    MOINE = "moine"
    NECROMANCIEN = "necromancien"
    CHRONOMANCIEN = "chronomancien"
    CHEVALIER_NOIR = "chevalier_noir"
    REVENANT = "revenant"
    GARDIEN_DU_NEANT = "gardien_du_neant"
    HERITIER_DE_LA_TOUR = "heritier_de_la_tour"
    ELU_DU_CREATEUR = "elu_du_createur"


CLASS_NAMES = {
    CharacterClass.BERSERKER: "Berserker",
    CharacterClass.GARDIEN: "Gardien",
    CharacterClass.ASSASSIN: "Assassin",
    CharacterClass.MAGE_INSTABLE: "Mage Instable",
    CharacterClass.LAME_SANGUINE: "Lame Sanguine",
    CharacterClass.AVENTURIER_CHANCEUX: "Aventurier Chanceux",
    CharacterClass.OCCULTISTE: "Occultiste",
    CharacterClass.ALCHIMISTE: "Alchimiste",
    CharacterClass.PALADIN: "Paladin",
    CharacterClass.CHASSEUR: "Chasseur",
    CharacterClass.INVOCATEUR: "Invocateur",
    CharacterClass.DUELISTE: "Dueliste",
    CharacterClass.MOINE: "Moine",
    CharacterClass.NECROMANCIEN: "Nécromancien",
    CharacterClass.CHRONOMANCIEN: "Chronomancien",
    CharacterClass.CHEVALIER_NOIR: "Chevalier Noir",
    CharacterClass.REVENANT: "Revenant",
    CharacterClass.GARDIEN_DU_NEANT: "Gardien du Néant",
    CharacterClass.HERITIER_DE_LA_TOUR: "Héritier de la Tour",
    CharacterClass.ELU_DU_CREATEUR: "Élu du Créateur",
}

# Rareté de chaque classe. Les communes/peu communes sont disponibles dès le
# départ ; les autres se débloquent avec le niveau de la Tour (UNLOCK_TOWER_LEVEL).
CLASS_RARITY = {
    CharacterClass.BERSERKER: Rarity.COMMUNE,
    CharacterClass.GARDIEN: Rarity.COMMUNE,
    CharacterClass.ASSASSIN: Rarity.COMMUNE,
    CharacterClass.MAGE_INSTABLE: Rarity.COMMUNE,
    CharacterClass.LAME_SANGUINE: Rarity.PEU_COMMUNE,
    CharacterClass.AVENTURIER_CHANCEUX: Rarity.PEU_COMMUNE,
    CharacterClass.OCCULTISTE: Rarity.PEU_COMMUNE,
    CharacterClass.ALCHIMISTE: Rarity.PEU_COMMUNE,
    CharacterClass.PALADIN: Rarity.RARE,
    CharacterClass.CHASSEUR: Rarity.RARE,
    CharacterClass.INVOCATEUR: Rarity.RARE,
    CharacterClass.DUELISTE: Rarity.RARE,
    CharacterClass.MOINE: Rarity.RARE,
    CharacterClass.NECROMANCIEN: Rarity.TRES_RARE,
    CharacterClass.CHRONOMANCIEN: Rarity.TRES_RARE,
    CharacterClass.CHEVALIER_NOIR: Rarity.TRES_RARE,
    CharacterClass.REVENANT: Rarity.TRES_RARE,
    CharacterClass.GARDIEN_DU_NEANT: Rarity.LEGENDAIRE,
    CharacterClass.HERITIER_DE_LA_TOUR: Rarity.LEGENDAIRE,
    CharacterClass.ELU_DU_CREATEUR: Rarity.MYTHIQUE,
}


def class_unlock_level(character_class: CharacterClass) -> int:
    return UNLOCK_TOWER_LEVEL[CLASS_RARITY[character_class]]


def unlocked_classes(tower_level: int) -> list[CharacterClass]:
    """Classes débloquées à un niveau de Tour donné, dans l'ordre de l'enum."""
    return [c for c in CharacterClass if class_unlock_level(c) <= tower_level]


def random_class(rng, tower_level: int = 1) -> CharacterClass:
    """Tire une classe aléatoire parmi celles débloquées, pondérée par rareté."""
    candidates = unlocked_classes(tower_level)
    weights = [RARITY_WEIGHTS[CLASS_RARITY[c]] for c in candidates]
    return rng.choices(candidates, weights=weights, k=1)[0]


def apply_class(player: "PlayerState", character_class: CharacterClass) -> None:
    if character_class == CharacterClass.BERSERKER:
        player.low_hp_threshold = max(player.low_hp_threshold, 0.3)
        player.low_hp_bonus += 0.8
    elif character_class == CharacterClass.GARDIEN:
        player.defense += 8
        player.block_charges += 1
    elif character_class == CharacterClass.ASSASSIN:
        player.crit_chance += 0.4
        player.crit_multiplier = max(player.crit_multiplier, 3.0)
        player.dodge_chance += 0.25
    elif character_class == CharacterClass.MAGE_INSTABLE:
        player.instable = True
        player.atk = round(player.atk * 1.8)
    elif character_class == CharacterClass.LAME_SANGUINE:
        player.lifesteal_ratio += 0.3
    elif character_class == CharacterClass.AVENTURIER_CHANCEUX:
        player.crit_chance += 0.15
        player.dodge_chance += 0.1
        player.gold_multiplier *= 1.3
    elif character_class == CharacterClass.OCCULTISTE:
        player.curse_chance += 0.30
    elif character_class == CharacterClass.ALCHIMISTE:
        player.heal_bonus_ratio += 0.50
    elif character_class == CharacterClass.PALADIN:
        player.defense += 5
        player.heal_bonus_ratio += 0.25
    elif character_class == CharacterClass.CHASSEUR:
        player.vs_monster_bonus += 0.30
    elif character_class == CharacterClass.INVOCATEUR:
        player.summon_damage += 8
    elif character_class == CharacterClass.DUELISTE:
        player.vs_boss_bonus += 0.40
    elif character_class == CharacterClass.MOINE:
        player.combo_bonus += 0.15
    elif character_class == CharacterClass.NECROMANCIEN:
        player.heal_on_kill_ratio += 0.20
        player.atk_on_kill += 2
    elif character_class == CharacterClass.CHRONOMANCIEN:
        player.freeze_chance += 0.20
    elif character_class == CharacterClass.CHEVALIER_NOIR:
        player.atk = round(player.atk * 1.4)
        player.max_hp = max(1, round(player.max_hp * 0.8))
        player.hp = min(player.hp, player.max_hp)
    elif character_class == CharacterClass.REVENANT:
        player.extra_lives += 1
    elif character_class == CharacterClass.GARDIEN_DU_NEANT:
        player.negates_statuses = True
    elif character_class == CharacterClass.HERITIER_DE_LA_TOUR:
        player.legacy_bonus_multiplier += 0.50
    elif character_class == CharacterClass.ELU_DU_CREATEUR:
        player.floor_scaling = True
