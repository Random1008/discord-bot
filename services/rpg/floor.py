import random
from enum import Enum


class RoomType(Enum):
    COMBAT = "combat"
    TRESOR = "tresor"
    REPOS = "repos"
    PIEGE = "piege"
    ENIGME = "enigme"
    EVENEMENT = "evenement"


MAIN_ROOM_POOL = list(RoomType)


class OptionalRoomType(Enum):
    CASINO = "casino"
    SALLE_MAUDITE = "salle_maudite"


OPTIONAL_ROOM_POOL = list(OptionalRoomType)


def draw_main_rooms(rng: random.Random) -> list[RoomType]:
    return rng.sample(MAIN_ROOM_POOL, 3)


def draw_optional_rooms(rng: random.Random) -> list[OptionalRoomType]:
    return rng.sample(OPTIONAL_ROOM_POOL, 2)
