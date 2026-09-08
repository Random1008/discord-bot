from dataclasses import dataclass, field


@dataclass
class PlayerState:
    hp: int
    max_hp: int
    atk: int
    defense: int
    gold: int = 0
    crit_chance: float = 0.0
    crit_multiplier: float = 2.0
    dodge_chance: float = 0.0
    block_charges: int = 0
    lifesteal_ratio: float = 0.0
    low_hp_threshold: float = 0.0
    low_hp_bonus: float = 0.0
    extra_lives: int = 0
    gold_multiplier: float = 1.0
    no_potions: bool = False
    instable: bool = False
    miss_chance: float = 0.0
    xp: int = 0
    level: int = 1
    statuses: list = field(default_factory=list)
    bag: list[str] = field(default_factory=list)
    revive_hp_ratio: float = 0.5
    heal_bonus_ratio: float = 0.0

    # --- Bonus de classe (voir services/rpg/classes.py) ---
    curse_chance: float = 0.0          # chance d'infliger MALEDICTION à l'ennemi en frappant
    vs_monster_bonus: float = 0.0      # multiplicateur de dégâts contre les monstres (non-boss)
    vs_boss_bonus: float = 0.0         # multiplicateur de dégâts contre les boss
    summon_damage: int = 0             # dégâts d'invocation supplémentaires par round
    combo_bonus: float = 0.0           # bonus de dégâts par coup consécutif (Moine)
    combo_count: int = 0               # compteur de combo (runtime)
    heal_on_kill_ratio: float = 0.0    # % de PV max rendu à chaque ennemi vaincu
    atk_on_kill: int = 0               # ATK permanente gagnée à chaque ennemi vaincu
    freeze_chance: float = 0.0         # chance de geler l'ennemi en frappant (Chronomancien)
    negates_statuses: bool = False     # immunité aux effets de statut (Gardien du Néant)
    legacy_bonus_multiplier: float = 0.0  # amplifie le bonus de legacy (Héritier)
    floor_scaling: bool = False        # stats qui montent à chaque étage (Élu du Créateur)

    # --- Bonus de trait (voir services/rpg/traits.py) ---
    combat_random_bonus: bool = False  # bonus aléatoire au début de chaque combat (Instable)
    shop_discount: float = 0.0         # réduction de prix en boutique (Économe)
    treasure_multiplier: float = 0.0   # bonus d'or des trésors (Collectionneur)
    regen_ratio: float = 0.0           # % de PV max régénéré après chaque combat (Survivant)
    unique_room_chance_bonus: float = 0.0  # +chance de salle rare (Visionnaire)
    xp_multiplier: float = 0.0         # bonus d'XP de run (Ancienne Âme)
    curse_resistance: float = 0.0      # résistance aux malédictions (Porteur des Ombres)
    floor_random_bonus: bool = False   # bonus aléatoire à chaque étage (Favori de la Tour)

    # --- Bonus d'équipement (voir services/rpg/equipment.py) ---
    bleed_chance: float = 0.0          # chance d'infliger SAIGNEMENT en frappant (arme)
    stun_chance: float = 0.0           # chance d'étourdir l'ennemi (arme)
    burn_resistance: float = 0.0       # résistance à la brûlure (armure)
    damage_reduction: int = 0          # réduction forfaitaire des dégâts subis (armure)
    copy_enemy_stats_ratio: float = 0.0  # part de l'ATK ennemie copiée en début de combat (arme)
    weapon_floor_growth: int = 0       # +ATK par étage (arme)
    armor_floor_growth: int = 0        # +DEF par étage (armure)
    lethal_guard: bool = False         # ignore un coup mortel une fois par run (armure)
    status_duration_reduction: int = 0  # réduit la durée des effets subis (armure)

    def take_damage(self, amount: int) -> int:
        amount = max(1, amount - self.defense)
        if self.damage_reduction:
            amount = max(1, amount - self.damage_reduction)
        self.hp -= amount
        if self.hp <= 0:
            if self.lethal_guard:
                self.lethal_guard = False
                self.hp = 1
            elif self.extra_lives > 0:
                self.extra_lives -= 1
                self.hp = round(self.max_hp * self.revive_hp_ratio)
        return amount

    def heal(self, amount: int) -> int:
        amount = round(amount * (1 + self.heal_bonus_ratio))
        healed = min(amount, self.max_hp - self.hp)
        self.hp += healed
        return healed

    def is_alive(self) -> bool:
        return self.hp > 0

    def add_gold(self, amount: int, *, apply_multiplier: bool = True) -> None:
        if amount > 0 and apply_multiplier:
            amount = round(amount * self.gold_multiplier)
        self.gold += amount
