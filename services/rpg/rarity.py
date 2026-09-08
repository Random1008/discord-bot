"""Système de rareté partagé par la Tour RPG (classes, traits, armes, armures,
potions, titres). Six niveaux, du Commun au Mythique."""

from enum import Enum


class Rarity(Enum):
    COMMUNE = "commune"
    PEU_COMMUNE = "peu_commune"
    RARE = "rare"
    TRES_RARE = "tres_rare"
    LEGENDAIRE = "legendaire"
    MYTHIQUE = "mythique"


RARITY_NAMES = {
    Rarity.COMMUNE: "Commun",
    Rarity.PEU_COMMUNE: "Peu Commun",
    Rarity.RARE: "Rare",
    Rarity.TRES_RARE: "Très Rare",
    Rarity.LEGENDAIRE: "Légendaire",
    Rarity.MYTHIQUE: "Mythique",
}

# Poids de tirage aléatoire (plus le poids est haut, plus la rareté est courante).
RARITY_WEIGHTS = {
    Rarity.COMMUNE: 50,
    Rarity.PEU_COMMUNE: 25,
    Rarity.RARE: 15,
    Rarity.TRES_RARE: 7,
    Rarity.LEGENDAIRE: 2,
    Rarity.MYTHIQUE: 1,
}

# Niveau de la Tour requis pour débloquer classes/traits de chaque rareté.
# Le niveau de la Tour est une progression propre à la Tour (persistante),
# distincte du leveling XP des messages : il monte en tuant des monstres et
# en gravissant des étages (voir services/rpg/tower_level.py).
UNLOCK_TOWER_LEVEL = {
    Rarity.COMMUNE: 1,
    Rarity.PEU_COMMUNE: 1,
    Rarity.RARE: 3,
    Rarity.TRES_RARE: 5,
    Rarity.LEGENDAIRE: 8,
    Rarity.MYTHIQUE: 12,
}

# Couleurs d'embed (hex) pour afficher les raretés.
RARITY_COLORS = {
    Rarity.COMMUNE: 0x9E9E9E,
    Rarity.PEU_COMMUNE: 0x4CAF50,
    Rarity.RARE: 0x2196F3,
    Rarity.TRES_RARE: 0x9C27B0,
    Rarity.LEGENDAIRE: 0xFF9800,
    Rarity.MYTHIQUE: 0xE91E63,
}

# Emoji par rareté (affichage compact).
RARITY_EMOJI = {
    Rarity.COMMUNE: "⬜",
    Rarity.PEU_COMMUNE: "🟩",
    Rarity.RARE: "🟦",
    Rarity.TRES_RARE: "🟪",
    Rarity.LEGENDAIRE: "🟧",
    Rarity.MYTHIQUE: "🟥",
}

RARITY_ORDER = list(Rarity)


def rarity_label(rarity: Rarity) -> str:
    return f"{RARITY_EMOJI[rarity]} {RARITY_NAMES[rarity]}"


def weighted_random_rarity(rng) -> Rarity:
    """Tire une rareté au hasard, pondérée par RARITY_WEIGHTS."""
    rarities = list(RARITY_WEIGHTS)
    weights = [RARITY_WEIGHTS[r] for r in rarities]
    return rng.choices(rarities, weights=weights, k=1)[0]
