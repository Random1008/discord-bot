from dataclasses import dataclass
from enum import Enum
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from services.rpg.player import PlayerState


class Rarity(Enum):
    COMMUNE = "commune"
    PEU_COMMUNE = "peu_commune"
    RARE = "rare"
    TRES_RARE = "tres_rare"
    LEGENDAIRE = "legendaire"


RARITY_WEIGHTS = {
    Rarity.COMMUNE: 50,
    Rarity.PEU_COMMUNE: 25,
    Rarity.RARE: 15,
    Rarity.TRES_RARE: 8,
    Rarity.LEGENDAIRE: 2,
}


UNLOCK_FLOOR_BY_RARITY = {
    Rarity.COMMUNE: 1,
    Rarity.PEU_COMMUNE: 1,
    Rarity.RARE: 10,
    Rarity.TRES_RARE: 20,
    Rarity.LEGENDAIRE: 30,
}

LEVEL_2_VISIT_THRESHOLD = 3
LEVEL_3_VISIT_THRESHOLD = 6
GENERIC_LEVEL_BONUS_GOLD_PER_LEVEL = 5


@dataclass
class RoomLevel:
    name: str
    description: str
    effect: Callable[["PlayerState", object], str]


@dataclass
class UniqueRoom:
    key: str
    name: str
    rarity: Rarity
    description: str
    effect: Callable[["PlayerState", object], str]
    levels: list[RoomLevel] | None = None

    @property
    def unlock_floor(self) -> int:
        return UNLOCK_FLOOR_BY_RARITY[self.rarity]


def _miroir_fissure(player, rng):
    player.crit_chance += 0.05
    return "Un fragment de vous-même vous observe. Vos réflexes s'affûtent."


def _miroir_fissure_avance(player, rng):
    player.crit_chance += 0.08
    player.crit_multiplier += 0.2
    return "Le reflet devient plus net : vos coups critiques sont plus dévastateurs."


def _miroir_du_veritable_moi(player, rng):
    player.crit_chance += 0.12
    player.dodge_chance += 0.05
    return "Vous fusionnez avec votre reflet : critique et esquive s'améliorent durablement."


def _arene_brisee(player, rng):
    dealt = player.take_damage(rng.randint(10, 20))
    gained = rng.randint(30, 50)
    player.add_gold(gained)
    return f"Un combattant fantôme vous blesse ({dealt} dégâts) puis s'incline, laissant {gained} or."


def _salle_des_murmures(player, rng):
    healed = player.heal(round(player.max_hp * 0.1))
    return f"Des murmures apaisants vous soignent de {healed} PV."


def _salle_des_murmures_avancee(player, rng):
    healed = player.heal(round(player.max_hp * 0.2))
    player.crit_chance += 0.02
    return f"Les murmures se font plus clairs et vous soignent de {healed} PV en aiguisant vos sens."


def _coeur_des_murmures(player, rng):
    healed = player.heal(player.max_hp)
    player.crit_chance += 0.05
    return f"Le Cœur des Murmures vous soigne entièrement ({healed} PV) et grave sa voix en vous."


def _laboratoire_instable(player, rng):
    if rng.random() < 0.5:
        player.atk += 3
        return "Une potion instable renforce votre force."
    player.defense = max(0, player.defense - 2)
    return "Une potion instable corrode votre armure."


def _laboratoire_instable_avance(player, rng):
    if rng.random() < 0.5:
        player.atk += 5
        return "Une potion plus concentrée renforce nettement votre force."
    player.defense = max(0, player.defense - 3)
    return "Une potion plus concentrée corrode plus fortement votre armure."


def _coeur_du_laboratoire(player, rng):
    player.atk += 6
    player.instable = True
    return "Le cœur du laboratoire instabilise durablement vos coups, plus forts mais imprévisibles."


def _sanctuaire_du_refus(player, rng):
    player.heal(player.max_hp)
    return "Le sanctuaire vous purifie entièrement, mais n'offre rien d'autre."


