from collections import deque


def stranded_ticker_pairs(legs: list) -> list:
    if not isinstance(legs, list) or not legs:
        raise ValueError("the desk published no legs")
    forward: dict = {}
    published = set()
    tickers = set()
    for leg in legs:
        if not isinstance(leg, list) or len(leg) != 2:
            raise ValueError("a leg is exactly two elements")
        sell, buy = leg
        for code in (sell, buy):
            if not isinstance(code, str) or not code:
                raise ValueError("a ticker is a non-empty string")
        if sell == buy:
            raise ValueError("a leg cannot sell and buy the same ticker")
        key = sell + ">" + buy
        if key in published:
            raise ValueError("the leg " + key + " is published twice")
        published.add(key)
        tickers.add(sell)
        tickers.add(buy)
        forward.setdefault(sell, []).append(buy)

    codes = sorted(tickers)
    stranded = []
    for start in codes:
        reached = set()
        queue = deque([start])
        while queue:
            node = queue.popleft()
            for nxt in forward.get(node, []):
                if nxt not in reached:
                    reached.add(nxt)
                    queue.append(nxt)
        for finish in codes:
            if finish != start and finish not in reached:
                stranded.append(start + ">" + finish)
    return stranded
