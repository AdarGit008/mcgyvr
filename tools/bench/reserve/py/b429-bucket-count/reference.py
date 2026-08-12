def bucket_count(readings: list, width: int) -> dict:
    buckets = {}
    for reading in readings:
        low = reading // width * width
        buckets[low] = buckets.get(low, 0) + 1
    return buckets
