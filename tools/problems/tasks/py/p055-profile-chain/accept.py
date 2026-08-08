from solution import resolve_profile

assert resolve_profile({"base": {"x": 1, "y": 2}}, "base") == {
    "x": 1,
    "y": 2,
}, "a chainless profile resolves to its own settings"
assert resolve_profile(
    {"base": {"x": 1, "y": 2}, "dev": {"extends": "base", "y": 3}}, "dev"
) == {"x": 1, "y": 3}, "a descendant setting beats its ancestor"
assert resolve_profile(
    {
        "base": {"retries": 1, "log": "warn"},
        "staging": {"extends": "base", "log": "info"},
        "local": {"extends": "staging", "debug": True},
    },
    "local",
) == {
    "retries": 1,
    "log": "info",
    "debug": True,
}, "three-level chains fold root-first"
assert resolve_profile(
    {"base": {"x": 1}, "dev": {"extends": "base"}}, "base"
) == {"x": 1}, "resolving an ancestor ignores its descendants"

untouched = {"base": {"x": 1}, "dev": {"extends": "base", "y": 2}}
resolve_profile(untouched, "dev")
assert untouched == {
    "base": {"x": 1},
    "dev": {"extends": "base", "y": 2},
}, "the input must not be mutated"


def rejects(profiles, wanted):
    try:
        resolve_profile(profiles, wanted)
    except ValueError:
        return True
    return False


assert rejects({"base": {"x": 1}}, "prod"), "an unknown requested name is rejected"
assert rejects(
    {"dev": {"extends": "ghost"}}, "dev"
), "an extends target with no profile is rejected"
assert rejects(
    {"a": {"extends": "b"}, "b": {"extends": "a"}}, "a"
), "a two-profile cycle is rejected"
assert rejects({"a": {"extends": "a"}}, "a"), "a self-extending profile is rejected"
print("ok")
