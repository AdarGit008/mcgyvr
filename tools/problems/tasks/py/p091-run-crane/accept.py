from solution import run_crane

assert run_crane([["load", "a"], ["load", "b"], ["ship"], ["ship"]]) == [
    "b",
    "a",
], "the pile ships last-in first-out"
assert run_crane([["load", "a"], ["load", "b"], ["load", "c"], ["bury"], ["ship"]]) == [
    "b"
], "bury sends the top crate to the bottom"
assert run_crane([["load", "a"], ["load", "b"], ["scrap"], ["ship"]]) == [
    "a"
], "a scrapped crate never reaches the manifest"
assert run_crane([["load", "x"], ["bury"], ["ship"]]) == [
    "x"
], "burying the only crate leaves it on top"
assert run_crane([]) == [], "an empty script ships nothing"
assert run_crane([["load", "q"]]) == [], "loading alone ships nothing"
assert run_crane(
    [["load", "a"], ["load", "b"], ["bury"], ["bury"], ["ship"], ["ship"]]
) == ["b", "a"], "two buries on two crates cycle the pile back"


def rejects(script):
    try:
        run_crane(script)
    except ValueError:
        return True
    return False


assert rejects([["ship"]]), "shipping from an empty pile is a fault"
assert rejects([["load", "a"], ["hoist"]]), "an unknown move is a fault"
assert rejects([["bury"]]), "burying with an empty pile is a fault"
assert rejects([["scrap"]]), "scrapping with an empty pile is a fault"
print("ok")
