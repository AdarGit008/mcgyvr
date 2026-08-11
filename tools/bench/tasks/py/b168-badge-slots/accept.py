from solution import badge_text

assert badge_text("gate 4", {}) == "gate 4", "a slotless pattern passes through"
assert badge_text("hi <who>", {"who": "Ada"}) == "hi Ada", "a slot takes its field value"
assert badge_text("<a>-<a>", {"a": "x"}) == "x-x", "the same field feeds two slots"
assert badge_text("<a><b>", {"a": "to", "b": "go"}) == "togo", "adjacent slots join their values"
assert badge_text("<a>!", {"a": ""}) == "!", "an empty field value is legal"


def rejects(*args):
    try:
        badge_text(*args)
    except Exception:
        return True
    return False


assert rejects(42, {}), "a non-string pattern is rejected"
assert rejects("a>b", {}), "a closing bracket outside any slot is rejected"
assert rejects("row <name", {"name": "x"}), "an unclosed opening bracket is rejected"
assert rejects("<>", {}), "an empty slot name is rejected"
assert rejects("<Big>", {"Big": "x"}), "a slot name outside lowercase letters is rejected"
assert rejects("<who> here", {}), "a slot name the mapping lacks is rejected"
print("ok")
