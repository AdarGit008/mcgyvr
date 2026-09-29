"""The product names no machine it did not invent.

Promise: what the product ships and what a contributor reads holds no home
folder of a named user, no address that reaches a machine, no private host
name, no card model, no identity digest of a real machine and no pointer into
the development repository, except in the files a list names, each with the
hits of each kind it holds; the list may only shrink. Not read: the folders
that leave the product, while they are in it, and the changelog from its
first released version's heading on.

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

import os
import re
import stat
import subprocess
import sys
import types
from pathlib import Path

import pytest

from tests import machine_shapes
from tests import uninvented_machines as um

_FOLDER = "tools"  # a folder that leaves the product and is a module name
_PRIVATE = ".".join(("10", "9", "8", "7"))
_HOST = "gpu" + "box"
_CARD = "RT" + "X 9999"
_HEX = "0123" + "456789abcdef"
_HEX8 = "0123" + "abcd"


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
    """The folders in UNREAD are passed over because they leave the product;
    once one holds no tracked file, its exclusion has outlived its reason."""
    if not _is_checkout():
        pytest.skip(f"{um.REPO} is not a git checkout")
    gone = [folder for folder in um.UNREAD if um.tracked_in(folder) == 0]
    assert not gone, (
        f"{', '.join(gone)} holds no tracked file any more: remove it from "
        "UNREAD in tests/uninvented_machines.py, so a file there is read again"
    )


def test_a_folder_read_again_is_still_a_place_no_pointer_may_lead(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Doing what the test above says, dropping a folder from UNREAD, makes
    its files read and keeps every pointer into it a hit: where a pointer may
    not lead is fixed apart from what is read."""
    assert _FOLDER in um.LAB_FOLDERS
    assert set(um.UNREAD) <= set(um.LAB_FOLDERS)
    monkeypatch.setattr(um, "UNREAD", (_FOLDER,))
    repo = _repo(tmp_path)
    (repo / _FOLDER).mkdir()
    (repo / _FOLDER / "x.txt").write_text(f"at {_PRIVATE}\n", "utf-8")
    (repo / "README.md").write_text(f"see {_FOLDER}/run.py\n", "utf-8")
    _commit(repo)
    assert _found(repo) == {"README.md": ["dev-pointer"]}
    monkeypatch.setattr(um, "UNREAD", ())
    assert _found(repo) == {
        "README.md": ["dev-pointer"],
        f"{_FOLDER}/x.txt": ["dev-pointer", "address"],  # its path, line 0
    }


def test_the_pointer_rules_are_built_from_the_lab_folders_not_from_unread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fresh copy of the helper whose source drops a folder from UNREAD, as
    the folder test asks, still finds a path, an import and a join into that
    folder: the rules are compiled from LAB_FOLDERS alone."""
    source = Path(um.__file__).read_text(encoding="utf-8")
    assignment = re.compile(r"^UNREAD = \(.*\)$", re.MULTILINE)
    assert len(assignment.findall(source)) == 1
    fewer = tuple(folder for folder in um.UNREAD if folder != _FOLDER)
    fresh = types.ModuleType("fresh_uninvented_machines")
    fresh.__file__ = um.__file__
    monkeypatch.setitem(sys.modules, fresh.__name__, fresh)
    changed = assignment.sub(f"UNREAD = {fewer!r}", source)
    exec(compile(changed, um.__file__, "exec"), fresh.__dict__)
    assert _FOLDER not in fresh.UNREAD
    dev_repo = um._dev_repo_name(um.REPO)
    for text in (
        f"see {_FOLDER}/x.md",
        f"from {_FOLDER}.x import y",
        f'REPO / "{_FOLDER}"',
    ):
        found = fresh.scan_text("a.md", text, dev_repo=dev_repo)
        assert [hit.kind for hit in found] == ["dev-pointer"], text


def test_the_folders_no_pointer_may_lead_into_are_the_five_that_leave() -> None:
    """Dropping a folder here would drop every pointer into it from the
    count, with nothing cleaned."""
    assert um.LAB_FOLDERS == ("archive", "fleet-setup", "okf", "records", "tools")


def test_the_count_of_tracked_files_is_of_the_one_top_folder_named(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    for path in (f"{_FOLDER}/a.txt", f"deep/{_FOLDER}/b.txt", "c.txt"):
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        (repo / path).write_text("x\n", "utf-8")
    _commit(repo)
    assert um.tracked_in(_FOLDER, repo) == 1
    assert um.tracked_in("absent", repo) == 0


def test_the_writers_temporary_file_is_ignored_and_a_tracked_one_is_read(
    tmp_path: Path,
) -> None:
    """A run killed before the new list replaced the old leaves the temporary
    file behind; git ignores it, so it is not read. A file of that name that
    git tracks is a file of the product, and is read."""
    if not _is_checkout():
        pytest.skip(f"{um.REPO} is not a git checkout")
    left = f"tests/.{um.LIST_PATH.name}.k2j4x_q"
    ignored = subprocess.run(["git", "-C", str(um.REPO), "check-ignore", "-q", left])
    assert ignored.returncode == 0
    repo = _repo(tmp_path)
    (repo / "tests").mkdir()
    kept = f"tests/.{um.LIST_PATH.name}.kept"
    (repo / kept).write_text(f"at {_PRIVATE}\n", "utf-8")
    _commit(repo)
    assert _found(repo) == {kept: ["address"]}


def test_this_folder_of_tests_is_read() -> None:
    if not _is_checkout():
        pytest.skip(f"{um.REPO} is not a git checkout")
    read = um.files()
    assert "tests/test_the_product_names_no_machine_it_did_not_invent.py" in read
    assert "tests/machine_shapes.py" in read


# --- the list's form ---------------------------------------------------------


def _listed(**kept: dict[str, int]) -> um.Listed:
    return um.Listed(cleaning={"a": {"host": 1}, "c": {"address": 2}}, kept=kept)


def test_the_list_is_read_only_in_the_form_the_writer_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sorted, one line per file, known kinds, positive counts, the fixed
    headers, no path the check does not read; anything else is refused."""
    monkeypatch.setattr(um, "UNREAD", (_FOLDER,))
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