def _sanctuaire_du_refus_avance(player, rng):
    player.heal(player.max_hp)
    player.block_charges += 1
    return "Le sanctuaire vous purifie et vous accorde une garde supplémentaire."


def _sanctuaire_inviolable(player, rng):
    player.heal(player.max_hp)
    player.extra_lives += 1
    return "Le sanctuaire devient inviolable : soin complet et une vie supplémentaire."


def _salle_maudite_silencieuse(player, rng):
    player.defense = max(0, player.defense - 2)
    player.gold_multiplier *= 1.2
    return "Une malédiction silencieuse affaiblit votre garde mais aiguise votre avidité."


def _chambre_du_sommeil_trompeur(player, rng):
    if rng.random() < 0.5:
        healed = player.heal(round(player.max_hp * 0.2))
        return f"Un sommeil bienfaiteur vous rend {healed} PV."
    dealt = player.take_damage(rng.randint(5, 10))
    return f"Un cauchemar vous inflige {dealt} dégâts."


def _autel_derniere_chance(player, rng):
    player.extra_lives += 1
    return "L'autel vous accorde une ultime chance de survie."


def _forge_brisee(player, rng):
    player.atk += 4
    player.defense = max(0, player.defense - 1)
    return "La forge brisée renforce votre arme au prix de votre protection."


def _forge_brisee_avancee(player, rng):
    player.atk += 6
    return "La forge crépite plus fort et forge une lame plus tranchante (+6 ATK)."


def _coeur_de_la_forge(player, rng):
    player.atk += 10
    player.defense += 2
    return "Le cœur incandescent de la forge renforce durablement votre arme et votre armure."


def _salle_du_pacte(player, rng):
    player.max_hp = max(1, player.max_hp - 15)
    player.hp = min(player.hp, player.max_hp)
    player.atk += 6
    return "Un pacte avec la tour échange votre vitalité contre de la puissance."


def _salle_du_pacte_avancee(player, rng):
    player.max_hp = max(1, player.max_hp - 10)
    player.hp = min(player.hp, player.max_hp)
    player.atk += 9
    return "Le pacte s'approfondit : encore plus de puissance, encore moins de vitalité."


def _pacte_ultime(player, rng):
    player.max_hp = max(1, player.max_hp - 20)
    player.hp = min(player.hp, player.max_hp)
    player.atk += 15
    player.lifesteal_ratio += 0.1
    return "Le pacte ultime scelle votre destin : puissance et vol de vie contre vitalité."


def _couloir_instable(player, rng):
    gained = rng.randint(5, 15)
    player.add_gold(gained)
    return f"Vous trouvez {gained} or éparpillé dans le couloir tremblant."


def _salle_du_hasard_total(player, rng):
    roll = rng.random()
    if roll < 0.25:
        healed = player.heal(20)
        return f"Le hasard vous soigne de {healed} PV."
    if roll < 0.5:
        dealt = player.take_damage(10)
        return f"Le hasard vous inflige {dealt} dégâts."
    if roll < 0.75:
        player.add_gold(25)
        return "Le hasard vous offre 25 or."
    player.defense = max(0, player.defense - 3)
    return "Le hasard corrode votre défense."


def _crypte_du_faux_heros(player, rng):
    gained = player.atk * 3
    player.add_gold(gained)
    return f"Le tombeau du faux héros vous rend hommage : {gained} or."


def _salle_des_chaines(player, rng):
    player.dodge_chance += 0.05
    return "Vous brisez des chaînes anciennes, plus agile qu'avant."


def _bibliotheque_dechiree(player, rng):
    player.xp += 15
    return "Des pages arrachées vous enseignent un savoir oublié (+15 XP)."


def _salle_echange_force(player, rng):
    exchanged = min(player.gold, 20)
    player.add_gold(-exchanged)
    healed = player.heal(exchanged)
    return f"Un marché forcé échange {exchanged} or contre {healed} PV."


def _chambre_du_battement(player, rng):
    cost = min(player.gold, 15)
    player.add_gold(-cost)
    player.max_hp += 10
    player.hp += 10
    return f"Un cœur de pierre bat plus fort en vous pour {cost} or (+10 PV max)."


