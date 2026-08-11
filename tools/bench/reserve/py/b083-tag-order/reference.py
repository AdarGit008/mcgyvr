"""Order release tags oldest first, candidates before their release."""

import re

FORM = r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-rc\.([1-9]\d*))?"


def order_releases(tags):
    if not isinstance(tags, list):
        raise ValueError("order_releases expects a list of tags")
    seen = set()
    keyed = []
    for tag in tags:
        if not isinstance(tag, str):
            raise ValueError("every tag must be a string")
        match = re.fullmatch(FORM, tag)
        if match is None:
            raise ValueError("malformed release tag: " + tag)
        if tag in seen:
            raise ValueError("tag appears twice: " + tag)
        seen.add(tag)
        major, minor, patch, rc = match.groups()
        rank = (1, 0) if rc is None else (0, int(rc))
        keyed.append(((int(major), int(minor), int(patch)) + rank, tag))
    keyed.sort()
    return [tag for _, tag in keyed]