def test_a_comment_line_the_writer_did_not_write_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    good = um.render(_listed())
    smuggled = good.replace("a\thost=1\n", f"# pending: {_PRIVATE}\na\thost=1\n")
    with pytest.raises(ValueError, match="does not write"):
        um.parse(smuggled)
    now = tmp_path / "list.txt"
    now.write_text(smuggled, encoding="utf-8")
    old = tmp_path / "old.txt"
    old.write_text(good, encoding="utf-8")
    monkeypatch.setattr(um, "LIST_PATH", now)
    assert um.main(["--compare", str(old)]) == 1


def test_the_comparison_reads_the_base_list_by_its_entries_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The base's list may carry headers worded before a change to them; its
    entries are what is compared, so a change of the headers is not growth."""
    now = tmp_path / "list.txt"
    now.write_text(um.render(_listed(k={"card-model": 1})), encoding="utf-8")
    older = "# A header line since removed.\n" + um.render(
        _listed(k={"card-model": 1})
    ).replace("# Section 1: not yet cleaned.", "# Section 1: worded otherwise.")
    old = tmp_path / "base.txt"
    old.write_text(older, encoding="utf-8")
    monkeypatch.setattr(um, "LIST_PATH", now)
    assert um.main(["--compare", str(old)]) == 0
    old.write_text(older.replace("c\taddress=2", "c\taddress=1"), encoding="utf-8")
    assert um.main(["--compare", str(old)]) == 1
    # A change that stops reading a folder the base lists hides its hits.
    monkeypatch.setattr(um, "UNREAD", (_FOLDER,))
    unread = older.replace("c\taddress=2\n", f"c\taddress=2\n{_FOLDER}/x\thost=1\n")
    old.write_text(unread, encoding="utf-8")
    assert um.main(["--compare", str(old)]) == 1


def test_the_list_only_shrinks_against_an_older_one() -> None:
    """The comparison CI runs: a new file, a new kind or a higher count grew."""
    old = {"a": {"host": 2}, "b": {"address": 1}}
    assert um.growth(old, {"a": {"host": 1}}) == []
    assert um.growth(old, {"a": {"host": 3}}) == ["a: host 2 -> 3"]
    assert um.growth(old, {"a": {"address": 1, "host": 2}}) == ["a: address 0 -> 1"]
    assert um.growth(old, {"c": {"host": 1}}) == ["c: host 0 -> 1"]


@pytest.mark.parametrize(
    ("base", "grew"),
    [
        (_listed(k={"card-model": 1}), False),
        (
            um.Listed(
                cleaning={"a": {"host": 1}, "c": {"address": 1}},
                kept={"k": {"card-model": 1}},
            ),
            True,
        ),
        (_listed(), True),
    ],
    ids=["the-same", "a-count-lower-in-the-base", "a-kept-entry-new"],
)
def test_the_comparison_ci_runs_fails_when_the_list_grew_in_either_section(
    base: um.Listed, grew: bool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Through the command itself: a count lower in the base, or an entry of
    section 2 the base does not hold, is growth and exits 1."""
    now = tmp_path / "list.txt"
    now.write_text(um.render(_listed(k={"card-model": 1})), encoding="utf-8")
    old = tmp_path / "base.txt"
    old.write_text(um.render(base), encoding="utf-8")
    monkeypatch.setattr(um, "LIST_PATH", now)
    assert um.main(["--compare", str(old)]) == (1 if grew else 0)


