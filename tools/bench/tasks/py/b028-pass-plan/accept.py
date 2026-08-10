from solution import cheapest_pass_plan

assert cheapest_pass_plan([], [{"span": 1, "cost": 5}]) == {"total": 0, "purchases": []}, "no trips cost nothing"
assert cheapest_pass_plan([3], [{"span": 1, "cost": 4}]) == {"total": 4, "purchases": [[3, 1]]}, "one day one pass"
assert cheapest_pass_plan([3], [{"span": 1, "cost": 4}, {"span": 7, "cost": 3}]) == {"total": 3, "purchases": [[3, 7]]}, "cheaper kind wins"
assert cheapest_pass_plan([1, 2, 3, 4, 5], [{"span": 1, "cost": 2}, {"span": 7, "cost": 8}]) == {"total": 8, "purchases": [[1, 7]]}, "one long pass beats five short"
assert cheapest_pass_plan([1, 15, 30], [{"span": 1, "cost": 2}, {"span": 7, "cost": 8}]) == {"total": 6, "purchases": [[1, 1], [15, 1], [30, 1]]}, "sparse days buy short passes"
assert cheapest_pass_plan([1, 4, 6, 7, 8, 20], [{"span": 1, "cost": 2}, {"span": 7, "cost": 7}, {"span": 30, "cost": 15}]) == {"total": 11, "purchases": [[1, 1], [4, 7], [20, 1]]}, "mixed plan"
assert cheapest_pass_plan([2], [{"span": 1, "cost": 3}, {"span": 5, "cost": 3}]) == {"total": 3, "purchases": [[2, 1]]}, "tie prefers the first-listed kind"
assert cheapest_pass_plan([1, 2], [{"span": 1, "cost": 0}]) == {"total": 0, "purchases": [[1, 1], [2, 1]]}, "free passes still purchased"
assert cheapest_pass_plan([10], [{"span": 30, "cost": 9}]) == {"total": 9, "purchases": [[10, 30]]}, "span may reach past the last day"
assert cheapest_pass_plan([1, 7], [{"span": 7, "cost": 3}]) == {"total": 3, "purchases": [[1, 7]]}, "last covered day is start plus span minus 1"
assert cheapest_pass_plan([1, 8], [{"span": 7, "cost": 3}]) == {"total": 6, "purchases": [[1, 7], [8, 7]]}, "day past the span needs a second pass"


def rejects(trip_days, passes):
    try:
        cheapest_pass_plan(trip_days, passes)
    except ValueError:
        return True
    return False


assert rejects([0], [{"span": 1, "cost": 1}]), "day zero is rejected"
assert rejects([1.5], [{"span": 1, "cost": 1}]), "fractional day is rejected"
assert rejects([5, 5], [{"span": 1, "cost": 1}]), "repeated day is rejected"
assert rejects([1], []), "empty pass list is rejected"
assert rejects([1], [{"span": 0, "cost": 1}]), "zero span is rejected"
assert rejects([1], [{"span": 1, "cost": -2}]), "negative cost is rejected"
print("ok")
