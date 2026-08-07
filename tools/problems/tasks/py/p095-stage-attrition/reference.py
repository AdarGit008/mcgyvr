def _fails(specimen: dict, stage: dict) -> bool:
    value = specimen.get(stage["field"])
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return True
    low = stage["low"]
    high = stage["high"]
    return (low is not None and value < low) or (high is not None and value > high)


def stage_attrition(specimens: list[dict], stages: list[dict]) -> list:
    seen = set()
    for stage in stages:
        name = stage.get("stage")
        if not isinstance(name, str) or name == "":
            raise ValueError("stage name must be a non-empty string")
        if name == "through":
            raise ValueError('a stage may not be named "through"')
        if name in seen:
            raise ValueError(f"stage name repeated: {name}")
        seen.add(name)
        low = stage["low"]
        high = stage["high"]
        if low is not None and high is not None and low > high:
            raise ValueError("low exceeds high")
    counts = {stage["stage"]: 0 for stage in stages}
    through = 0
    for specimen in specimens:
        first = next((stage for stage in stages if _fails(specimen, stage)), None)
        if first is None:
            through += 1
        else:
            counts[first["stage"]] += 1
    pairs = [[name, left] for name, left in counts.items()]
    pairs.append(["through", through])
    return pairs
