from solution import translate_strand_frame

assert translate_strand_frame("WWW") == {
    "residues": "a",
    "halted": False,
}, "the first residue of the run"
assert translate_strand_frame("XYZ") == {
    "residues": "g",
    "halted": False,
}, "four times one plus two lands on g"
assert translate_strand_frame("WWWXYZ") == {
    "residues": "ag",
    "halted": False,
}, "two codons read in order"
assert translate_strand_frame("WWWWWXWWYWWZ") == {
    "residues": "aaaa",
    "halted": False,
}, "the third symbol never moves the residue"
assert translate_strand_frame("ZWWZXWZYWZZY") == {
    "residues": "mnop",
    "halted": False,
}, "the tail of the sixteen-letter run"
assert translate_strand_frame("ZZW") == {
    "residues": "",
    "halted": True,
}, "a halt marker on its own"
assert translate_strand_frame("ZZX") == {
    "residues": "",
    "halted": True,
}, "the other halt marker"
assert translate_strand_frame("WWWZZXYYY") == {
    "residues": "a",
    "halted": True,
}, "what follows a halt marker is never read"
assert translate_strand_frame("ZZYZZZ") == {
    "residues": "pp",
    "halted": False,
}, "a codon close to a halt marker still names a residue"
assert translate_strand_frame("ZWXWWW") == {
    "residues": "ma",
    "halted": False,
}, "no halt marker leaves halted false"


def rejects(strand):
    try:
        translate_strand_frame(strand)
    except ValueError:
        return True
    return False


assert rejects(3), "a strand that is not a string is thrown out"
assert rejects(""), "an empty strand is thrown out"
assert rejects("WWWW"), "a length off the multiple of three is thrown out"
assert rejects("WWA"), "a symbol outside the four is thrown out"
assert rejects("www"), "lower case is thrown out"
print("ok")
