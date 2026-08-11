import re


def bump_release(version, part):
    if not isinstance(version, str):
        raise ValueError("version must be a string")
    pieces = version.split(".")
    if len(pieces) != 3:
        raise ValueError("version must have exactly three components")
    for piece in pieces:
        if re.fullmatch(r"0|[1-9]\d*", piece) is None:
            raise ValueError("bad version component: %s" % piece)
    major, minor, patch = (int(piece) for piece in pieces)
    if part == "major":
        return "%d.0.0" % (major + 1)
    if part == "minor":
        return "%d.%d.0" % (major, minor + 1)
    if part == "patch":
        return "%d.%d.%d" % (major, minor, patch + 1)
    raise ValueError("unknown part: %s" % part)
