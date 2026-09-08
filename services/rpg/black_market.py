"""Marché noir de la Tour RPG : propose de l'équipement (armes/armures) et des
potions rares, à prix variables. L'équipement rejoint l'inventaire persistant."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from services.rpg.equipment import ARMORS, WEAPONS
from services.rpg.potions import POTIONS
from services.rpg.rarity import Rarity, RARITY_WEIGHTS

if TYPE_CHECKING:
    from services.rpg.player import PlayerState

OFFERS_PER_VISIT = 3

# L'équipement proposé est au moins de rareté Peu Commune.
MIN_EQUIPMENT_RARITY = Rarity.PEU_COMMUNE


@dataclass
class BlackMarketOffer:
    kind: str  # "weapon" | "armor" | "potion"
    key: str
    name: str
    price: int


def _equipment_pool():
    weapons = [w for w in WEAPONS if RARITY_WEIGHTS[w.rarity] <= RARITY_WEIGHTS[MIN_EQUIPMENT_RARITY]]
    armors = [a for a in ARMORS if RARITY_WEIGHTS[a.rarity] <= RARITY_WEIGHTS[MIN_EQUIPMENT_RARITY]]
    return weapons, armors


def _rare_potions():
    return [p for p in POTIONS if p.rarity not in (Rarity.COMMUNE, Rarity.PEU_COMMUNE)]


def generate_black_market(rng) -> list[BlackMarketOffer]:
    """Trois offres : équipement (arme/armure) et potions rares, prix variables."""
    weapons, armors = _equipment_pool()
    rare_potions = _rare_potions()
    offers: list[BlackMarketOffer] = []

    candidates = []
    for w in weapons:
        candidates.append(("weapon", w.key, w.name, w.rarity))
    for a in armors:
        candidates.append(("armor", a.key, a.name, a.rarity))
    for p in rare_potions:
        candidates.append(("potion", p.key, p.name, p.rarity))

    weights = [RARITY_WEIGHTS[rarity] for _, _, _, rarity in candidates]
    picks = rng.choices(candidates, weights=weights, k=OFFERS_PER_VISIT)

    for kind, key, name, rarity in picks:
        if kind == "potion":
            base_price = next(p.price for p in POTIONS if p.key == key)
        else:
            base_price = _base_price_for_rarity(rarity)
        offers.append(BlackMarketOffer(kind, key, name, round(base_price * rng.uniform(0.8, 1.5))))
    return offers


def _base_price_for_rarity(rarity: Rarity) -> int:
    return {
        Rarity.COMMUNE: 30,
        Rarity.PEU_COMMUNE: 60,
        Rarity.RARE: 120,
        Rarity.TRES_RARE: 250,
        Rarity.LEGENDAIRE: 500,
        Rarity.MYTHIQUE: 1000,
    }[rarity]
