def parse_role_config(text: str) -> dict[str, int | None]:
    config: dict[str, int | None] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        key = key.strip()
        value = value.strip()
        config[key] = int(value) if value else None
    return config


def compute_role_changes(current_holder_ids: set[int], new_holder_id: int | None) -> tuple[set[int], int | None]:
    if new_holder_id is None:
        return current_holder_ids, None
    to_remove = current_holder_ids - {new_holder_id}
    to_add = None if new_holder_id in current_holder_ids else new_holder_id
    return to_remove, to_add


def compute_multi_role_changes(current_holder_ids: set[int], eligible_ids: set[int]) -> tuple[set[int], set[int]]:
    to_remove = current_holder_ids - eligible_ids
    to_add = eligible_ids - current_holder_ids
    return to_remove, to_add
