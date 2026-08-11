from solution import explode_kit

catalog = {
    "desk": {"makes": 1, "parts": [("frame", 1), ("top", 1), ("bolt", 8)]},
    "frame": {"makes": 2, "parts": [("tube", 4), ("bolt", 6)]},
    "cart": {"makes": 1, "parts": [("frame", 2), ("wheel", 4)]},
    "rig": {"makes": 1, "parts": [("frame", 1), ("cart", 1)]},
    "crate": {"makes": 1, "parts": []},
}


def rejects(kit, want):
    try:
        explode_kit(catalog, kit, want)
    except Exception:
        return True
    return False


assert explode_kit(catalog, "desk", 1) == {"tube": 4, "bolt": 14, "top": 1}, "one unit reaches through a sub-kit and sums a shared part"
assert explode_kit(catalog, "desk", 3) == {"tube": 8, "bolt": 36, "top": 3}, "a sub-kit making two at a time needs two runs for three"
assert explode_kit(catalog, "frame", 5) == {"tube": 12, "bolt": 18}, "five units of a recipe making two take three runs"
assert explode_kit(catalog, "cart", 1) == {"tube": 4, "bolt": 6, "wheel": 4}, "a requirement of two is filled by a single run"
assert explode_kit(catalog, "rig", 1) == {"tube": 8, "bolt": 12, "wheel": 4}, "spare units are never shared between requirements"
assert explode_kit(catalog, "crate", 4) == {}, "a recipe consuming nothing reports nothing"
assert rejects("shed", 1), "an undefined kit name is rejected"
print("ok")
