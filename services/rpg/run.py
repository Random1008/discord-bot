import random
from dataclasses import dataclass, field

from services.rpg.bosses import Boss, is_boss_floor, random_boss
from services.rpg.floor import OptionalRoomType, RoomType, draw_main_rooms, draw_optional_rooms
from services.rpg.player import PlayerState


@dataclass
class FloorState:
    number: int
    main_rooms: list[RoomType] = field(default_factory=list)
    optional_rooms: list[OptionalRoomType] = field(default_factory=list)
    boss: Boss | None = None


@dataclass
class Run:
    player: PlayerState
    floor: FloorState


def generate_floor(number: int, player: PlayerState, rng: random.Random, ng_plus: int = 0) -> FloorState:
    if is_boss_floor(number):
        return FloorState(number=number, boss=random_boss(number, player, rng, ng_plus=ng_plus))
    return FloorState(
        number=number,
        main_rooms=draw_main_rooms(rng),
        optional_rooms=draw_optional_rooms(rng),
    )


def start_run(player: PlayerState, rng: random.Random, ng_plus: int = 0) -> Run:
    return Run(player=player, floor=generate_floor(1, player, rng, ng_plus=ng_plus))


def advance_floor(run: Run, rng: random.Random, ng_plus: int = 0) -> None:
    run.floor = generate_floor(run.floor.number + 1, run.player, rng, ng_plus=ng_plus)
