RULE_KEYS = {"amount", "band", "code", "floor", "mode", "solo"}


def _whole(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _subtotal_of(basket: list[list]) -> int:
    if not isinstance(basket, list):
        raise ValueError("the basket must be a list of triples")
    subtotal = 0
    for line in basket:
        if not isinstance(line, (list, tuple)) or len(line) != 3:
            raise ValueError("a basket line is a [sku, cents, count] triple")
        sku, cents, count = line
        if not isinstance(sku, str) or not sku:
            raise ValueError("a sku must be a non-empty string")
        if not _whole(cents) or cents < 0:
            raise ValueError("cents must be whole and at nought or above")
        if not _whole(count) or count < 1:
            raise ValueError("a count must be a whole number of at least one")
        subtotal += cents * count
    return subtotal


def apply_discount_bands(basket: list[list], rules: list[dict]) -> dict:
    running = _subtotal_of(basket)
    if not isinstance(rules, list):
        raise ValueError("the rules must be a list of mappings")

    seen: set[str] = set()
    for rule in rules:
        if not isinstance(rule, dict):
            raise ValueError("a rule must be a mapping")
        if set(rule) != RULE_KEYS:
            raise ValueError(
                "a rule carries exactly code, band, mode, amount, floor, solo"
            )
        code = rule["code"]
        if not isinstance(code, str) or not code:
            raise ValueError("a code must be a non-empty string")
        if code in seen:
            raise ValueError(f"two rules share the code {code}")
        seen.add(code)
        if not isinstance(rule["band"], str) or not rule["band"]:
            raise ValueError("a band must be a non-empty string")
        if rule["mode"] not in ("share", "flat"):
            raise ValueError("a mode is either share or flat")
        amount = rule["amount"]
        if rule["mode"] == "share":
            if not _whole(amount) or amount < 1 or amount > 100:
                raise ValueError("a share amount runs from 1 through 100")
        elif not _whole(amount) or amount < 1:
            raise ValueError("a flat amount must be a whole number of cents above nought")
        if not _whole(rule["floor"]) or rule["floor"] < 0:
            raise ValueError("a floor must be whole and at nought or above")
        if not isinstance(rule["solo"], bool):
            raise ValueError("a solo flag must be a boolean")

    bitten: set[str] = set()
    applied: list[str] = []
    for rule in rules:
        band = rule["band"]
        if band in bitten:
            continue
        if running < rule["floor"]:
            continue
        amount = rule["amount"]
        cut = running * amount // 100 if rule["mode"] == "share" else min(amount, running)
        running -= cut
        bitten.add(band)
        applied.append(rule["code"])
        if rule["solo"] is True:
            break
    return {"total": running, "applied": applied}
