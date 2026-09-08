"""Armes et armures persistantes de la Tour RPG.

L'équipement est conservé entre les runs (stocké en base) : une arme et une
armure équipées, appliquées au début de chaque run. Obtenu via les coffres,
les drops d'ennemis et le marché noir.
"""

from dataclasses import dataclass
from typing import Callable, TYPE_CHECKING

from services.rpg.rarity import Rarity

if TYPE_CHECKING:
    from services.rpg.player import PlayerState


@dataclass
class Weapon:
    key: str
    name: str
    rarity: Rarity
    description: str
    effect: Callable[["PlayerState"], None]


@dataclass
class Armor:
    key: str
    name: str
    rarity: Rarity
    description: str
    effect: Callable[["PlayerState"], None]


def _add(field: str, value):
    def apply(player: "PlayerState") -> None:
        setattr(player, field, getattr(player, field) + value)
    return apply


def _set_true(field: str):
    def apply(player: "PlayerState") -> None:
        setattr(player, field, True)
    return apply


def _dague(player: "PlayerState") -> None:
    player.atk += 2
    player.crit_chance += 0.02


def _marteau_titan(player: "PlayerState") -> None:
    player.atk += 15
    player.crit_multiplier += 0.5


def _arc_spectral(player: "PlayerState") -> None:
    player.crit_chance += 0.10
    player.crit_multiplier += 0.5


def _max_hp(delta: int):
    def apply(player: "PlayerState") -> None:
        player.max_hp += delta
        player.hp += delta
    return apply


# --- ARMES (20) ---
WEAPONS = [
    Weapon("epee_rouillee", "Épée Rouillée", Rarity.COMMUNE, "+3 ATK", _add("atk", 3)),
    Weapon("dague_de_cuir", "Dague de Cuir", Rarity.COMMUNE, "+2 ATK, +2% critique", _dague),
    Weapon("marteau_du_mineur", "Marteau du Mineur", Rarity.COMMUNE, "+5 ATK", _add("atk", 5)),
    Weapon("lance_du_soldat", "Lance du Soldat", Rarity.COMMUNE, "+4 ATK", _add("atk", 4)),
    Weapon("arc_court", "Arc Court", Rarity.COMMUNE, "+3 ATK", _add("atk", 3)),
    Weapon("sabre_du_vent", "Sabre du Vent", Rarity.PEU_COMMUNE, "+5% esquive", _add("dodge_chance", 0.05)),
    Weapon("hache_sanglante", "Hache Sanglante", Rarity.PEU_COMMUNE, "Chance de saignement", _add("bleed_chance", 0.25)),
    Weapon("lame_du_chasseur", "Lame du Chasseur", Rarity.PEU_COMMUNE, "Bonus contre les monstres", _add("vs_monster_bonus", 0.30)),
    Weapon("epee_de_bronze", "Épée de Bronze", Rarity.PEU_COMMUNE, "+10 ATK", _add("atk", 10)),
    Weapon("fouet_electrique", "Fouet Électrique", Rarity.PEU_COMMUNE, "Chance d'étourdir", _add("stun_chance", 0.20)),
    Weapon("epee_du_berserker", "Épée du Berserker", Rarity.RARE, "Bonus si HP faibles", _add("low_hp_bonus", 0.40)),
    Weapon("lance_du_gardien", "Lance du Gardien", Rarity.RARE, "+10 DEF", _add("defense", 10)),
    Weapon("faux_de_l_occultiste", "Faux de l'Occultiste", Rarity.RARE, "Malédictions renforcées", _add("curse_chance", 0.25)),
    Weapon("marteau_du_titan", "Marteau du Titan", Rarity.RARE, "Gros dégâts", _marteau_titan),
    Weapon("arc_spectral", "Arc Spectral", Rarity.RARE, "Critiques accrus", _arc_spectral),
    Weapon("lame_vampirique", "Lame Vampirique", Rarity.TRES_RARE, "Vol de vie", _add("lifesteal_ratio", 0.15)),
    Weapon("epee_du_faux_heros", "Épée du Faux Héros", Rarity.TRES_RARE, "Copie une partie des stats ennemies", _add("copy_enemy_stats_ratio", 0.30)),
    Weapon("katana_du_jugement", "Katana du Jugement", Rarity.LEGENDAIRE, "+50% dégâts critiques", _add("crit_multiplier", 0.5)),
    Weapon("coeur_de_la_tour", "Cœur de la Tour", Rarity.LEGENDAIRE, "Plus forte à chaque étage", _add("weapon_floor_growth", 1)),
    Weapon("lame_de_l_infini", "Lame de l'Infini", Rarity.MYTHIQUE, "Gain permanent après chaque boss", _add("atk", 5)),
]

