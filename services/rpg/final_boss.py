from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from services.rpg.bosses import Boss, BossGimmick, scale_boss
from services.rpg.combat import monster_attack, player_attack
from services.rpg.status_effects import StatusEffectKind, apply_status_effect, consume_freeze, tick_statuses

if TYPE_CHECKING:
    from services.rpg.achievements import PlayerStats
    from services.rpg.legacy import Legacy
    from services.rpg.player import PlayerState

FINAL_BOSS_FLOOR = 100
FINAL_BOSS_HP_MULTIPLIER = 1.5
PHASE_2_HP_RATIO = 0.66
PHASE_3_HP_RATIO = 0.33
ABILITY_CHANCE = 0.5


def create_final_boss(ng_plus: int = 0) -> Boss:
    boss = scale_boss(FINAL_BOSS_FLOOR, BossGimmick.LE_COEUR_DE_LA_TOUR, "Le Cœur de la Tour", ng_plus=ng_plus)
    boss.hp = boss.max_hp = round(boss.max_hp * FINAL_BOSS_HP_MULTIPLIER)
    return boss


@dataclass
class FinalBossState:
    boss: Boss
    announced_phases: set = field(default_factory=set)


def create_final_boss_state(ng_plus: int = 0) -> FinalBossState:
    return FinalBossState(boss=create_final_boss(ng_plus=ng_plus))


def current_phase(boss: Boss) -> int:
    ratio = boss.hp / boss.max_hp if boss.max_hp else 0
    if ratio > PHASE_2_HP_RATIO:
        return 1
    if ratio > PHASE_3_HP_RATIO:
        return 2
    return 3


def phase_dialogue(phase: int, stats: "PlayerStats", legacy: "Legacy", codex_discovered: int) -> str:
    if phase == 1:
        return (
            "« Je t'ai regardé grimper mes marches... "
            f"{stats.monsters_killed} créatures sont tombées sous ta lame, "
            f"{stats.gold_earned_total} pièces d'or ont traversé tes mains. Voyons ce que tu vaux vraiment. »"
        )
    if phase == 2:
        if stats.deaths > 0:
            deaths_note = f"Tu es mort {stats.deaths} fois avant de me trouver, et pourtant tu es revenu."
        else:
            deaths_note = "Tu n'es jamais tombé avant moi. Voyons si cela dure."
        return f"« {deaths_note} Le Cœur se met à saigner de lumière... »"
    return (
        "« "
        f"Tu as découvert {codex_discovered} de mes salles secrètes, "
        f"traversé {len(legacy.history)} vies avant celle-ci. "
        "Ceci est ma dernière forme. »"
    )


def _apply_phase_ability(boss: Boss, player: "PlayerState", phase: int, rng) -> str | None:
    if rng.random() >= ABILITY_CHANCE:
        return None
    if phase == 1:
        apply_status_effect(player, StatusEffectKind.MALEDICTION, rounds=3, magnitude=3)
        return "Le Cœur de la Tour murmure une malédiction : ta force et ta garde faiblissent."
    if phase == 2:
        apply_status_effect(player, StatusEffectKind.BRULURE, rounds=3, magnitude=6)
        apply_status_effect(boss, StatusEffectKind.RAGE, rounds=2, magnitude=5)
        return "Des flammes anciennes s'enroulent autour de toi tandis que le Cœur s'embrase de rage."
    apply_status_effect(player, StatusEffectKind.SAIGNEMENT, rounds=3, magnitude=8)
    apply_status_effect(player, StatusEffectKind.GEL, rounds=1)
    return "Le Cœur déchire ta chair et fige le temps autour de toi."


@dataclass
class FinalBossRoundResult:
    player_damage_dealt: int
    monster_damage_dealt: int
    player_dot_damage: int
    boss_dot_damage: int
    player_frozen: bool
    ability_message: str | None
    phase: int
    phase_intro: str | None


def resolve_final_boss_round(
    state: FinalBossState,
    player: "PlayerState",
    stats: "PlayerStats",
    legacy: "Legacy",
    codex_discovered: int,
    rng,
    *,
    player_attacks: bool = True,
) -> FinalBossRoundResult:
    boss = state.boss
    phase = current_phase(boss)
    phase_intro = None
    if phase not in state.announced_phases:
        state.announced_phases.add(phase)
        phase_intro = phase_dialogue(phase, stats, legacy, codex_discovered)

    player_dot_damage, _ = tick_statuses(player)
    boss_dot_damage, _ = tick_statuses(boss)

    player_frozen = consume_freeze(player)
    player_dealt = 0
    if player_attacks and not player_frozen:
        player_dealt = player_attack(player, boss, rng)

    ability_message = None
    monster_dealt = 0
    if boss.is_alive():
        ability_message = _apply_phase_ability(boss, player, phase, rng)
        boss_frozen = consume_freeze(boss)
        if not boss_frozen:
            monster_dealt = monster_attack(boss, player, rng)

    return FinalBossRoundResult(
        player_damage_dealt=player_dealt,
        monster_damage_dealt=monster_dealt,
        player_dot_damage=player_dot_damage,
        boss_dot_damage=boss_dot_damage,
        player_frozen=player_frozen,
        ability_message=ability_message,
        phase=phase,
        phase_intro=phase_intro,
    )
