from solution import find_motif_sites

assert find_motif_sites("AACGTT", "ACG") == [1], "a plain motif sits once"
assert find_motif_sites("AAAA", "AA") == [0, 1, 2], "sittings may overlap"
assert find_motif_sites("ACGTACGT", "N") == [
    0,
    1,
    2,
    3,
    4,
    5,
    6,
    7,
], "N sits on every letter of the strand"
assert find_motif_sites("ACGT", "RY") == [0, 2], "R and Y each cover two letters"
assert find_motif_sites("GGCC", "S") == [0, 1, 2, 3], "S covers C and G"
assert find_motif_sites("AT", "W") == [0, 1], "W covers A and T"
assert find_motif_sites("ACGTG", "KM") == [], "a motif that fits nowhere sits nowhere"
assert find_motif_sites("TAGC", "KM") == [0, 2], "K and M read in that order"
assert find_motif_sites("ACGTACGT", "ACGT") == [0, 4], "a long plain motif sits twice"
assert find_motif_sites("AC", "ACG") == [], "a motif longer than the strand sits nowhere"
assert find_motif_sites("", "A") == [], "an empty strand holds nothing"
assert find_motif_sites("GATTACA", "NNN") == [
    0,
    1,
    2,
    3,
    4,
], "a run of N sits at every full-length window"
assert find_motif_sites("CAGGTAAGT", "GGTRAGT") == [
    2
], "a mixed motif pins one site in a longer strand"


def rejects(strand, motif):
    try:
        find_motif_sites(strand, motif)
    except ValueError:
        return True
    return False


assert rejects("ACGT", ""), "an empty motif is rejected"
assert rejects("ACGT", "ACX"), "an unnamed motif symbol is rejected"
assert rejects("ACGT", "acg"), "a lowercase motif is rejected"
assert rejects("ACGN", "AC"), "a degenerate symbol in the strand is rejected"
assert rejects(5, "AC"), "a non-string strand is rejected"
assert rejects("ACGT", 5), "a non-string motif is rejected"
print("ok")
