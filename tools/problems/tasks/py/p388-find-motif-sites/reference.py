TABLE = {
    "A": "A",
    "C": "C",
    "G": "G",
    "T": "T",
    "R": "AG",
    "Y": "CT",
    "S": "CG",
    "W": "AT",
    "K": "GT",
    "M": "AC",
    "N": "ACGT",
}


def find_motif_sites(strand: str, motif: str) -> list[int]:
    if not isinstance(strand, str) or not isinstance(motif, str):
        raise ValueError("strand and motif must both be strings")
    if not motif:
        raise ValueError("motif must not be empty")
    for letter in strand:
        if letter not in "ACGT":
            raise ValueError(f"strand carries {letter}, which is not A, C, G or T")
    for symbol in motif:
        if symbol not in TABLE:
            raise ValueError(f"motif carries {symbol}, which the table does not name")

    sites: list[int] = []
    for start in range(0, len(strand) - len(motif) + 1):
        if all(
            strand[start + offset] in TABLE[symbol] for offset, symbol in enumerate(motif)
        ):
            sites.append(start)
    return sites
