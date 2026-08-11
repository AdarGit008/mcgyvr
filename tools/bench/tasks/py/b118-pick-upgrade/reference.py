"""Firmware build selection within an installed release line."""

import re

BUILD = re.compile(r"^(0|[1-9]\d*)(\.(0|[1-9]\d*))*$")


def compare_builds(a, b):
    left = [int(part) for part in a.split(".")]
    right = [int(part) for part in b.split(".")]
    for i in range(max(len(left), len(right))):
        x = left[i] if i < len(left) else 0
        y = right[i] if i < len(right) else 0
        if x > y:
            return 1
        if x < y:
            return -1
    return 0


def _check_build(text):
    if not isinstance(text, str) or not BUILD.match(text):
        raise ValueError("a build is dot-separated decimal numbers")


def pick_upgrade(installed, offers):
    _check_build(installed)
    if not isinstance(offers, list):
        raise ValueError("offers must be a list")
    major = int(installed.split(".")[0])
    best = None
    for offer in offers:
        _check_build(offer)
        if int(offer.split(".")[0]) != major:
            continue
        if compare_builds(offer, installed) <= 0:
            continue
        if best is None or compare_builds(offer, best) > 0:
            best = offer
    return best
