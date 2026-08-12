from solution import pack_dials

assert pack_dials({}) == "", "an empty preset renders as the empty string"
assert pack_dials({"gain": 3}) == "gain=3", "a single dial renders as one pair"
assert pack_dials({"tone": 2, "bass": 10}) == "bass=10;tone=2", "pairs come out sorted by name"
assert pack_dials({"mix": 0}) == "mix=0", "a zero position is rendered"
assert pack_dials({"b": 1, "a": 2, "c": 3}) == "a=2;b=1;c=3", "insertion order does not matter"


def rejects(value):
    try:
        pack_dials(value)
    except Exception:
        return True
    return False


assert rejects(42), "a non-mapping is rejected"
assert rejects({"": 4}), "an empty name is rejected"
assert rejects({"lo=fi": 1}), "a name holding = is rejected"
assert rejects({"a;b": 1}), "a name holding ; is rejected"
assert rejects({"hum": 2.5}), "a fractional position is rejected"
assert rejects({"vol": -1}), "a negative position is rejected"
print("ok")
