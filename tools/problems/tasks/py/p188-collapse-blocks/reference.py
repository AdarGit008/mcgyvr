def _render(node, pin):
    start = node * (8 ** (4 - pin))
    fields = [0, 0, 0, 0]
    rest = start
    for slot in (3, 2, 1, 0):
        fields[slot] = rest % 8
        rest //= 8
    return ".".join(str(field) for field in fields) + "/" + str(pin)


def collapse_blocks(berths: list) -> list:
    if not isinstance(berths, list):
        raise ValueError("berths must be a list")
    leaves = set()
    for berth in berths:
        if not isinstance(berth, str):
            raise ValueError("every berth must be a string")
        fields = berth.split(".")
        if len(fields) != 4:
            raise ValueError("a berth has exactly four fields")
        value = 0
        for field in fields:
            if len(field) != 1 or not ("0" <= field <= "7"):
                raise ValueError("field is not a single character between 0 and 7")
            value = value * 8 + int(field)
        leaves.add(value)

    found = []
    nodes = sorted(leaves)
    pin = 4
    while pin > 0:
        kin = {}
        for node in nodes:
            kin.setdefault(node // 8, []).append(node)
        promoted = []
        for parent, siblings in kin.items():
            if len(siblings) == 8:
                promoted.append(parent)
            else:
                for node in siblings:
                    found.append((node * (8 ** (4 - pin)), _render(node, pin)))
        nodes = promoted
        pin -= 1
    if nodes:
        found.append((0, "0.0.0.0/0"))
    found.sort(key=lambda entry: entry[0])
    return [entry[1] for entry in found]
