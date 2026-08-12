from solution import vote_lead


def rejects(value):
    try:
        vote_lead(value)
    except Exception:
        return True
    return False


assert vote_lead(["a", "b", "a"]) == "a", "the clear winner"
assert vote_lead(["b", "a"]) == "a", "a tie goes alphabetically"
assert vote_lead(["z"]) == "z", "a single ballot decides it"
assert vote_lead(["c", "c", "d", "d", "a"]) == "c", "a tie at the top"
assert vote_lead(["x", "x", "y", "y", "y"]) == "y", "the later name still wins"
assert rejects([]), "no ballots is rejected"
print("ok")
