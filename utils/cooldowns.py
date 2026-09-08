from datetime import datetime, timezone


class CooldownManager:
    def __init__(self) -> None:
        self._data: dict[str, datetime] = {}

    def is_ready(self, key: str, seconds: int) -> bool:
        if key not in self._data:
            return True
        return (datetime.now(timezone.utc) - self._data[key]).total_seconds() >= seconds

    def set(self, key: str) -> None:
        self._data[key] = datetime.now(timezone.utc)

    def clear(self, key: str) -> None:
        self._data.pop(key, None)

    def has(self, key: str) -> bool:
        return key in self._data

    def remaining(self, key: str, seconds: int) -> str:
        if key not in self._data:
            return "0s"
        elapsed = (datetime.now(timezone.utc) - self._data[key]).total_seconds()
        rem = max(0, int(seconds - elapsed))
        h, r = divmod(rem, 3600)
        m, s = divmod(r, 60)
        if h:
            return f"{h}h {m}min"
        if m:
            return f"{m}min {s}s"
        return f"{s}s"
