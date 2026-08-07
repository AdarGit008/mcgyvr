def tally_ballots(events: list) -> dict:
    standing: dict = {}
    seen: set = set()
    closed = False
    for event in events:
        if closed:
            raise ValueError("event after close")
        kind = event["type"]
        if kind == "cast":
            if event["voter"] in standing:
                raise ValueError("voter already has a standing vote")
            standing[event["voter"]] = event["option"]
            seen.add(event["option"])
        elif kind == "retract":
            if event["voter"] not in standing:
                raise ValueError("no standing vote to retract")
            del standing[event["voter"]]
        elif kind == "close":
            closed = True
        else:
            raise ValueError("unknown event type: " + str(kind))
    counts = {option: 0 for option in seen}
    for option in standing.values():
        counts[option] += 1
    return counts
