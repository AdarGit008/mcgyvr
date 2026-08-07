def free_trail_parcels(depth: int, issued: list) -> list:
    if not isinstance(depth, int) or isinstance(depth, bool):
        raise ValueError("the depth must be a whole number")
    if depth < 1 or depth > 8:
        raise ValueError("the depth must lie between 1 and 8")
    if not isinstance(issued, list):
        raise ValueError("the issued parcels must be a list")
    for parcel in issued:
        if not isinstance(parcel, str):
            raise ValueError("a parcel must be a string")
        if len(parcel) > depth:
            raise ValueError("a parcel may not be longer than the depth")
        for letter in parcel:
            if letter not in ("L", "R"):
                raise ValueError("a parcel carries only the letters L and R")
    for one, first in enumerate(issued):
        for two, second in enumerate(issued):
            if one != two and second.startswith(first):
                raise ValueError("one issued parcel holds another")

    free = []

    def walk(path):
        if any(path.startswith(parcel) for parcel in issued):
            return
        if any(parcel.startswith(path) for parcel in issued):
            walk(path + "L")
            walk(path + "R")
            return
        free.append(path)

    walk("")
    return free
