"""Route patterns over slash-separated paths: literals, :name, * and **."""

import re

NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def split_segments(path):
    if not isinstance(path, str) or not path:
        raise ValueError("path must be a non-empty string")
    if path[0] != "/":
        raise ValueError("path must start with a slash")
    if path == "/":
        return []
    segments = path[1:].split("/")
    for segment in segments:
        if not segment:
            raise ValueError("path holds an empty segment")
    return segments


def _match_from(pattern, pi, segments, si, captures):
    if pi == len(pattern):
        return si == len(segments)
    token = pattern[pi]
    if token == "**":
        for take in range(len(segments) - si + 1):
            if _match_from(pattern, pi + 1, segments, si + take, captures):
                return True
        return False
    if si == len(segments):
        return False
    if token.startswith(":"):
        captures[token[1:]] = segments[si]
        return _match_from(pattern, pi + 1, segments, si + 1, captures)
    if token != "*" and token != segments[si]:
        return False
    return _match_from(pattern, pi + 1, segments, si + 1, captures)


def match_route(pattern, path):
    tokens = split_segments(pattern)
    names = set()
    rests = 0
    for token in tokens:
        if token == "**":
            rests += 1
            if rests > 1:
                raise ValueError("** may appear at most once")
        elif token.startswith(":"):
            name = token[1:]
            if NAME_RE.fullmatch(name) is None:
                raise ValueError("malformed capture name: " + token)
            if name in names:
                raise ValueError("repeated capture name: " + name)
            names.add(name)
    segments = split_segments(path)
    captures = {}
    if _match_from(tokens, 0, segments, 0, captures):
        return captures
    return None


def first_route(patterns, path):
    for index, pattern in enumerate(patterns):
        if match_route(pattern, path) is not None:
            return index
    return -1
