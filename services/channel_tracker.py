from datetime import date as Date


class DailyChannelTracker:
    """Tracks, per user and calendar date, which channels a user has already posted in today."""

    def __init__(self):
        self._seen: dict[int, tuple[Date, set[int]]] = {}

    def record_channel(self, user_id: int, channel_id: int, today: Date) -> bool:
        entry = self._seen.get(user_id)
        if entry is None or entry[0] != today:
            self._seen[user_id] = (today, {channel_id})
            return True

        _seen_date, channels = entry
        if channel_id in channels:
            return False
        channels.add(channel_id)
        return True
