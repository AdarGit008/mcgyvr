from solution import trace_parcel

assert trace_parcel([]) == ["created"], "no events yields the start state"
assert trace_parcel(["pack"]) == ["created", "packed"], "one event"
assert trace_parcel(["pack", "ship", "deliver"]) == [
    "created",
    "packed",
    "shipped",
    "delivered",
], "the delivery path"
assert trace_parcel(["pack", "ship", "bounce"]) == [
    "created",
    "packed",
    "shipped",
    "returned",
], "the return path"


def rejects(value):
    try:
        trace_parcel(value)
    except Exception:
        return True
    return False


assert rejects("pack"), "non-list argument is rejected"
assert rejects(["melt"]), "unknown event is rejected"
assert rejects(["ship"]), "ship before pack is rejected"
assert rejects(["pack", "pack"]), "repeated event is rejected"
assert rejects(["pack", "ship", "deliver", "pack"]), "an event after a final state is rejected"
print("ok")
