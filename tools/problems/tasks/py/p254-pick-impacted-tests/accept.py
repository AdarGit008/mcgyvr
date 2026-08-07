from solution import pick_impacted_tests

table = {
    "api-smoke": ["src/api.ts", "src/util.ts"],
    "cli-args": ["src/cli.ts"],
    "lint-all": ["*"],
    "util-unit": ["src/util.ts"],
}

assert pick_impacted_tests(table, ["src/util.ts"]) == [
    "api-smoke",
    "lint-all",
    "util-unit",
], "one edited path reaches two touchers and the blanket test"
assert pick_impacted_tests(table, []) == [], "an empty edit list impacts nothing"
assert pick_impacted_tests(table, ["docs/readme.md"]) == [
    "lint-all"
], "an untouched path still wakes the blanket test"
assert pick_impacted_tests(table, ["src/cli.ts", "src/api.ts"]) == [
    "api-smoke",
    "cli-args",
    "lint-all",
], "results are ascending, not input order"
assert pick_impacted_tests(table, ["src/util.ts", "src/util.ts", "src/api.ts"]) == [
    "api-smoke",
    "lint-all",
    "util-unit",
], "a repeated edit does not repeat a test"
assert pick_impacted_tests({}, ["src/api.ts"]) == [], "an empty table picks nothing"

starred = {"blanket": ["*"], "mixed": ["*", "src/a.ts"]}
assert pick_impacted_tests(starred, ["src/z.ts"]) == [
    "blanket"
], "a two-entry list is not a blanket even when it holds a star"
assert pick_impacted_tests(starred, ["*"]) == [
    "blanket",
    "mixed",
], "inside a longer list the star is compared as a path"


def rejects(coverage, edited):
    try:
        pick_impacted_tests(coverage, edited)
    except ValueError:
        return True
    return False


assert rejects({"t": []}, ["a"]), "empty coverage is rejected"
assert rejects({"t": ["a", "a"]}, ["a"]), "a repeated path is rejected"
assert rejects({"": ["a"]}, ["a"]), "an empty test name is rejected"
assert rejects({"t": "a"}, ["a"]), "a non-list coverage value is rejected"
assert rejects(table, [7]), "a non-string edited path is rejected"
assert rejects([["t", ["a"]]], ["a"]), "a list table is rejected"
assert rejects(table, "src/api.ts"), "a string edit list is rejected"
print("ok")
