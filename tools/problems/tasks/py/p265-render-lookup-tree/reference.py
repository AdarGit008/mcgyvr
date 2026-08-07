def plant(cell, held):
    if cell is None:
        return {"held": held, "lo": None, "hi": None}
    if held < cell["held"]:
        cell["lo"] = plant(cell["lo"], held)
    elif held > cell["held"]:
        cell["hi"] = plant(cell["hi"], held)
    return cell


def holds(cell, wanted):
    while cell is not None:
        if wanted == cell["held"]:
            return True
        cell = cell["lo"] if wanted < cell["held"] else cell["hi"]
    return False


def pull(cell, wanted):
    if cell is None:
        return None
    if wanted < cell["held"]:
        cell["lo"] = pull(cell["lo"], wanted)
        return cell
    if wanted > cell["held"]:
        cell["hi"] = pull(cell["hi"], wanted)
        return cell
    if cell["lo"] is None:
        return cell["hi"]
    if cell["hi"] is None:
        return cell["lo"]
    lowest = cell["hi"]
    while lowest["lo"] is not None:
        lowest = lowest["lo"]
    cell["held"] = lowest["held"]
    cell["hi"] = pull(cell["hi"], lowest["held"])
    return cell


def draw(cell):
    if cell is None:
        return "."
    return "[" + str(cell["held"]) + "|" + draw(cell["lo"]) + "|" + draw(cell["hi"]) + "]"


def whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def render_lookup_tree(planted: list, pulled: list) -> str:
    if not isinstance(planted, list) or not isinstance(pulled, list):
        raise ValueError("both arguments must be lists")
    root = None
    for value in planted:
        if not whole(value):
            raise ValueError("planted values must be whole numbers")
        root = plant(root, value)
    for value in pulled:
        if not whole(value):
            raise ValueError("pulled values must be whole numbers")
        if not holds(root, value):
            raise ValueError("cannot pull a value the tree does not carry")
        root = pull(root, value)
    return draw(root)
