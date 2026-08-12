from solution import resolve_layers


def plain(assigned, removed=(), frozen=()):
    return {"set": assigned, "drop": list(removed), "lock": list(frozen)}


assert resolve_layers([]) == {}, "no layers settle nothing"
assert resolve_layers([plain({"mode": "fast", "tint": "warm"})]) == {"mode": "fast", "tint": "warm"}, "a lone layer settles its assignments"
assert resolve_layers([plain({"mode": "fast"}), plain({"mode": "safe"})]) == {"mode": "safe"}, "a later layer beats an earlier one"
assert resolve_layers([plain({"mode": "fast"}, (), ("mode",)), plain({"mode": "safe"})]) == {"mode": "fast"}, "a lock in force refuses a later assignment"
assert resolve_layers([plain({"mode": "fast", "tint": "warm"}), plain({}, ("tint",))]) == {"mode": "fast"}, "a removal takes a settled name away"
assert resolve_layers([plain({"tint": "warm"}, (), ("tint",)), plain({}, ("tint",))]) == {"tint": "warm"}, "a lock in force refuses a later removal"
assert resolve_layers([plain({}, (), ("tint",)), plain({"tint": "warm"})]) == {}, "a name locked before assignment stays absent"
print("ok")
