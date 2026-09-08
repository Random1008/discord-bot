"""Potions de la Tour RPG (20). Achetées en boutique/marché noir, rangées dans
le sac, utilisées en combat via le bouton OBJET."""

from dataclasses import dataclass
from typing import Callable, TYPE_CHECKING

from services.rpg.rarity import Rarity
from services.rpg.status_effects import (
    StatusEffectKind,
    apply_status_effect,
)

if TYPE_CHECKING:
    from services.rpg.player import PlayerState


@dataclass
class Potion:
    key: str
    name: str
    rarity: Rarity
    description: str
    price: int
    effect: Callable[["PlayerState"], str]


def _heal(amount: int):
    def apply(player: "PlayerState") -> str:
        healed = player.heal(amount)
        return f"{healed} PV récupérés."
    return apply


def _buff(kind: StatusEffectKind, magnitude, rounds: int):
    def apply(player: "PlayerState") -> str:
        apply_status_effect(player, kind, rounds=rounds, magnitude=magnitude)
        return "Bonus temporaire appliqué."
    return apply


POTIONS = [
    Potion("petite_potion", "Petite Potion", Rarity.COMMUNE, "Soigne 25 HP", 20, _heal(25)),
    Potion("potion_moyenne", "Potion Moyenne", Rarity.COMMUNE, "Soigne 50 HP", 40, _heal(50)),
    Potion("grande_potion", "Grande Potion", Rarity.COMMUNE, "Soigne 100 HP", 80, _heal(100)),
    Potion("potion_de_force", "Potion de Force", Rarity.PEU_COMMUNE, "+10 ATK temporaire", 60,
           _buff(StatusEffectKind.RAGE, 10, rounds=3)),
    Potion("potion_de_defense", "Potion de Défense", Rarity.PEU_COMMUNE, "+10 DEF temporaire", 60,
           _buff(StatusEffectKind.GARDE, 10, rounds=3)),
    Potion("potion_de_critique", "Potion de Critique", Rarity.PEU_COMMUNE, "+10% critique", 70,
           _buff(StatusEffectKind.PRECISION, 0.10, rounds=3)),
    Potion("potion_d_esquive", "Potion d'Esquive", Rarity.PEU_COMMUNE, "+10% esquive", 70,
           _buff(StatusEffectKind.AGILITE, 0.10, rounds=3)),
    Potion("potion_de_rage", "Potion de Rage", Rarity.PEU_COMMUNE, "Dégâts augmentés", 80,
           _buff(StatusEffectKind.RAGE, 15, rounds=2)),
    Potion("potion_mysterieuse", "Potion Mystérieuse", Rarity.RARE, "Effet aléatoire", 90,
           lambda p: _mysterious(p)),
    Potion("potion_de_feu", "Potion de Feu", Rarity.RARE, "Attaques brûlantes", 100,
           _buff(StatusEffectKind.BRULURE_ATTAQUE, 0, rounds=3)),
    Potion("potion_de_glace", "Potion de Glace", Rarity.RARE, "Chance de geler l'ennemi", 100,
           _buff(StatusEffectKind.GEL_ATTAQUE, 0, rounds=3)),
    Potion("potion_de_sang", "Potion de Sang", Rarity.RARE, "Vol de vie temporaire", 110,
           _buff(StatusEffectKind.VAMPIRISME, 0.20, rounds=3)),
    Potion("elixir_du_chasseur", "Élixir du Chasseur", Rarity.RARE, "Bonus contre les monstres", 120,
           lambda p: _permanent(p, "vs_monster_bonus", 0.30, "Bonus contre les monstres (run).")),
    Potion("elixir_du_gardien", "Élixir du Gardien", Rarity.RARE, "Réduction des dégâts", 120,
           lambda p: _permanent(p, "damage_reduction", 2, "Réduction des dégâts (run).")),
    Potion("elixir_de_renaissance", "Élixir de Renaissance", Rarity.TRES_RARE, "Réanimation", 200,
           lambda p: _permanent(p, "extra_lives", 1, "Une vie supplémentaire (run).")),
    Potion("potion_du_temps", "Potion du Temps", Rarity.TRES_RARE, "Réinitialise les cooldowns", 200,
           lambda p: _reset_statuses(p)),
    Potion("elixir_vampirique", "Élixir Vampirique", Rarity.TRES_RARE, "Vol de vie puissant", 220,
           lambda p: _permanent(p, "lifesteal_ratio", 0.20, "Vol de vie (run).")),
    Potion("ambroisie_divine", "Ambroisie Divine", Rarity.LEGENDAIRE, "Soigne totalement", 250,
           lambda p: _full_heal(p)),
    Potion("nectar_de_la_tour", "Nectar de la Tour", Rarity.LEGENDAIRE, "Bonus toutes stats", 300,
           lambda p: _all_stats(p)),
    Potion("elixir_du_createur", "Élixir du Créateur", Rarity.MYTHIQUE, "Bonus permanent aléatoire", 500,
           lambda p: _random_permanent(p)),
]


def _mysterious(player: "PlayerState") -> str:
    import random
    roll = random.random()
    if roll < 0.4:
        return _heal(40)(player)
    if roll < 0.7:
        player.atk += 5
        return "La potion renforce durablement ton attaque (+5 ATK)."
    player.take_damage(15)
    return "La potion était toxique : 15 dégâts."


def _permanent(player: "PlayerState", attr: str, value, msg: str) -> str:
    current = getattr(player, attr)
    if isinstance(current, bool):
        setattr(player, attr, True)
    else:
        setattr(player, attr, current + value)
    return msg


def _reset_statuses(player: "PlayerState") -> str:
    from services.rpg.status_effects import _revert_stat_effect, STAT_KINDS
    for effect in list(player.statuses):
        if effect.kind in STAT_KINDS:
            _revert_stat_effect(player, effect)
        player.statuses.remove(effect)
    return "Tes effets en cours sont dissipés."


def _full_heal(player: "PlayerState") -> str:
    healed = player.heal(player.max_hp)
    return f"Soin complet : {healed} PV récupérés."


def _all_stats(player: "PlayerState") -> str:
    player.atk += 5
    player.defense += 5
    player.max_hp += 20
    player.hp += 20
    player.crit_chance += 0.05
    return "Toutes tes stats augmentent (+5 ATK, +5 DEF, +20 HP, +5% critique)."


def _random_permanent(player: "PlayerState") -> str:
    import random
    roll = random.random()
    if roll < 0.33:
        player.atk += 8
        return "Un don permanent : +8 ATK."
    if roll < 0.66:
        player.max_hp += 30
        player.hp += 30
        return "Un don permanent : +30 HP max."
    player.crit_chance += 0.10
    return "Un don permanent : +10% critique."


POTION_BY_KEY = {p.key: p for p in POTIONS}


def get_potion(key: str) -> Potion | None:
    return POTION_BY_KEY.get(key)
