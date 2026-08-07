CODE = {
    "A": "A",
    "C": "C",
    "G": "G",
    "T": "T",
    "AG": "R",
    "CT": "Y",
    "CG": "S",
    "AT": "W",
    "GT": "K",
    "AC": "M",
    "CGT": "B",
    "AGT": "D",
    "ACT": "H",
    "ACG": "V",
    "ACGT": "N",
}

LETTERS = ("A", "C", "G", "T")


def fold_aligned_motif(alignment: object, least: object) -> dict[str, object]:
    if not isinstance(alignment, list) or not alignment:
        raise ValueError("alignment must be a non-empty list of rows")
    for row in alignment:
        if not isinstance(row, str) or not row:
            raise ValueError("every row must be a non-empty string")
        if len(row) != len(alignment[0]):
            raise ValueError("every row must be the same length")
        for letter in row:
            if letter not in LETTERS:
                raise ValueError(f"a row holds {letter}, which is not A, C, G or T")
    if not isinstance(least, int) or isinstance(least, bool) or least < 1:
        raise ValueError("least must be a whole number of at least one")

    width = len(alignment[0])
    codes: list[str] = []
    outliers: list[int] = []
    for column in range(width):
        tally = {letter: 0 for letter in LETTERS}
        for row in alignment:
            tally[row[column]] += 1
        present = [letter for letter in LETTERS if tally[letter] > 0]
        kept = [letter for letter in present if tally[letter] >= least]
        if not kept:
            kept = present
        elif len(kept) < len(present):
            outliers.append(column)
        codes.append(CODE["".join(kept)])
    return {"pattern": "".join(codes), "outliers": outliers}
