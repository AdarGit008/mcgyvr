def span_merge(spans: list) -> list:
    merged = []
    for span in sorted(spans, key=lambda s: s[0]):
        if merged and span[0] <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], span[1])
        else:
            merged.append([span[0], span[1]])
    return merged
