"""The product names no machine it did not invent.

Promise: what the product ships and what a contributor reads holds no home
folder of a named user, no address that reaches a machine, no private host
name, no card model, no identity digest of a real machine and no pointer into
the development repository, except in the files a list names; the list may
only shrink.

The kinds, what passes by rule and what the check cannot see are stated in
:mod:`tests.uninvented_machines`, which this test and the command that writes
the list share. The list (``tests/uninvented_machines_not_yet_cleaned.txt``)
holds paths and counts, never the text found.

"The list may only shrink" is held in two places. Here: no file off the list
has a hit, no listed count is exceeded, and no file or kind is listed without
a hit, so every entry is true today. What the working tree cannot show is the
list as it was before a change; a pull request's CI compares the list with
the one on its base branch (``python tests/uninvented_machines.py --compare``)
and fails when it gained a file or a kind or a count rose. That job is not a
required check unless the repository's rules are changed to require it.
"""

from __future__ import annotations

import ipaddress
from pathlib import Path

import pytest

from tests import machine_shapes
from tests import uninvented_machines as um


def _is_checkout() -> bool:
    return (um.REPO / ".git").exists()


@pytest.fixture(scope="module")
def found() -> list[um.Hit]:
    if not _is_checkout():
        pytest.skip(f"{um.REPO} is not a git checkout; the files read are git's")
    return um.scan()


@pytest.fixture(scope="module")
def listed() -> um.Counts:
    return um.read_list()


def _say(where: list[str], limit: int = 60) -> str:
    shown = where[:limit]
    more = len(where) - len(shown)
    return "\n".join(shown) + (f"\n... and {more} more" if more > 0 else "")


def test_no_file_off_the_list_names_a_machine_the_product_did_not_invent(
    found: list[um.Hit], listed: um.Counts
) -> None:
    """A file not on the list holds no hit of any kind."""
    off = [hit for hit in found if hit.path not in listed]
    assert not off, (
        f"{len({hit.path for hit in off})} files off the list hold "
        f"{len(off)} hits. Per kind:\n{um.summary(off)}\n"
        "Where (path:line: kind; line 0 is the path name):\n"
        + _say([hit.where() for hit in off])
    )


def test_no_listed_file_holds_more_than_the_list_says(
    found: list[um.Hit], listed: um.Counts
) -> None:
    """A listed file may lose hits; it may not gain one, of any kind."""
    now = um.counts(found)
    more = [
        f"{path}: {kind} listed {listed[path].get(kind, 0)}, found {n}"
        for path, kinds in now.items()
        if path in listed
        for kind, n in kinds.items()
        if n > listed[path].get(kind, 0)
    ]
    assert not more, "listed files hold more than the list says:\n" + _say(more)


def test_every_entry_on_the_list_is_still_true(
    found: list[um.Hit], listed: um.Counts
) -> None:
    """A file or kind whose hits are gone leaves the list."""
    now = um.counts(found)
    stale = [
        f"{path}: {kind} listed {n}, none found"
        for path, kinds in listed.items()
        for kind, n in kinds.items()
        if not now.get(path, {}).get(kind)
    ]
    assert not stale, (
        "entries with nothing left to list; rewrite the list with "
        "`uv run --no-sync python -m tests.uninvented_machines --write`:\n"
        + _say(stale)
    )


def test_the_list_holds_paths_and_counts_in_order() -> None:
    """Sorted, one line per file, known kinds, positive counts, and no path the
    check does not read. Anything else is refused by name."""
    text = um.render({"a": {"host": 1}})
    assert um.parse(text) == {"a": {"host": 1}}
    for bad, says in [
        ("b\thost=1\na\thost=1\n", "out of order"),
        ("a\thost=1\na\thost=2\n", "listed twice"),
        ("a\tname=1\n", "not a kind"),
        ("a\thost=0\n", "not a positive number"),
        ("a\n", "no kind"),
        (f"{um.LEAVING[0]}/x\thost=1\n", "does not read"),
    ]:
        with pytest.raises(ValueError, match=says):
            um.parse(bad)
    um.read_list()


def test_the_list_only_shrinks_against_an_older_one() -> None:
    """The comparison CI runs: a new file, a new kind or a higher count grew."""
    old = {"a": {"host": 2}, "b": {"address": 1}}
    assert um.growth(old, {"a": {"host": 1}}) == []
    assert um.growth(old, {"a": {"host": 3}}) == ["a: host 2 -> 3"]
    assert um.growth(old, {"a": {"address": 1, "host": 2}}) == ["a: address 0 -> 1"]
    assert um.growth(old, {"c": {"host": 1}}) == ["c: host 0 -> 1"]


def _hits(text: str, path: str = "sample.txt") -> list[str]:
    return [hit.kind for hit in um.scan_text(path, text, allowed=um.invented_names())]


def test_the_invented_machines_and_reserved_names_pass() -> None:
    """Every name the generator of invented machines carries, the examples'
    names, reserved host names and documentation addresses pass."""
    lines = []
    for machine in machine_shapes.shapes():
        lines.append(f"host: {machine.host}")
        lines.append(f'"host": "{machine.host}", "rig": "{machine.label}"')
        lines.append(f"http://{machine.host}:8080/v1 {machine.machine_id}")
        lines.extend(card.name for card in machine.cards)
    for host in ("gpu-7.invalid", "box.test", "api.example.com", "localhost"):
        lines.append(f"http://{host}:8000 host={host!r}")
    for block in um.PASSING_NETWORKS:
        lines.append(f"http://{block.network_address}:9 {block.network_address}")
    lines.append("/home/someone/models /Users/<user>/x")
    lines.append("rig-" + "0" * 16 + " unt-" + "1" * 64)
    assert _hits("\n".join(lines)) == []


def test_each_kind_is_found_in_a_sample_made_up_here() -> None:
    """A made-up string of each kind is a hit of that kind.

    The samples are assembled from parts so that this file itself holds none.
    """
    documentation = ipaddress.ip_address("198.51.100.7")
    private = ".".join(("10", "9", "8", "7"))
    samples = (
        ("home-path", "/" + "home/" + "jdoe/models"),
        ("address", f"reach {private}; not {documentation}"),
        ("host", "http:/" + "/gpubox:8080/v1"),
        ("card-model", "one " + "RT" + "X 9999 card"),
        ("identity", "rig" + "-" + "0123456789abcdef"),
        ("dev-pointer", "see " + um.LEAVING[2] + "/" + "rules.md"),
    )
    for kind, text in samples:
        assert _hits(text) == [kind], (kind, text)
    name = um.product_name()
    assert _hits(f"{name}-" + "lab") == ["dev-pointer"]
    assert _hits("at node" + ".la" + "n") == ["host"]
    assert _hits('"host": "' + "gpubox" + '"') == ["host"]


def test_the_readme_may_name_the_development_repository_on_one_line() -> None:
    name = um.product_name() + "-" + "lab"
    assert _hits(f"x\nsee {name}\n", "README.md") == []
    assert _hits(f"see {name}\nand {name}\n", "README.md") == ["dev-pointer"] * 2
    assert _hits(f"see {name}\n", "other.md") == ["dev-pointer"]
    assert _hits(f"see {name}/rules.md\n", "README.md") == ["dev-pointer"]


def test_released_changelog_sections_are_history(tmp_path: Path) -> None:
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n## [Unreleased]\nnow\n## [0.1.0] - then\nold\n",
        encoding="utf-8",
    )
    assert um.text_of(tmp_path, "CHANGELOG.md") == "# Changelog\n## [Unreleased]\nnow\n"
