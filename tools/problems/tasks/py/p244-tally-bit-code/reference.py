import re


def build_weight_code(entries: list) -> dict:
    if not isinstance(entries, list) or not entries:
        raise ValueError("the entry list must hold at least one entry")
    tally_of = {}
    for entry in entries:
        if not isinstance(entry, list) or len(entry) != 2:
            raise ValueError("an entry must be a list of exactly two things")
        token, tally = entry
        if not isinstance(token, str) or re.fullmatch(r"[a-z]+", token) is None:
            raise ValueError("a token must be a non-empty string of lowercase letters")
        if token in tally_of:
            raise ValueError("a token shows up twice")
        if not isinstance(tally, int) or isinstance(tally, bool) or tally < 1:
            raise ValueError("a tally must be a whole number of one or more")
        tally_of[token] = tally
    tokens = sorted(tally_of)
    if len(tokens) == 1:
        only = tokens[0]
        return {"codes": {only: "0"}, "bits": tally_of[only], "tallest": 1}
    load = []
    near = []
    far = []
    holds = []
    for token in tokens:
        load.append(tally_of[token])
        near.append(-1)
        far.append(-1)
        holds.append(token)
    live = set(range(len(tokens)))

    def smallest():
        best = -1
        for bud in live:
            if best == -1 or (load[bud], bud) < (load[best], best):
                best = bud
        live.discard(best)
        return best

    while len(live) > 1:
        first = smallest()
        second = smallest()
        fresh = len(load)
        load.append(load[first] + load[second])
        near.append(first)
        far.append(second)
        holds.append("")
        live.add(fresh)
    crown = next(iter(live))
    codes = {}
    pending = [(crown, "")]
    while pending:
        bud, written = pending.pop()
        if near[bud] == -1:
            codes[holds[bud]] = written
            continue
        pending.append((far[bud], written + "1"))
        pending.append((near[bud], written + "0"))
    bits = 0
    tallest = 0
    for token in tokens:
        width = len(codes[token])
        bits += tally_of[token] * width
        tallest = max(tallest, width)
    return {"codes": codes, "bits": bits, "tallest": tallest}
