from solution import shift_roster

assert shift_roster([]) == {}, "no entries yields an empty roster"
assert shift_roster([["mira", "day"]]) == {"day": ["mira"]}, "one entry fills one shift"
assert shift_roster([["zoe", "day"], ["abe", "day"]]) == {"day": ["abe", "zoe"]}, "names within a shift come out alphabetical"
assert shift_roster([["kai", "night"], ["ana", "day"], ["ben", "night"]]) == {"night": ["ben", "kai"], "day": ["ana"]}, "entries group under their own shifts"
assert shift_roster([["cyd", "late"], ["ada", "early"], ["bo", "late"], ["eli", "early"]]) == {"late": ["bo", "cyd"], "early": ["ada", "eli"]}, "several shifts fill independently"


def rejects(entries):
    try:
        shift_roster(entries)
    except Exception:
        return True
    return False


assert rejects("crew"), "an entries argument that is not a list is rejected"
assert rejects([["solo"]]), "a one-item entry is rejected"
assert rejects([["ana", "day", "extra"]]), "a three-item entry is rejected"
assert rejects([["", "day"]]), "an empty name is rejected"
assert rejects([["ana", 7]]), "a shift that is not a string is rejected"
assert rejects([["ana", "day"], ["ana", "night"]]), "a name signed up twice is rejected"
print("ok")
