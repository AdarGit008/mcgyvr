from solution import fill_placeholders

assert fill_placeholders("dear %who%,", {"who": "Sam"}) == "dear Sam,", (
    "simple slot"
)

assert fill_placeholders(
    "%a% and %b%", {"a": "salt", "b": "pepper"}
) == "salt and pepper", "two slots"

assert fill_placeholders("100%% sure", {}) == "100% sure", (
    "doubled percent is a literal"
)

assert fill_placeholders("%%who%%", {"who": "Sam"}) == "%who%", (
    "doubled percents around a word stay literal"
)

assert fill_placeholders("%a%", {"a": "see %b%", "b": "nope"}) == "see %b%", (
    "replacement text is never scanned again"
)

assert fill_placeholders("%a%%b%", {"a": "x", "b": "y"}) == "xy", (
    "adjacent slots both fill"
)


def rejects(text, slots):
    try:
        fill_placeholders(text, slots)
    except ValueError:
        return True
    return False


assert rejects("hi %stranger%", {}), "unknown slot raises"
assert rejects("50% off", {"off": "x"}), "unpaired percent raises"

print("ok")
