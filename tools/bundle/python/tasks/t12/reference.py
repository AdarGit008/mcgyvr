def drop_small(counts: dict[str, int], threshold: int) -> dict[str, int]:
    """Delete entries below threshold in place and return the same dict."""
    for key in [k for k, v in counts.items() if v < threshold]:
        del counts[key]
    return counts