def _salle_du_jugement(player, rng):
    if player.gold >= 50:
        player.add_gold(50)
        return "La tour juge votre richesse digne et double votre offrande."
    player.defense = max(0, player.defense - 2)
    return "La tour juge votre pauvreté insuffisante et vous punit."


def _antichambre_du_boss(player, rng):
    player.heal(player.max_hp)
    player.block_charges += 1
    return "Un dernier répit avant le boss : soins complets et une garde assurée."


def _salle_de_la_memoire(player, rng):
    player.xp += 30
    return "La tour partage un souvenir précieux avec vous (+30 XP)."


UNIQUE_ROOMS = [
    UniqueRoom("miroir_fissure", "Salle du Miroir Fissuré", Rarity.RARE,
               "Un miroir brisé reflète une version différente de vous.", _miroir_fissure,
               levels=[
                   RoomLevel("Salle du Miroir Fissuré Avancée",
                              "Le reflet brisé se recompose lentement.", _miroir_fissure_avance),
                   RoomLevel("Miroir du Véritable Moi",
                              "Vous ne faites plus qu'un avec votre reflet.", _miroir_du_veritable_moi),
               ]),
    UniqueRoom("arene_brisee", "Arène Brisée", Rarity.PEU_COMMUNE,
               "Les ruines d'une arène résonnent encore de combats passés.", _arene_brisee),
    UniqueRoom("salle_des_murmures", "Salle des Murmures", Rarity.COMMUNE,
               "Des voix indistinctes chuchotent depuis les murs.", _salle_des_murmures,
               levels=[
                   RoomLevel("Salle des Murmures Avancée",
                              "Les voix se font plus nettes et plus bienveillantes.", _salle_des_murmures_avancee),
                   RoomLevel("Cœur des Murmures",
                              "Le cœur de la salle bat au rythme de mille voix.", _coeur_des_murmures),
               ]),
    UniqueRoom("laboratoire_instable", "Laboratoire Instable", Rarity.RARE,
               "Des fioles bouillonnent dangereusement sur des étagères penchées.", _laboratoire_instable,
               levels=[
                   RoomLevel("Laboratoire Instable Avancé",
                              "Les fioles bouillonnent plus violemment.", _laboratoire_instable_avance),
                   RoomLevel("Cœur du Laboratoire",
                              "Le cœur du laboratoire bat d'une énergie instable.", _coeur_du_laboratoire),
               ]),
    UniqueRoom("sanctuaire_du_refus", "Sanctuaire du Refus", Rarity.PEU_COMMUNE,
               "Un lieu paisible qui refuse toute violence.", _sanctuaire_du_refus,
               levels=[
                   RoomLevel("Sanctuaire du Refus Avancé",
                              "La paix du lieu s'approfondit.", _sanctuaire_du_refus_avance),
                   RoomLevel("Sanctuaire Inviolable",
                              "Rien ne peut plus vous atteindre ici.", _sanctuaire_inviolable),
               ]),
    UniqueRoom("salle_maudite_silencieuse", "Salle Maudite Silencieuse", Rarity.PEU_COMMUNE,
               "Le silence ici est oppressant, presque vivant.", _salle_maudite_silencieuse),
    UniqueRoom("chambre_du_sommeil_trompeur", "Chambre du Sommeil Trompeur", Rarity.COMMUNE,
               "Un lit confortable cache peut-être un piège.", _chambre_du_sommeil_trompeur),
    UniqueRoom("autel_derniere_chance", "Autel de la Dernière Chance", Rarity.LEGENDAIRE,
               "Un autel ancien promet un sursis face à la mort.", _autel_derniere_chance),
    UniqueRoom("forge_brisee", "Forge Brisée", Rarity.RARE,
               "Une forge abandonnée crépite encore d'une chaleur résiduelle.", _forge_brisee,
               levels=[
                   RoomLevel("Forge Brisée Avancée",
                              "La chaleur résiduelle devient une vraie fournaise.", _forge_brisee_avancee),
                   RoomLevel("Cœur de la Forge",
                              "Le cœur incandescent de la forge s'éveille.", _coeur_de_la_forge),
               ]),
    UniqueRoom("salle_du_pacte", "Salle du Pacte", Rarity.TRES_RARE,
               "La tour propose un pacte : puissance contre vitalité.", _salle_du_pacte,
               levels=[
                   RoomLevel("Salle du Pacte Avancée",
                              "La tour exige un pacte plus profond.", _salle_du_pacte_avancee),
                   RoomLevel("Pacte Ultime",
                              "Le pacte final scelle votre destin.", _pacte_ultime),
               ]),
    UniqueRoom("couloir_instable", "Couloir Instable", Rarity.COMMUNE,
               "Le sol tremble sous vos pas dans ce couloir fissuré.", _couloir_instable),
    UniqueRoom("salle_du_hasard_total", "Salle du Hasard Total", Rarity.RARE,
               "Tout ici semble régi par un hasard absolu.", _salle_du_hasard_total),
    UniqueRoom("crypte_du_faux_heros", "Crypte du Faux Héros", Rarity.TRES_RARE,
               "Une tombe honore un héros qui n'a peut-être jamais existé.", _crypte_du_faux_heros),
    UniqueRoom("salle_des_chaines", "Salle des Chaînes", Rarity.PEU_COMMUNE,
               "Des chaînes rouillées pendent du plafond.", _salle_des_chaines),
    UniqueRoom("bibliotheque_dechiree", "Bibliothèque Déchirée", Rarity.COMMUNE,
               "Des livres éventrés jonchent le sol de cette bibliothèque.", _bibliotheque_dechiree),
    UniqueRoom("salle_echange_force", "Salle de l'Échange Forcé", Rarity.RARE,
               "Une balance ancienne exige un échange équitable.", _salle_echange_force),
    UniqueRoom("chambre_du_battement", "Chambre du Battement", Rarity.PEU_COMMUNE,
               "Un battement sourd résonne comme un cœur de pierre.", _chambre_du_battement),
    UniqueRoom("salle_du_jugement", "Salle du Jugement", Rarity.LEGENDAIRE,
               "Une présence invisible évalue votre valeur.", _salle_du_jugement),
    UniqueRoom("antichambre_du_boss", "Antichambre du Boss", Rarity.COMMUNE,
               "Le calme avant la tempête, juste avant l'antre du boss.", _antichambre_du_boss),
    UniqueRoom("salle_de_la_memoire", "Salle de la Mémoire", Rarity.TRES_RARE,
               "La tour vous montre un fragment de son passé.", _salle_de_la_memoire),
]


