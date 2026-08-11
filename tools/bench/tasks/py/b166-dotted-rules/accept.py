from solution import match_setting

assert match_setting({"editor.font": "mono", "editor.*": "serif"}, "editor.font") == "mono", "the exact selector beats a wildcard"
assert match_setting({"editor.*": "serif", "editor.font.*": "mono"}, "editor.font.size") == "mono", "the longer covering prefix wins"
assert match_setting({"*": "plain"}, "log.level") == "plain", "the lone star covers any name"
assert match_setting({"net.*": "fast", "*": "plain"}, "net.retry") == "fast", "a prefix wildcard beats the lone star"
assert match_setting({"editor.*": "serif"}, "net.retry") is None, "an uncovered name yields None"
assert match_setting({"editor.*": "serif"}, "editor") is None, "a wildcard does not cover its bare prefix"
assert match_setting({}, "editor.font") is None, "no rules yields None"


def rejects(*args):
    try:
        match_setting(*args)
    except ValueError:
        return True
    return False


assert rejects({"*": "plain"}, 7), "a non-string name is rejected"
assert rejects({"*": "plain"}, ""), "an empty name is rejected"
assert rejects({"*": "plain"}, "a*b"), "a name holding a star is rejected"
assert rejects({"editor.*": 7}, "editor.font"), "a non-string rule value is rejected"
assert rejects({"edi*tor.x": "v"}, "editor.font"), "a misplaced star in a selector is rejected"
print("ok")
