"""Prune a file listing with ordered drop and keep rules."""


def prune_listing(listing, rules):
    def segment_fits(pattern, text):
        p = t = mark = 0
        star = -1
        while t < len(text):
            if p < len(pattern) and pattern[p] == "*":
                star = p
                mark = t
                p += 1
            elif p < len(pattern) and pattern[p] == text[t]:
                p += 1
                t += 1
            elif star >= 0:
                p = star + 1
                mark += 1
                t = mark
            else:
                return False
        while p < len(pattern) and pattern[p] == "*":
            p += 1
        return p == len(pattern)

    def split_strict(text, what):
        if not isinstance(text, str) or text == "":
            raise ValueError(f"{what} must be a non-empty string")
        segments = text.split("/")
        if any(segment == "" for segment in segments):
            raise ValueError(f"{what} has an empty segment: {text}")
        return segments

    parsed = []
    for rule in rules:
        if not isinstance(rule, str):
            raise ValueError("every rule must be a string")
        keep = rule.startswith("!")
        body = rule[1:] if keep else rule
        parsed.append((keep, split_strict(body, "rule pattern")))
    kept = []
    for path in listing:
        steps = split_strict(path, "path")
        retained = True
        for keep, segments in parsed:
            if len(segments) > len(steps):
                continue
            if all(segment_fits(s, steps[i]) for i, s in enumerate(segments)):
                retained = keep
        if retained:
            kept.append(path)
    return kept
