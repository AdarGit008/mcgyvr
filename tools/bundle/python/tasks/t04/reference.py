class LRUCache:
    """Least-recently-used cache with a fixed capacity."""

    def __init__(self, capacity: int):
        if capacity <= 0:
            raise ValueError(f"capacity must be positive, got {capacity}")
        self.capacity = capacity
        self._data: dict = {}

    def get(self, key):
        """Return the value for key, refreshing its recency; None if absent."""
        if key not in self._data:
            return None
        value = self._data.pop(key)
        self._data[key] = value
        return value

    def put(self, key, value) -> None:
        """Insert or update key, evicting the least recently used if full."""
        if key in self._data:
            self._data.pop(key)
        elif len(self._data) >= self.capacity:
            oldest = next(iter(self._data))
            del self._data[oldest]
        self._data[key] = value
