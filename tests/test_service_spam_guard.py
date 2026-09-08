from services.spam_guard import MAX_MESSAGES_IN_WINDOW, SPAM_MUTE_DURATION_SECONDS, MessageSpamGuard


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def advance(self, seconds):
        self.now += seconds

    def __call__(self):
        return self.now


def test_first_message_is_always_awarded():
    clock = FakeClock()
    guard = MessageSpamGuard(clock=clock)

    assert guard.record_message(1) == (True, False)


def test_first_messages_under_the_window_threshold_are_awarded():
    clock = FakeClock()
    guard = MessageSpamGuard(clock=clock)

    results = []
    for _ in range(MAX_MESSAGES_IN_WINDOW - 1):
        results.append(guard.record_message(1))
        clock.advance(0.5)

    assert results == [(True, False)] * (MAX_MESSAGES_IN_WINDOW - 1)


def test_fifth_message_within_five_seconds_triggers_the_spam_mute():
    clock = FakeClock()
    guard = MessageSpamGuard(clock=clock)

    for _ in range(MAX_MESSAGES_IN_WINDOW - 1):
        guard.record_message(1)
        clock.advance(0.5)

    assert guard.record_message(1) == (False, True)


def test_mute_is_only_reported_as_just_triggered_once():
    clock = FakeClock()
    guard = MessageSpamGuard(clock=clock)

    for _ in range(MAX_MESSAGES_IN_WINDOW - 1):
        guard.record_message(1)
        clock.advance(0.5)
    guard.record_message(1)  # triggers the mute

    clock.advance(1.0)
    assert guard.record_message(1) == (False, False)  # still muted, but not a new trigger


def test_mute_suppresses_xp_even_after_a_gap_longer_than_the_window():
    clock = FakeClock()
    guard = MessageSpamGuard(clock=clock)

    for _ in range(MAX_MESSAGES_IN_WINDOW - 1):
        guard.record_message(1)
        clock.advance(0.5)
    guard.record_message(1)  # triggers the mute

    clock.advance(30.0)  # a gap that would normally clear the window
    assert guard.record_message(1) == (False, False)  # mute still active


def test_xp_resumes_once_the_mute_duration_has_elapsed():
    clock = FakeClock()
    guard = MessageSpamGuard(clock=clock)

    for _ in range(MAX_MESSAGES_IN_WINDOW - 1):
        guard.record_message(1)
        clock.advance(0.5)
    guard.record_message(1)  # triggers the mute

    clock.advance(SPAM_MUTE_DURATION_SECONDS)
    assert guard.record_message(1) == (True, False)


def test_messages_spaced_more_than_the_window_apart_never_trigger_a_mute():
    clock = FakeClock()
    guard = MessageSpamGuard(clock=clock)

    results = []
    for _ in range(20):
        results.append(guard.record_message(1))
        clock.advance(2.0)

    assert all(should_award for should_award, _ in results)


def test_new_activity_after_the_mute_expires_is_not_immediately_flagged():
    clock = FakeClock()
    guard = MessageSpamGuard(clock=clock)

    for _ in range(MAX_MESSAGES_IN_WINDOW - 1):
        guard.record_message(1)
        clock.advance(0.5)
    assert guard.record_message(1) == (False, True)  # 5th rapid message triggers the mute

    clock.advance(SPAM_MUTE_DURATION_SECONDS)  # let the mute expire
    clock.advance(1.0)

    assert guard.record_message(1) == (True, False)


def test_different_users_are_tracked_independently():
    clock = FakeClock()
    guard = MessageSpamGuard(clock=clock)

    for _ in range(MAX_MESSAGES_IN_WINDOW):
        guard.record_message(1)
        clock.advance(0.5)

    assert guard.record_message(2) == (True, False)


def test_pop_clawback_amount_sums_the_recorded_message_xp():
    guard = MessageSpamGuard()

    guard.record_awarded_xp(1, 10)
    guard.record_awarded_xp(1, 15)
    guard.record_awarded_xp(1, 5)

    assert guard.pop_clawback_amount(1) == 30


def test_pop_clawback_amount_only_keeps_the_last_ten_entries():
    guard = MessageSpamGuard()

    for amount in range(1, 13):  # 12 entries, only the last 10 (3..12) should count
        guard.record_awarded_xp(1, amount)

    assert guard.pop_clawback_amount(1) == sum(range(3, 13))


def test_pop_clawback_amount_returns_zero_when_nothing_was_recorded():
    guard = MessageSpamGuard()

    assert guard.pop_clawback_amount(1) == 0


def test_pop_clawback_amount_clears_history_after_popping():
    guard = MessageSpamGuard()
    guard.record_awarded_xp(1, 10)

    assert guard.pop_clawback_amount(1) == 10
    assert guard.pop_clawback_amount(1) == 0


def test_pop_clawback_amount_is_isolated_per_user():
    guard = MessageSpamGuard()
    guard.record_awarded_xp(1, 10)
    guard.record_awarded_xp(2, 20)

    assert guard.pop_clawback_amount(1) == 10
    assert guard.pop_clawback_amount(2) == 20
