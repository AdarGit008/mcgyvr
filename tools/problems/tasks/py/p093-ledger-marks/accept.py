from solution import link_ledger_marks

assert link_ledger_marks(["av-0042q", "AV/42Q", "vw 42q", "kx/26a"], {"VW": "AV"}) == [
    ["AV-42-Q", ["av-0042q", "AV/42Q", "vw 42q"]],
    ["KX-26-A", ["kx/26a"]],
], "case, zeros, separators and an alias all link"
assert link_ledger_marks(["KX/1b", "av-42q", "kx 001B"], {}) == [
    ["KX-1-B", ["KX/1b", "kx 001B"]],
    ["AV-42-Q", ["av-42q"]],
], "groups keep first-appearance order and raw spellings"
assert link_ledger_marks([], {}) == [], "no marks, no groups"
assert link_ledger_marks(["abc-7h"], {}) == [
    ["ABC-7-H", ["abc-7h"]]
], "three-letter house code, serial 7 checks as H"


def rejects(marks, aliases):
    try:
        link_ledger_marks(marks, aliases)
    except ValueError:
        return True
    return False


assert rejects(["av-42q"], {"VW": "AV", "AV": "KX"}), "chained alias is rejected"
assert rejects([], {"AV": "AV"}), "self alias is rejected"
assert rejects(["av-42r"], {}), "wrong check letter is rejected"
assert rejects(["av-0a"], {}), "serial 0 is rejected"
assert rejects(["a-42q"], {}), "one-letter house is rejected"
assert rejects(["av--42q"], {}), "double separator is rejected"
assert rejects(["av-42"], {}), "missing check letter is rejected"
assert rejects([7], {}), "non-string mark is rejected"
print("ok")
