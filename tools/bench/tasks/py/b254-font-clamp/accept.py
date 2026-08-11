from solution import font_clamp


def rejects(size, smallest, largest):
    try:
        font_clamp(size, smallest, largest)
    except Exception:
        return True
    return False


assert font_clamp(5, 8, 20) == 8, "below the range comes up"
assert font_clamp(30, 8, 20) == 20, "above the range comes down"
assert font_clamp(12, 8, 20) == 12, "inside the range is untouched"
assert font_clamp(8, 8, 20) == 8, "sitting on the lower edge"
assert font_clamp(20, 8, 20) == 20, "sitting on the upper edge"
assert rejects(5, 20, 8), "an inverted range is rejected"
print("ok")
