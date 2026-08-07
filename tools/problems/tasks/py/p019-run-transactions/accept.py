from solution import run_transactions

assert run_transactions(["set a 1"]) == {"a": "1"}, "plain set"
assert run_transactions(["set a 1", "set a 2"]) == {"a": "2"}, "later set wins"
assert run_transactions(["begin", "set a 1", "commit"]) == {"a": "1"}, (
    "committed change lands"
)
assert run_transactions(["begin", "set a 1", "rollback"]) == {}, (
    "rolled-back change vanishes"
)
assert run_transactions(
    ["set a 1", "begin", "set a 2", "begin", "set a 3", "rollback", "commit"]
) == {"a": "2"}, "inner rollback spares the middle value"
assert run_transactions(
    ["begin", "set a 1", "begin", "set b 2", "commit", "rollback"]
) == {}, "outer rollback swallows an inner commit"
assert run_transactions(["set a 1", "begin", "unset a", "commit"]) == {}, (
    "a committed removal removes"
)
assert run_transactions(["set a 1", "begin", "unset a", "rollback"]) == {"a": "1"}, (
    "a rolled-back removal restores"
)
assert run_transactions(
    ["set a 1", "begin", "begin", "unset a", "commit", "commit"]
) == {}, "a removal survives two commits"
assert run_transactions(["unset ghost"]) == {}, "removing an absent key is fine"


def rejects(commands):
    try:
        run_transactions(commands)
    except ValueError:
        return True
    return False


assert rejects(["commit"]), "bare commit rejected"
assert rejects(["rollback"]), "bare rollback rejected"
assert rejects(["begin", "set a 1"]), "still-open transaction rejected"
assert rejects(["set a"]), "set missing its value rejected"
assert rejects(["frob x"]), "unknown verb rejected"
print("ok")
