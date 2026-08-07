import re

_CHANNEL_RANK = {"dev": 0, "alpha": 1, "beta": 2, "rc": 3}
_RELEASE = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-(dev|alpha|beta|rc)\.(\d+))?")


def _parse(text):
    if not isinstance(text, str):
        raise ValueError("release must be a string")
    match = _RELEASE.fullmatch(text)
    if match is None:
        raise ValueError("malformed release string")
    major, minor, channel, build = match.groups()
    if channel is None:
        return (int(major), int(minor), 4, 0)
    return (int(major), int(minor), _CHANNEL_RANK[channel], int(build))


def newer_release(a: str, b: str) -> int:
    x = _parse(a)
    y = _parse(b)
    if x > y:
        return 1
    if x < y:
        return -1
    return 0
