from dataclasses import dataclass


@dataclass(frozen=True)
class LootEntry:
    kind: str  # "coins" | "xp" | "badge" | "key" | "cosmetic"
    value: str | int | None
    label: str


def _coins(amount: int, label: str) -> LootEntry:
    return LootEntry(kind="coins", value=amount, label=label)


def _xp(amount: int, label: str) -> LootEntry:
    return LootEntry(kind="xp", value=amount, label=label)


def _badge(key: str, label: str) -> LootEntry:
    return LootEntry(kind="badge", value=key, label=label)


def _key(rarity: str, label: str) -> LootEntry:
    return LootEntry(kind="key", value=rarity, label=label)


def _key_bundle(rarity: str, count: int, label: str) -> LootEntry:
    return LootEntry(kind="key_bundle", value=(rarity, count), label=label)


def _cosmetic(label: str) -> LootEntry:
    return LootEntry(kind="cosmetic", value=None, label=label)


def _gacha_pull(count: int, label: str) -> LootEntry:
    return LootEntry(kind="gacha_pull", value=count, label=label)


def _gacha_pull_guaranteed(min_rarity: str, label: str, count: int = 1) -> LootEntry:
    return LootEntry(kind="gacha_pull_guaranteed", value=(min_rarity, count), label=label)


def _gacha_fragments(amount: int, label: str) -> LootEntry:
    return LootEntry(kind="gacha_fragments", value=amount, label=label)


def _gacha_boost(bonus: float, duration_seconds: int, label: str) -> LootEntry:
    return LootEntry(kind="gacha_boost", value=(bonus, duration_seconds), label=label)


def _key_upgrade(label: str, from_rarity: str | None = None) -> LootEntry:
    return LootEntry(kind="key_upgrade", value=from_rarity, label=label)


def _effect(
    effect_type: str,
    label: str,
    magnitude: float | None = None,
    uses: int | None = None,
    duration_seconds: int | None = None,
) -> LootEntry:
    return LootEntry(
        kind="effect",
        value={"effect_type": effect_type, "magnitude": magnitude, "uses": uses, "duration_seconds": duration_seconds},
        label=label,
    )


def _bonus_open(rarity: str, label: str, count: int = 1) -> LootEntry:
    return LootEntry(kind="bonus_open", value=(rarity, count), label=label)


def _reroll(label: str) -> LootEntry:
    return LootEntry(kind="reroll", value=None, label=label)


def _mystery(label: str) -> LootEntry:
    return LootEntry(kind="mystery", value=None, label=label)


