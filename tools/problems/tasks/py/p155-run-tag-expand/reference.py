import re


def expand_run_tag(pattern: str) -> list:
    if not isinstance(pattern, str):
        raise ValueError("pattern must be a string")
    open_at = pattern.find("[")
    close_at = pattern.find("]")
    if open_at == -1 or close_at == -1:
        raise ValueError("no group")
    if close_at < open_at:
        raise ValueError("brackets reversed")
    if pattern.find("[", open_at + 1) != -1 or pattern.find("]", close_at + 1) != -1:
        raise ValueError("extra bracket")
    stem = pattern[:open_at]
    tail = pattern[close_at + 1 :]
    body = pattern[open_at + 1 : close_at]
    if body == "":
        raise ValueError("empty body")
    run = re.fullmatch(r"(\d+)-(\d+)(?:/(\d+))?", body)
    if run is not None:
        lo, hi = int(run.group(1)), int(run.group(2))
        step = 1 if run.group(3) is None else int(run.group(3))
        if lo > hi:
            raise ValueError("descending run")
        if step == 0:
            raise ValueError("zero step")
        items = [str(v) for v in range(lo, hi + 1, step)]
    else:
        items = body.split(",")
        for item in items:
            if item == "":
                raise ValueError("empty item")
    return sorted({stem + item + tail for item in items})
