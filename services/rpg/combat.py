from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from services.rpg.status_effects import (
    StatusEffectKind,
    apply_status_effect,
    consume_freeze,
    has_status,
    tick_statuses,
)

if TYPE_CHECKING:
    from services.rpg.player import PlayerState

BASE_HP = 20
BASE_ATK = 5
HP_PER_FLOOR = 5
ATK_PER_FLOOR = 2
INSTABLE_SWING_MIN = -3
INSTABLE_SWING_MAX = 5
NG_PLUS_MULTIPLIER_PER_LEVEL = 0.2


@dataclass
class Monster:
    hp: int
    max_hp: int
    atk: int
    defense: int = 0
    name: str = ""
    statuses: list = field(default_factory=list)

    def take_damage(self, amount: int) -> int:
        dealt = max(1, amount - self.defense)
        self.hp -= dealt
        return dealt

    def is_alive(self) -> bool:
        return self.hp > 0


def scale_monster(floor: int, ng_plus: int = 0) -> Monster:
    multiplier = 1 + NG_PLUS_MULTIPLIER_PER_LEVEL * ng_plus
    hp = round((BASE_HP + HP_PER_FLOOR * (floor - 1)) * multiplier)
    atk = round((BASE_ATK + ATK_PER_FLOOR * (floor - 1)) * multiplier)
    return Monster(hp=hp, max_hp=hp, atk=atk)


def _is_boss(target) -> bool:
    """Les boss portent un attribut `gimmick` (contrairement aux monstres)."""
    return hasattr(target, "gimmick")


def player_attack(player: "PlayerState", monster: Monster, rng) -> int:
    if player.miss_chance > 0 and rng.random() < player.miss_chance:
        player.combo_count = 0
        return 0

    damage = player.atk
    if player.instable:
        damage += rng.randint(INSTABLE_SWING_MIN, INSTABLE_SWING_MAX)

    is_boss = _is_boss(monster)
    if is_boss and player.vs_boss_bonus:
        damage = round(damage * (1 + player.vs_boss_bonus))
    elif not is_boss and player.vs_monster_bonus:
        damage = round(damage * (1 + player.vs_monster_bonus))

    if player.combo_bonus:
        damage = round(damage * (1 + player.combo_bonus * player.combo_count))

    if player.low_hp_threshold > 0 and player.hp / player.max_hp <= player.low_hp_threshold:
        damage = round(damage * (1 + player.low_hp_bonus))

    if player.crit_chance > 0 and rng.random() < player.crit_chance:
        damage = round(damage * player.crit_multiplier)

    if player.summon_damage:
        damage += player.summon_damage

    dealt = monster.take_damage(damage)

    if player.combo_bonus:
        player.combo_count += 1

    # Effets d'arme à l'impact.
    if player.bleed_chance > 0 and rng.random() < player.bleed_chance:
        apply_status_effect(monster, StatusEffectKind.SAIGNEMENT, rounds=3, magnitude=4)
    if player.curse_chance > 0 and rng.random() < player.curse_chance:
        apply_status_effect(monster, StatusEffectKind.MALEDICTION, rounds=2, magnitude=3)
    if player.freeze_chance > 0 and rng.random() < player.freeze_chance:
        apply_status_effect(monster, StatusEffectKind.GEL, rounds=1)
    if player.stun_chance > 0 and rng.random() < player.stun_chance:
        apply_status_effect(monster, StatusEffectKind.GEL, rounds=1)
    if has_status(player, StatusEffectKind.BRULURE_ATTAQUE):
        apply_status_effect(monster, StatusEffectKind.BRULURE, rounds=3, magnitude=5)
    if has_status(player, StatusEffectKind.GEL_ATTAQUE):
        apply_status_effect(monster, StatusEffectKind.GEL, rounds=1)

    if player.lifesteal_ratio > 0:
        player.heal(round(dealt * player.lifesteal_ratio))
    return dealt


def monster_attack(monster: Monster, player: "PlayerState", rng) -> int:
    if player.block_charges > 0:
        player.block_charges -= 1
        return 0
    if player.dodge_chance > 0 and rng.random() < player.dodge_chance:
        return 0
    return player.take_damage(monster.atk)


@dataclass
class RoundResult:
    player_damage_dealt: int
    monster_damage_dealt: int
    player_frozen: bool = False
    monster_frozen: bool = False
    player_dot_damage: int = 0
    monster_dot_damage: int = 0


def resolve_round(player: "PlayerState", monster: Monster, rng, *, player_attacks: bool = True) -> RoundResult:
    player_dot_damage, _ = tick_statuses(player)
    monster_dot_damage, _ = tick_statuses(monster)

    player_frozen = consume_freeze(player)
    player_dealt = 0
    if player_attacks and not player_frozen:
        player_dealt = player_attack(player, monster, rng)

    monster_dealt = 0
    monster_frozen = False
    if monster.is_alive():
        monster_frozen = consume_freeze(monster)
        monster_dealt = 0 if monster_frozen else monster_attack(monster, player, rng)

    return RoundResult(
        player_damage_dealt=player_dealt,
        monster_damage_dealt=monster_dealt,
        player_frozen=player_frozen,
        monster_frozen=monster_frozen,
        player_dot_damage=player_dot_damage,
        monster_dot_damage=monster_dot_damage,
    )
