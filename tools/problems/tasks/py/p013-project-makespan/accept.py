from solution import project_makespan

assert project_makespan({"a": 3}, []) == 3, "single task"
assert project_makespan({"a": 2, "b": 3}, []) == 3, "independent tasks overlap"
assert (
    project_makespan({"a": 1, "b": 2, "c": 3}, [["a", "b"], ["b", "c"]]) == 6
), "a chain adds up"
assert (
    project_makespan(
        {"a": 1, "b": 5, "c": 2, "d": 1},
        [["a", "b"], ["a", "c"], ["b", "d"], ["c", "d"]],
    )
    == 7
), "diamond takes its slowest branch"
assert (
    project_makespan({"a": 4, "b": 1, "c": 1}, [["b", "c"]]) == 4
), "a lone slow task dominates a short chain"
assert (
    project_makespan({"a": 2, "b": 2, "c": 2}, [["a", "c"], ["b", "c"]]) == 4
), "join waits for both prerequisites"


def rejects(durations, deps):
    try:
        project_makespan(durations, deps)
    except ValueError:
        return True
    return False


assert rejects({"a": 0}, []), "zero duration rejected"
assert rejects({"a": 2.5}, []), "fractional duration rejected"
assert rejects({"a": 1}, [["a", "ghost"]]), "unknown task in a pair rejected"
assert rejects({"a": 1}, [["a", "a"]]), "self-dependency rejected"
assert rejects({"a": 1, "b": 1}, [["a", "b"], ["b", "a"]]), "cycle rejected"
print("ok")
