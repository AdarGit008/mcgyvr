from solution import fold_attempts

assert fold_attempts([]) == [], "no records, no cases"
assert fold_attempts(["alpha 1 pass"]) == ["alpha=pass"], "one try that passed"
assert fold_attempts(["alpha 1 fail"]) == ["alpha=fail"], "one try that failed"
assert fold_attempts(["alpha 1 fail", "alpha 2 pass"]) == [
    "alpha=flake"
], "failed then passed is a flake"
assert fold_attempts(["alpha 2 pass", "alpha 1 fail"]) == [
    "alpha=flake"
], "records may arrive out of order"
assert fold_attempts(["alpha 1 fail", "alpha 2 fail", "alpha 3 fail"]) == [
    "alpha=fail"
], "three failures settle to fail"
assert fold_attempts(["alpha 1 pass", "alpha 2 fail", "alpha 3 pass"]) == [
    "alpha=flake"
], "one failure among passes is a flake"
assert fold_attempts(["beta 1 pass", "alpha 1 fail"]) == [
    "alpha=fail",
    "beta=pass",
], "cases come out ordered by name"
assert fold_attempts(
    ["beta 1 fail", "alpha 1 pass", "beta 2 pass", "alpha 2 pass"]
) == ["alpha=pass", "beta=flake"], "two cases interleaved"


def rejects(records):
    try:
        fold_attempts(records)
    except ValueError:
        return True
    return False


assert rejects(["alpha 1"]), "two pieces are rejected"
assert rejects(["alpha 1 pass extra"]), "four pieces are rejected"
assert rejects(["alpha 1 skip"]), "a third word is rejected"
assert rejects(["alpha 0 pass"]), "try zero is rejected"
assert rejects(["alpha 01 pass"]), "a padded try is rejected"
assert rejects(["alpha x pass"]), "a lettered try is rejected"
assert rejects([" 1 pass"]), "an empty name is rejected"
assert rejects(["alpha 1 pass", "alpha 3 pass"]), "a skipped try number is rejected"
assert rejects(["alpha 1 pass", "alpha 1 fail"]), "a repeated try number is rejected"
assert rejects("alpha 1 pass"), "a bare string is rejected"
assert rejects([12]), "a non-string record is rejected"
print("ok")