def test_a_rewrite_that_would_grow_the_list_is_refused_without_the_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Through the command itself: a scan that finds more than is listed
    leaves the list byte for byte as it was and exits 1."""
    target = tmp_path / "list.txt"
    target.write_text(um.render(_listed()), encoding="utf-8")
    before = target.read_bytes()
    monkeypatch.setattr(um, "LIST_PATH", target)
    monkeypatch.setattr(
        um, "scan", lambda: [um.Hit("a", 1, "host"), um.Hit("a", 2, "host")]
    )
    assert um.main(["--write"]) == 1
    assert target.read_bytes() == before
    assert um.main(["--write", "--allow-growth"]) == 0
    assert um.read_list(target) == um.Listed(cleaning={"a": {"host": 2}})


def test_a_rewrite_that_shrinks_the_list_needs_no_flag_and_keeps_each_section(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Through the command itself: a scan that finds less rewrites the list
    without a flag, and an entry of section 2 stays in section 2."""
    target = tmp_path / "list.txt"
    target.write_text(um.render(_listed(k={"card-model": 2})), encoding="utf-8")
    monkeypatch.setattr(um, "LIST_PATH", target)
    monkeypatch.setattr(
        um, "scan", lambda: [um.Hit("a", 1, "host"), um.Hit("k", 1, "card-model")]
    )
    assert um.main(["--write"]) == 0
    assert um.read_list(target) == um.Listed(
        cleaning={"a": {"host": 1}}, kept={"k": {"card-model": 1}}
    )


