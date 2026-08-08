def shingle_overlap_ratio(left: str, right: str, width: int) -> list[int]:
    if not isinstance(width, int) or isinstance(width, bool) or width <= 0:
        raise ValueError("width must be a positive whole number")

    def windows(passage):
        if not isinstance(passage, str):
            raise ValueError("a passage must be a string")
        tokens = [token for token in passage.split(" ") if token]
        if not tokens:
            raise ValueError("a passage must carry at least one token")
        if len(tokens) < width:
            raise ValueError("a passage carries fewer tokens than the width")
        return {
            " ".join(tokens[start : start + width])
            for start in range(len(tokens) - width + 1)
        }

    here = windows(left)
    there = windows(right)
    shared = len(here & there)
    if shared == 0:
        return [0, 1]
    either = len(here | there)
    a, b = shared, either
    while b:
        a, b = b, a % b
    return [shared // a, either // a]
