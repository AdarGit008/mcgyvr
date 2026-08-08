def _read_order(raw, at):
    if not isinstance(raw, dict):
        raise ValueError("an order must be a mapping")
    tag = raw.get("tag")
    if not isinstance(tag, str) or tag == "":
        raise ValueError("an order needs a non-empty tag")
    side = raw.get("side")
    if side not in ("bid", "ask"):
        raise ValueError("a side must be bid or ask")
    price = raw.get("price")
    size = raw.get("size")
    for value in (price, size):
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError("price and size must be positive whole numbers")
    return {"tag": tag, "side": side, "price": price, "size": size, "at": at}


def cross_resting_orders(book: list, arriving: dict) -> dict:
    if not isinstance(book, list):
        raise ValueError("the book must be a list")
    resting = [_read_order(raw, at) for at, raw in enumerate(book)]
    tags = set()
    for order in resting:
        if order["tag"] in tags:
            raise ValueError("two resting orders share a tag")
        tags.add(order["tag"])
    taker = _read_order(arriving, len(resting))
    if taker["tag"] in tags:
        raise ValueError("the arriving tag already rests")

    bids = [order for order in resting if order["side"] == "bid"]
    asks = [order for order in resting if order["side"] == "ask"]
    if bids and asks:
        dearest = max(order["price"] for order in bids)
        cheapest = min(order["price"] for order in asks)
        if dearest >= cheapest:
            raise ValueError("the book already crosses")

    buying = taker["side"] == "bid"
    far = [
        order
        for order in resting
        if order["side"] != taker["side"]
        and (
            order["price"] <= taker["price"]
            if buying
            else order["price"] >= taker["price"]
        )
    ]
    far.sort(key=lambda o: (o["price"] if buying else -o["price"], o["at"]))

    trades = []
    left = taker["size"]
    for order in far:
        if left == 0:
            break
        size = min(left, order["size"])
        trades.append({"maker": order["tag"], "price": order["price"], "size": size})
        order["size"] -= size
        left -= size

    survivors = [order for order in resting if order["size"] > 0]
    if left > 0:
        rested = dict(taker)
        rested["size"] = left
        survivors.append(rested)

    def shelf(side, keen):
        rows = [order for order in survivors if order["side"] == side]
        rows.sort(key=lambda o: (keen * o["price"], o["at"]))
        return [
            {
                "tag": o["tag"],
                "side": o["side"],
                "price": o["price"],
                "size": o["size"],
            }
            for o in rows
        ]

    return {"trades": trades, "book": shelf("bid", -1) + shelf("ask", 1)}
