def any_over(readings: list, level: int) -> bool:
    for reading in readings:
        if reading > level:
            return True
    return False


def window_any(readings: list, width: int, level: int) -> list:
    answers = []
    for i in range(len(readings) - width + 1):
        answers.append(any_over(readings[i : i + width], level))
    return answers
