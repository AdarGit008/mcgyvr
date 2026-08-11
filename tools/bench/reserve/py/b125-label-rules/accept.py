from solution import compile_rules, best_action

assert compile_rules([["invoice-????", "review"], ["*", "hold"]]) == [
    {"pattern": "invoice-????", "action": "review", "literals": 8},
    {"pattern": "*", "action": "hold", "literals": 0},
], "compiled rules carry their literal counts"


def rejects(fn, *args):
    try:
        fn(*args)
    except ValueError:
        return True
    return False


assert rejects(compile_rules, [["", "x"]]), "empty pattern"
assert rejects(compile_rules, [["a*b*", "x"]]), "second star"
assert rejects(compile_rules, [["ab", ""]]), "empty action"
assert rejects(compile_rules, [["ab", "x"], ["ab", "y"]]), "repeated pattern"
billing = compile_rules([
    ["*", "any"],
    ["invoice-??", "short"],
    ["invoice-2026", "exact"],
])
assert best_action(billing, "invoice-2026") == "exact", "most literals win over rule order"
assert best_action(billing, "invoice-77") == "short", "a ? run fits its exact length"
cache = compile_rules([["cache", "hit"]])
assert best_action(cache, "cachex") is None, "a starless pattern refuses longer text"
assert best_action(cache, "cache") == "hit", "a starless pattern fits its own length"
logs = compile_rules([["log*", "keep"]])
assert best_action(logs, "log") == "keep", "a star may span nothing"
sweeps = compile_rules([["*.tmp", "sweep"]])
assert best_action(sweeps, "notes.tmp") == "sweep", "a star-led tail anchors at the end"
assert best_action(sweeps, "notes.tmp.bak") is None, "text past the tail refuses"
loops = compile_rules([["ab*ba", "loop"]])
assert best_action(loops, "abba") == "loop", "head and tail may touch"
assert best_action(loops, "aba") is None, "text shorter than head plus tail refuses"
tie = compile_rules([["a?c", "first"], ["?bc", "second"]])
assert best_action(tie, "abc") == "first", "equal literals go to the earlier rule"
assert best_action(compile_rules([]), "anything") is None, "no rules, no action"
assert rejects(best_action, cache, 42), "non-string candidate"
print("ok")
