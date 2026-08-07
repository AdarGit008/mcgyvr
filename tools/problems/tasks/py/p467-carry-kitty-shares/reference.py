def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def carry_kitty_shares(hops: list) -> dict:
    if not isinstance(hops, list):
        raise ValueError("carry_kitty_shares expects a list of hops")
    if not hops:
        raise ValueError("the journey has no hops")

    each = []
    kitty = 0
    for hop in hops:
        if not isinstance(hop, dict):
            raise ValueError("a hop is not a mapping")
        if sorted(hop) != ["cents", "heads"]:
            raise ValueError("a hop carries exactly cents and heads")
        cents = hop["cents"]
        heads = hop["heads"]
        if not _whole(cents) or cents < 0:
            raise ValueError("a hop's cents are not whole or fall below nought")
        if not _whole(heads) or heads < 1:
            raise ValueError("a hop's heads are not whole or fall below one")
        kitty += cents
        share = kitty // heads
        each.append(share)
        kitty -= share * heads
    return {"each": each, "left": kitty}
