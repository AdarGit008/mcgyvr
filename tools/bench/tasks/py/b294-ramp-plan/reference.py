def ramp_step(current: int, target: int, step: int) -> int:
    if current < target:
        return min(current + step, target)
    if current > target:
        return max(current - step, target)
    return current


def ramp_plan(start: int, target: int, step: int) -> list:
    visited = [start]
    while visited[-1] != target:
        visited.append(ramp_step(visited[-1], target, step))
    return visited
