"""The product names no machine it did not invent.

Promise: what the product ships and what a contributor reads holds no home
folder of a named user, no address that reaches a machine, no private host
name, no card model, no identity digest of a real machine and no pointer into
the development repository, except in the files a list names, each with the
hits of each kind it holds; the list may only shrink.

The kinds, what passes and what the check cannot see are stated in
:mod:`tests.uninvented_machines`, which this test and the command that writes
the list share. The list (``tests/uninvented_machines_not_yet_cleaned.txt``)
holds paths and counts, never the text found, in two sections: files not yet
cleaned, and files that keep such strings on purpose as their inputs.

What is held here: the scan finds exactly the files, kinds and counts the list
names, so a cleaned hit needs the list rewritten and a count cannot climb back.
A hit replaced by another of the same kind in a listed file keeps the count
and is not seen. What the working tree cannot show is the list as it was
before a change; a pull request's CI compares the list with the one on its
base branch (``python tests/uninvented_machines.py --compare``) and fails when
it gained a file or a kind or a count rose. That job is not a required check
unless the repository's rules are changed to require it.

Every sample below that must be a hit is assembled from parts, so this file
itself holds none.
"""

from __future__ import annotations

import ipaddress
import os
import subprocess
from pathlib import Path

import pytest

from tests import machine_shapes
from tests import uninvented_machines as um

_FOLDER = um.LEAVING[4]  # a folder that leaves the product and is a module name
_PRIVATE = ".".join(("10", "9", "8", "7"))
_HOST = "gpu" + "box"
_CARD = "RT" + "X 9999"


def _is_checkout() -> bool:
    return (um.REPO / ".git").exists()


@pytest.fixture(scope="module")
def found() -> list[um.Hit]:
    if not _is_checkout():
        pytest.skip(f"{um.REPO} is not a git checkout; the files read are git's")
    return um.scan()


@pytest.fixture(scope="module")
def listed() -> um.Listed:
    return um.read_list()


def _say(where: list[str], limit: int = 60) -> str:
    shown = where[:limit]
    more = len(where) - len(shown)
    return "\n".join(shown) + (f"\n... and {more} more" if more > 0 else "")


def _hits(text: str, path: str = "sample.txt") -> list[str]:
    return [hit.kind for hit in um.scan_text(path, text)]


# --- the product against its list -------------------------------------------


def test_no_file_off_the_list_names_a_machine_the_product_did_not_invent(
    found: list[um.Hit], listed: um.Listed
) -> None:
    """A file on neither section of the list holds no hit of any kind."""
    off = [hit for hit in found if hit.path not in listed.all()]
    assert not off, (
        f"{len({hit.path for hit in off})} files off the list hold "
        f"{len(off)} hits. Per kind:\n{um.summary(off)}\n"
        "Where (path:line: kind; line 0 is the path name):\n"
        + _say([hit.where() for hit in off])
    )


def test_every_listed_count_is_the_count_found(
    found: list[um.Hit], listed: um.Listed
) -> None:
    """Found equals listed, per file and kind, in both sections: a cleaned
    hit needs the list rewritten, and a count cannot climb back."""
    now = um.counts(found)
    table = listed.all()
    differ = [
        f"{um.shown(path)}: {kind} listed {table[path].get(kind, 0)}, "
        f"found {now.get(path, {}).get(kind, 0)}"
        for path in sorted(table)
        for kind in um.KINDS
        if now.get(path, {}).get(kind, 0) != table[path].get(kind, 0)
    ]
    assert not differ, (
        "the list does not say what the scan finds; after cleaning, rewrite it "
        "with `uv run --no-sync python -m tests.uninvented_machines --write`:\n"
        + _say(differ)
    )


def test_every_folder_left_unread_is_still_in_the_product() -> None:
    """The five folders are passed over because they leave the product; once
    one holds no tracked file, its exclusion has outlived its reason."""
    if not _is_checkout():
        pytest.skip(f"{um.REPO} is not a git checkout")
    gone = [folder for folder in um.LEAVING if um.tracked_in(folder) == 0]
    assert not gone, (
        f"{', '.join(gone)} holds no tracked file any more: remove it from "
        "LEAVING in tests/uninvented_machines.py, so a file there is read again"
    )


