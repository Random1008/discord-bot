from enum import Enum
from typing import TYPE_CHECKING

from services.rpg.rarity import Rarity, RARITY_WEIGHTS, UNLOCK_TOWER_LEVEL

if TYPE_CHECKING:
    from services.rpg.player import PlayerState


class Trait(Enum):
    CHANCE_INSOLENTE = "chance_insolente"
    PRUDENT = "prudent"
    INSTABLE = "instable"
    AGILE = "agile"
    ROBUSTE = "robuste"
    FRAGILE_MAIS_DANGEREUX = "fragile_mais_dangereux"
    ECONOME = "econome"
    COLLECTIONNEUR = "collectionneur"
    CHASSEUR_DE_BOSS = "chasseur_de_boss"
    SURVIVANT = "survivant"
    BERSERK_LATENT = "berserk_latent"
    SOIF_DE_SANG = "soif_de_sang"
    TEMERAIRE = "temeraire"
    VISIONNAIRE = "visionnaire"
    BENI = "beni"
    PORTEUR_DES_OMBRES = "porteur_des_ombres"
    ANCIENNE_AME = "ancienne_ame"
    HERITIER = "heritier"
    FAVORI_DE_LA_TOUR = "favori_de_la_tour"


TRAIT_NAMES = {
    Trait.CHANCE_INSOLENTE: "Chance Insolente",
    Trait.PRUDENT: "Prudent",
    Trait.INSTABLE: "Instable",
    Trait.AGILE: "Agile",
    Trait.ROBUSTE: "Robuste",
    Trait.FRAGILE_MAIS_DANGEREUX: "Fragile mais Dangereux",
    Trait.ECONOME: "Économe",
    Trait.COLLECTIONNEUR: "Collectionneur",
    Trait.CHASSEUR_DE_BOSS: "Chasseur de Boss",
    Trait.SURVIVANT: "Survivant",
    Trait.BERSERK_LATENT: "Berserk Latent",
    Trait.SOIF_DE_SANG: "Soif de Sang",
    Trait.TEMERAIRE: "Téméraire",
    Trait.VISIONNAIRE: "Visionnaire",
    Trait.BENI: "Béni",
    Trait.PORTEUR_DES_OMBRES: "Porteur des Ombres",
    Trait.ANCIENNE_AME: "Ancienne Âme",
    Trait.HERITIER: "Héritier",
    Trait.FAVORI_DE_LA_TOUR: "Favori de la Tour",
}

TRAIT_RARITY = {
    Trait.CHANCE_INSOLENTE: Rarity.COMMUNE,
    Trait.PRUDENT: Rarity.COMMUNE,
    Trait.INSTABLE: Rarity.COMMUNE,
    Trait.AGILE: Rarity.COMMUNE,
    Trait.ROBUSTE: Rarity.COMMUNE,
    Trait.FRAGILE_MAIS_DANGEREUX: Rarity.PEU_COMMUNE,
    Trait.ECONOME: Rarity.PEU_COMMUNE,
    Trait.COLLECTIONNEUR: Rarity.PEU_COMMUNE,
    Trait.CHASSEUR_DE_BOSS: Rarity.PEU_COMMUNE,
    Trait.SURVIVANT: Rarity.PEU_COMMUNE,
    Trait.BERSERK_LATENT: Rarity.RARE,
    Trait.SOIF_DE_SANG: Rarity.RARE,
    Trait.TEMERAIRE: Rarity.RARE,
    Trait.VISIONNAIRE: Rarity.RARE,
    Trait.BENI: Rarity.RARE,
    Trait.PORTEUR_DES_OMBRES: Rarity.TRES_RARE,
    Trait.ANCIENNE_AME: Rarity.LEGENDAIRE,
    Trait.HERITIER: Rarity.LEGENDAIRE,
    Trait.FAVORI_DE_LA_TOUR: Rarity.MYTHIQUE,
}


def trait_unlock_level(trait: Trait) -> int:
    return UNLOCK_TOWER_LEVEL[TRAIT_RARITY[trait]]


def unlocked_traits(tower_level: int) -> list[Trait]:
    return [t for t in Trait if trait_unlock_level(t) <= tower_level]


def random_trait(rng, tower_level: int = 1) -> Trait:
    """Tire un trait aléatoire parmi ceux débloqués, pondéré par la rareté."""
    candidates = unlocked_traits(tower_level)
    weights = [RARITY_WEIGHTS[TRAIT_RARITY[t]] for t in candidates]
    return rng.choices(candidates, weights=weights, k=1)[0]


def apply_trait(player: "PlayerState", trait: Trait) -> None:
    if trait == Trait.CHANCE_INSOLENTE:
        player.crit_chance += 0.20
    elif trait == Trait.PRUDENT:
        player.defense += 15
        player.atk = max(1, player.atk - 10)
    elif trait == Trait.INSTABLE:
        player.combat_random_bonus = True
    elif trait == Trait.AGILE:
        player.dodge_chance += 0.10
    elif trait == Trait.ROBUSTE:
        player.max_hp = round(player.max_hp * 1.2)
        player.hp = round(player.hp * 1.2)
    elif trait == Trait.FRAGILE_MAIS_DANGEREUX:
        player.max_hp = round(player.max_hp * 0.8)
        player.hp = round(player.hp * 0.8)
        player.atk = round(player.atk * 1.25)
    elif trait == Trait.ECONOME:
        player.shop_discount += 0.2
    elif trait == Trait.COLLECTIONNEUR:
        player.treasure_multiplier += 0.5
    elif trait == Trait.CHASSEUR_DE_BOSS:
        player.vs_boss_bonus += 0.3
    elif trait == Trait.SURVIVANT:
        player.regen_ratio += 0.05
    elif trait == Trait.BERSERK_LATENT:
        player.low_hp_threshold = max(player.low_hp_threshold, 0.3)
        player.low_hp_bonus += 0.3
    elif trait == Trait.SOIF_DE_SANG:
        player.lifesteal_ratio += 0.15
    elif trait == Trait.TEMERAIRE:
        player.atk = round(player.atk * 1.35)
        player.defense = max(0, player.defense - 8)
    elif trait == Trait.VISIONNAIRE:
        player.unique_room_chance_bonus += 0.15
    elif trait == Trait.BENI:
        player.gold_multiplier *= 1.3
    elif trait == Trait.PORTEUR_DES_OMBRES:
        player.curse_resistance += 0.5
    elif trait == Trait.ANCIENNE_AME:
        player.xp_multiplier += 0.3
    elif trait == Trait.HERITIER:
        player.legacy_bonus_multiplier += 0.3
    elif trait == Trait.FAVORI_DE_LA_TOUR:
        player.floor_random_bonus = True
