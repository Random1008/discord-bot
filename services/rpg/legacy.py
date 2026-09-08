from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.rpg.player import PlayerState


@dataclass
class DeathRecord:
    floor_reached: int
    monsters_killed: int
    gold_earned: int


@dataclass
class Legacy:
    history: list[DeathRecord] = field(default_factory=list)


def record_death(legacy: Legacy, record: DeathRecord) -> None:
    legacy.history.append(record)


def apply_legacy_bonus(player: "PlayerState", legacy: Legacy) -> None:
    # Bounded: only the single best ascent (highest floor reached) leaves a
    # permanent mark, so dying many times can't snowball into trivial runs.
    if not legacy.history:
        return
    best_floor = max(record.floor_reached for record in legacy.history)
    player.atk += best_floor // 5
    player.defense += best_floor // 10
    player.max_hp += best_floor * 2
    player.hp += best_floor * 2


def death_message(record: DeathRecord) -> str:
    return (
        f"Tu es mort à l'étage {record.floor_reached}... "
        "mais la Tour se souvient de toi."
    )
