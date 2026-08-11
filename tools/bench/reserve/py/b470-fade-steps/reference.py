def fade_steps(level: int) -> list[int]:
    run = []
    current = level
    while current > 0:
        run.append(current)
        current = current // 2
    return run
