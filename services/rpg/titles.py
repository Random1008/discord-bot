"""Titres de la Tour RPG (20), débloqués par des accomplissements persistants."""

from dataclasses import dataclass
from typing import Callable

from services.rpg.rarity import Rarity


@dataclass
class TitleProgress:
    """Toutes les métriques persistantes nécessaires à l'évaluation des titres."""
    floor_reached_max: int = 0
    monsters_killed: int = 0
    gold_earned_total: int = 0
    deaths: int = 0
    rooms_discovered: int = 0
    chests_opened: int = 0
    casino_wins: int = 0
    jackpots: int = 0
    boss_kills: int = 0
    curses_survived: int = 0
    pacts_used: int = 0
    runs_completed: int = 0
    infinite_mode_reached: bool = False
    all_rooms_discovered: bool = False
    all_bosses_defeated: bool = False
    all_achievements: bool = False
    all_classes_unlocked: bool = False


@dataclass
class Title:
    key: str
    name: str
    rarity: Rarity
    description: str
    check: Callable[[TitleProgress], bool]


TITLES = [
    Title("aventurier_debutant", "Aventurier Débutant", Rarity.COMMUNE,
          "Atteindre l'étage 10", lambda p: p.floor_reached_max >= 10),
    Title("survivant", "Survivant", Rarity.COMMUNE,
          "Mourir 10 fois", lambda p: p.deaths >= 10),
    Title("explorateur", "Explorateur", Rarity.COMMUNE,
          "Découvrir 25 salles", lambda p: p.rooms_discovered >= 25),
    Title("chasseur_de_gobelins", "Chasseur de Gobelins", Rarity.COMMUNE,
          "Tuer 100 monstres", lambda p: p.monsters_killed >= 100),
    Title("chercheur_de_tresors", "Chercheur de Trésors", Rarity.PEU_COMMUNE,
          "Ouvrir 50 coffres", lambda p: p.chests_opened >= 50),
    Title("marchand", "Marchand", Rarity.PEU_COMMUNE,
          "Gagner 10 000 Or", lambda p: p.gold_earned_total >= 10000),
    Title("chanceux", "Chanceux", Rarity.PEU_COMMUNE,
          "Gagner au casino 25 fois", lambda p: p.casino_wins >= 25),
    Title("veteran", "Vétéran", Rarity.PEU_COMMUNE,
          "Atteindre l'étage 30", lambda p: p.floor_reached_max >= 30),
    Title("chasseur_de_boss", "Chasseur de Boss", Rarity.RARE,
          "Battre 25 boss", lambda p: p.boss_kills >= 25),
    Title("briseur_de_maledictions", "Briseur de Malédictions", Rarity.RARE,
          "Survivre à 50 malédictions", lambda p: p.curses_survived >= 50),
    Title("maitre_du_casino", "Maître du Casino", Rarity.RARE,
          "Gagner un jackpot", lambda p: p.jackpots >= 1),
    Title("porteur_du_pacte", "Porteur du Pacte", Rarity.RARE,
          "Utiliser 50 pactes", lambda p: p.pacts_used >= 50),
    Title("heros_de_la_tour", "Héros de la Tour", Rarity.TRES_RARE,
          "Finir une run", lambda p: p.runs_completed >= 1),
    Title("seigneur_des_secrets", "Seigneur des Secrets", Rarity.TRES_RARE,
          "Découvrir toutes les salles secrètes", lambda p: p.all_rooms_discovered),
    Title("tueur_de_titans", "Tueur de Titans", Rarity.TRES_RARE,
          "Battre tous les boss", lambda p: p.all_bosses_defeated),
    Title("maitre_des_etages", "Maître des Étages", Rarity.TRES_RARE,
          "Atteindre l'étage 100", lambda p: p.floor_reached_max >= 100),
    Title("elu_de_la_tour", "Élu de la Tour", Rarity.LEGENDAIRE,
          "Finir 5 runs", lambda p: p.runs_completed >= 5),
    Title("legende_vivante", "Légende Vivante", Rarity.LEGENDAIRE,
          "Débloquer tout le contenu",
          lambda p: p.all_classes_unlocked and p.all_rooms_discovered and p.all_achievements),
    Title("gardien_eternel", "Gardien Éternel", Rarity.LEGENDAIRE,
          "Atteindre le mode infini", lambda p: p.infinite_mode_reached),
    Title("createur_de_destin", "Créateur de Destin", Rarity.MYTHIQUE,
          "Obtenir tous les succès", lambda p: p.all_achievements),
]


def check_new_titles(progress: TitleProgress, already_unlocked: set[str]) -> list[Title]:
    return [t for t in TITLES if t.key not in already_unlocked and t.check(progress)]
