from datetime import datetime

ALT_ACCOUNT_THRESHOLD_DAYS = 7
ALT_ACCOUNT_XP_MULTIPLIER = 0.2


def is_recent_account(created_at: datetime, now: datetime, threshold_days: int = ALT_ACCOUNT_THRESHOLD_DAYS) -> bool:
    """A Discord account younger than `threshold_days` is treated as a possible alt."""
    return (now - created_at).days < threshold_days


def apply_alt_penalty(amount: int, flagged: bool, multiplier: float = ALT_ACCOUNT_XP_MULTIPLIER) -> int:
    """Reduce an XP amount for a flagged (possible alt) account instead of blocking it outright."""
    if not flagged or amount <= 0:
        return amount
    return max(1, round(amount * multiplier))
