from solution import final_door_state

assert final_door_state([]) == "locked:0", "no events, still locked"
assert final_door_state(["unlock"]) == "closed:0", "unlock releases the lock"
assert final_door_state(["unlock", "open"]) == "open:0", "unlock then open"
assert final_door_state(["open"]) == "locked:1", "a locked door does not open"
assert final_door_state(["unlock", "open", "open"]) == "open:1", (
    "opening an open door is ignored"
)
assert final_door_state(["unlock", "open", "close", "lock"]) == "locked:0", (
    "a full lawful cycle"
)
assert final_door_state(["lock", "close", "unlock"]) == "closed:2", (
    "only the last event applies"
)
assert final_door_state(["unlock", "open", "unlock"]) == "open:1", (
    "unlock means nothing to an open door"
)


def rejects(events):
    try:
        final_door_state(events)
    except ValueError:
        return True
    return False


assert rejects(["knock"]), "unknown event rejected"
print("ok")
