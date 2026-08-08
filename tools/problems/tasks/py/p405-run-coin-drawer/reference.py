def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _read_till(till):
    if not isinstance(till, list) or not till:
        raise ValueError("the till must list at least one denomination")
    seen = set()
    rows = []
    for row in till:
        if not isinstance(row, (list, tuple)) or len(row) != 2:
            raise ValueError("each till entry is a denomination and a count")
        denomination, count = row
        if not _whole(denomination) or denomination < 1:
            raise ValueError("a denomination must be a whole number above nothing")
        if not _whole(count) or count < 0:
            raise ValueError("a count must be a whole number of nothing or more")
        if denomination in seen:
            raise ValueError("denomination {} is listed twice".format(denomination))
        seen.add(denomination)
        rows.append((denomination, count))
    rows.sort(key=lambda pair: -pair[0])
    return rows


def run_coin_drawer(till: list, queue: list) -> dict:
    rows = _read_till(till)
    if not isinstance(queue, list):
        raise ValueError("the queue must be a list of purchases")
    held = {denomination: count for denomination, count in rows}
    turned_away = []
    earnings = 0
    for index, purchase in enumerate(queue):
        if not isinstance(purchase, dict):
            raise ValueError("a purchase must be a record")
        price = purchase.get("price")
        if not _whole(price) or price < 1:
            raise ValueError("a price must be a whole number above nothing")
        paid = purchase.get("paid")
        if not isinstance(paid, list):
            raise ValueError("the pushed coins must be a list")
        pushed = 0
        for coin in paid:
            if not _whole(coin) or coin not in held:
                raise ValueError("the till does not handle a coin of {}".format(coin))
            pushed += coin
        before = dict(held)
        for coin in paid:
            held[coin] += 1
        owed = pushed - price
        hand_out = {}
        if owed >= 0:
            for denomination, _count in rows:
                take = min(held[denomination], owed // denomination)
                if take > 0:
                    hand_out[denomination] = take
                    owed -= take * denomination
        if owed != 0:
            held = before
            turned_away.append(index)
            continue
        for denomination, take in hand_out.items():
            held[denomination] -= take
        earnings += price
    return {
        "till": [[denomination, held[denomination]] for denomination, _count in rows],
        "turnedAway": turned_away,
        "earnings": earnings,
    }
