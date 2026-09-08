from dataclasses import dataclass
from enum import Enum


class StatusEffectKind(Enum):
    BRULURE = "brulure"
    GEL = "gel"
    SAIGNEMENT = "saignement"
    RAGE = "rage"
    MALEDICTION = "malediction"
    GARDE = "garde"
    PRECISION = "precision"
    AGILITE = "agilite"
    VAMPIRISME = "vampirisme"
    BRULURE_ATTAQUE = "brulure_attaque"
    GEL_ATTAQUE = "gel_attaque"


DOT_KINDS = {StatusEffectKind.BRULURE, StatusEffectKind.SAIGNEMENT}
STAT_KINDS = {
    StatusEffectKind.RAGE,
    StatusEffectKind.MALEDICTION,
    StatusEffectKind.GARDE,
    StatusEffectKind.PRECISION,
    StatusEffectKind.AGILITE,
    StatusEffectKind.VAMPIRISME,
}

_DOT_LABELS = {
    StatusEffectKind.BRULURE: "brûlure",
    StatusEffectKind.SAIGNEMENT: "saignement",
}


@dataclass
class StatusEffect:
    kind: StatusEffectKind
    remaining_rounds: int
    magnitude: float = 0.0
    applied_atk_delta: int = 0
    applied_defense_delta: int = 0
    applied_crit_delta: float = 0.0
    applied_dodge_delta: float = 0.0
    applied_lifesteal_delta: float = 0.0


def _revert_stat_effect(target, effect: "StatusEffect") -> None:
    target.atk -= effect.applied_atk_delta
    target.defense -= effect.applied_defense_delta
    if effect.applied_crit_delta:
        target.crit_chance = getattr(target, "crit_chance", 0.0) - effect.applied_crit_delta
    if effect.applied_dodge_delta:
        target.dodge_chance = getattr(target, "dodge_chance", 0.0) - effect.applied_dodge_delta
    if effect.applied_lifesteal_delta:
        target.lifesteal_ratio = getattr(target, "lifesteal_ratio", 0.0) - effect.applied_lifesteal_delta


def apply_status_effect(target, kind: StatusEffectKind, rounds: int, magnitude: float = 0.0) -> StatusEffect | None:
    """Applique (ou rafraîchit) un effet de statut. `target` doit exposer
    `.statuses`, `.atk`, `.defense` (et `.crit_chance`/`.dodge_chance`/
    `.lifesteal_ratio` pour les buffs). Retourne None si l'effet est annulé
    (immunité Gardien du Néant) ou réduit à néant (résistance aux
    malédictions)."""
    if getattr(target, "negates_statuses", False):
        return None

    reduction = getattr(target, "status_duration_reduction", 0)
    rounds = max(1, rounds - reduction)

    if kind == StatusEffectKind.MALEDICTION:
        resistance = getattr(target, "curse_resistance", 0.0)
        if resistance > 0:
            magnitude = round(magnitude * (1 - resistance))
        if magnitude <= 0:
            return None

    existing = next((e for e in target.statuses if e.kind == kind), None)
    if existing is not None:
        _revert_stat_effect(target, existing)
        target.statuses.remove(existing)

    effect = StatusEffect(kind=kind, remaining_rounds=rounds, magnitude=magnitude)
    if kind == StatusEffectKind.RAGE:
        effect.applied_atk_delta = int(magnitude)
        target.atk += int(magnitude)
    elif kind == StatusEffectKind.MALEDICTION:
        before_atk, before_defense = target.atk, target.defense
        target.atk = max(1, target.atk - int(magnitude))
        target.defense = max(0, target.defense - int(magnitude))
        effect.applied_atk_delta = target.atk - before_atk
        effect.applied_defense_delta = target.defense - before_defense
    elif kind == StatusEffectKind.GARDE:
        effect.applied_defense_delta = int(magnitude)
        target.defense += int(magnitude)
    elif kind == StatusEffectKind.PRECISION:
        effect.applied_crit_delta = magnitude
        target.crit_chance = getattr(target, "crit_chance", 0.0) + magnitude
    elif kind == StatusEffectKind.AGILITE:
        effect.applied_dodge_delta = magnitude
        target.dodge_chance = getattr(target, "dodge_chance", 0.0) + magnitude
    elif kind == StatusEffectKind.VAMPIRISME:
        effect.applied_lifesteal_delta = magnitude
        target.lifesteal_ratio = getattr(target, "lifesteal_ratio", 0.0) + magnitude
    # BRULURE_ATTAQUE / GEL_ATTAQUE : simples drapeaux, aucune stat modifiée.
    target.statuses.append(effect)
    return effect


def has_status(target, kind: StatusEffectKind) -> bool:
    return any(e.kind == kind for e in target.statuses)


def consume_freeze(target) -> bool:
    """Décrémente un GEL actif d'une utilisation. Retourne True si la cible
    était figée ce round (son action est sautée)."""
    effect = next((e for e in target.statuses if e.kind == StatusEffectKind.GEL), None)
    if effect is None:
        return False
    effect.remaining_rounds -= 1
    if effect.remaining_rounds <= 0:
        target.statuses.remove(effect)
    return True


def tick_statuses(target) -> tuple[int, list[str]]:
    """Appelé une fois par round de combat. Applique les dégâts sur la durée
    (BRULURE/SAIGNEMENT), décrémente la durée des effets (révertant les deltas
    de stats à expiration) et laisse GEL tranquille (géré par consume_freeze).
    Retourne (total_dot_damage, messages)."""
    total_damage = 0
    messages: list[str] = []
    for effect in list(target.statuses):
        if effect.kind in DOT_KINDS:
            magnitude = effect.magnitude
            if effect.kind == StatusEffectKind.BRULURE:
                resistance = getattr(target, "burn_resistance", 0.0)
                magnitude = round(magnitude * (1 - resistance))
            dealt = target.take_damage(magnitude)
            total_damage += dealt
            messages.append(f"{dealt} dégâts de {_DOT_LABELS[effect.kind]}")
        if effect.kind == StatusEffectKind.GEL:
            continue
        effect.remaining_rounds -= 1
        if effect.remaining_rounds <= 0:
            if effect.kind in STAT_KINDS:
                _revert_stat_effect(target, effect)
            target.statuses.remove(effect)
    return total_damage, messages