LOOT_TABLE: dict[str, list[LootEntry]] = {
    "commun": [
        _effect("casino_free_bet", "Ticket casino", uses=1),
        _effect("casino_free_bet", "Jeton machine à sous", uses=1),
        _gacha_pull(1, "1 invocation gacha"),
        _gacha_pull(2, "2 invocations gacha"),
        _key("commun", "Coffre commun"),
        _key("commun", "Clé commune"),
        _gacha_fragments(2, "Fragment rare"),
        _gacha_fragments(1, "Fragment épique"),
        _effect("xp_boost", "Bonus XP 15 min", magnitude=1.2, duration_seconds=900),
        _effect("coins_boost", "Bonus coins 15 min", magnitude=1.2, duration_seconds=900),
        _effect("casino_insurance", "Assurance casino (rembourse une défaite)", uses=1),
        _effect("casino_double_win", "Double gain prochain pari", uses=1),
        _effect("coins_boost", "Multiplier la prochaine récompense x1.5", magnitude=1.5, duration_seconds=300),
        _reroll("Reroll de box"),
        _mystery("Gain aléatoire"),
        _effect("coins_boost", "Bonus quotidien amélioré", magnitude=1.3, duration_seconds=86400),
        _effect("casino_free_bet", "Pari gratuit", uses=1),
        _effect("streak_protection", "Protection de série", uses=1),
        _mystery("Cadeau mystère"),
        _mystery("Coffre surprise"),
        _effect("casino_jackpot_chance_boost", "Pièce porte-bonheur", magnitude=1.5, duration_seconds=1800),
        _effect("casino_free_bet", "Bonus roulette", uses=1),
        _coins(300, "Petit jackpot"),
        _gacha_fragments(3, "Fragment gacha"),
        _mystery("Carte mystère"),
        _effect("coins_boost", "Multiplicateur temporaire", magnitude=1.3, duration_seconds=600),
        _bonus_open("commun", "Deuxième ouverture de box"),
        _effect("coins_boost", "Heure chanceuse", magnitude=1.5, duration_seconds=3600),
        _effect("casino_double_win", "Dé bonus", uses=1),
        _reroll("Relance gratuite"),
        _mystery("Récompense cachée"),
        _key("commun", "Clé bonus"),
    ],
    "rare": [
        _gacha_pull(5, "5 invocations gacha"),
        _key("rare", "Coffre rare"),
        _key("rare", "Clé rare"),
        _effect("casino_free_bet", "Ticket casino premium", uses=2),
        _effect("casino_free_bet", "Ticket de roulette", uses=1),
        _effect("casino_free_bet", "Ticket poker", uses=1),
        _gacha_fragments(3, "Fragment légendaire"),
        _gacha_fragments(2, "Fragment mythique"),
        _effect("casino_jackpot_chance_boost", "Boost chance 30 min", magnitude=2.0, duration_seconds=1800),
        _effect("coins_boost", "Boost casino 30 min", magnitude=1.3, duration_seconds=1800),
        _effect("casino_insurance", "Assurance premium", uses=2),
        _coins(2000, "Jackpot garanti mineur"),
        _reroll("Reroll rare"),
        _effect("casino_free_bet", "Deux paris gratuits", uses=2),
        _effect("coins_boost", "Double récompense quotidienne", magnitude=2.0, duration_seconds=86400),
        _gacha_pull(1, "Relance de gacha gratuite"),
        _gacha_pull_guaranteed("Rare", "Invocation garantie rare"),
        _effect("coins_boost", "Multiplicateur x2 temporaire", magnitude=2.0, duration_seconds=1800),
        _mystery("Coffre mystère"),
        _mystery("Carte joker"),
        _mystery("Cadeau rare"),
        _effect("casino_jackpot_chance_boost", "Chance critique", magnitude=2.0, duration_seconds=1800),
        _badge("collectionneur", "Badge collection (gacha)"),
        _cosmetic("Jeton prestige"),
        _mystery("Coffre casino"),
        _effect("casino_jackpot_chance_boost", "Carte fortune", magnitude=2.0, duration_seconds=1800),
        _effect("coins_boost", "Bonus gains passifs", magnitude=1.5, duration_seconds=3600),
        _mystery("Ticket surprise"),
        _gacha_boost(0.05, 3600, "Boost gacha 1h"),
        _effect("casino_jackpot_chance_boost", "Relance jackpot", magnitude=3.0, duration_seconds=600),
        _key_bundle("commun", 3, "Clé commune x3"),
        _mystery("Coffre bonus"),
    ],
    "epique": [
        _gacha_pull_guaranteed("Épique", "Invocation épique garantie"),
        _key("epique", "Clé épique"),
        _key("epique", "Coffre épique"),
        _effect("casino_free_bet", "Ticket casino VIP", uses=3),
        _coins(8000, "Ticket jackpot"),
        _gacha_fragments(2, "Fragment divin"),
        _effect("casino_jackpot_chance_boost", "Boost chance x2", magnitude=2.0, duration_seconds=3600),
        _effect("coins_boost", "Boost casino x2", magnitude=2.0, duration_seconds=3600),
        _gacha_boost(0.08, 3600, "Boost gacha x2"),
        _bonus_open("epique", "Double ouverture de coffre"),
        _effect("coins_boost", "Triple récompense prochain jeu", magnitude=3.0, duration_seconds=300),
        _effect("casino_insurance", "Assurance totale", uses=5),
        _reroll("Reroll épique"),
        _mystery("Carte joker dorée"),
        _mystery("Cadeau épique"),
        _coins(15000, "Jackpot garanti"),
        _gacha_pull(10, "Invocation rare x10"),
        _gacha_pull(1, "Invocation gratuite quotidienne"),
        _effect("casino_jackpot_chance_boost", "Boost critique", magnitude=2.5, duration_seconds=3600),
        _effect("coins_boost", "Bonus série important", magnitude=2.0, duration_seconds=7200),
        _key_bundle("rare", 3, "Coffre rare x3"),
        _mystery("Coffre mystère premium"),
        _gacha_pull(1, "Tirage supplémentaire"),
        _key_upgrade("Upgrade de clé"),
        _effect("casino_jackpot_chance_boost", "Chance légendaire 1h", magnitude=3.0, duration_seconds=3600),
        _reroll("Relance totale"),
        _effect("coins_boost", "Multiplicateur x3", magnitude=3.0, duration_seconds=1800),
        _cosmetic("Bonus collection"),
        _effect("casino_free_bet", "Ticket roulette VIP", uses=2),
        _mystery("Bonus surprise géant"),
        _coins(20000, "Coffre jackpot"),
        _gacha_pull_guaranteed("Secret", "Invocation secrète"),
    ],
    "legendaire": [
        _gacha_pull_guaranteed("Légendaire", "Invocation légendaire garantie"),
        _key("legendaire", "Clé légendaire"),
        _key("legendaire", "Coffre légendaire"),
        _key_upgrade("Upgrade automatique d'une clé"),
        _coins(40000, "Ticket Mega Jackpot"),
        _reroll("Relance complète d'une box"),
        _key_bundle("epique", 3, "Coffre épique x3"),
        _key("legendaire", "Coffre légendaire bonus"),
        _effect("casino_jackpot_chance_boost", "Bonus chance x3", magnitude=3.0, duration_seconds=3600),
        _effect("coins_boost", "Boost casino x3", magnitude=3.0, duration_seconds=3600),
        _gacha_boost(0.12, 7200, "Boost gacha x3"),
        _gacha_fragments(5, "Fragment divin x5"),
        _mystery("Carte joker suprême"),
        _gacha_pull(25, "Invocation x25"),
        _effect("streak_protection", "Série protégée 24h", uses=1),
        _coins(35000, "Jackpot garanti moyen"),
        _mystery("Ticket tirage spécial"),
        _key_bundle("legendaire", 2, "Double clé obtenue"),
        _mystery("Coffre casino premium"),
        _gacha_pull(1, "Tirage légendaire bonus"),
        _effect("coins_boost", "Multiplicateur x5", magnitude=5.0, duration_seconds=3600),
        _mystery("Cadeau légendaire"),
        _cosmetic("Bonus collection majeur"),
        _effect("casino_jackpot_chance_boost", "Relance jackpot", magnitude=4.0, duration_seconds=900),
        _key_upgrade("Upgrade coffre"),
        _mystery("Bonus surprise énorme"),
        _effect("casino_jackpot_chance_boost", "Chance critique extrême", magnitude=4.0, duration_seconds=3600),
        _mystery("Coffre secret"),
        _gacha_pull(1, "Invocation mystère"),
        _cosmetic("Bonus prestige"),
        _effect("coins_boost", "Gain passif 24h", magnitude=2.0, duration_seconds=86400),
        _effect("casino_insurance", "Couverture anti-malchance", uses=3),
        _effect("coins_boost", "Booster ultime", magnitude=4.0, duration_seconds=7200),
        _coins(50000, "Jackpot personnel"),
        _mystery("Clé mystère"),
    ],
    "mythique": [
        _gacha_pull_guaranteed("Mythique", "Invocation mythique garantie"),
        _key("mythique", "Clé mythique"),
        _key("mythique", "Coffre mythique"),
        _coins(150000, "Jackpot garanti élevé"),
        _key_upgrade("Upgrade aléatoire vers Divin"),
        _effect("casino_free_bet", "Ticket Casino Royal", uses=5),
        _gacha_pull(3, "Ticket Gacha Royal"),
        _gacha_pull(50, "Invocation x50"),
        _gacha_fragments(15, "Fragment divin x15"),
        _key_bundle("mythique", 2, "Double clé mythique"),
        _bonus_open("mythique", "Triple ouverture", count=2),
        _reroll("Relance mythique"),
        _mystery("Coffre secret mythique"),
        _gacha_pull(2, "Tirage exclusif"),
        _effect("casino_jackpot_chance_boost", "Bonus chance x5", magnitude=5.0, duration_seconds=7200),
        _effect("coins_boost", "Bonus casino x5", magnitude=5.0, duration_seconds=7200),
        _gacha_boost(0.2, 14400, "Bonus gacha x5"),
        _effect("casino_insurance", "Protection anti-malchance", uses=5),
        _mystery("Cadeau mythique"),
        _coins(200000, "Jackpot personnel garanti"),
        _effect("casino_free_bet", "Ticket roulette royale", uses=3),
        _key_bundle("legendaire", 5, "Clé légendaire x5"),
        _key_bundle("legendaire", 5, "Coffre légendaire x5"),
        _effect("coins_boost", "Multiplicateur x10", magnitude=10.0, duration_seconds=3600),
        _cosmetic("Bonus prestige important"),
        _gacha_pull_guaranteed("Légendaire", "Invocation légendaire x10", count=10),
        _effect("coins_boost", "Bonus série extrême", magnitude=6.0, duration_seconds=3600),
        _mystery("Coffre royal"),
        _gacha_pull_guaranteed("Secret", "Ticket secret"),
        _gacha_pull(5, "Tirage cosmique"),
        _mystery("Récompense mystère géante"),
        _effect("casino_insurance", "Remboursement de pertes casino 24h", uses=20, duration_seconds=86400),
        _gacha_boost(0.3, 600, "Tirage infini 10 min"),
        _mystery("Clé mystère améliorée"),
        _mystery("Coffre céleste"),
    ],
    "divin": [
        _gacha_pull_guaranteed("Secret", "Invocation divine garantie"),
        _key("divin", "Clé divine"),
        _key("divin", "Coffre divin"),
        _coins(500000, "Jackpot divin"),
        _key_upgrade("Upgrade garanti en Divin", from_rarity="mythique"),
        _gacha_pull(100, "Invocation x100"),
        _effect("casino_free_bet", "Ticket Casino Divin", uses=10),
        _gacha_pull(10, "Ticket Gacha Divin"),
        _key_bundle("divin", 3, "Triple clé divine"),
        _key_bundle("divin", 3, "Coffre divin x3"),
        _reroll("Relance divine"),
        _gacha_pull_guaranteed("Secret", "Tirage exclusif divin", count=3),
        _gacha_fragments(50, "Fragment divin x50"),
        _effect("casino_insurance", "Protection absolue", uses=50),
        _gacha_pull_guaranteed("Mythique", "Mythique garanti au prochain gacha"),
        _gacha_boost(0.3, 86400, "Légendaire garanti pendant 24h"),
        _effect("coins_boost", "Bonus casino x10", magnitude=10.0, duration_seconds=14400),
        _gacha_boost(0.3, 14400, "Bonus gacha x10"),
        _effect("casino_jackpot_chance_boost", "Bonus chance x10", magnitude=10.0, duration_seconds=14400),
        _coins(750000, "Mega Jackpot garanti"),
        _mystery("Coffre secret divin"),
        _effect("coins_boost", "Multiplicateur x20", magnitude=20.0, duration_seconds=3600),
        _key_bundle("mythique", 10, "Clé mythique x10"),
        _key_bundle("legendaire", 25, "Clé légendaire x25"),
        _gacha_pull_guaranteed("Mythique", "Invocation mythique x10", count=10),
        _cosmetic("Bonus prestige énorme"),
        _coins(1000000, "Récompense cosmique"),
        _mystery("Clé mystère divine"),
        _mystery("Cadeau divin"),
        _mystery("Ticket trésor caché"),
        _gacha_pull(20, "Tirage céleste"),
        _mystery("Récompense aléatoire unique"),
        _mystery("Coffre royal divin"),
        _effect("casino_insurance", "Assurance totale 7 jours", uses=999, duration_seconds=604800),
        _gacha_pull_guaranteed("Secret", "Tirage ultime", count=5),
    ],
}
