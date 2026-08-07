def _tallied(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _held(value):
    return isinstance(value, str) and value != ""


def fold_mutual_dues(slips) -> list:
    if not isinstance(slips, list):
        raise ValueError("the slips must be a list")
    running = {}
    people = set()
    for slip in slips:
        if not isinstance(slip, dict):
            raise ValueError("a slip must be a record")
        for name in ("who", "whom", "cents"):
            if name not in slip:
                raise ValueError("a slip is missing " + name)
        if not _held(slip["who"]) or not _held(slip["whom"]):
            raise ValueError("a name must be a non-empty string")
        if slip["who"] == slip["whom"]:
            raise ValueError("a slip must not name one person twice")
        if not _tallied(slip["cents"]) or slip["cents"] < 1:
            raise ValueError("cents must be a whole number of one or more")
        row = running.setdefault(slip["who"], {})
        row[slip["whom"]] = row.get(slip["whom"], 0) + slip["cents"]
        people.add(slip["who"])
        people.add(slip["whom"])

    def owed(start, end):
        return running.get(start, {}).get(end, 0)

    names = sorted(people)
    folded = []
    for i, left in enumerate(names):
        for right in names[i + 1 :]:
            net = owed(left, right) - owed(right, left)
            if net > 0:
                folded.append({"who": left, "whom": right, "cents": net})
            elif net < 0:
                folded.append({"who": right, "whom": left, "cents": -net})
    folded.sort(key=lambda slip: (slip["who"], slip["whom"]))
    return folded
