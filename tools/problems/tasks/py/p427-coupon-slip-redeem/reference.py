def _whole(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def redeem_coupon_slips(
    tickets: list[list], slips: list[list], ceiling: int
) -> dict:
    if not _whole(ceiling) or ceiling < 0:
        raise ValueError("the ceiling must be whole and at nought or above")
    if not isinstance(tickets, list) or not isinstance(slips, list):
        raise ValueError("tickets and slips must be lists")

    standing: dict[str, int] = {}
    for ticket in tickets:
        if not isinstance(ticket, (list, tuple)) or len(ticket) != 2:
            raise ValueError("a ticket is a [label, cents] pair")
        label, cents = ticket
        if not isinstance(label, str) or not label:
            raise ValueError("a label must be a non-empty string")
        if label in standing:
            raise ValueError(f"two tickets share the label {label}")
        if not _whole(cents) or cents < 0:
            raise ValueError("a price must be whole and at nought or above")
        standing[label] = cents

    tags: set[str] = set()
    for slip in slips:
        if not isinstance(slip, (list, tuple)) or len(slip) != 3:
            raise ValueError("a slip is a [tag, label, share] triple")
        tag, label, share = slip
        if not isinstance(tag, str) or not tag:
            raise ValueError("a tag must be a non-empty string")
        if tag in tags:
            raise ValueError(f"two slips share the tag {tag}")
        tags.add(tag)
        if not isinstance(label, str) or not label:
            raise ValueError("a label must be a non-empty string")
        if not _whole(share) or share < 1 or share > 100:
            raise ValueError("a share runs from 1 through 100")

    struck: dict[str, int] = {}
    ignored: list[str] = []
    saved = 0
    for slip in slips:
        tag, label, share = slip
        if label not in standing or struck.get(label, 0) >= 2:
            ignored.append(tag)
            continue
        price = standing[label]
        saving = price * share // 100
        if saved + saving > ceiling:
            ignored.append(tag)
            continue
        standing[label] = price - saving
        saved += saving
        struck[label] = struck.get(label, 0) + 1

    return {"due": sum(standing.values()), "saved": saved, "ignored": ignored}
