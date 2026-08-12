def pace_of(seconds: int, kilometres: int) -> int:
    if kilometres <= 0:
        raise ValueError("a leg must cover ground")
    return seconds // kilometres


def pace_list(legs: list) -> list:
    return [pace_of(leg["seconds"], leg["kilometres"]) for leg in legs]
