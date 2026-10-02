"""Invented link numbers and an invented link reader for the tests of the interconnect.

The values are made up here, so a test built on them promises how a link is
answered, layered, fitted and refused, never what any shipped number is. The
numbers file a test reads is its own, written under ``tmp_path`` and put in
place of the shipped one for that test; the user's config and data folders are
moved under ``tmp_path`` too.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr import derived
from mcgyvr.fleet import links
from tests import numbers_fixture as nf

HOST_A = "box-a.example"
HOST_B = "box-b.example"

#: Bandwidth (GiB/s) and latency (microseconds) the invented estimate states.
ESTIMATED: dict[str, tuple[float, float]] = {
    links.PCIE: (20.0, 5.0),
    links.NETWORK: (1.0, 400.0),
}
#: What the invented link a reader times really is.
TRUE_GIB_S = 3.0
TRUE_LATENCY_US = 50.0
#: Payloads of four sizes, small to large, in bytes.
SIZES = (1 << 10, 1 << 20, 1 << 26, 1 << 30)

_GIB = 2**30
_US = 1_000_000.0


def invented_estimates() -> dict[str, object]:
    """A shipped-shaped document stating the link numbers with invented values."""
    entry = {
        "kind": "estimate",
        "estimates": "an invented quantity",
        "used_for": "nothing; a test reads it",
        "key": "link_class",
        "note": "invented for a test",
    }
    return {
        "_doc": "Invented for a test.",
        "schema": derived.NUMBERS_SCHEMA,
        "numbers": {
            derived.LINK_GIB_S: {
                **entry,
                "unit": "GiB/s",
                "values": {name: pair[0] for name, pair in ESTIMATED.items()},
            },
            derived.LINK_LATENCY_US: {
                **entry,
                "unit": "microseconds",
                "values": {name: pair[1] for name, pair in ESTIMATED.items()},
            },
        },
    }


def own_folders(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    document: dict[str, object] | None = None,
) -> None:
    """The user's folders and the shipped numbers are this test's own."""
    monkeypatch.setenv("MCGYVR_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("MCGYVR_DATA", str(tmp_path / "data"))
    shipped = nf.write_json(
        tmp_path / "shipped" / "numbers.json", document or invented_estimates()
    )
    monkeypatch.setattr(derived, "shipped_path", lambda: shipped)


def set_by_user(tmp_path: Path, content: dict[str, dict[str, float]]) -> Path:
    """Write the user's own ``numbers.yaml`` under this test's own config folder."""
    import yaml

    path = derived.overrides_path()
    assert path.is_relative_to(tmp_path), f"{path} is not under {tmp_path}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(content), encoding="utf-8")
    return path


def timed(
    gib_s: float = TRUE_GIB_S, latency_us: float = TRUE_LATENCY_US
) -> list[tuple[int, float]]:
    """Transfers of :data:`SIZES` over a link that really has these figures."""
    return [(size, latency_us / _US + size / (gib_s * _GIB)) for size in SIZES]


def reader(host_a: str, host_b: str) -> list[tuple[int, float]]:
    """A reader that times the invented link; it opens nothing."""
    return timed()
