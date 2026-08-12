from solution import fresh_value

assert fresh_value({"value": "a", "stored": 5, "ttl": 10}, 5) == "a", "a record is usable the tick it is stored"
assert fresh_value({"value": "b", "stored": 5, "ttl": 10}, 14) == "b", "the last usable tick still yields the value"
assert fresh_value({"value": "tok", "stored": 0, "ttl": 1}, 0) == "tok", "a one-tick record works at tick zero"
assert fresh_value({"value": "", "stored": 2, "ttl": 3}, 3) == "", "an empty string is a value like any other"
assert fresh_value({"value": "z", "stored": 100, "ttl": 50}, 120) == "z", "a mid-life record yields its value"


def rejects(entry, now):
    try:
        fresh_value(entry, now)
    except Exception:
        return True
    return False


assert rejects(42, 0), "an entry that is not a record is rejected"
assert rejects({"value": 7, "stored": 0, "ttl": 5}, 0), "a non-string value is rejected"
assert rejects({"value": "a", "stored": -1, "ttl": 5}, 0), "a negative stored is rejected"
assert rejects({"value": "a", "stored": 0, "ttl": 0}, 0), "a zero ttl is rejected"
assert rejects({"value": "a", "stored": 9, "ttl": 5}, 8), "a now before stored is rejected"
assert rejects({"value": "a", "stored": 5, "ttl": 10}, 15), "the record stops being usable at stored plus ttl"
print("ok")
