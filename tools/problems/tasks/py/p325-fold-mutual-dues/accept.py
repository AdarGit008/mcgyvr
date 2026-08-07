from solution import fold_mutual_dues

assert fold_mutual_dues([]) == [], "no slips fold to nothing"
assert fold_mutual_dues([{"who": "ivy", "whom": "jon", "cents": 700}]) == [
    {"who": "ivy", "whom": "jon", "cents": 700}
], "a lone slip survives untouched"
assert (
    fold_mutual_dues(
        [
            {"who": "ivy", "whom": "jon", "cents": 700},
            {"who": "jon", "whom": "ivy", "cents": 700},
        ]
    )
    == []
), "matching directions wipe the pair out"
assert fold_mutual_dues(
    [
        {"who": "ivy", "whom": "jon", "cents": 700},
        {"who": "jon", "whom": "ivy", "cents": 250},
    ]
) == [{"who": "ivy", "whom": "jon", "cents": 450}], "the heavier direction keeps the difference"
assert fold_mutual_dues(
    [
        {"who": "ivy", "whom": "jon", "cents": 250},
        {"who": "jon", "whom": "ivy", "cents": 700},
    ]
) == [
    {"who": "jon", "whom": "ivy", "cents": 450}
], "the surviving slip may point the other way"
assert fold_mutual_dues(
    [
        {"who": "ivy", "whom": "jon", "cents": 100},
        {"who": "ivy", "whom": "jon", "cents": 50},
        {"who": "jon", "whom": "ivy", "cents": 30},
    ]
) == [{"who": "ivy", "whom": "jon", "cents": 120}], "repeated slips in one direction add up first"
assert fold_mutual_dues(
    [
        {"who": "jon", "whom": "ivy", "cents": 40},
        {"who": "ivy", "whom": "kai", "cents": 10},
        {"who": "kai", "whom": "jon", "cents": 5},
    ]
) == [
    {"who": "ivy", "whom": "kai", "cents": 10},
    {"who": "jon", "whom": "ivy", "cents": 40},
    {"who": "kai", "whom": "jon", "cents": 5},
], "a ring of three pairs is left as three slips in name order"
assert fold_mutual_dues(
    [
        {"who": "ivy", "whom": "jon", "cents": 50},
        {"who": "jon", "whom": "kai", "cents": 50},
    ]
) == [
    {"who": "ivy", "whom": "jon", "cents": 50},
    {"who": "jon", "whom": "kai", "cents": 50},
], "a debt never hops onto a third person"


def rejects(value):
    try:
        fold_mutual_dues(value)
    except ValueError:
        return True
    return False


assert rejects("slips"), "a non-list is rejected"
assert rejects([{"who": "ivy", "cents": 5}]), "a slip missing whom is rejected"
assert rejects(
    [{"who": "ivy", "whom": "ivy", "cents": 5}]
), "one person named twice is rejected"
assert rejects([{"who": "ivy", "whom": "jon", "cents": 0}]), "cents of zero is rejected"
assert rejects(
    [{"who": "ivy", "whom": "jon", "cents": 1.25}]
), "fractional cents are rejected"
assert rejects([{"who": "", "whom": "jon", "cents": 5}]), "an empty name is rejected"
assert rejects([["ivy", "jon", 5]]), "a slip that is a list is rejected"
print("ok")
