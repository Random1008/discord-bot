def diff_invite_uses(before: dict[str, int], after: dict[str, int]) -> str | None:
    """Return the invite code whose use count increased between two snapshots,
    or None if it can't be determined (e.g. vanity URL join, or no change found)."""
    for code, uses_after in after.items():
        if uses_after > before.get(code, 0):
            return code
    return None
