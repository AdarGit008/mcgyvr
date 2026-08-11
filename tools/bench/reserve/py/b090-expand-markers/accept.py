from solution import expand_markers

assert expand_markers("all clear", {}) == "all clear", "no markers passes through"
assert expand_markers("gate %gate% open", {"gate": "B4"}) == "gate B4 open", "single marker"
assert expand_markers("%a%-%b%-%a%", {"a": "x", "b": "y"}) == "x-y-x", (
    "a repeated marker expands each time"
)
assert expand_markers("%left%%right%", {"left": "L", "right": "R"}) == "LR", (
    "adjacent markers both expand"
)
assert expand_markers("100%% done", {}) == "100% done", "doubled percent is literal"
assert expand_markers("%pct%%% full", {"pct": "75"}) == "75% full", (
    "a marker then a literal percent"
)
assert expand_markers("", {}) == "", "empty template stays empty"


def rejects(*args):
    try:
        expand_markers(*args)
    except Exception:
        return True
    return False


assert rejects(9, {}), "non-string template is rejected"
assert rejects("%who%", {}), "unknown marker is rejected"
assert rejects("%a b%", {"a b": "x"}), "malformed name is rejected"
assert rejects("half %done", {"done": "d"}), "unclosed marker is rejected"
assert rejects("%n%", {"n": 3}), "non-string value is rejected"
print("ok")