def test_this_folder_of_tests_is_read() -> None:
    if not _is_checkout():
        pytest.skip(f"{um.REPO} is not a git checkout")
    read = um.files()
    assert "tests/test_the_product_names_no_machine_it_did_not_invent.py" in read
    assert "tests/machine_shapes.py" in read


# --- the list's form ---------------------------------------------------------


def _listed(**kept: dict[str, int]) -> um.Listed:
    return um.Listed(cleaning={"a": {"host": 1}, "c": {"address": 2}}, kept=kept)


def test_the_list_is_read_only_in_the_form_the_writer_writes() -> None:
    """Sorted, one line per file, known kinds, positive counts, the fixed
    headers, no path the check does not read; anything else is refused."""
    good = um.render(_listed(b={"card-model": 1}))
    assert um.parse(good) == _listed(b={"card-model": 1})
    cleaning, kept = good.split(um.KEPT_HEADER)
    for bad, says in [
        (cleaning + "b\thost=1\n" + um.KEPT_HEADER + kept, "both sections"),
        (
            cleaning.replace("a\thost=1\n", "") + "a\thost=1\n" + um.KEPT_HEADER + kept,
            "not as --write",
        ),
        (good.replace("c\taddress=2", "c\taddress=0"), "positive"),
        (good.replace("c\taddress=2", "c\tname=2"), "not a kind"),
        (good.replace("c\taddress=2\n", "c\n"), "no kind"),
        (good + f"{_FOLDER}/x\thost=1\n", "does not read"),
        (good.replace(um.KEPT_HEADER, ""), "section 2"),
        (good + "\n", "does not write"),
        (good[1:], "header"),
    ]:
        with pytest.raises(ValueError, match=says):
            um.parse(bad)
    um.read_list()


def test_a_comment_line_the_writer_did_not_write_is_refused(tmp_path: Path) -> None:
    good = um.render(_listed())
    smuggled = good.replace("a\thost=1\n", f"# pending: {_PRIVATE}\na\thost=1\n")
    with pytest.raises(ValueError, match="does not write"):
        um.parse(smuggled)
    old = tmp_path / "old.txt"
    old.write_text(smuggled, encoding="utf-8")
    assert um.main(["--compare", str(old)]) == 1


def test_the_list_only_shrinks_against_an_older_one() -> None:
    """The comparison CI runs: a new file, a new kind or a higher count grew."""
    old = {"a": {"host": 2}, "b": {"address": 1}}
    assert um.growth(old, {"a": {"host": 1}}) == []
    assert um.growth(old, {"a": {"host": 3}}) == ["a: host 2 -> 3"]
    assert um.growth(old, {"a": {"address": 1, "host": 2}}) == ["a: address 0 -> 1"]
    assert um.growth(old, {"c": {"host": 1}}) == ["c: host 0 -> 1"]


def test_the_writer_keeps_each_file_in_its_section() -> None:
    old = um.Listed(cleaning={"a": {"host": 2}}, kept={"k": {"address": 3}})
    found = {"a": {"host": 1}, "k": {"address": 2}, "n": {"host": 1}}
    assert um.rewritten(old, found) == um.Listed(
        cleaning={"a": {"host": 1}, "n": {"host": 1}}, kept={"k": {"address": 2}}
    )
    assert um.rewritten(old, {}) == um.Listed()


