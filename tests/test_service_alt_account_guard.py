from datetime import datetime, timedelta, timezone

from services.alt_account_guard import (
    ALT_ACCOUNT_THRESHOLD_DAYS,
    apply_alt_penalty,
    is_recent_account,
)


def test_is_recent_account_true_for_account_created_today():
    now = datetime(2026, 7, 22, tzinfo=timezone.utc)
    created_at = now - timedelta(days=1)

    assert is_recent_account(created_at, now) is True


def test_is_recent_account_false_at_exact_threshold():
    now = datetime(2026, 7, 22, tzinfo=timezone.utc)
    created_at = now - timedelta(days=ALT_ACCOUNT_THRESHOLD_DAYS)

    assert is_recent_account(created_at, now) is False


def test_is_recent_account_false_for_old_account():
    now = datetime(2026, 7, 22, tzinfo=timezone.utc)
    created_at = now - timedelta(days=365)

    assert is_recent_account(created_at, now) is False


def test_apply_alt_penalty_reduces_amount_when_flagged():
    assert apply_alt_penalty(100, flagged=True) == 20


def test_apply_alt_penalty_never_rounds_down_to_zero():
    assert apply_alt_penalty(2, flagged=True) == 1


def test_apply_alt_penalty_leaves_amount_untouched_when_not_flagged():
    assert apply_alt_penalty(100, flagged=False) == 100


def test_apply_alt_penalty_leaves_non_positive_amount_untouched():
    assert apply_alt_penalty(0, flagged=True) == 0
