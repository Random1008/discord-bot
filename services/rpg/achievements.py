from dataclasses import dataclass
from typing import Callable


@dataclass
class PlayerStats:
    floor_reached_max: int = 0
    monsters_killed: int = 0
    gold_earned_total: int = 0
    deaths: int = 0
    boss_no_damage_wins: int = 0


@dataclass
class Achievement:
    key: str
    name: str
    description: str
    check: Callable[[PlayerStats], bool]


ACHIEVEMENTS = [
    Achievement("etage_10", "Explorateur", "Atteindre l'étage 10.",
                lambda s: s.floor_reached_max >= 10),
    Achievement("etage_50", "Grimpeur Aguerri", "Atteindre l'étage 50.",
                lambda s: s.floor_reached_max >= 50),
    Achievement("finir_la_tour", "Vainqueur de la Tour", "Atteindre l'étage 100.",
                lambda s: s.floor_reached_max >= 100),
    Achievement("tuer_100_monstres", "Exterminateur", "Tuer 100 monstres.",
                lambda s: s.monsters_killed >= 100),
    Achievement("gagner_1000_pieces", "Fortune Faite", "Gagner 1000 pièces d'or au total.",
                lambda s: s.gold_earned_total >= 1000),
    Achievement("mourir_50_fois", "Increvable", "Mourir 50 fois.",
                lambda s: s.deaths >= 50),
    Achievement("boss_sans_degats", "Intouchable", "Battre un boss sans subir de dégâts.",
                lambda s: s.boss_no_damage_wins >= 1),
]


def check_new_achievements(stats: PlayerStats, already_unlocked: set[str]) -> list[Achievement]:
    return [a for a in ACHIEVEMENTS if a.key not in already_unlocked and a.check(stats)]
