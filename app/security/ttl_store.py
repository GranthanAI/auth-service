"""Bounded in-memory TTL store used as the fallback when Redis is unavailable.

Entries expire on their own and the store never grows past ``max_entries`` (least-recently-used entries are evicted),
so an attacker rotating IPs/emails cannot grow process memory without bound.
"""
import time
from collections import OrderedDict


class BoundedTTLStore:
    def __init__(self, max_entries: int = 10_000):
        self.max_entries = max_entries
        self._data: OrderedDict[str, tuple[int, float]] = OrderedDict()  # key -> (value, expires_at)

    def __len__(self) -> int:
        return len(self._data)

    def get(self, key: str, now: float | None = None) -> tuple[int, float] | None:
        """Return (value, expires_at) or None if missing/expired."""
        now = time.time() if now is None else now
        entry = self._data.get(key)
        if entry is None:
            return None
        if entry[1] <= now:
            del self._data[key]
            return None
        self._data.move_to_end(key)
        return entry

    def set(self, key: str, value: int, expires_at: float) -> None:
        self._data[key] = (value, expires_at)
        self._data.move_to_end(key)
        if len(self._data) > self.max_entries:
            self._purge_expired()
        while len(self._data) > self.max_entries:
            self._data.popitem(last=False)

    def incr(self, key: str, ttl_seconds: float, now: float | None = None) -> tuple[int, float]:
        """Increment within a fixed window started by the first hit. Returns (count, expires_at)."""
        now = time.time() if now is None else now
        entry = self.get(key, now)
        if entry is None:
            self.set(key, 1, now + ttl_seconds)
            return 1, now + ttl_seconds
        self.set(key, entry[0] + 1, entry[1])
        return entry[0] + 1, entry[1]

    def delete(self, key: str) -> None:
        self._data.pop(key, None)

    def clear(self) -> None:
        self._data.clear()

    def _purge_expired(self) -> None:
        now = time.time()
        for k in [k for k, (_, exp) in self._data.items() if exp <= now]:
            del self._data[k]
