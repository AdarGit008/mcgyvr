from solution import select_by_impact

graph = {
    "core": [],
    "util": ["core"],
    "parser": ["util"],
    "render": ["util", "core"],
    "cli": ["parser", "render"],
    "docs": [],
}
suites = {
    "core-unit": ["core"],
    "parse-unit": ["parser"],
    "render-unit": ["render"],
    "cli-e2e": ["cli"],
    "docs-lint": ["docs"],
    "smoke": ["docs", "cli"],
}

assert select_by_impact(graph, suites, []) == [], "no edits run nothing"
assert select_by_impact(graph, suites, ["docs"]) == [
    "docs-lint",
    "smoke",
], "a leaf module disturbs only its own drivers"
assert select_by_impact(graph, suites, ["parser"]) == [
    "cli-e2e",
    "parse-unit",
    "smoke",
], "disturbance climbs one level to cli and stops"
assert select_by_impact(graph, suites, ["core"]) == [
    "ALL"
], "five of six suites trips the override"
assert select_by_impact(graph, suites, ["core", "docs"]) == [
    "ALL"
], "every suite running is still the override"
assert select_by_impact(graph, suites, ["util", "util"]) == [
    "ALL"
], "a repeated edit is the same edit"

looped = {"alpha": ["beta"], "beta": ["alpha"], "tool": ["alpha"], "leaf": []}
loop_suites = {
    "loop-a": ["alpha"],
    "loop-b": ["beta"],
    "tooly": ["tool"],
    "leafy": ["leaf"],
    "spare-x": ["leaf"],
    "spare-y": ["leaf"],
}
assert select_by_impact(looped, loop_suites, ["alpha"]) == [
    "loop-a",
    "loop-b",
    "tooly",
], "a two-module cycle terminates and drags in its importer"
assert select_by_impact(looped, loop_suites, ["leaf"]) == [
    "leafy",
    "spare-x",
    "spare-y",
], "exactly half is not more than half"
assert select_by_impact(looped, loop_suites, ["tool"]) == [
    "tooly"
], "nothing imports tool so nothing climbs"
assert select_by_impact({}, {}, []) == [], "an empty world runs nothing"


def rejects(imports, suites_arg, edited):
    try:
        select_by_impact(imports, suites_arg, edited)
    except ValueError:
        return True
    return False


assert rejects(graph, suites, ["ghost"]), "an undeclared edit is rejected"
assert rejects({"a": ["b"]}, {}, []), "an import of an undeclared module is rejected"
assert rejects({"a": []}, {"s": ["b"]}, []), "a suite driving an undeclared module is rejected"
assert rejects({"a": ["a"]}, {}, []), "a self-import is rejected"
assert rejects({"a": ["b", "b"], "b": []}, {}, []), "a repeated import is rejected"
assert rejects({"a": []}, {"": ["a"]}, []), "an empty suite name is rejected"
assert rejects(graph, suites, "core"), "a string edit list is rejected"
assert rejects([], suites, []), "a list module graph is rejected"
print("ok")
