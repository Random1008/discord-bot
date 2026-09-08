from services.prestige import multiplier_for_prestige, prestige_for_level


def test_prestige_for_level_thresholds():
    assert prestige_for_level(0) == 0
    assert prestige_for_level(99) == 0
    assert prestige_for_level(100) == 1
    assert prestige_for_level(199) == 1
    assert prestige_for_level(200) == 2
    assert prestige_for_level(300) == 3
    assert prestige_for_level(499) == 3
    assert prestige_for_level(500) == 4
    assert prestige_for_level(600) == 4


def test_multiplier_for_prestige():
    assert multiplier_for_prestige(0) == 1.0
    assert multiplier_for_prestige(1) == 1.1
    assert multiplier_for_prestige(2) == 1.2
    assert multiplier_for_prestige(3) == 1.3
    assert multiplier_for_prestige(4) == 1.5
