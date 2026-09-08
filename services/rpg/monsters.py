from services.rpg.combat import Monster, scale_monster

MONSTER_FAMILY_TIERS = [
    (1, 10, ["Gobelins"]),
    (6, 20, ["Squelettes"]),
    (16, 35, ["Esprits"]),
    (26, 50, ["Créatures mécaniques"]),
    (41, 70, ["Bêtes mutées"]),
    (61, 90, ["Démons"]),
    (81, None, ["Gardiens antiques"]),
]


def family_for_floor(floor: int, rng) -> str:
    candidates = [
        name
        for min_floor, max_floor, names in MONSTER_FAMILY_TIERS
        for name in names
        if floor >= min_floor and (max_floor is None or floor <= max_floor)
    ]
    if not candidates:
        candidates = MONSTER_FAMILY_TIERS[-1][2]
    return rng.choice(candidates)


def spawn_monster(floor: int, rng, ng_plus: int = 0) -> Monster:
    monster = scale_monster(floor, ng_plus=ng_plus)
    monster.name = family_for_floor(floor, rng)
    return monster
