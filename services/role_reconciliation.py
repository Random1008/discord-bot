def resolve_role_ids(mapping: dict, settings) -> dict:
    """Resolves a {key: settings_attr_name} mapping to {key: role_id}, skipping unset roles."""
    resolved = {}
    for key, setting_name in mapping.items():
        role_id = getattr(settings, setting_name, None)
        if role_id:
            resolved[key] = int(role_id)
    return resolved


def compute_expected_reward_role_ids(
    level: int,
    prestige: int,
    reward_role_ids: dict[str, int],
    reward_thresholds: dict[str, int],
    prestige_role_ids: dict[int, int],
) -> set[int]:
    """Role/prestige tiers are cumulative milestones (matching how badges already work):
    reaching level 40 keeps the level-20 role too, prestige 2 keeps the prestige-1 role too.
    """
    expected = set()
    for reward_value, role_id in reward_role_ids.items():
        threshold = reward_thresholds.get(reward_value)
        if threshold is not None and level >= threshold:
            expected.add(role_id)
    for tier, role_id in prestige_role_ids.items():
        if prestige >= tier:
            expected.add(role_id)
    return expected


def compute_role_diff(
    current_role_ids: set[int], expected_role_ids: set[int], managed_role_ids: set[int]
) -> tuple[set[int], set[int]]:
    """Returns (to_add, to_remove). Removal is restricted to `managed_role_ids` so this
    never touches a role unrelated to the reward/prestige system being reconciled."""
    to_add = expected_role_ids - current_role_ids
    to_remove = (current_role_ids & managed_role_ids) - expected_role_ids
    return to_add, to_remove
