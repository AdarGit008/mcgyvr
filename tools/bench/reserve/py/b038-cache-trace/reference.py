"""Replay a request trace against a bounded key cache with
least-recently-used eviction, recording hits, misses, removals and
evictions along with the final residency, most recently used first,
the hottest key and the peak residency."""


def trace_cache(capacity: int, requests: list) -> dict:
    if isinstance(capacity, bool) or not isinstance(capacity, int):
        raise ValueError("capacity must be a positive integer")
    if capacity < 1:
        raise ValueError("capacity must be a positive integer")
    if not isinstance(requests, list):
        raise ValueError("requests must be a list")
    contents = []  # most recently used first
    evictions = []
    hit_counts = {}
    hits = 0
    misses = 0
    dropped = 0
    peak = 0
    for request in requests:
        if not isinstance(request, list) or len(request) != 2:
            raise ValueError("each trace entry is an [operation, key] pair")
        op, key = request
        if op not in ("get", "put", "del"):
            raise ValueError("operation must be get, put or del")
        if not isinstance(key, str) or key == "":
            raise ValueError("key must be a non-empty string")
        resident = key in contents
        if op == "get":
            if not resident:
                misses += 1
            else:
                hits += 1
                hit_counts[key] = hit_counts.get(key, 0) + 1
                contents.remove(key)
                contents.insert(0, key)
        elif op == "put":
            if resident:
                contents.remove(key)
            contents.insert(0, key)
            if len(contents) > capacity:
                evictions.append(contents.pop())
        elif resident:
            contents.remove(key)
            dropped += 1
        if len(contents) > peak:
            peak = len(contents)
    hot_key = None
    best = 0
    for key in hit_counts:
        count = hit_counts[key]
        if hot_key is None or count > best or (count == best and key < hot_key):
            hot_key = key
            best = count
    return {
        "hits": hits,
        "misses": misses,
        "dropped": dropped,
        "evictions": evictions,
        "contents": contents,
        "hot_key": hot_key,
        "peak": peak,
    }
