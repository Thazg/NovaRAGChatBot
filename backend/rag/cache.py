from collections import OrderedDict
from threading import RLock
from typing import Any


class SimpleCache:
    def __init__(self, max_entries: int = 128):
        self.max_entries = max_entries
        self._store: OrderedDict[str, Any] = OrderedDict()
        self._lock = RLock()

    def get(self, key: str):
        with self._lock:
            if key not in self._store:
                return None
            self._store.move_to_end(key)
            return self._store[key]

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._store[key] = value
            self._store.move_to_end(key)
            while len(self._store) > self.max_entries:
                self._store.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
