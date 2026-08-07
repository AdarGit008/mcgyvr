import re

def parse_semver(version: str) -> tuple[int, int, int, str | None]:
    """Parse MAJOR.MINOR.PATCH[-prerelease] into a tuple."""
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?", version)
    if not m:
        raise ValueError(f"invalid semver: {version!r}")
    return int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
