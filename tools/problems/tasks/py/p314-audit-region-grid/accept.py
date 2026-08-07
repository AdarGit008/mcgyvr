from solution import audit_region_grid

SHAPES = ["AAAB", "CABB", "CCDB", "CDDD"]


def rejects(digits, territories):
    try:
        audit_region_grid(digits, territories)
    except ValueError:
        return True
    return False


assert (
    audit_region_grid(["1234", "3412", "2143", "4321"], SHAPES) == "ok"
), "a sound board under jagged territories"
assert audit_region_grid(["1"], ["A"]) == "ok", "a board of side one"
assert audit_region_grid(["12", "21"], ["AB", "AB"]) == "ok", "territories as files"
assert (
    audit_region_grid(["1234", "2143", "3412", "4321"], SHAPES) == "territory A"
), "rows and files hold but the first territory does not"
assert (
    audit_region_grid(["1234", "3421", "4312", "2143"], SHAPES) == "territory B"
), "the earliest broken territory by letter"
assert (
    audit_region_grid(["1234", "3421", "4311", "2143"], SHAPES) == "row 3"
), "a repeated digit in a row outranks anything later"
assert (
    audit_region_grid(["1234", "1234", "3412", "4321"], SHAPES) == "file 1"
), "files are tested once every row has held"
assert rejects(["1234", "341", "2143", "4321"], SHAPES), "a short row is rejected"
assert rejects(["12", "21"], ["AB"]), "unequal heights are rejected"
assert rejects(
    ["1235", "3412", "2143", "4321"], SHAPES
), "a digit above the side is rejected"
assert rejects(
    ["1234", "3412", "2143", "4321"], ["aaab", "CABB", "CCDB", "CDDD"]
), "a lowercase label is rejected"
assert rejects(
    ["1234", "3412", "2143", "4321"], ["AAAA", "BBBB", "CCCC", "CCCC"]
), "three territories on a board of four is rejected"
assert rejects(
    ["1234", "3412", "2143", "4321"], ["AAAA", "AABB", "BBCC", "CCDD"]
), "territories of unequal size are rejected"
print("ok")
