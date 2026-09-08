from services.role_reconciliation import compute_expected_reward_role_ids, compute_role_diff, resolve_role_ids


class FakeSettings:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


def test_resolve_role_ids_skips_unset_settings():
    settings = FakeSettings(role_actif_id="111", role_habitue_id=None)
    mapping = {"role_actif": "role_actif_id", "role_habitue": "role_habitue_id"}

    resolved = resolve_role_ids(mapping, settings)

    assert resolved == {"role_actif": 111}


def test_compute_expected_reward_role_ids_is_cumulative_across_thresholds():
    reward_role_ids = {"role_actif": 111, "role_habitue": 222, "role_veteran": 333}
    reward_thresholds = {"role_actif": 5, "role_habitue": 20, "role_veteran": 40}

    expected = compute_expected_reward_role_ids(25, 0, reward_role_ids, reward_thresholds, {})

    assert expected == {111, 222}


def test_compute_expected_reward_role_ids_includes_cumulative_prestige_tiers():
    prestige_role_ids = {1: 501, 2: 502, 3: 503, 4: 504}

    expected = compute_expected_reward_role_ids(999, 2, {}, {}, prestige_role_ids)

    assert expected == {501, 502}


def test_compute_expected_reward_role_ids_empty_below_every_threshold():
    reward_role_ids = {"role_actif": 111}
    reward_thresholds = {"role_actif": 5}

    expected = compute_expected_reward_role_ids(3, 0, reward_role_ids, reward_thresholds, {})

    assert expected == set()


def test_compute_role_diff_adds_missing_and_leaves_unmanaged_roles_alone():
    current = {111, 999}  # 999 is unrelated to this system
    expected = {111, 222}
    managed = {111, 222, 333}

    to_add, to_remove = compute_role_diff(current, expected, managed)

    assert to_add == {222}
    assert to_remove == set()


def test_compute_role_diff_removes_managed_role_no_longer_expected():
    current = {111, 222}
    expected = {111}
    managed = {111, 222}

    to_add, to_remove = compute_role_diff(current, expected, managed)

    assert to_add == set()
    assert to_remove == {222}
