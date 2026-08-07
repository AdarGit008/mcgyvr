MILLION = 1000000


def _whole(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _beats(candidate: tuple, incumbent) -> bool:
    if incumbent is None:
        return True
    amount, path = candidate
    held_amount, held_path = incumbent
    if amount != held_amount:
        return amount > held_amount
    if len(path) != len(held_path):
        return len(path) < len(held_path)
    return path < held_path


def best_rate_path(quotes: list, amount: int, source: str, destination: str) -> dict:
    if not isinstance(quotes, list) or not quotes:
        raise ValueError("no quotes were supplied")
    edges: dict = {}
    seen = set()
    known = set()
    for quote in quotes:
        if not isinstance(quote, list) or len(quote) != 3:
            raise ValueError("a quote is three elements")
        base, counter, micro = quote
        for code in (base, counter):
            if not isinstance(code, str) or not code:
                raise ValueError("a currency code is a non-empty string")
        if base == counter:
            raise ValueError("a quote cannot name one code on both sides")
        if not _whole(micro) or micro <= 0:
            raise ValueError("micro must be a positive whole number")
        key = base + ">" + counter
        if key in seen:
            raise ValueError("the ordered pair " + key + " is quoted twice")
        seen.add(key)
        known.add(base)
        known.add(counter)
        edges.setdefault(base, []).append((counter, micro))
    if not _whole(amount) or amount <= 0:
        raise ValueError("the amount must be a positive whole number")
    if not isinstance(source, str) or not isinstance(destination, str):
        raise ValueError("source and destination are currency codes")
    if source == destination:
        raise ValueError("a run must move between two different codes")
    for code in (source, destination):
        if code not in known:
            raise ValueError("no quote names " + code)

    best = None
    path = [source]
    on_path = {source}

    def walk(node: str, value: int) -> None:
        nonlocal best
        if node == destination:
            candidate = (value, list(path))
            if _beats(candidate, best):
                best = candidate
            return
        for nxt, micro in edges.get(node, []):
            if nxt in on_path:
                continue
            on_path.add(nxt)
            path.append(nxt)
            walk(nxt, value * micro // MILLION)
            path.pop()
            on_path.discard(nxt)

    walk(source, amount)
    if best is None:
        raise ValueError("no run connects " + source + " to " + destination)
    return {"amount": best[0], "path": best[1]}
