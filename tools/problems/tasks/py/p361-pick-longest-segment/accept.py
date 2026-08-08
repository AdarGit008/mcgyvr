from solution import pick_longest_segment

assert pick_longest_segment("ZWXWWWZZW") == {
    "frame": 0,
    "start": 0,
    "residues": "ma",
}, "one segment shutting on a closing marker"
assert pick_longest_segment("ZWXZZW") == {
    "frame": 0,
    "start": 0,
    "residues": "m",
}, "the opening marker alone still names m"
assert pick_longest_segment("ZWXZWXWWWZZW") == {
    "frame": 0,
    "start": 0,
    "residues": "mma",
}, "an opening marker inside a segment reads as a residue too"
assert pick_longest_segment("WZWXWWWXYZZZX") == {
    "frame": 1,
    "start": 1,
    "residues": "mag",
}, "the win sits in the second frame"
assert pick_longest_segment("WWZWXXYZZZWWWW") == {
    "frame": 2,
    "start": 2,
    "residues": "mg",
}, "the win sits in the third frame"
assert pick_longest_segment("ZWXWWWZZWZWXXYZWWWZZX") == {
    "frame": 0,
    "start": 9,
    "residues": "mga",
}, "the later segment is the longer one"
assert pick_longest_segment("WZWXZZWWWZWXZZW") == {
    "frame": 0,
    "start": 9,
    "residues": "m",
}, "equal lengths hand it to the smaller frame"
assert pick_longest_segment("ZWXWWWZZWZWXWWWZZW") == {
    "frame": 0,
    "start": 0,
    "residues": "ma",
}, "equal lengths in one frame hand it to the smaller start"
assert pick_longest_segment("ZWXWWW") == {
    "frame": -1,
    "start": -1,
    "residues": "",
}, "a segment that never shuts is thrown away"
assert pick_longest_segment("WWW") == {
    "frame": -1,
    "start": -1,
    "residues": "",
}, "a strand with no opening marker"
assert pick_longest_segment("ZZWZZX") == {
    "frame": -1,
    "start": -1,
    "residues": "",
}, "closing markers with nothing opened"


def rejects(strand):
    try:
        pick_longest_segment(strand)
    except ValueError:
        return True
    return False


assert rejects(7), "a strand that is not a string is thrown out"
assert rejects(""), "an empty strand is thrown out"
assert rejects("WWA"), "a symbol outside the four is thrown out"
assert rejects("zwx"), "lower case is thrown out"
print("ok")
