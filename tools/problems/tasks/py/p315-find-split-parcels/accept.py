from solution import find_split_parcels


def rejects(plan):
    try:
        find_split_parcels(plan)
    except ValueError:
        return True
    return False


assert find_split_parcels(["AAB", "AAB", "CCB"]) == [], "three whole parcels"
assert (
    find_split_parcels(["AAAA", "A..A", "AAAA"]) == []
), "a ring around unclaimed ground is still whole"
assert find_split_parcels(["..A..", ".AAA.", "..A.."]) == [], "a cross is whole"
assert find_split_parcels(["ABA", "BBB", "ABA"]) == [
    "A:4"
], "corners of one letter are four pieces while the letter between them holds"
assert find_split_parcels(["AB", "BA"]) == [
    "A:2",
    "B:2",
], "diagonal neighbours do not touch"
assert find_split_parcels(["A.A"]) == ["A:2"], "unclaimed ground cuts a parcel in two"
assert find_split_parcels(["ABCA"]) == [
    "A:2"
], "a single row with the same letter at both ends"
assert (
    find_split_parcels(["AABBB", "A.B.B", "AABBB"]) == []
), "two whole parcels side by side"
assert rejects([]), "a map with no rows is rejected"
assert rejects(["AB", "A"]), "a ragged map is rejected"
assert rejects(["Ab"]), "a lowercase marking is rejected"
assert rejects(["A1"]), "a digit marking is rejected"
assert rejects([".."]), "a map claiming nothing is rejected"
assert rejects("AB"), "a bare string is rejected"
print("ok")
