from solution import scan_manifest

assert scan_manifest("8ff2 pump.log", {"pump.log": "seal ok"}) == {
    "intact": ["pump.log"],
    "altered": [],
    "lost": [],
    "strays": [],
}, "a matching digest is intact"
assert scan_manifest("ffff pump.log", {"pump.log": "seal ok"}) == {
    "intact": [],
    "altered": ["pump.log"],
    "lost": [],
    "strays": [],
}, "a differing digest is altered"
assert scan_manifest("d952 tally.csv", {}) == {
    "intact": [],
    "altered": [],
    "lost": ["tally.csv"],
    "strays": [],
}, "a listed file not held is lost"
assert scan_manifest("", {"attic.txt": "x"}) == {
    "intact": [],
    "altered": [],
    "lost": [],
    "strays": ["attic.txt"],
}, "a held file never listed is a stray"
assert scan_manifest("", {}) == {
    "intact": [],
    "altered": [],
    "lost": [],
    "strays": [],
}, "nothing listed, nothing held"
assert scan_manifest(
    "8ff2 pump.log\n0001 rounds.txt\nddd4 gone.md",
    {"pump.log": "seal ok", "rounds.txt": "west wing clear", "attic.txt": "x"},
) == {
    "intact": ["pump.log"],
    "altered": ["rounds.txt"],
    "lost": ["gone.md"],
    "strays": ["attic.txt"],
}, "all four kinds report together"
assert scan_manifest("\n8ff2 pump.log\n\n", {"pump.log": "seal ok"}) == {
    "intact": ["pump.log"],
    "altered": [],
    "lost": [],
    "strays": [],
}, "blank manifest lines are ignored"
assert scan_manifest("0078 field notes.txt", {"field notes.txt": "x"}) == {
    "intact": ["field notes.txt"],
    "altered": [],
    "lost": [],
    "strays": [],
}, "a file name may contain spaces"
assert scan_manifest("0000 blank.cfg", {"blank.cfg": ""}) == {
    "intact": ["blank.cfg"],
    "altered": [],
    "lost": [],
    "strays": [],
}, "empty content digests to 0000"
assert scan_manifest("", {"loft.txt": "x", "attic.txt": "x"}) == {
    "intact": [],
    "altered": [],
    "lost": [],
    "strays": ["attic.txt", "loft.txt"],
}, "each list is sorted alphabetically"


def rejects(manifest, files):
    try:
        scan_manifest(manifest, files)
    except Exception:
        return True
    return False


assert rejects(42, {}), "non-string manifest is rejected"
assert rejects("8ff2", {}), "a line with no space is rejected"
assert rejects("zz pump.log", {}), "a short digest is rejected"
assert rejects("wxyz pump.log", {}), "non-hex digest is rejected"
assert rejects("8FF2 pump.log", {}), "uppercase digest is rejected"
assert rejects("8ff2 ", {}), "a line naming no file is rejected"
assert rejects("8ff2 pump.log\n8ff2 pump.log", {}), "a file listed twice is rejected"
assert rejects("", {"junk.bin": 7}), "non-string content is rejected"
print("ok")
