def badge_runs(badges: str) -> str:
    if not badges:
        raise ValueError("no badges to compress")
    out = []
    start = 0
    for i in range(1, len(badges) + 1):
        if i == len(badges) or badges[i] != badges[start]:
            out.append(badges[start] + str(i - start))
            start = i
    return "".join(out)
