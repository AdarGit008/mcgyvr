def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def earn_loyalty_points(receipts: list, ladder: list) -> list:
    if not isinstance(receipts, list) or not isinstance(ladder, list):
        raise ValueError("earn_loyalty_points expects two lists")
    if not ladder:
        raise ValueError("the ladder carries no rungs")

    rungs = []
    for entry in ladder:
        if not isinstance(entry, dict):
            raise ValueError("a rung is not a mapping")
        if sorted(entry) != ["from", "per"]:
            raise ValueError("a rung carries exactly from and per")
        opens = entry["from"]
        per = entry["per"]
        if not _whole(opens) or opens < 0:
            raise ValueError("a rung's from is not whole or falls below nought")
        if not _whole(per) or per < 0:
            raise ValueError("a rung's per is not whole or falls below nought")
        rungs.append((opens, per))

    if rungs[0][0] != 0:
        raise ValueError("the opening rung does not sit at nought")
    for earlier, later in zip(rungs, rungs[1:]):
        if later[0] <= earlier[0]:
            raise ValueError("the from values fail to climb strictly")

    for receipt in receipts:
        if not _whole(receipt) or receipt < 0:
            raise ValueError("a receipt is not whole or falls below nought")

    awards = []
    outlay = 0
    for receipt in receipts:
        per = rungs[0][1]
        for opens, rate in rungs:
            if opens <= outlay:
                per = rate
        awards.append(receipt * per // 1000)
        outlay += receipt
    return awards
