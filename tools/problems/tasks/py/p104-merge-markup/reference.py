def merge_markup(spans: list) -> list:
    by_tag = {}
    for span in spans:
        start = span.get("start")
        end = span.get("end")
        tag = span.get("tag")
        if (
            not isinstance(start, int)
            or isinstance(start, bool)
            or not isinstance(end, int)
            or isinstance(end, bool)
        ):
            raise ValueError("span bounds must be integers")
        if start < 0 or start >= end:
            raise ValueError("bad span bounds")
        if not isinstance(tag, str) or tag == "":
            raise ValueError("bad tag")
        by_tag.setdefault(tag, []).append([start, end])
    merged = []
    for tag, pieces in by_tag.items():
        pieces.sort()
        lo, hi = pieces[0]
        for s, e in pieces[1:]:
            if s <= hi:
                hi = max(hi, e)
            else:
                merged.append([lo, hi, tag])
                lo, hi = s, e
        merged.append([lo, hi, tag])
    merged.sort(key=lambda triple: (triple[0], triple[1]))
    for previous, current in zip(merged, merged[1:]):
        if current[0] < previous[1]:
            raise ValueError("spans with different tags share a position")
    return merged
