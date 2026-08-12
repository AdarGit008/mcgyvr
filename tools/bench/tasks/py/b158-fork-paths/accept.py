from solution import fork_paths

assert fork_paths("src/main") == ["src/main"], "a forkless pattern names itself"
assert fork_paths("src/{lib,app}/main") == ["src/lib/main", "src/app/main"], "one fork in the middle"
assert fork_paths("{one}") == ["one"], "a fork of a single option"
assert fork_paths("{a,b,c}") == ["a", "b", "c"], "options keep their written order"
assert fork_paths("{a,b}/x") == ["a/x", "b/x"], "a fork may open the pattern"
assert fork_paths("logs/{old,new}") == ["logs/old", "logs/new"], "a fork may close the pattern"
assert fork_paths("s/{i,j}/{1,2}") == ["s/i/1", "s/i/2", "s/j/1", "s/j/2"], "an earlier fork varies slower"


def rejects(value):
    try:
        fork_paths(value)
    except Exception:
        return True
    return False


assert rejects(42), "a non-string pattern is rejected"
assert rejects(""), "an empty pattern is rejected"
assert rejects("a//b"), "an empty segment is rejected"
assert rejects("{a,}/x"), "an empty option is rejected"
assert rejects("x{y}/z"), "a brace inside a literal is rejected"
print("ok")
