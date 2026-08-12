from solution import drive_bridge

assert drive_bridge([]) == "lowered", "no commands leaves the span lowered"
assert drive_bridge(["raise"]) == "raised", "raise lifts a lowered span"
assert drive_bridge(["raise", "lower"]) == "lowered", "lower drops a raised span"
assert drive_bridge(["raise", "lock"]) == "locked", "lock pins a raised span"
assert drive_bridge(["raise", "lock", "unlock"]) == "raised", "unlock frees a locked span"
assert drive_bridge(["raise", "lock", "unlock", "lower"]) == "lowered", "a full cycle comes back down"


def rejects(value):
    try:
        drive_bridge(value)
    except Exception:
        return True
    return False


assert rejects(42), "a non-list is rejected"
assert rejects(["open"]), "an unknown command word is rejected"
assert rejects(["lower"]), "lowering a lowered span is rejected"
assert rejects(["raise", "raise"]), "raising a raised span is rejected"
assert rejects(["raise", "lock", "lower"]), "lowering a locked span is rejected"
print("ok")
