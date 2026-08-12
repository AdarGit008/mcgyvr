from solution import flag_states

assert flag_states(5, ["read", "write", "exec"]) == {
    "read": True,
    "write": False,
    "exec": True,
}, "mixed bits"
assert flag_states(0, ["trace", "color"]) == {
    "trace": False,
    "color": False,
}, "zero mask clears every flag"
assert flag_states(7, ["read", "write", "exec"]) == {
    "read": True,
    "write": True,
    "exec": True,
}, "saturated mask"
assert flag_states(1, ["armed"]) == {"armed": True}, "single-flag catalog"


def rejects(*args):
    try:
        flag_states(*args)
    except Exception:
        return True
    return False


assert rejects(-3, ["dryrun"]), "negative mask is rejected"
assert rejects(0, []), "empty catalog is rejected"
assert rejects(1, ["", "quiet"]), "empty flag name is rejected"
assert rejects(1, ["quiet", "quiet"]), "repeated flag name is rejected"
assert rejects(4, ["quiet", "loud"]), "bit beyond the catalog is rejected"
print("ok")
