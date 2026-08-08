from solution import fold_aligned_motif

assert fold_aligned_motif(["ACGT", "ACGA", "ACGT"], 2) == {
    "pattern": "ACGT",
    "outliers": [3],
}, "a lone stray letter is thrown away and its column is an outlier"
assert fold_aligned_motif(["AC", "GT"], 1) == {
    "pattern": "RY",
    "outliers": [],
}, "a least of one keeps everything and names the pairs"
assert fold_aligned_motif(["A", "C", "G", "T"], 2) == {
    "pattern": "N",
    "outliers": [],
}, "a column no letter carries far enough falls back to all of them"
assert fold_aligned_motif(["AAC", "AGC", "ATC", "AAC"], 2) == {
    "pattern": "AAC",
    "outliers": [1],
}, "two strays in one column still make one outlier"
assert fold_aligned_motif(["ACGTA", "AGGTC", "ACGTG", "ACTTA"], 3) == {
    "pattern": "ACGTV",
    "outliers": [1, 2],
}, "outliers come back in ascending order beside a rescued column"
assert fold_aligned_motif(["A", "C", "G", "A", "C", "G"], 2) == {
    "pattern": "V",
    "outliers": [],
}, "three surviving letters name a triple code"
assert fold_aligned_motif(["C", "G", "T", "C", "G", "T"], 2) == {
    "pattern": "B",
    "outliers": [],
}, "the triple without A is B"
assert fold_aligned_motif(["A", "G", "T", "A", "G", "T"], 2) == {
    "pattern": "D",
    "outliers": [],
}, "the triple without C is D"
assert fold_aligned_motif(["A", "C", "T", "A", "C", "T"], 2) == {
    "pattern": "H",
    "outliers": [],
}, "the triple without G is H"
assert fold_aligned_motif(["CGAT", "GCTA"], 1) == {
    "pattern": "SSWW",
    "outliers": [],
}, "every pair code is reachable"
assert fold_aligned_motif(["GA", "TC"], 1) == {
    "pattern": "KM",
    "outliers": [],
}, "K and M name their own pairs"
assert fold_aligned_motif(["AC", "AT"], 5) == {
    "pattern": "AY",
    "outliers": [],
}, "a least beyond the row count rescues every column"
assert fold_aligned_motif(["GATTACA"], 1) == {
    "pattern": "GATTACA",
    "outliers": [],
}, "one row folds to itself"


def rejects(alignment, least):
    try:
        fold_aligned_motif(alignment, least)
    except ValueError:
        return True
    return False


assert rejects([], 1), "an empty alignment is rejected"
assert rejects("ACGT", 1), "a non-list alignment is rejected"
assert rejects(["ACGT", ""], 1), "an empty row is rejected"
assert rejects(["ACGT", "AC"], 1), "rows of unequal length are rejected"
assert rejects(["ACGT", 5], 1), "a row that is not a string is rejected"
assert rejects(["ACGN"], 1), "a code inside a row is rejected"
assert rejects(["ACGT"], 0), "a least of zero is rejected"
assert rejects(["ACGT"], 1.5), "a fractional least is rejected"
print("ok")
