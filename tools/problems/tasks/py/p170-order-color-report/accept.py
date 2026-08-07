from solution import order_color_report

path = [[1], [0, 2], [1, 3], [2]]
ring = [[1, 4], [0, 2], [1, 3], [2, 4], [0, 3]]
star = [[1, 2, 3], [0], [0], [0]]
triangle = [[1, 2], [0, 2], [0, 1]]

assert order_color_report(path, [0, 1, 2, 3]) == [[0, 1, 0, 1], [2]], "chain"
assert order_color_report(path, [1, 2, 0, 3]) == [[1, 0, 1, 0], [2]], "middle start"
assert order_color_report(path, [0, 3, 1, 2]) == [
    [0, 1, 2, 0],
    [3],
], "an awkward sequence costs a third channel"
assert order_color_report(triangle, [0, 1, 2]) == [[0, 1, 2], [3]], "all clash"
assert order_color_report(star, [1, 2, 3, 0]) == [[1, 0, 0, 0], [2]], "hub last"
assert order_color_report(star, [0, 1, 2, 3]) == [[0, 1, 1, 1], [2]], "hub first"
assert order_color_report(ring, [0, 1, 2, 3, 4]) == [
    [0, 1, 0, 1, 2],
    [3],
], "an odd ring needs three"
assert order_color_report([[], [], []], [2, 0, 1]) == [[0, 0, 0], [1]], "no clashes"
assert order_color_report([[]], [0]) == [[0], [1]], "a lone transmitter"


def rejects(neighbours, visit_order):
    try:
        order_color_report(neighbours, visit_order)
    except ValueError:
        return True
    return False


assert rejects([], []), "no transmitters rejected"
assert rejects([[1], [0]], [0, 5]), "sequence names a stranger"
assert rejects([[1], [0]], [0, 0]), "sequence repeats a transmitter"
assert rejects([[1], [0]], [0]), "sequence too short rejected"
assert rejects([[0], [0]], [0, 1]), "self clash rejected"
assert rejects([[1], []], [0, 1]), "one-sided clash rejected"
assert rejects([[2], [0]], [0, 1]), "clash with a stranger rejected"
print("ok")
