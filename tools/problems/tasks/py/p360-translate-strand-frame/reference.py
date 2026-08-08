VALUES = {"W": 0, "X": 1, "Y": 2, "Z": 3}
RESIDUES = "abcdefghijklmnop"
HALTS = ("ZZW", "ZZX")


def translate_strand_frame(strand: str) -> dict:
    if not isinstance(strand, str):
        raise ValueError("the strand must be a string")
    if len(strand) == 0:
        raise ValueError("the strand must not be empty")
    if len(strand) % 3 != 0:
        raise ValueError("the strand must run in whole codons of three")
    for symbol in strand:
        if symbol not in VALUES:
            raise ValueError("the strand holds a symbol outside W, X, Y and Z")
    letters = []
    halted = False
    for place in range(0, len(strand), 3):
        codon = strand[place : place + 3]
        if codon in HALTS:
            halted = True
            break
        letters.append(RESIDUES[4 * VALUES[codon[0]] + VALUES[codon[1]]])
    return {"residues": "".join(letters), "halted": halted}
