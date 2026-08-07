def final_door_state(events: list[str]) -> str:
    lawful = {
        "unlock": {"locked": "closed"},
        "lock": {"closed": "locked"},
        "open": {"closed": "open"},
        "close": {"open": "closed"},
    }
    state = "locked"
    ignored = 0
    for event in events:
        if event not in lawful:
            raise ValueError(f"unknown event {event}")
        moves = lawful[event]
        if state in moves:
            state = moves[state]
        else:
            ignored += 1
    return state + ":" + str(ignored)
