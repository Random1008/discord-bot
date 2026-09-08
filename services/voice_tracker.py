import time

from services.xp import VOICE_XP_INTERVAL_SECONDS


class VoiceTracker:
    """Tracks per-user voice presence eligible for XP (channel has >=2 non-bot members)."""

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._eligible_since: dict[int, float] = {}
        self._accumulated: dict[int, float] = {}

    def update_channel(self, user_id: int, channel_id: int | None, human_count: int) -> int:
        now = self._clock()
        self._flush_eligibility(user_id, now)

        if channel_id is not None and human_count >= 2:
            self._eligible_since[user_id] = now
        else:
            self._eligible_since.pop(user_id, None)

        accumulated = self._accumulated.get(user_id, 0.0)
        payable_seconds = int(accumulated // VOICE_XP_INTERVAL_SECONDS) * VOICE_XP_INTERVAL_SECONDS
        if payable_seconds:
            self._accumulated[user_id] = accumulated - payable_seconds

        if channel_id is None:
            self._accumulated.pop(user_id, None)
            self._eligible_since.pop(user_id, None)

        return payable_seconds

    def _flush_eligibility(self, user_id: int, now: float) -> None:
        since = self._eligible_since.get(user_id)
        if since is None:
            return
        elapsed = now - since
        self._accumulated[user_id] = self._accumulated.get(user_id, 0.0) + elapsed
