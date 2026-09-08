import time
from collections import deque

RAPID_MESSAGE_WINDOW_SECONDS = 5.0
MAX_MESSAGES_IN_WINDOW = 5
SPAM_MUTE_DURATION_SECONDS = 600.0
SPAM_XP_CLAWBACK_MESSAGE_COUNT = 10


class MessageSpamGuard:
    """Suppresses message XP during spam bursts: once a user sends 5 messages
    within a 5-second window, XP gain is cut off entirely for the next 10
    minutes — not just the triggering message, and not reset by a later gap
    between messages while the mute is active. The XP already granted for the
    user's last 10 XP-awarding messages can then be clawed back via
    record_awarded_xp/pop_clawback_amount."""

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._recent_timestamps: dict[int, deque] = {}
        self._muted_until: dict[int, float] = {}
        self._recent_xp: dict[int, deque] = {}

    def record_message(self, user_id: int) -> tuple[bool, bool]:
        """Returns (should_award_xp, spam_mute_just_triggered)."""
        now = self._clock()

        muted_until = self._muted_until.get(user_id)
        if muted_until is not None:
            if now < muted_until:
                return False, False
            del self._muted_until[user_id]
            self._recent_timestamps.pop(user_id, None)

        timestamps = self._recent_timestamps.setdefault(user_id, deque(maxlen=MAX_MESSAGES_IN_WINDOW))
        timestamps.append(now)

        if len(timestamps) == MAX_MESSAGES_IN_WINDOW and (now - timestamps[0]) < RAPID_MESSAGE_WINDOW_SECONDS:
            self._muted_until[user_id] = now + SPAM_MUTE_DURATION_SECONDS
            timestamps.clear()
            return False, True

        return True, False

    def record_awarded_xp(self, user_id: int, amount: int) -> None:
        """Tracks XP granted for a message, so it can be clawed back if the user is later muted for spam."""
        history = self._recent_xp.setdefault(user_id, deque(maxlen=SPAM_XP_CLAWBACK_MESSAGE_COUNT))
        history.append(amount)

    def pop_clawback_amount(self, user_id: int) -> int:
        """Returns and clears the sum of the user's last (up to 10) awarded message-XP amounts."""
        history = self._recent_xp.pop(user_id, None)
        if not history:
            return 0
        return sum(history)
