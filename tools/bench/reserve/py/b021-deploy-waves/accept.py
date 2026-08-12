from solution import deploy_waves

assert deploy_waves([]) == [], "empty input yields no waves"
assert deploy_waves([("api", [])]) == [["api"]], "single service"
assert deploy_waves([("c", ["b"]), ("b", ["a"]), ("a", [])]) == [
    ["a"],
    ["b"],
    ["c"],
], "a chain is one service per wave"
assert deploy_waves([("zeta", []), ("alpha", []), ("mid", [])]) == [
    ["alpha", "mid", "zeta"]
], "independent services share a wave, sorted"
assert deploy_waves([("d", ["b", "c"]), ("b", ["a"]), ("c", ["a"]), ("a", [])]) == [
    ["a"],
    ["b", "c"],
    ["d"],
], "a diamond fans out and rejoins"
assert deploy_waves([("a", []), ("b", ["a"]), ("c", ["a", "b"])]) == [
    ["a"],
    ["b"],
    ["c"],
], "a service waits for its latest dependency"
assert deploy_waves([("a", []), ("c", ["a"]), ("d", ["b", "c"]), ("b", ["a"])]) == [
    ["a"],
    ["b", "c"],
    ["d"],
], "input order never affects the result"
assert deploy_waves(
    [
        ("web", ["db", "cache"]),
        ("db", []),
        ("cache", []),
        ("worker", ["db"]),
        ("mail", ["worker", "web"]),
    ]
) == [["cache", "db"], ["web", "worker"], ["mail"]], "a wider graph settles"


def rejects(services):
    try:
        deploy_waves(services)
    except Exception:
        return True
    return False


assert rejects([("a", []), ("a", [])]), "duplicate service name is rejected"
assert rejects([("", [])]), "empty name is rejected"
assert rejects([(7, [])]), "non-string name is rejected"
assert rejects([("a", [7])]), "non-string dependency is rejected"
assert rejects([("a", ["ghost"])]), "unknown dependency is rejected"
assert rejects([("a", ["a"])]), "self-dependency is rejected"
assert rejects([("a", []), ("b", ["a", "a"])]), "dependency listed twice is rejected"
assert rejects([("a", ["b"]), ("b", ["a"])]), "a two-cycle is rejected"
assert rejects([("a", ["b"]), ("b", ["c"]), ("c", ["a"])]), "a three-cycle is rejected"
print("ok")
