from services.gacha_logic import (
    CHARACTERS_BY_RARITY,
    PityState,
    RARITY_ORDER,
    apply_pity,
    pick_character,
    pull,
    rarity_rank,
    roll_bonus_fragments,
    roll_rarity,
    update_pity,
)


class FakeRandom:
    def __init__(self, value):
        self.value = value

    def random(self):
        return self.value

    def randint(self, a, b):
        return a


class FakeChoiceRandom(FakeRandom):
    def __init__(self, value, choice_value):
        super().__init__(value)
        self.choice_value = choice_value

    def choice(self, seq):
        return self.choice_value


def test_rarity_rank_orders_by_rarity():
    assert rarity_rank("Commun") < rarity_rank("Rare") < rarity_rank("Secret")


def test_roll_rarity_returns_commun_at_zero_roll():
    assert roll_rarity(FakeRandom(0.0)) == "Commun"


def test_roll_rarity_returns_secret_at_top_roll():
    assert roll_rarity(FakeRandom(0.9999)) == "Secret"


def test_roll_rarity_mythique_bonus_can_push_a_commun_roll_into_mythique():
    assert roll_rarity(FakeRandom(0.55), mythique_bonus=0.60) == "Mythique"


def test_apply_pity_forces_epique_at_threshold():
    pity = PityState(pulls_since_epique=10)
    assert apply_pity("Commun", pity) == "Épique"


def test_apply_pity_does_not_downgrade_already_higher_rarity():
    pity = PityState(pulls_since_epique=10)
    assert apply_pity("Légendaire", pity) == "Légendaire"


def test_apply_pity_mythique_takes_priority_over_epique():
    pity = PityState(pulls_since_epique=50, pulls_since_mythique=100)
    assert apply_pity("Commun", pity) == "Mythique"


def test_update_pity_resets_counters_at_or_above_rarity():
    pity = PityState(pulls_since_epique=5, pulls_since_legendaire=5, pulls_since_mythique=5)
    update_pity(pity, "Épique")
    assert pity.pulls_since_epique == 0
    assert pity.pulls_since_legendaire == 6
    assert pity.pulls_since_mythique == 6


def test_pick_character_returns_none_for_empty_pool():
    assert pick_character("Secret", FakeChoiceRandom(0.0, "n/a")) is None


def test_pick_character_returns_from_matching_pool():
    name = pick_character("Commun", FakeChoiceRandom(0.0, CHARACTERS_BY_RARITY["Commun"][0]))
    assert name == CHARACTERS_BY_RARITY["Commun"][0]


def test_roll_bonus_fragments_secret_is_always_ten():
    assert roll_bonus_fragments("Secret", FakeRandom(0.99)) == 10


def test_roll_bonus_fragments_commun_can_be_zero():
    assert roll_bonus_fragments("Commun", FakeRandom(0.99)) == 0


def test_pull_updates_pity_state_and_returns_result():
    pity = PityState()
    result = pull(pity, FakeChoiceRandom(0.0, "Comptable"))
    assert result.rarity == "Commun"
    assert pity.pulls_since_epique == 1


def test_rarity_order_has_six_tiers():
    assert RARITY_ORDER == ["Commun", "Rare", "Épique", "Légendaire", "Mythique", "Secret"]
