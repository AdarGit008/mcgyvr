def hand_out_chores(chores: list, crew: list) -> dict:
    if not isinstance(chores, list):
        raise ValueError("the chore board must be a list")
    listed = set()
    for chore in chores:
        if not isinstance(chore, str) or chore == "":
            raise ValueError("every chore must be a non-empty string")
        if chore in listed:
            raise ValueError("the board lists " + chore + " twice")
        listed.add(chore)
    if not isinstance(crew, list) or len(crew) == 0:
        raise ValueError("the crew must be a list with somebody on it")
    share = {}
    for who in crew:
        if not isinstance(who, str) or who == "":
            raise ValueError("every crew name must be a non-empty string")
        if who in share:
            raise ValueError("two crew members share the name " + who)
        share[who] = []

    marker = 0
    for chore in chores:
        share[crew[marker]].append(chore)
        marker = (marker + len(chore)) % len(crew)
    return share