def test_the_writer_replaces_the_list_in_one_step(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "list.txt"
    target.write_text("before\n", encoding="utf-8")
    um.write_list(_listed(), target)
    assert um.parse(target.read_text(encoding="utf-8")) == _listed()

    def broken(*_: object) -> None:
        raise OSError("the disk is full")

    monkeypatch.setattr(os, "replace", broken)
    with pytest.raises(OSError, match="full"):
        um.write_list(um.Listed(), target)
    assert um.parse(target.read_text(encoding="utf-8")) == _listed()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["list.txt"]


@pytest.mark.parametrize(
    "name", ["x\udcff.py", "a\tb.py", "a\nb.py", "#top.py"], ids=ascii
)
def test_a_file_name_the_list_cannot_hold_is_refused_by_name(
    name: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(ValueError, match="cannot hold the file name"):
        um.render(um.Listed(cleaning={name: {"host": 1}}))
    target = tmp_path / "list.txt"
    target.write_text(um.render(um.Listed()), encoding="utf-8")
    monkeypatch.setattr(um, "LIST_PATH", target)
    monkeypatch.setattr(um, "scan", lambda: [um.Hit(name, 1, "host")])
    assert um.main(["--write", "--allow-growth"]) == 1
    assert ascii(name) in capsys.readouterr().err
    assert target.read_text(encoding="utf-8") == um.render(um.Listed())


# --- what is read ------------------------------------------------------------


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "demo"\n', "utf-8")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    return repo


def _commit(repo: Path) -> None:
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t.invalid",
            "commit",
            "-q",
            "-m",
            "t",
        ],
        check=True,
    )


def _found(repo: Path) -> dict[str, list[str]]:
    table: dict[str, list[str]] = {}
    for hit in um.scan(repo):
        table.setdefault(hit.path, []).append(hit.kind)
    return table


def test_untracked_files_are_read_and_ignored_ones_are_not(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / ".gitignore").write_text("ignored.txt\n", "utf-8")
    (repo / "tracked.txt").write_text(f"at {_PRIVATE}\n", "utf-8")
    _commit(repo)
    (repo / "untracked.txt").write_text(f"at {_PRIVATE}\n", "utf-8")
    (repo / "ignored.txt").write_text(f"at {_PRIVATE}\n", "utf-8")
    (repo / _FOLDER).mkdir()
    (repo / _FOLDER / "x.txt").write_text(f"at {_PRIVATE}\n", "utf-8")
    assert _found(repo) == {"tracked.txt": ["address"], "untracked.txt": ["address"]}


def test_a_name_declared_in_an_example_passes_nowhere_else(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "examples").mkdir()
    (repo / "examples" / "fleet.yaml").write_text(
        f"units:\n  {_HOST}:\n    width: 1\n", "utf-8"
    )
    (repo / "src.py").write_text(f'URL = "http://{_HOST}:8000"\n', "utf-8")
    assert _found(repo) == {"src.py": ["host"]}


def test_a_symlink_is_read_as_where_it_points(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    os.symlink("/" + "home/" + "jdoe/notes", repo / "link")
    assert _found(repo) == {"link": ["home-path"]}


def test_a_path_name_is_read_as_line_zero() -> None:
    path = "tests/test_on_" + "rt" + "x_9999.py"
    assert [(h.line, h.kind) for h in um.scan_text(path, "")] == [(0, "card-model")]


def test_released_changelog_sections_are_history(tmp_path: Path) -> None:
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n## [Unreleased]\nnow\n## [0.1.0] - then\nold\n",
        encoding="utf-8",
    )
    assert um.text_of(tmp_path, "CHANGELOG.md") == "# Changelog\n## [Unreleased]\nnow\n"


# --- the kinds ---------------------------------------------------------------


def test_the_invented_machines_and_reserved_names_pass() -> None:
    """Every name the generator of invented machines carries, reserved host
    names and documentation addresses pass by the kinds' own rules."""
    lines = []
    for machine in machine_shapes.shapes():
        lines.append(f"host: {machine.host}")
        lines.append(f'"host": "{machine.host}", "rig": "{machine.label}"')
        lines.append(f"http://{machine.host}:8080/v1 {machine.machine_id}")
        for card in machine.cards:
            lines.append(card.name)
            lines.extend(holder.name for holder in card.holders)
        for server in machine.servers:
            lines.append(f"{server.kind} {' '.join(server.models)}")
    for host in ("gpu-7.invalid", "box.test", "api.example.com", "localhost"):
        lines.append(f"http://{host}:8000 host={host!r} --host {host}")
    for block in um.PASSING_NETWORKS:
        lines.append(f"http://{block.network_address}:9 {block.network_address}")
    lines.append("/home/someone/models /Users/<user>/x /home/runner/work")
    lines.append("rig-" + "0" * 16 + " unt-" + "1" * 64 + " rig_id: " + "2" * 16)
    assert _hits("\n".join(lines)) == []