def test_the_report_fails_when_the_scan_and_the_list_differ(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "list.txt"
    target.write_text(um.render(um.Listed(cleaning={"a": {"host": 1}})), "utf-8")
    monkeypatch.setattr(um, "LIST_PATH", target)
    monkeypatch.setattr(um, "scan", lambda: [um.Hit("a", 1, "host")])
    assert um.main([]) == 0
    monkeypatch.setattr(um, "scan", lambda: [])
    assert um.main([]) == 1


def test_the_command_runs_by_its_file_path_as_ci_runs_it() -> None:
    """`python tests/uninvented_machines.py`, not only `-m`: the report reads
    the changelog through the release script, which needs the checkout on the
    import path."""
    if not _is_checkout():
        pytest.skip(f"{um.REPO} is not a git checkout")
    ran = subprocess.run(
        [sys.executable, str(Path(um.__file__))],
        cwd=um.REPO,
        capture_output=True,
        text=True,
    )
    assert "Traceback" not in ran.stderr, ran.stderr[-2000:]
    assert ran.returncode == 0, ran.stdout[-2000:]


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
    assert stat.S_IMODE(target.stat().st_mode) == 0o644

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


def test_untracked_files_are_read_and_ignored_ones_are_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(um, "UNREAD", (_FOLDER,))
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
    """What is read ends at the first heading that names a version, as the
    release reads it: an open section spelled in lower case, or a heading of
    prose before it, is still read; a heading of prose after it is not."""
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n## [unreleased]\nnow\n## Notes\nkept\n## [0.1.0] - then\nold\n"
        "## Entries written before 0.1.0\nolder\n",
        encoding="utf-8",
    )
    assert um.text_of(tmp_path, "CHANGELOG.md") == (
        "# Changelog\n## [unreleased]\nnow\n## Notes\nkept\n"
    )


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
    # Loopback, unspecified, and each documentation block, written out.
    for address in (
        "127.0.0.2",
        "0.0.0.0",
        "192.0.2.7",
        "198.51.100.7",
        "203.0.113.7",
        "::1",
        "::",
        "2001:db8::7",
    ):
        host = f"[{address}]" if ":" in address else address
        lines.append(f"http://{host}:9 {address}")
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
        ("address", "reach fd1" + "::1"),
        ("address", "http://[100" + "::2]:8080/v1"),
        ("address", "y = x[fd12" + ":3456::1]"),
        ("address", "conversion_host = " + _PRIVATE),
        ("host", "http:/" + f"/{_HOST}:8080/v1"),
        ("host", "http:/" + f"/{_HOST}" + ".inter" + "nal:8080/v1"),
        ("host", '"host": "' + _HOST + '"'),
        ("host", "host: " + _HOST),
        ("host", "host: " + _HOST + ".loc" + "al"),
        ("host", "  ssh_target: ops@" + _HOST),
        ("host", "mcgyvr init --host " + _HOST),
        ("host", "HOST=1 host=" + _HOST),
        ("host", "host = " + _HOST),
        ("host", "ss" + "h -p 22 ops@" + _HOST + " true"),
        ("host", "ss" + "h -p22 ops@" + _HOST + " true"),
        ("host", "ss" + "h -oBatchMode=yes ops@" + _HOST),
        ("host", "sc" + "p model.bin ops@" + _HOST + ":/srv/models/"),
        ("host", "rsy" + "nc -a ops@" + _HOST + ":models/ ."),
        ("host", '["ss' + 'h", "ops@' + _HOST + '"]'),
        ("host", '"-o BatchMode=yes -o X ops@' + _HOST + ' cmd"'),
        ("host", "ss" + "h $USER@" + _HOST),
        ("host", "ss" + "h ${USER}@" + _HOST),
        ("host", 'f"ss' + "h {user}@" + _HOST + '"'),
        ("host", "ss" + "h -- ops@" + _HOST),
        ("host", "ss" + "h -p 22 -- ops@" + _HOST),
        ("host", "ss" + "h ops@" + _HOST + ".la" + "n; ping " + _HOST + ".la" + "n"),
        ("host", "at node" + ".la" + "n"),
        ("host", "at node" + ".la" + "n."),
        ("host", "host: node" + ".la" + "n."),
        ("card-model", "one " + _CARD + " card"),
        ("card-model", "one " + "GT" + "X 99 card"),
        ("card-model", "one " + "rt" + "x 9999 card"),
        ("card-model", "NVIDIA GeForce " + "GT" + "X_9999"),
        ("card-model", "def test_on_the_" + "rt" + "x_9999(): pass"),
        ("identity", "rig" + "-" + "0123456789abcdef"),
        ("identity", "rig" + "-" + _HEX8),
        ("identity", "rig_" + "id: 0123456789abcdef"),
        ("identity", "unit_id=" + _HEX8),
        ("identity", "machine_id: " + _HEX),
        ("identity", '"os_machine_id": "' + _HEX + '"'),
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
        "    host: int",
        "self.private = 1",
        '{"method": "tools/call"} {"method": "tools/list"}',
        "step = x[100::2]",
        "__version__ = " + '"' + ".".join("1234") + '"',
        'tag = "v@2026-09-29"',
        "docker pull img@sha256:" + "ab" * 32,
        "docker " + "run -d img@sha256:" + "ab" * 32,
        "docker pull img@SHA256:" + "ab" * 32 + " img@blake3:" + "cd" * 32,
        "uv add pkg@https://files.example/pkg.whl other@file:///srv/other.whl",
        "git clone git@github.com:org/repo.git",
        "y = f()[100::2]",
        "node_version = " + ".".join("1234"),
        "orig_id: " + _HEX + " trig_id: " + _HEX,
    ],
)
def test_what_an_honest_change_writes_is_not_a_hit(text: str) -> None:
    assert _hits(text) == []


def test_a_colon_after_a_machine_is_a_copy_only_before_a_path() -> None:
    assert _hits("ask ops@" + _HOST + ": done") == []
    assert _hits("ops@" + _HOST + ":done") == ["host"]


def test_an_unquoted_host_value_in_python_is_a_variable() -> None:
    assert _hits("host = " + _HOST, "run.py") == []
    assert _hits("host = " + _HOST, "rig.ini") == ["host"]


def test_a_lock_file_holds_versions_not_addresses() -> None:
    four = ".".join(("10", "2", "3", "4"))
    assert _hits(f"x {four}\n", "uv.lock") == []
    assert _hits(f"x {four}\n", "notes.txt") == ["address"]


def test_a_card_is_found_as_vendors_write_it() -> None:
    assert _hits(_CARD) == ["card-model"]
    assert _hits("Rade" + "on 9999") == ["card-model"]
    assert _hits("rt" + "x 9999") == ["card-model"]


def test_ipv6_is_read_and_its_documentation_block_passes() -> None:
    assert _hits("fd12" + ":3456::1") == ["address"]
    assert _hits("2001:db8::1") == []
