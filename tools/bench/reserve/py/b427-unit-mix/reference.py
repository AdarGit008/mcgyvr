def unit_mix(units: int, parts: int, per_unit: int) -> list:
    if per_unit <= 0:
        raise ValueError("a unit must hold parts")
    carried = parts // per_unit
    return [units + carried, parts - carried * per_unit]
