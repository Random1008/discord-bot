from services.xp import (
    EVENT_PARTICIPATION_XP,
    INVITE_VALIDATION_XP,
    REACTION_XP,
    roll_message_xp,
    voice_xp_for_seconds,
)


class FixedRng:
    def __init__(self, value):
        self.value = value

    def randint(self, low, high):
        return self.value


def test_roll_message_xp_within_range():
    for _ in range(50):
        assert 5 <= roll_message_xp() <= 15


def test_roll_message_xp_uses_injected_rng():
    assert roll_message_xp(rng=FixedRng(9)) == 9


def test_voice_xp_for_seconds_pays_per_ten_minutes():
    assert voice_xp_for_seconds(0) == 0
    assert voice_xp_for_seconds(599) == 0
    assert voice_xp_for_seconds(600) == 10
    assert voice_xp_for_seconds(1199) == 10
    assert voice_xp_for_seconds(1200) == 20


def test_flat_xp_constants():
    assert REACTION_XP == 2
    assert EVENT_PARTICIPATION_XP == 50
    assert INVITE_VALIDATION_XP == 200
