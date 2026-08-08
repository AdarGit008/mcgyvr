def _is_track(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def classify_hump_cars(cut: list, table: dict) -> dict:
    if not isinstance(cut, list):
        raise ValueError("the cut is a list of cars")
    if not cut:
        raise ValueError("the hump has nothing to work")
    if not isinstance(table, dict):
        raise ValueError("the routing table is a mapping")
    for track in table.values():
        if not _is_track(track):
            raise ValueError("a track number is a whole number of one or more")

    numbers: set = set()
    tracks: dict = {}
    unrouted: list = []
    for entry in cut:
        if not isinstance(entry, list) or len(entry) != 2:
            raise ValueError("every car is a pair of a number and a destination")
        car, chalked = entry
        if (
            not isinstance(car, str)
            or car == ""
            or not isinstance(chalked, str)
            or chalked == ""
        ):
            raise ValueError("a car number and a destination are non-empty strings")
        if car in numbers:
            raise ValueError(f"two cars carry the number {car}")
        numbers.add(car)
        if chalked not in table:
            unrouted.append(car)
            continue
        tracks.setdefault(table[chalked], []).append(car)

    train: list = []
    for track in sorted(tracks):
        train.extend(tracks[track])
    return {"train": train, "unrouted": unrouted}