@pytest.mark.parametrize(
    ("kind", "text"),
    [
        ("home-path", "/" + "home/" + "jdoe/models"),
        ("home-path", "~" + "jdoe/models"),
        ("address", f"reach {_PRIVATE}"),
        ("address", "reach " + ".".join(("010", "009", "008", "007"))),
        ("address", "reach fd12" + ":3456::1"),
        ("address", "http://[fd12" + ":3456::1]:8080/v1"),
        ("host", "http:/" + f"/{_HOST}:8080/v1"),
        ("host", '"host": "' + _HOST + '"'),
        ("host", "host: " + _HOST),
        ("host", "  ssh_target: ops@" + _HOST),
        ("host", "mcgyvr init --host " + _HOST),
        ("host", "HOST=1 host=" + _HOST),
        ("host", "ss" + "h -p 22 ops@" + _HOST + " true"),
        ("host", "at node" + ".la" + "n"),
        ("card-model", "one " + _CARD + " card"),
        ("card-model", "NVIDIA GeForce " + "GT" + "X_9999"),
        ("card-model", "def test_on_the_" + "rt" + "x_9999(): pass"),
        ("identity", "rig" + "-" + "0123456789abcdef"),
        ("identity", "rig_" + "id: 0123456789abcdef"),
        ("dev-pointer", "see " + _FOLDER + "/" + "rules.md"),
        ("dev-pointer", "see `" + _FOLDER + "/` there"),
        ("dev-pointer", "from " + _FOLDER + ".x import y"),
        ("dev-pointer", "import " + _FOLDER + ".x"),
        ("dev-pointer", "python -m " + _FOLDER + ".x"),
        ("dev-pointer", 'REPO / "' + _FOLDER + '" / "x"'),
    ],
)
def test_each_kind_is_found_in_a_sample_made_up_here(kind: str, text: str) -> None:
    assert _hits(text) == [kind]


def test_the_development_repository_is_named_on_one_readme_line_only() -> None:
    name = um.product_name() + "-" + "lab"
    assert _hits(f"x\nsee {name}\n", "README.md") == []
    assert _hits(f"see {name}\nand {name}\n", "README.md") == ["dev-pointer"] * 2
    assert _hits(f"see {name}\n", "other.md") == ["dev-pointer"]
    assert _hits(f"see {name}/rules.md\n", "README.md") == ["dev-pointer"]


@pytest.mark.parametrize(
    "text",
    [
        "if [ $n -gt 10 ]; then",
        "rx 1500 bytes",
        "an arc 90 degrees wide",
        "mi 100 miles",
        "__gt__ 10",
        "localhost.localdomain",
        "numpy==1.26.4.1",
        '"version": "1.26.4.1"',
        "file:///srv/models unix:///run/docker.sock s3://bucket/key",
        "/home/runner/work/x",
        "host: int = 0",
        "self.private = 1",
        '{"method": "tools/call"} {"method": "tools/list"}',
    ],
)
def test_what_an_honest_change_writes_is_not_a_hit(text: str) -> None:
    assert _hits(text) == []


def test_a_lock_file_holds_versions_not_addresses() -> None:
    four = ".".join(("10", "2", "3", "4"))
    assert _hits(f"x {four}\n", "uv.lock") == []
    assert _hits(f"x {four}\n", "notes.txt") == ["address"]


def test_a_card_is_found_as_vendors_write_it_and_not_in_lower_case_prose() -> None:
    assert _hits("rt" + "x 9999") == []
    assert _hits(_CARD) == ["card-model"]
    assert _hits("Rade" + "on 9999") == ["card-model"]


def test_ipv6_is_read_and_its_documentation_block_passes() -> None:
    assert _hits("fd12" + ":3456::1") == ["address"]
    assert _hits(str(ipaddress.ip_address("2001:db8::1"))) == []
