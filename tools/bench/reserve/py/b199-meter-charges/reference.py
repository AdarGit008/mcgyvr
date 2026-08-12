def meter_charges(allowance: dict, charges: list) -> dict:
    """Meter a period of charges against each caller's granted units."""
    report = {}
    for caller, granted in allowance.items():
        report[caller] = {"used": 0, "left": granted, "refused": 0}
    for caller, cost in charges:
        if caller not in report:
            raise ValueError(f"no allowance granted to {caller}")
        meter = report[caller]
        if cost < 0:
            returned = min(-cost, meter["used"])
            meter["used"] -= returned
            meter["left"] += returned
        elif cost <= meter["left"]:
            meter["used"] += cost
            meter["left"] -= cost
        else:
            meter["refused"] += 1
    return report
