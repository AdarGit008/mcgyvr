from solution import build_set_meal

menu = [
    [{"code": "soup", "price": 300}, {"code": "pate", "price": 450}],
    [{"code": "beef", "price": 900}, {"code": "tofu", "price": 700}],
    [{"code": "tart", "price": 250}, {"code": "ices", "price": 200}],
]


def rejects(courses, quarrels):
    try:
        build_set_meal(courses, quarrels)
    except ValueError:
        return True
    return False


assert build_set_meal(menu, []) == {
    "total": 1200,
    "picks": ["soup", "tofu", "ices"],
}, "with no quarrel every course takes its cheapest option"
assert build_set_meal(menu, [["soup", "tofu"]]) == {
    "total": 1350,
    "picks": ["pate", "tofu", "ices"],
}, "one quarrel can make a dearer starter the cheaper tray"
assert build_set_meal(menu, [["soup", "tofu"], ["pate", "tofu"]]) == {
    "total": 1400,
    "picks": ["soup", "beef", "ices"],
}, "an option quarrelling with every starter is unreachable"
assert build_set_meal([[{"code": "one", "price": 50}]], []) == {
    "total": 50,
    "picks": ["one"],
}, "a single course of a single option"
assert build_set_meal(
    [[{"code": "b", "price": 100}, {"code": "a", "price": 100}]], []
) == {"total": 100, "picks": ["a"]}, (
    "an equal price is settled by the code reading smaller, not by listing order"
)
assert build_set_meal(
    [
        [{"code": "zz", "price": 100}, {"code": "yy", "price": 100}],
        [{"code": "mm", "price": 200}, {"code": "nn", "price": 200}],
    ],
    [["yy", "mm"]],
) == {"total": 300, "picks": ["yy", "nn"]}, (
    "the first course is settled before the second is looked at"
)
assert build_set_meal(menu, [["tart", "ices"]]) == {
    "total": 1200,
    "picks": ["soup", "tofu", "ices"],
}, "a quarrel between two options of one course can never bite"

assert rejects(
    [[{"code": "x", "price": 100}], [{"code": "y", "price": 100}]], [["x", "y"]]
), "a quarrel leaving no tray at all is refused"
assert rejects([], []), "no courses is refused"
assert rejects([[]], []), "a course offering nothing is refused"
assert rejects(menu, [["soup", "soup"]]), (
    "a quarrel of a code with itself is rejected"
)
assert rejects(menu, [["soup", "fish"]]), (
    "a quarrel naming an unoffered code is rejected"
)
assert rejects(
    [[{"code": "a", "price": 1}], [{"code": "a", "price": 2}]], []
), "a code offered by two courses is rejected"
assert rejects([[{"code": "a", "price": 0}]], []), (
    "a price below one penny is rejected"
)
assert rejects(
    [[{"code": "o" + str(n), "price": 5} for n in range(7)]], []
), "a course of seven options is too wide to search"
print("ok")
