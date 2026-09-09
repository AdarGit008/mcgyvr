#!/usr/bin/env python3
"""Refuse to publish a wheel whose version is not the tag's.

    python tools/release/wheel_is_tag.py v0.1.0 dist/mcgyvr-0.1.0-py3-none-any.whl

The release workflow runs this between `uv build` and `gh release create`.
A mismatch is a tag on the wrong commit, or a build that read something
other than the tag, and a product that says one version while its tag says
another is the thing the release exists to make impossible. Compared as
versions and not as strings: a wheel's filename is PEP 440-normalised, so
`v0.1.0-rc1` builds `mcgyvr-0.1.0rc1-…` and the two are the same version.
"""

from __future__ import annotations

import sys
from pathlib import Path

from packaging.version import InvalidVersion, Version


def wheel_version(wheel: Path) -> str:
    """The version in a wheel's filename: `<dist>-<version>-<tags>.whl`."""
    return wheel.name.split("-")[1]


def mismatch(tag: str, wheel: Path) -> str | None:
    """Why ``wheel`` is not ``tag``'s, or None when it is."""
    try:
        wanted = Version(tag.removeprefix("v"))
    except InvalidVersion:
        return f"the tag {tag!r} is not a version; a release tag is v<PEP 440>"
    try:
        built = Version(wheel_version(wheel))
    except (InvalidVersion, IndexError):
        return f"{wheel.name} does not name a version"
    if built != wanted:
        return f"{wheel.name} is version {built}, and the tag {tag} is {wanted}"
    return None


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {Path(sys.argv[0]).name} TAG WHEEL", file=sys.stderr)
        return 2
    tag, wheel = argv[0], Path(argv[1])
    why = mismatch(tag, wheel)
    if why is not None:
        print(f"REFUSED — {why}", file=sys.stderr)
        return 1
    print(f"{wheel.name} is {tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
