from solution import read_switches

KINDS = {"force": "switch", "level": "value"}

assert read_switches(KINDS, ["--force", "a"]) == {
    "found": {"force": True},
    "extra": ["a"],
}, "switch records true, bare token passes through"
assert read_switches(KINDS, ["--level", "3"]) == {
    "found": {"level": "3"},
    "extra": [],
}, "value option takes the next token"
assert read_switches(KINDS, ["--level=a=b"]) == {
    "found": {"level": "a=b"},
    "extra": [],
}, "split on the first = only"
assert read_switches(KINDS, ["--level", "1", "--level=2"]) == {
    "found": {"level": "2"},
    "extra": [],
}, "the later recording stands"
assert read_switches(KINDS, ["x", "--force", "y"]) == {
    "found": {"force": True},
    "extra": ["x", "y"],
}, "extras keep their order"
assert read_switches(KINDS, ["--level=", "z"]) == {
    "found": {"level": ""},
    "extra": ["z"],
}, "inline empty text is recorded"


def rejects(tokens):
    try:
        read_switches(KINDS, tokens)
    except ValueError:
        return True
    return False


assert rejects(["--wat"]), "unknown name errors"
assert rejects(["--level"]), "dangling value option errors"
assert rejects(["--force=on"]), "switch with inline form errors"
print("ok")