# --- ARMURES (20) ---
ARMORS = [
    Armor("tunique_usee", "Tunique Usée", Rarity.COMMUNE, "+3 DEF", _add("defense", 3)),
    Armor("armure_de_cuir", "Armure de Cuir", Rarity.COMMUNE, "+5 DEF", _add("defense", 5)),
    Armor("manteau_de_voyage", "Manteau de Voyage", Rarity.COMMUNE, "+20 HP", _max_hp(20)),
    Armor("casque_de_fer", "Casque de Fer", Rarity.COMMUNE, "+2 DEF", _add("defense", 2)),
    Armor("plastron_leger", "Plastron Léger", Rarity.COMMUNE, "+4 DEF", _add("defense", 4)),
    Armor("cotte_du_gardien", "Cotte du Gardien", Rarity.PEU_COMMUNE, "+10 DEF", _add("defense", 10)),
    Armor("armure_du_voyageur", "Armure du Voyageur", Rarity.PEU_COMMUNE, "+50 HP", _max_hp(50)),
    Armor("armure_d_ecailles", "Armure d'Écailles", Rarity.PEU_COMMUNE, "Réduit les dégâts subis", _add("damage_reduction", 2)),
    Armor("robe_de_mana", "Robe de Mana", Rarity.PEU_COMMUNE, "Bonus de sorts", _add("atk", 4)),
    Armor("armure_du_chasseur", "Armure du Chasseur", Rarity.PEU_COMMUNE, "Bonus contre les monstres", _add("vs_monster_bonus", 0.20)),
    Armor("carapace_du_titan", "Carapace du Titan", Rarity.RARE, "+25 DEF", _add("defense", 25)),
    Armor("manteau_spectral", "Manteau Spectral", Rarity.RARE, "+10% esquive", _add("dodge_chance", 0.10)),
    Armor("robe_du_mage_instable", "Robe du Mage Instable", Rarity.RARE, "Effets renforcés", _add("atk", 5)),
    Armor("armure_d_acier_noir", "Armure d'Acier Noir", Rarity.RARE, "Défense élevée", _add("defense", 18)),
    Armor("cape_du_dueliste", "Cape du Dueliste", Rarity.RARE, "Bonus contre les boss", _add("vs_boss_bonus", 0.30)),
    Armor("armure_sanglante", "Armure Sanglante", Rarity.TRES_RARE, "Régénération après combat", _add("regen_ratio", 0.15)),
    Armor("peau_du_dragon_noir", "Peau du Dragon Noir", Rarity.TRES_RARE, "Résistance brûlure", _add("burn_resistance", 0.7)),
    Armor("armure_du_temps", "Armure du Temps", Rarity.LEGENDAIRE, "Réduit la durée des effets subis", _add("status_duration_reduction", 1)),
    Armor("egide_de_la_tour", "Égide de la Tour", Rarity.LEGENDAIRE, "Ignore un coup mortel", _set_true("lethal_guard")),
    Armor("armure_de_l_infini", "Armure de l'Infini", Rarity.MYTHIQUE, "DEF augmente à chaque étage", _add("armor_floor_growth", 1)),
]

WEAPON_BY_KEY = {w.key: w for w in WEAPONS}
ARMOR_BY_KEY = {a.key: a for a in ARMORS}


def get_weapon(key: str) -> Weapon | None:
    return WEAPON_BY_KEY.get(key)


def get_armor(key: str) -> Armor | None:
    return ARMOR_BY_KEY.get(key)


def apply_equipment(player: "PlayerState", weapon_key: str | None, armor_key: str | None) -> None:
    """Applique les bonus de l'arme et de l'armure équipées au joueur (en début
    de run). `weapon_key`/`armor_key` sont les clés d'équipement persistantes,
    ou None si rien n'est équipé."""
    if weapon_key:
        weapon = get_weapon(weapon_key)
        if weapon is not None:
            weapon.effect(player)
    if armor_key:
        armor = get_armor(armor_key)
        if armor is not None:
            armor.effect(player)
