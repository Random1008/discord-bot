from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from services.rpg.combat import NG_PLUS_MULTIPLIER_PER_LEVEL, player_attack, monster_attack, scale_monster
from services.rpg.status_effects import consume_freeze, tick_statuses

if TYPE_CHECKING:
    from services.rpg.player import PlayerState

BOSS_FLOOR_INTERVAL = 10
BOSS_HP_MULTIPLIER = 3
BOSS_ATK_MULTIPLIER = 1.5
MIRROR_REFLECT_RATIO = 0.3
BOUCHER_HEAL_RATIO = 0.4
ROI_PARESSEUX_CHARGE = 3
BETE_INSTABLE_STATES = [(0.5, 6), (1.0, 0), (1.5, -2)]
HORLOGER_FREEZE_CHANCE = 0.5
ROI_PARESSEUX_ATK_CAP_MULTIPLIER = 3.0


class BossGimmick(Enum):
    GARDIEN_MIROIR = "gardien_miroir"
    BOUCHER_AFFAME = "boucher_affame"
    FAUX_HEROS = "faux_heros"
    ROI_PARESSEUX = "roi_paresseux"
    BETE_INSTABLE = "bete_instable"
    HORLOGER_DE_LA_TOUR = "horloger_de_la_tour"
    LE_COEUR_DE_LA_TOUR = "le_coeur_de_la_tour"


@dataclass
class Boss:
    name: str
    gimmick: BossGimmick
    hp: int
    max_hp: int
    atk: int
    defense: int = 0
    statuses: list = field(default_factory=list)
    base_atk: int = 0
    base_defense: int = 0

    def take_damage(self, amount: int) -> int:
        dealt = max(1, amount - self.defense)
        self.hp -= dealt
        return dealt

    def heal(self, amount: int) -> int:
        healed = min(amount, self.max_hp - self.hp)
        self.hp += healed
        return healed

    def is_alive(self) -> bool:
        return self.hp > 0


def is_boss_floor(floor: int) -> bool:
    return floor % BOSS_FLOOR_INTERVAL == 0


def scale_boss(floor: int, gimmick: BossGimmick, name: str, ng_plus: int = 0) -> Boss:
    base = scale_monster(floor)
    ng_plus_multiplier = 1 + NG_PLUS_MULTIPLIER_PER_LEVEL * ng_plus
    hp = round(base.hp * BOSS_HP_MULTIPLIER * ng_plus_multiplier)
    atk = round(base.atk * BOSS_ATK_MULTIPLIER * ng_plus_multiplier)
    return Boss(name=name, gimmick=gimmick, hp=hp, max_hp=hp, atk=atk, base_atk=atk)


BOSS_NAMES = {
    BossGimmick.GARDIEN_MIROIR: "Gardien Miroir",
    BossGimmick.BOUCHER_AFFAME: "Boucher Affamé",
    BossGimmick.ROI_PARESSEUX: "Roi Paresseux",
    BossGimmick.BETE_INSTABLE: "Bête Instable",
    BossGimmick.HORLOGER_DE_LA_TOUR: "Horloger de la Tour",
    BossGimmick.LE_COEUR_DE_LA_TOUR: "Le Cœur de la Tour",
}

REGULAR_BOSS_GIMMICKS = [g for g in BossGimmick if g != BossGimmick.LE_COEUR_DE_LA_TOUR]


def random_boss(floor: int, player: "PlayerState", rng, ng_plus: int = 0) -> Boss:
    gimmick = rng.choice(REGULAR_BOSS_GIMMICKS)
    if gimmick == BossGimmick.FAUX_HEROS:
        return make_faux_heros(player)
    return scale_boss(floor, gimmick, BOSS_NAMES[gimmick], ng_plus=ng_plus)


def make_faux_heros(player: "PlayerState") -> Boss:
    return Boss(
        name="Faux Héros",
        gimmick=BossGimmick.FAUX_HEROS,
        hp=player.max_hp,
        max_hp=player.max_hp,
        atk=player.atk,
        defense=player.defense,
        base_atk=player.atk,
        base_defense=player.defense,
    )


@dataclass
class BossRoundResult:
    player_damage_dealt: int
    reflected_damage: int
    monster_damage_dealt: int
    healed: int
    frozen: bool = False
    player_dot_damage: int = 0
    boss_dot_damage: int = 0
    player_status_frozen: bool = False


def resolve_boss_round(player: "PlayerState", boss: Boss, rng, *, player_attacks: bool = True) -> BossRoundResult:
    player_dot_damage, _ = tick_statuses(player)
    boss_dot_damage, _ = tick_statuses(boss)

    if boss.gimmick == BossGimmick.BETE_INSTABLE:
        factor, defense = rng.choice(BETE_INSTABLE_STATES)
        boss.atk = max(1, round(boss.base_atk * factor))
        boss.defense = defense

    horloger_frozen = boss.gimmick == BossGimmick.HORLOGER_DE_LA_TOUR and rng.random() < HORLOGER_FREEZE_CHANCE
    player_status_frozen = consume_freeze(player)
    frozen = horloger_frozen or player_status_frozen
    player_dealt = 0
    if player_attacks and not frozen:
        player_dealt = player_attack(player, boss, rng)

    reflected = 0
    if player_dealt > 0 and boss.gimmick == BossGimmick.GARDIEN_MIROIR:
        reflected = player.take_damage(round(player_dealt * MIRROR_REFLECT_RATIO))

    monster_dealt = 0
    healed = 0
    if boss.is_alive():
        boss_frozen = consume_freeze(boss)
        if not boss_frozen:
            monster_dealt = monster_attack(boss, player, rng)
            if boss.gimmick == BossGimmick.BOUCHER_AFFAME:
                healed = boss.heal(round(monster_dealt * BOUCHER_HEAL_RATIO))

    if boss.gimmick == BossGimmick.ROI_PARESSEUX:
        cap = round(boss.base_atk * ROI_PARESSEUX_ATK_CAP_MULTIPLIER)
        boss.atk = min(boss.atk + ROI_PARESSEUX_CHARGE, cap)

    return BossRoundResult(
        player_damage_dealt=player_dealt,
        reflected_damage=reflected,
        monster_damage_dealt=monster_dealt,
        healed=healed,
        frozen=frozen,
        player_dot_damage=player_dot_damage,
        boss_dot_damage=boss_dot_damage,
        player_status_frozen=player_status_frozen,
    )