def drawable_rooms(floor: int) -> list[UniqueRoom]:
    return [room for room in UNIQUE_ROOMS if room.unlock_floor <= floor]


def draw_unique_room(rng, floor: int) -> UniqueRoom:
    candidates = drawable_rooms(floor)
    weights = [RARITY_WEIGHTS[room.rarity] for room in candidates]
    return rng.choices(candidates, weights=weights, k=1)[0]


def room_level_for_visits(visit_count: int) -> int:
    if visit_count >= LEVEL_3_VISIT_THRESHOLD:
        return 3
    if visit_count >= LEVEL_2_VISIT_THRESHOLD:
        return 2
    return 1


def resolve_room_visit(room: UniqueRoom, visit_count: int, player: "PlayerState", rng) -> tuple[str, str, str]:
    """Resolves a unique room's effect at the level implied by visit_count.
    Returns (display_name, message, description)."""
    level = room_level_for_visits(visit_count)
    if room.levels is not None and level >= 2:
        room_level = room.levels[level - 2]
        message = room_level.effect(player, rng)
        return room_level.name, message, room_level.description

    message = room.effect(player, rng)
    if level >= 2:
        bonus_gold = GENERIC_LEVEL_BONUS_GOLD_PER_LEVEL * (level - 1)
        player.add_gold(bonus_gold)
        message = f"{message} (Niveau {level} de la salle : +{bonus_gold} or bonus.)"
    return room.name, message, room.description
