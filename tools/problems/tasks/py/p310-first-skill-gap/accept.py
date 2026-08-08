from solution import first_skill_gap

ROSTER = [
    ["ivy", "540", "780", "till", "keys"],
    ["rex", "600", "900", "till"],
]


def rejects(shifts, required):
    try:
        first_skill_gap(shifts, required)
    except ValueError:
        return True
    return False


assert (
    first_skill_gap(ROSTER, [["till", "1", "540", "900"]]) == "covered"
), "one till hand is on duty right across the demand"
assert (
    first_skill_gap(ROSTER, [["keys", "1", "540", "900"]]) == "780-900 keys"
), "the only key holder goes home before the demand closes"
assert (
    first_skill_gap(ROSTER, [["till", "2", "540", "900"]]) == "540-600 till"
), "the second till hand has not arrived yet"
assert (
    first_skill_gap(ROSTER, [["till", "2", "600", "780"]]) == "covered"
), "a demand narrowed to the busy stretch is met"
assert (
    first_skill_gap(
        ROSTER,
        [["keys", "1", "540", "900"], ["till", "2", "540", "900"]],
    )
    == "540-600 till"
), "the earliest stretch wins over the earliest demand"
assert (
    first_skill_gap(
        ROSTER,
        [["spare", "1", "780", "900"], ["keys", "1", "780", "900"]],
    )
    == "780-900 spare"
), "within one stretch the demands are read in the order handed over"
assert (
    first_skill_gap(ROSTER, [["till", "1", "0", "300"]]) == "0-300 till"
), "an hour nobody is rostered for is a gap"
assert (
    first_skill_gap(
        [["ivy", "540", "600", "till"], ["rex", "660", "720", "till"]],
        [["till", "1", "540", "720"]],
    )
    == "600-660 till"
), "the hole between two tours is named"
assert (
    first_skill_gap([], [["till", "1", "540", "900"]]) == "540-900 till"
), "an empty roster leaves the whole demand bare"
assert (
    first_skill_gap(
        [["ivy", "0", "1440", "till", "keys", "safe"]],
        [["till", "1", "0", "1440"], ["safe", "1", "0", "1440"]],
    )
    == "covered"
), "one person covering the whole day answers every demand"

assert rejects("ivy", [["till", "1", "0", "60"]]), "a string is not a roster"
assert rejects(
    [["ivy", "540", "780"]], [["till", "1", "0", "60"]]
), "a tour with no skills is rejected"
assert rejects(
    [["ivy", "54x", "780", "till"]], [["till", "1", "0", "60"]]
), "a lettered minute is rejected"
assert rejects(
    [["ivy", "780", "540", "till"]], [["till", "1", "0", "60"]]
), "a tour that ends before it starts is rejected"
assert rejects(
    [["ivy", "540", "1500", "till"]], [["till", "1", "0", "60"]]
), "a minute past 1440 is rejected"
assert rejects(
    [["ivy", "540", "780", "till", "till"]], [["till", "1", "0", "60"]]
), "one skill written twice in a tour is rejected"
assert rejects(
    [["ivy", "540", "780", "till"], ["ivy", "600", "900", "keys"]],
    [["till", "1", "0", "60"]],
), "the same name rostered twice is rejected"
assert rejects(ROSTER, []), "a demand list with nothing in it is rejected"
assert rejects(ROSTER, [["till", "1", "540"]]), "a demand of three fields is rejected"
assert rejects(
    ROSTER, [["till", "0", "540", "900"]]
), "a demand for nobody is rejected"
assert rejects(
    ROSTER, [["till", "1", "900", "540"]]
), "a demand that closes before it opens is rejected"
print("ok")
