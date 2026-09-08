from services.leaderboard_roles import compute_multi_role_changes, compute_role_changes, parse_role_config


def test_parse_role_config_reads_filled_and_empty_values():
    text = """# comment line
roi_du_chat: 123456789
maitre_vocal:
top_10: 987654321
"""
    config = parse_role_config(text)

    assert config == {"roi_du_chat": 123456789, "maitre_vocal": None, "top_10": 987654321}


def test_parse_role_config_ignores_blank_lines():
    text = "roi_du_chat: 111\n\nmaitre_vocal: 222\n"

    config = parse_role_config(text)

    assert config == {"roi_du_chat": 111, "maitre_vocal": 222}


def test_compute_role_changes_removes_old_holders_adds_new():
    to_remove, to_add = compute_role_changes({1, 2}, 3)

    assert to_remove == {1, 2}
    assert to_add == 3


def test_compute_role_changes_no_change_when_holder_unchanged():
    to_remove, to_add = compute_role_changes({1}, 1)

    assert to_remove == set()
    assert to_add is None


def test_compute_role_changes_no_leaderboard_data_removes_all_keeps_none_to_add():
    to_remove, to_add = compute_role_changes({1, 2}, None)

    assert to_remove == {1, 2}
    assert to_add is None


def test_compute_role_changes_empty_holders_adds_new_leader():
    to_remove, to_add = compute_role_changes(set(), 5)

    assert to_remove == set()
    assert to_add == 5


def test_compute_multi_role_changes_removes_ineligible_adds_new_eligible():
    to_remove, to_add = compute_multi_role_changes({1, 2, 3}, {2, 3, 4})

    assert to_remove == {1}
    assert to_add == {4}


def test_compute_multi_role_changes_no_change_when_holders_match_eligible():
    to_remove, to_add = compute_multi_role_changes({1, 2}, {1, 2})

    assert to_remove == set()
    assert to_add == set()


def test_compute_multi_role_changes_empty_eligible_removes_everyone():
    to_remove, to_add = compute_multi_role_changes({1, 2}, set())

    assert to_remove == {1, 2}
    assert to_add == set()
