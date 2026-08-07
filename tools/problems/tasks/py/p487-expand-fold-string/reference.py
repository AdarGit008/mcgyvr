"""The entries a squeezed line stands for."""

import re


def expand_fold_string(line: str) -> list:
    if not isinstance(line, str) or line == "":
        raise ValueError("the line must be a non-empty string")
    if re.fullmatch(r"[a-z()|-]+", line) is None:
        raise ValueError("the line holds a character that has no meaning here")

    at = 0

    def read_series(depth):
        nonlocal at
        found = []
        while True:
            found.extend(read_branch(depth))
            if at < len(line) and line[at] == "|":
                at += 1
                continue
            return found

    def read_branch(depth):
        nonlocal at
        if at < len(line) and line[at] == "-":
            if depth == 0:
                raise ValueError("a hyphen may only stand within a bracket")
            at += 1
            if at < len(line) and line[at] not in "|)":
                raise ValueError("a hyphen must stand alone")
            return [""]
        start = at
        while at < len(line) and "a" <= line[at] <= "z":
            at += 1
        stem = line[start:at]
        if stem == "":
            raise ValueError("a branch must carry a stem or a hyphen")
        if at < len(line) and line[at] == "(":
            at += 1
            inner = read_series(depth + 1)
            if at >= len(line) or line[at] != ")":
                raise ValueError("a bracket is never closed")
            at += 1
            if at < len(line) and line[at] not in "|)":
                raise ValueError("nothing may follow a closing bracket inside a branch")
            return [stem + tail for tail in inner]
        return [stem]

    entries = read_series(0)
    if at != len(line):
        raise ValueError("the line carries a bracket closed with none open")
    return entries
