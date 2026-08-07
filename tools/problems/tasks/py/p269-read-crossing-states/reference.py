def whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def read_crossing_states(period: int, crossings: list, moments: list) -> list:
    if not whole(period) or period < 1 or period > 86400:
        raise ValueError("period must be a whole number of seconds in 1..86400")
    if not isinstance(crossings, list) or not crossings:
        raise ValueError("crossings must be a non-empty list")
    seen = set()
    for crossing in crossings:
        if not isinstance(crossing, dict):
            raise ValueError("each crossing must be a record")
        if sorted(crossing) != ["clear", "name", "start", "walk"]:
            raise ValueError("each crossing carries exactly name, start, walk, clear")
        if not isinstance(crossing["name"], str) or crossing["name"] == "":
            raise ValueError("a crossing name must be non-empty text")
        if (
            not whole(crossing["start"])
            or not whole(crossing["walk"])
            or not whole(crossing["clear"])
        ):
            raise ValueError("start, walk and clear must be whole numbers")
        if crossing["start"] < 0 or crossing["start"] >= period:
            raise ValueError("start must lie in 0..period-1")
        if crossing["walk"] < 1 or crossing["clear"] < 0:
            raise ValueError("walk must be at least one second and clear at least none")
        if crossing["walk"] + crossing["clear"] > period:
            raise ValueError("walk plus clear must not outrun the period")
        if crossing["name"] in seen:
            raise ValueError("crossing names must not repeat")
        seen.add(crossing["name"])
    if not isinstance(moments, list):
        raise ValueError("moments must be a list")
    out = []
    for moment in moments:
        if not whole(moment) or moment < 0 or moment > 1000000:
            raise ValueError("each moment must be a whole number in 0..1000000")
        line = ""
        for crossing in crossings:
            local = (moment - crossing["start"]) % period
            if local < crossing["walk"]:
                line += "W"
            elif local < crossing["walk"] + crossing["clear"]:
                line += "C"
            else:
                line += "S"
        out.append(line)
    return out
