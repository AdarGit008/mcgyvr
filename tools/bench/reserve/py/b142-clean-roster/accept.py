from solution import clean_roster

assert clean_roster([]) == [], "an empty sheet stays empty"
assert clean_roster(["Rosa Vane"]) == ["Rosa Vane"], "a tidy entry is unchanged"
assert clean_roster(["  Piet   Aker "]) == ["Piet Aker"], "spacing is trimmed and collapsed"
assert clean_roster(["Mo\tPine"]) == ["Mo Pine"], "a tab collapses to one space"
assert clean_roster(["Ana Reyes", "ANA REYES"]) == ["Ana Reyes"], "a case-insensitive repeat keeps the first spelling"
assert clean_roster(["Kit Snow", "Kit  Snow"]) == ["Kit Snow"], "a repeat appearing after cleaning is dropped"
assert clean_roster(["Zia Kade", "Ann Bell", "zia kade"]) == ["Zia Kade", "Ann Bell"], "first-appearance order is kept"


def rejects(value):
    try:
        clean_roster(value)
    except Exception:
        return True
    return False


assert rejects(42), "a non-list is rejected"
assert rejects([7]), "a non-string entry is rejected"
assert rejects(["   "]), "a whitespace-only entry is rejected"
assert rejects([""]), "an empty entry is rejected"
print("ok")
