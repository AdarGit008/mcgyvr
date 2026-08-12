from solution import deal_bags

assert deal_bags([], [2, 2]) == {"loads": [[], []], "spare": []}, "no parcels leaves every bag empty"
assert deal_bags(["a", "b", "c", "d"], [2, 2]) == {"loads": [["a", "c"], ["b", "d"]], "spare": []}, "the round hands bags one parcel each in turn"
assert deal_bags(["a", "b", "c", "d", "e", "f", "g"], [2, 1, 3]) == {"loads": [["a", "d"], ["b"], ["c", "e", "f"]], "spare": ["g"]}, "a filled bag drops out of the round and the rest goes spare"
assert deal_bags(["a", "b", "c"], [2]) == {"loads": [["a", "b"]], "spare": ["c"]}, "one bag fills and the overflow is spare"


def rejects(parcels, caps):
    try:
        deal_bags(parcels, caps)
    except Exception:
        return True
    return False


assert rejects("abc", [2]), "a parcels argument that is not a list is rejected"
assert rejects(["a"], [2, 0]), "a capacity that is not positive is rejected"
print("ok")
