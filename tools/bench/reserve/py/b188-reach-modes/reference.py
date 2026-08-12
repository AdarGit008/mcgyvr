"""Every mode a control panel can still reach by walking its signals."""


def reachable_modes(table, start):
    if not isinstance(table, dict):
        raise ValueError("reachable_modes expects a table of modes")
    if start not in table:
        raise ValueError("the starting mode is not keyed by the table")
    found = set()

    # Walk out of a mode only the first time it is entered, so cycles settle.
    def walk(mode):
        if mode in found:
            return
        found.add(mode)
        for signal in table.get(mode, {}):
            walk(table[mode][signal])

    walk(start)
    return sorted(found)
