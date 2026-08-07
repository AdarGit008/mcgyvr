from solution import fold_signature_map

assert fold_signature_map(20, 8, [1, 2, 5, 8, 9, 16, 20]) == [
    "1 1 1 front right",
    "2 1 1 back left",
    "5 1 2 back right",
    "8 1 1 front left",
    "9 2 1 front right",
    "16 2 1 front left",
    "20 3 2 back left",
], "eight-page signatures across three gatherings"

assert fold_signature_map(10, 4, [1, 2, 3, 4, 5, 9, 10]) == [
    "1 1 1 front right",
    "2 1 1 back left",
    "3 1 1 back right",
    "4 1 1 front left",
    "5 2 1 front right",
    "9 3 1 front right",
    "10 3 1 back left",
], "four-page signatures put all four places on one sheet"

assert fold_signature_map(64, 16, [1, 8, 9, 16, 17, 32]) == [
    "1 1 1 front right",
    "8 1 4 back left",
    "9 1 4 back right",
    "16 1 1 front left",
    "17 2 1 front right",
    "32 2 1 front left",
], "sixteen-page signatures fold onto four sheets"

assert fold_signature_map(12, 4, [3, 3]) == [
    "3 1 1 back right",
    "3 1 1 back right",
], "a repeated page is answered twice"

assert fold_signature_map(12, 4, []) == [], "no wanted pages gives no lines"

assert fold_signature_map(6, 8, [5, 6]) == [
    "5 1 2 back right",
    "6 1 2 front left",
], "a book padded out short of a whole signature"


def rejects(*args):
    try:
        fold_signature_map(*args)
    except ValueError:
        return True
    return False


assert rejects(0, 4, [1]), "a page count of nought is refused"
assert rejects(20001, 4, [1]), "beyond twenty thousand is refused"
assert rejects(20, 6, [1]), "a signature not dividing by four is refused"
assert rejects(20, 2, [1]), "a signature below four is refused"
assert rejects(20, 404, [1]), "a signature beyond four hundred is refused"
assert rejects(20, 4, "no"), "the wanted pages must be a list"
assert rejects(20, 4, [0]), "a wanted page of nought is refused"
assert rejects(20, 4, [21]), "a wanted page past the book is refused"
assert rejects(20, 4, [2.5]), "a fractional wanted page is refused"
print("ok")
