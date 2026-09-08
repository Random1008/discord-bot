from typing import TYPE_CHECKING

from services.rpg.combat import Monster
from services.rpg.status_effects import StatusEffectKind, apply_status_effect

if TYPE_CHECKING:
    from services.rpg.bosses import Boss
    from services.rpg.player import PlayerState

BASE_XP_TO_LEVEL = 50
XP_GROWTH = 1.15
BOSS_XP_MULTIPLIER = 3
LEVEL_UP_HP_BONUS = 10
LEVEL_UP_ATK_BONUS = 2
LEVEL_UP_DEFENSE_BONUS = 1


def xp_for_next_level(level: int) -> int:
    return round(BASE_XP_TO_LEVEL * (XP_GROWTH ** (level - 1)))


def xp_reward_for_monster(monster: Monster) -> int:
    return round(monster.max_hp * 0.5 + monster.atk)


def xp_reward_for_boss(boss: "Boss") -> int:
    return xp_reward_for_monster(boss) * BOSS_XP_MULTIPLIER


def add_xp(player: "PlayerState", amount: int) -> int:
    # Trait Ancienne Âme : XP de run augmentée.
    amount = round(amount * (1 + player.xp_multiplier))
    player.xp += amount
    levels_gained = 0
    while player.xp >= xp_for_next_level(player.level):
        player.xp -= xp_for_next_level(player.level)
        player.level += 1
        player.max_hp += LEVEL_UP_HP_BONUS
        player.hp += LEVEL_UP_HP_BONUS
        player.atk += LEVEL_UP_ATK_BONUS
        player.defense += LEVEL_UP_DEFENSE_BONUS
        levels_gained += 1
    return levels_gained


def apply_combat_start_bonus(player: "PlayerState", rng) -> str | None:
    """Trait Instable : bonus aléatoire au début de chaque combat."""
    if not player.combat_random_bonus:
        return None
    roll = rng.random()
    if roll < 0.34:
        apply_status_effect(player, StatusEffectKind.RAGE, rounds=3, magnitude=5)
        return "Ton sang bouillonne : +5 ATK pour ce combat."
    if roll < 0.67:
        apply_status_effect(player, StatusEffectKind.GARDE, rounds=3, magnitude=5)
        return "Tes muscles se crispent : +5 DEF pour ce combat."
    apply_status_effect(player, StatusEffectKind.PRECISION, rounds=3, magnitude=0.10)
    return "Ton œil s'aiguise : +10% critique pour ce combat."


def apply_floor_growth(player: "PlayerState", rng) -> None:
    """Bonus appliqués à chaque étage gravi (Élu du Créateur, arme/armure
    « de l'Infini », Favori de la Tour)."""
    if player.floor_scaling:
        player.atk += 1
        player.defense += 1
        player.max_hp += 5
        player.hp += 5
    if player.weapon_floor_growth:
        player.atk += player.weapon_floor_growth
    if player.armor_floor_growth:
        player.defense += player.armor_floor_growth
    if player.floor_random_bonus:
        roll = rng.random()
        if roll < 0.34:
            player.atk += 2
        elif roll < 0.67:
            player.defense += 2
        else:
            player.max_hp += 10
            player.hp += 10
