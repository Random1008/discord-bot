from services.leveling import level_for_xp, xp_for_level


def test_xp_for_level_matches_formula():
    assert xp_for_level(0) == 0
    assert xp_for_level(1) == 100
    assert xp_for_level(5) == 2500
    assert xp_for_level(10) == 10000


def test_level_for_xp_matches_formula():
    assert level_for_xp(0) == 0
    assert level_for_xp(99) == 0
    assert level_for_xp(100) == 1
    assert level_for_xp(2499) == 4
    assert level_for_xp(2500) == 5
    assert level_for_xp(9999) == 9
    assert level_for_xp(10000) == 10
