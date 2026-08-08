def line_choke_point(stations: list) -> dict:
    if not isinstance(stations, list) or not stations:
        raise ValueError("empty station list")
    seen = set()
    best_name = ""
    best_output = None
    for entry in stations:
        if not isinstance(entry, (list, tuple)) or len(entry) != 3:
            raise ValueError("malformed station")
        name, machines, rate = entry
        if not isinstance(name, str) or name == "":
            raise ValueError("bad station name")
        if not isinstance(machines, int) or isinstance(machines, bool) or machines < 1:
            raise ValueError("bad machine count")
        if not isinstance(rate, int) or isinstance(rate, bool) or rate < 1:
            raise ValueError("bad rate")
        if name in seen:
            raise ValueError("duplicate station name")
        seen.add(name)
        output = machines * rate
        if best_output is None or output < best_output:
            best_output = output
            best_name = name
    return {"station": best_name, "output": best_output}
