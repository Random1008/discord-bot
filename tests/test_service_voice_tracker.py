from services.voice_tracker import VoiceTracker


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def advance(self, seconds):
        self.now += seconds

    def __call__(self):
        return self.now


def test_no_payout_below_two_humans():
    clock = FakeClock()
    tracker = VoiceTracker(clock=clock)

    tracker.update_channel(1, channel_id=100, human_count=1)
    clock.advance(700)
    payout = tracker.update_channel(1, channel_id=100, human_count=1)

    assert payout == 0


def test_payout_after_ten_minutes_with_two_humans():
    clock = FakeClock()
    tracker = VoiceTracker(clock=clock)

    tracker.update_channel(1, channel_id=100, human_count=2)
    clock.advance(650)
    payout = tracker.update_channel(1, channel_id=100, human_count=2)

    assert payout == 600


def test_remainder_carries_over_across_channel_move():
    clock = FakeClock()
    tracker = VoiceTracker(clock=clock)

    tracker.update_channel(1, channel_id=100, human_count=2)
    clock.advance(650)
    first_payout = tracker.update_channel(1, channel_id=200, human_count=2)  # moved channel
    clock.advance(550)
    second_payout = tracker.update_channel(1, channel_id=200, human_count=2)

    assert first_payout == 600
    assert second_payout == 600  # 50s leftover + 550s new = 600s


def test_disconnect_drops_unpaid_remainder():
    clock = FakeClock()
    tracker = VoiceTracker(clock=clock)

    tracker.update_channel(1, channel_id=100, human_count=2)
    clock.advance(300)
    payout = tracker.update_channel(1, channel_id=None, human_count=0)
    clock.advance(300)
    tracker.update_channel(1, channel_id=100, human_count=2)
    second_payout = tracker.update_channel(1, channel_id=100, human_count=2)

    assert payout == 0
    assert second_payout == 0  # the 300s before disconnect was dropped, not carried
