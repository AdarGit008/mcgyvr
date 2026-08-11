from solution import count_by


def rejects(records, field):
    try:
        count_by(records, field)
    except Exception:
        return True
    return False


assert count_by(
    [{"city": "rome"}, {"city": "rome"}, {"city": "oslo"}], "city"
) == {"rome": 2, "oslo": 1}, "counted by value"
assert count_by([{"city": "rome"}], "town") == {}, "no record holds the field"
assert count_by([], "city") == {}, "no records at all"
assert count_by([{"city": "rome"}, {"town": "oslo"}], "city") == {
    "rome": 1
}, "a record lacking the field is passed over"
assert count_by([{"city": ""}], "city") == {"": 1}, "an empty value counts"
assert rejects([], ""), "an unnamed field is rejected"
print("ok")
