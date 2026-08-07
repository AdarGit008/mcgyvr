"""A chart with its twin rows squashed together."""


def squash_rows(chart: dict) -> dict:
    if not isinstance(chart, dict):
        raise ValueError("a chart must be a mapping")
    signals = chart.get("signals")
    if not isinstance(signals, list) or not signals:
        raise ValueError("the signal list is empty")
    signal_seen = set()
    for signal in signals:
        if not isinstance(signal, str) or not signal:
            raise ValueError("a signal is a non-empty string")
        if signal in signal_seen:
            raise ValueError("the signal " + signal + " is listed twice")
        signal_seen.add(signal)
    raw = chart.get("rows")
    if not isinstance(raw, list) or not raw:
        raise ValueError("the chart holds no rows")
    rows = []
    at = {}
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("a row must be a mapping")
        label = item.get("label")
        if not isinstance(label, str) or not label:
            raise ValueError("a row needs a non-empty label")
        if label in at:
            raise ValueError("two rows share the label " + label)
        mark = item.get("mark")
        if not isinstance(mark, str) or not mark:
            raise ValueError("a row needs a non-empty mark")
        nxt = item.get("next")
        if not isinstance(nxt, list) or len(nxt) != len(signals):
            raise ValueError(label + " does not hold one next entry per signal")
        at[label] = len(rows)
        rows.append({"label": label, "mark": mark, "next": nxt})
    for row in rows:
        for target in row["next"]:
            if not isinstance(target, str) or target not in at:
                raise ValueError(row["label"] + " leads to a row nobody declared")
    head = chart.get("head")
    if not isinstance(head, str) or head not in at:
        raise ValueError("the head names no row")

    marks = []
    block = []
    for row in rows:
        if row["mark"] not in marks:
            marks.append(row["mark"])
        block.append(marks.index(row["mark"]))
    blocks = len(marks)
    while True:
        seen: dict = {}
        nxt_block = []
        for index, row in enumerate(rows):
            parts = [str(block[at[target]]) for target in row["next"]]
            signature = str(block[index]) + "|" + ",".join(parts)
            if signature not in seen:
                seen[signature] = len(seen)
            nxt_block.append(seen[signature])
        block = nxt_block
        if len(seen) == blocks:
            break
        blocks = len(seen)

    numbered: dict = {}
    leaders = []
    for index in range(len(rows)):
        if block[index] not in numbered:
            numbered[block[index]] = len(leaders)
            leaders.append(index)
    folded = [
        {
            "at": number,
            "mark": rows[index]["mark"],
            "next": [numbered[block[at[target]]] for target in rows[index]["next"]],
        }
        for number, index in enumerate(leaders)
    ]
    return {"entry": numbered[block[at[head]]], "rows": folded}
