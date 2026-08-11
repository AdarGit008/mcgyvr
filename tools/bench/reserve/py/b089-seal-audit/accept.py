from solution import audit_chain, seal_of

assert seal_of("cargo", 0) == 6800, "seal of a note on a zero base"
assert seal_of("", 7) == 7, "empty note keeps the base"
assert audit_chain([]) == [], "empty trail is intact"
assert audit_chain([
    {"seq": 1, "note": "load", "seal": 6197},
    {"seq": 2, "note": "move", "seal": 470},
    {"seq": 3, "note": "drop", "seal": 568},
]) == [], "an intact trail reports nothing"
assert audit_chain([
    {"seq": 1, "note": "load", "seal": 6197},
    {"seq": 2, "note": "mole", "seal": 470},
    {"seq": 3, "note": "drop", "seal": 568},
]) == [2], "a reworded note flags only its record"
assert audit_chain([
    {"seq": 1, "note": "load", "seal": 6197},
    {"seq": 2, "note": "move", "seal": 471},
    {"seq": 3, "note": "drop", "seal": 568},
]) == [2, 3], "a forged seal flags the next record too"
assert audit_chain([
    {"seq": 1, "note": "load", "seal": 6202},
    {"seq": 2, "note": "move", "seal": 576},
]) == [1], "the opening seal is checked against zero"


def rejects(value):
    try:
        audit_chain(value)
    except ValueError:
        return True
    return False


assert rejects("x"), "non-list is rejected"
assert rejects([{"seq": 1, "note": "a"}]), "a missing seal is rejected"
assert rejects([{"seq": 1, "note": 7, "seal": 0}]), "a non-string note is rejected"
assert rejects([
    {"seq": 1, "note": "load", "seal": 6197},
    {"seq": 3, "note": "move", "seal": 470},
]), "a seq gap is rejected"
assert rejects([{"seq": 1, "note": "load", "seal": "6197"}]), "a string seal is rejected"
print("ok")
