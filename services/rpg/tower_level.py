"""Niveau de progression propre à la Tour RPG.

Distinct du leveling XP des messages (services/leveling.py) et du niveau de
run (services/rpg/progression.py). Le niveau de la Tour est persistant et
monte en tuant des monstres et en gravissant des étages. C'est lui qui
débloque les classes/traits par rareté (voir services/rpg/rarity.py).
"""

import math

# XP de Tour gagnée en gravissant chaque nouvel étage.
TOWER_XP_PER_FLOOR = 5
# XP de Tour bonus par boss vaincu.
TOWER_XP_PER_BOSS = 50
# Dénominateur de la formule de niveau : level = floor(sqrt(xp / DENOM)).
TOWER_XP_DENOM = 100


def tower_level_for_xp(xp: int) -> int:
    """Niveau de Tour (commence à 1) pour un total d'XP de Tour donné."""
    return math.isqrt(max(0, xp) // TOWER_XP_DENOM) + 1


def tower_xp_for_next_level(level: int) -> int:
    """XP totale requise pour atteindre `level` (level >= 1)."""
    target = max(0, level - 1)
    return target * target * TOWER_XP_DENOM
