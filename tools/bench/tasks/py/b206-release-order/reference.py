"""Order release tags by version, previews ahead of their plain release."""

import re


def _tag_key(tag):
    core, dash, preview = tag[1:].partition("-")
    major, minor, patch = (int(part) for part in core.split("."))
    if not dash:
        return (major, minor, patch, 1, "", 0)
    match = re.fullmatch(r"([a-z]+)(\d+)", preview)
    word = match.group(1)
    return (major, minor, patch, 0, word, int(match.group(2)))


def order_release_tags(tags: list) -> list:
    return sorted(tags, key=_tag_key)
