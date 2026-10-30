"""The helper is fetched only as pinned for its system and architecture.

``mcgyvr-wg`` is pinned like llama.cpp: one tag, one archive per system and
architecture whose name one function makes (spelled as the wire spells a
system and an architecture), and for each the length and sha256 to hold it
to. A system with no pinned archive fetches nothing and offers no native
session; ``mcgyvr.rig.wgpin`` answers which systems have one from its table
alone, without fetching.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr import hubwire
from mcgyvr.rig import wgpin
from mcgyvr.serving.release import Asset, Release, ReleaseError

DIGEST = "0" * 64


@pytest.mark.parametrize(
    ("system", "arch", "name"),
    [
        ("darwin", "arm64", f"mcgyvr-wg-{wgpin.TAG}-darwin-arm64.tar.gz"),
        ("windows", "x86_64", f"mcgyvr-wg-{wgpin.TAG}-windows-x86_64.zip"),
        ("linux", "arm64", f"mcgyvr-wg-{wgpin.TAG}-linux-arm64.tar.gz"),
    ],
)
def test_each_helper_archive_is_named_once_by_system_and_architecture(
    system: str, arch: str, name: str
) -> None:
    assert wgpin.asset_name(system, arch) == name


def test_a_system_or_architecture_the_wire_does_not_name_has_no_archive() -> None:
    with pytest.raises(ReleaseError):
        wgpin.asset_name("plan9", "arm64")
    with pytest.raises(ReleaseError):
        wgpin.asset_name("darwin", "riscv64")
    assert not wgpin.pinned_for("plan9", "arm64")


def test_every_pinned_helper_archive_is_named_by_the_rule_with_its_digest() -> None:
    names = {
        wgpin.asset_name(system, arch)
        for system in hubwire.HOST_OS
        for arch in hubwire.HOST_ARCH
    }
    for asset in wgpin.RELEASE.assets:
        assert asset.name in names
        assert len(asset.sha256) == 64 and asset.sha256 == asset.sha256.lower()
        assert asset.bytes > 0
    assert (wgpin.RELEASE.tag, wgpin.RELEASE.repo) == (wgpin.TAG, wgpin.REPO)


def test_a_pinned_archive_is_known_from_the_table_without_a_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    name = wgpin.asset_name("windows", "x86_64")
    monkeypatch.setattr(
        wgpin, "RELEASE", Release(wgpin.REPO, wgpin.TAG, (Asset(name, 10, DIGEST),))
    )
    assert wgpin.pinned_for("windows", "x86_64")
    assert not wgpin.pinned_for("windows", "arm64")
    assert not wgpin.pinned_for("darwin", "x86_64")


def test_no_helper_is_fetched_for_a_system_nothing_is_pinned_for(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MCGYVR_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(wgpin, "RELEASE", Release(wgpin.REPO, wgpin.TAG, ()))
    with pytest.raises(ReleaseError, match="no pinned mcgyvr-wg"):
        wgpin.helper("darwin", "arm64")
    assert not (tmp_path / "home").exists()
