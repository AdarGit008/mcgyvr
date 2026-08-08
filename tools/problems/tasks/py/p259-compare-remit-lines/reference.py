def _read_advice(lines, side):
    if not isinstance(lines, list):
        raise ValueError(f"the {side} advice must be a list")
    amounts = {}
    for pair in lines:
        if not isinstance(pair, list) or len(pair) != 2:
            raise ValueError(f"a {side} line is a label and an amount")
        label, cents = pair
        if not isinstance(label, str) or label == "":
            raise ValueError(f"a {side} label must be a non-empty string")
        if not isinstance(cents, int) or isinstance(cents, bool):
            raise ValueError(f"{label} carries an amount that is not whole")
        if label in amounts:
            raise ValueError(f"the {side} advice repeats {label}")
        amounts[label] = cents
    return amounts


def compare_remit_lines(ours: list[list], theirs: list[list]) -> dict:
    mine = _read_advice(ours, "our")
    yours = _read_advice(theirs, "their")
    agreed = []
    queried = []
    our_side = []
    their_side = []
    for label, cents in mine.items():
        if label not in yours:
            our_side.append(label)
        elif yours[label] == cents:
            agreed.append(label)
        else:
            queried.append(label)
    for label in yours:
        if label not in mine:
            their_side.append(label)
    return {
        "agreed": sorted(agreed),
        "queried": sorted(queried),
        "ourSide": sorted(our_side),
        "theirSide": sorted(their_side),
    }
