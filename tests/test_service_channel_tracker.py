from datetime import date

from services.channel_tracker import DailyChannelTracker


def test_first_message_in_channel_returns_true():
    tracker = DailyChannelTracker()

    assert tracker.record_channel(1, 100, date(2026, 7, 21)) is True


def test_second_message_in_same_channel_same_day_returns_false():
    tracker = DailyChannelTracker()
    tracker.record_channel(1, 100, date(2026, 7, 21))

    assert tracker.record_channel(1, 100, date(2026, 7, 21)) is False


def test_different_channel_same_day_returns_true():
    tracker = DailyChannelTracker()
    tracker.record_channel(1, 100, date(2026, 7, 21))

    assert tracker.record_channel(1, 200, date(2026, 7, 21)) is True


def test_same_channel_next_day_resets_and_returns_true():
    tracker = DailyChannelTracker()
    tracker.record_channel(1, 100, date(2026, 7, 21))

    assert tracker.record_channel(1, 100, date(2026, 7, 22)) is True


def test_tracking_is_independent_per_user():
    tracker = DailyChannelTracker()
    tracker.record_channel(1, 100, date(2026, 7, 21))

    assert tracker.record_channel(2, 100, date(2026, 7, 21)) is True
