from solution import install_order

assert install_order(["c", "a", "b"], []) == [
    "a",
    "b",
    "c",
], "no requirements installs alphabetically"
assert install_order(["app", "lib", "core"], [["app", "lib"], ["lib", "core"]]) == [
    "core",
    "lib",
    "app",
], "a chain follows its requirements"
assert install_order(["d", "b", "a", "c"], [["d", "a"], ["c", "a"]]) == [
    "a",
    "b",
    "c",
    "d",
], "ties break alphabetically mid-run"
assert install_order(
    ["top", "left", "right", "base"],
    [["top", "left"], ["top", "right"], ["left", "base"], ["right", "base"]],
) == ["base", "left", "right", "top"], "a diamond resolves bottom-up"
assert install_order(
    ["mail", "auth", "db", "ui"],
    [["mail", "auth"], ["ui", "auth"], ["mail", "db"]],
) == ["auth", "db", "mail", "ui"], "independent branches interleave alphabetically"
assert install_order(["solo"], []) == ["solo"], "a single package"
assert install_order(["a", "b"], [["b", "a"], ["b", "a"]]) == [
    "a",
    "b",
], "a repeated requirement pair is harmless"


def rejects(*args):
    try:
        install_order(*args)
    except ValueError:
        return True
    return False


assert rejects(["pkg", "pkg"], []), "duplicate name"
assert rejects(["a", "b"], [["a", "ghost"]]), "unknown package in a pair"
assert rejects(["a"], [["a", "a"]]), "self-cycle"
assert rejects(["a", "b"], [["a", "b"], ["b", "a"]]), "two-package cycle"
assert rejects(
    ["a", "b", "c"], [["b", "a"], ["c", "b"], ["b", "c"]]
), "a cycle behind a valid head is still rejected"
print("ok")
