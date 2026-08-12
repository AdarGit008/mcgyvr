MOVES = {"lowered": {"raise": "raised"}, "locked": {"unlock": "raised"},
         "raised": {"lower": "lowered", "lock": "locked"}}

def drive_bridge(commands):
    if not isinstance(commands, list):
        raise ValueError("drive_bridge expects a list of commands")
    state = "lowered"
    for command in commands:
        if command not in ("raise", "lower", "lock", "unlock"):
            raise ValueError("unknown command word")
        if command not in MOVES[state]:
            raise ValueError(command + " is not allowed while " + state)
        state = MOVES[state][command]
    return state
