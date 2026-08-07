PARTS = ("ref", "board", "alight", "leaves", "lands")


def _counted(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _named(value):
    return isinstance(value, str) and value != ""


def check_layovers(hops, layover, ready_at) -> dict:
    if not isinstance(hops, list) or not hops:
        raise ValueError("the hop list must be a non-empty list")
    if not _counted(layover) or layover < 0:
        raise ValueError("layover must be a whole number of zero or more")
    if not _counted(ready_at) or ready_at < 0:
        raise ValueError("ready_at must be a whole number of zero or more")
    chain = []
    for raw in hops:
        if not isinstance(raw, dict):
            raise ValueError("a hop must be a record")
        for part in PARTS:
            if part not in raw:
                raise ValueError("a hop is missing " + part)
        if not _named(raw["ref"]):
            raise ValueError("a ref must be a non-empty string")
        if not _named(raw["board"]) or not _named(raw["alight"]):
            raise ValueError("a halt name must be a non-empty string")
        if raw["board"] == raw["alight"]:
            raise ValueError("a hop must not board and alight at one halt")
        if not _counted(raw["leaves"]) or not _counted(raw["lands"]):
            raise ValueError("leaves and lands must be whole numbers")
        if raw["lands"] <= raw["leaves"]:
            raise ValueError("lands must be past leaves")
        chain.append(raw)
    if chain[0]["leaves"] < ready_at:
        return {"verdict": "early", "at": 0, "arrive": -1}
    for i in range(1, len(chain)):
        if chain[i]["board"] != chain[i - 1]["alight"]:
            return {"verdict": "place", "at": i, "arrive": -1}
        if chain[i]["leaves"] < chain[i - 1]["lands"] + layover:
            return {"verdict": "tight", "at": i, "arrive": -1}
    return {"verdict": "sound", "at": -1, "arrive": chain[-1]["lands"]}
