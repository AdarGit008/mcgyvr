from collections import deque


def _reads_first(left: list[str], right: list[str]) -> bool:
    shared = min(len(left), len(right))
    for i in range(shared):
        if left[i] != right[i]:
            return left[i] < right[i]
    return len(left) < len(right)


def critical_chain_name(steps: list[dict]) -> str:
    if not isinstance(steps, list) or len(steps) == 0:
        raise ValueError("the job must hold at least one step")
    hours: dict[str, int] = {}
    needs: dict[str, list[str]] = {}
    for step in steps:
        if not isinstance(step, dict):
            raise ValueError("every step must be a mapping")
        label = step.get("label")
        if not isinstance(label, str) or label == "":
            raise ValueError("a label must be a non-empty string")
        if label in hours:
            raise ValueError("two steps carry the same label")
        cost = step.get("hours")
        if isinstance(cost, bool) or not isinstance(cost, int) or cost <= 0:
            raise ValueError("hours must be a whole number greater than zero")
        before = step.get("needs")
        if not isinstance(before, list):
            raise ValueError("the needs list must be a list")
        for earlier in before:
            if not isinstance(earlier, str):
                raise ValueError("the needs list must hold strings")
            if earlier == label:
                raise ValueError("a step may not need itself")
        hours[label] = cost
        needs[label] = list(before)
    for before in needs.values():
        for earlier in before:
            if earlier not in hours:
                raise ValueError("a needs entry matches no label in the job")

    labels = sorted(hours)
    later: dict[str, list[str]] = {label: [] for label in labels}
    owing: dict[str, int] = {}
    for label in labels:
        owing[label] = len(needs[label])
        for earlier in needs[label]:
            later[earlier].append(label)
    order: list[str] = []
    ready = deque(label for label in labels if owing[label] == 0)
    while ready:
        label = ready.popleft()
        order.append(label)
        for following in later[label]:
            owing[following] -= 1
            if owing[following] == 0:
                ready.append(following)
    if len(order) != len(labels):
        raise ValueError("the needs relation closes into a ring")

    weight: dict[str, int] = {}
    run: dict[str, list[str]] = {}
    for label in order:
        best_weight = 0
        best_run: list[str] = []
        for earlier in needs[label]:
            there = weight[earlier]
            if there > best_weight or (
                there == best_weight and _reads_first(run[earlier], best_run)
            ):
                best_weight = there
                best_run = run[earlier]
        weight[label] = best_weight + hours[label]
        run[label] = best_run + [label]

    picked_weight = -1
    picked: list[str] = []
    for label in labels:
        here = weight[label]
        if here > picked_weight or (
            here == picked_weight and _reads_first(run[label], picked)
        ):
            picked_weight = here
            picked = run[label]
    return ">".join(picked)
