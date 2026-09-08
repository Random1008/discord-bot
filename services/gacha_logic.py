from dataclasses import dataclass

RARITY_ORDER: list[str] = ["Commun", "Rare", "Épique", "Légendaire", "Mythique", "Secret"]

RATES: dict[str, float] = {
    "Commun": 0.60,
    "Rare": 0.25,
    "Épique": 0.10,
    "Légendaire": 0.04,
    "Mythique": 0.009,
    "Secret": 0.001,
}

CHARACTERS_BY_RARITY: dict[str, list[str]] = {
    "Commun": ["Comptable", "Joueur professionnel", "Trafiquant", "Aventurier", "Guerrier"],
    "Rare": ["Banquier", "Croupier", "Parrain", "Explorateur", "Archer"],
    "Épique": ["Investisseur", "Roi du casino", "Seigneur criminel", "Cartographe", "Mage"],
    "Légendaire": ["Magnat", "Maître du hasard", "Voyageur dimensionnel", "Dragonier"],
    "Mythique": ["Génie financier"],
    "Secret": [],
}

PITY_THRESHOLDS: dict[str, int] = {"Épique": 10, "Légendaire": 30, "Mythique": 100}
PITY_CHECK_ORDER: list[str] = ["Mythique", "Légendaire", "Épique"]
PITY_FIELD_BY_RARITY: dict[str, str] = {
    "Épique": "pulls_since_epique",
    "Légendaire": "pulls_since_legendaire",
    "Mythique": "pulls_since_mythique",
}

FRAGMENT_BONUS_CHANCE: float = 0.20
SECRET_FRAGMENT_BONUS: int = 10


@dataclass
class PityState:
    pulls_since_epique: int = 0
    pulls_since_legendaire: int = 0
    pulls_since_mythique: int = 0


@dataclass
class PullResult:
    rarity: str
    character: str | None
    bonus_fragments: int


def rarity_rank(rarity: str) -> int:
    return RARITY_ORDER.index(rarity)


def roll_rarity(rng, mythique_bonus: float = 0.0) -> str:
    roll = rng.random()
    cumulative = 0.0
    for rarity in RARITY_ORDER:
        rate = RATES[rarity]
        if rarity == "Commun":
            rate -= mythique_bonus
        elif rarity == "Mythique":
            rate += mythique_bonus
        cumulative += rate
        if roll < cumulative:
            return rarity
    return RARITY_ORDER[-1]


def apply_pity(rarity: str, pity: PityState) -> str:
    for pity_rarity in PITY_CHECK_ORDER:
        threshold = PITY_THRESHOLDS[pity_rarity]
        counter = getattr(pity, PITY_FIELD_BY_RARITY[pity_rarity])
        if counter >= threshold and rarity_rank(rarity) < rarity_rank(pity_rarity):
            return pity_rarity
    return rarity


def update_pity(pity: PityState, final_rarity: str) -> None:
    for pity_rarity, field in PITY_FIELD_BY_RARITY.items():
        if rarity_rank(final_rarity) >= rarity_rank(pity_rarity):
            setattr(pity, field, 0)
        else:
            setattr(pity, field, getattr(pity, field) + 1)


def pick_character(rarity: str, rng) -> str | None:
    pool = CHARACTERS_BY_RARITY[rarity]
    if not pool:
        return None
    return rng.choice(pool)


def roll_bonus_fragments(rarity: str, rng) -> int:
    if rarity == "Secret":
        return SECRET_FRAGMENT_BONUS
    if rng.random() < FRAGMENT_BONUS_CHANCE:
        return rng.randint(1, 2)
    return 0


def pull(pity: PityState, rng, mythique_bonus: float = 0.0, fragment_bonus_flat: int = 0) -> PullResult:
    raw_rarity = roll_rarity(rng, mythique_bonus)
    final_rarity = apply_pity(raw_rarity, pity)
    update_pity(pity, final_rarity)
    character = pick_character(final_rarity, rng)
    bonus_fragments = roll_bonus_fragments(final_rarity, rng) + fragment_bonus_flat
    return PullResult(rarity=final_rarity, character=character, bonus_fragments=bonus_fragments)
