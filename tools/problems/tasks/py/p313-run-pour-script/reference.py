"""Flask contents after replaying a measuring script."""


def run_pour_script(capacities: list, script: list) -> list:
    if not isinstance(capacities, list) or not capacities:
        raise ValueError("the rack must hold at least one flask")
    if not isinstance(script, list):
        raise ValueError("script must be a list of lines")
    held = [0] * len(capacities)

    def mark_index(mark):
        if not isinstance(mark, str) or len(mark) != 1:
            raise ValueError("unusable flask mark: " + str(mark))
        index = ord(mark) - 65
        if index < 0 or index >= len(capacities):
            raise ValueError("no flask is marked " + mark)
        return index

    for line in script:
        if not isinstance(line, str):
            raise ValueError("every script line must be a string")
        parts = line.split(" ")
        if parts[0] in ("fill", "empty"):
            if len(parts) != 2:
                raise ValueError("malformed line: " + line)
            index = mark_index(parts[1])
            held[index] = capacities[index] if parts[0] == "fill" else 0
        elif parts[0] == "pour":
            if len(parts) != 3:
                raise ValueError("malformed line: " + line)
            giver = mark_index(parts[1])
            taker = mark_index(parts[2])
            if giver == taker:
                raise ValueError("a flask cannot pour into itself")
            moved = min(held[giver], capacities[taker] - held[taker])
            held[giver] -= moved
            held[taker] += moved
        else:
            raise ValueError("unknown action: " + parts[0])
    return held
