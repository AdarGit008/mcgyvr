from solution import course_weight_total


def only(items, weight=10000):
    return [{"label": "all", "weight": weight, "items": items}]


def rejects(value):
    try:
        course_weight_total(value)
    except ValueError:
        return True
    return False


assert course_weight_total(only([[45, 50]])) == 9000, "one category, one item"
assert course_weight_total(only([[50, 50], [20, 20]])) == 10000, "flawless reads 10000"
assert course_weight_total(only([[1, 3]])) == 3333, "the remainder is dropped"
assert course_weight_total(only([[0, 5], [0, 5]])) == 0, "nothing earned scores nothing"
assert course_weight_total(only([[1, 1], [0, 9]])) == 1000, "points pool across items"

assert (
    course_weight_total(
        [
            {"label": "quizzes", "weight": 6000, "items": [[7, 10]]},
            {"label": "final", "weight": 4000, "items": [[1, 3]]},
        ]
    )
    == 5533
), "two categories, each truncated on its own"

assert (
    course_weight_total(
        [
            {"label": "labs", "weight": 5000, "items": [[3, 4]]},
            {"label": "essays", "weight": 3000, "items": [[2, 7], [5, 7]]},
            {"label": "oral", "weight": 2000, "items": [[9, 10]]},
        ]
    )
    == 7050
), "three categories"

assert (
    course_weight_total(
        [
            {"label": "graded", "weight": 10000, "items": [[1, 2]]},
            {"label": "practice", "weight": 0, "items": [[0, 1]]},
        ]
    )
    == 5000
), "a zero weight contributes nothing but is still counted in the sum"

assert rejects([]), "an empty syllabus is rejected"
assert rejects(
    [
        {"label": "same", "weight": 5000, "items": [[1, 1]]},
        {"label": "same", "weight": 5000, "items": [[1, 1]]},
    ]
), "a repeated label is rejected"
assert rejects(only([[1, 1]], 9000)), "weights short of 10000 are rejected"
assert rejects(
    [
        {"label": "a", "weight": 11000, "items": [[1, 1]]},
        {"label": "b", "weight": -1000, "items": [[1, 1]]},
    ]
), "a negative weight is rejected"
assert rejects(
    [{"label": "empty", "weight": 10000, "items": []}]
), "a category with no items is rejected"
assert rejects(only([[0, 0]])), "an item worth nothing is rejected"
assert rejects(only([[6, 5]])), "earning more than the item is worth is rejected"
assert rejects(only([[-1, 5]])), "negative earned points are rejected"

print("ok")
