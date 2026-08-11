def step_rate(amount: int, fixed: int, percent: int) -> int:
    return fixed + amount * percent // 100


def rate_steps(amounts: list, fixed: int, percent: int) -> list:
    return [step_rate(amount, fixed, percent) for amount in amounts]
