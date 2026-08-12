"""Replay a support ticket's lifecycle and report its final state."""

TRANSITIONS = {
    "new": {"triage": "triaged"},
    "triaged": {"resolve": "resolved"},
    "resolved": {"reopen": "triaged", "archive": "archived"},
    "archived": {},
}

EVENTS = {"triage", "resolve", "reopen", "archive"}


def replay_ticket(events: list) -> str:
    state = "new"
    for event in events:
        if event not in EVENTS:
            raise ValueError("unknown event: " + event)
        next_state = TRANSITIONS[state].get(event)
        if next_state is None:
            raise ValueError(event + " is not lawful in state " + state)
        state = next_state
    return state
