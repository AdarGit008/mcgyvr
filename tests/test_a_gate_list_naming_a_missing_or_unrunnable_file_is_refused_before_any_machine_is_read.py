"""A gate list the door cannot hold a run to is refused before any gate runs.

A gate list is input the door does not trust. A gate that is missing or not
executable, a path that leaves the list's root (by name or through a link), a
root that is not an absolute folder or that is or lies inside the package's
own folder, a gate inside that folder, a key or a phase the door does not
know, a key given twice, a name two gates both export, a bound that is not a
positive number of seconds or is longer than the door holds a gate to, more
gates than the door holds a list to, and input that cannot be read as a path
or as JSON at all: each is refused before the door runs its first gate, and
the refusal names the list file and the entry at fault, with no control
character of the list printed raw. A list that is not JSON is refused saying
where the reading stopped, a root inside the package is refused as the root
and not as a gate, and a list named relative to a working folder that is
gone is refused, not raised.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.serving import run
from tests import callergates as cg

#: Writes a bad list under the folder it is given and returns the list's
#: path and the words the refusal must carry to name the entry at fault.
Case = Callable[[Path], tuple[Path, str]]


def _ok(root: Path, name: str = "fine.py") -> str:
    cg.executable(root / name, "#!/usr/bin/env python3\n")
    return name


def _missing(tmp: Path) -> tuple[Path, str]:
    root = tmp / "caller"
    root.mkdir()
    listed = cg.write_list(tmp / "g.json", str(root), [cg.entry("gone.py", "before")])
    return listed, "gone.py"


def _not_executable(tmp: Path) -> tuple[Path, str]:
    root = tmp / "caller"
    root.mkdir()
    (root / "plain.py").write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    listed = cg.write_list(tmp / "g.json", str(root), [cg.entry("plain.py", "after")])
    return listed, "plain.py"


def _outside_by_absolute_path(tmp: Path) -> tuple[Path, str]:
    root = tmp / "caller"
    root.mkdir()
    elsewhere = cg.executable(tmp / "elsewhere" / "far.py", "#!/usr/bin/env python3\n")
    listed = cg.write_list(
        tmp / "g.json", str(root), [cg.entry(str(elsewhere), "before")]
    )
    return listed, "far.py"


def _outside_by_parent_step(tmp: Path) -> tuple[Path, str]:
    root = tmp / "caller"
    root.mkdir()
    cg.executable(tmp / "up.py", "#!/usr/bin/env python3\n")
    listed = cg.write_list(tmp / "g.json", str(root), [cg.entry("../up.py", "before")])
    return listed, "../up.py"


def _link_leaving_root(tmp: Path) -> tuple[Path, str]:
    root = tmp / "caller"
    root.mkdir()
    target = cg.executable(tmp / "elsewhere" / "real.py", "#!/usr/bin/env python3\n")
    os.symlink(target, root / "link.py")
    listed = cg.write_list(tmp / "g.json", str(root), [cg.entry("link.py", "after")])
    return listed, "link.py"


def _relative_root(tmp: Path) -> tuple[Path, str]:
    listed = cg.write_list(tmp / "g.json", "caller", [])
    return listed, "root"


def _root_not_a_folder(tmp: Path) -> tuple[Path, str]:
    listed = cg.write_list(tmp / "g.json", str(tmp / "nowhere"), [])
    return listed, "root"


def _unknown_entry_key(tmp: Path) -> tuple[Path, str]:
    root = tmp / "caller"
    gate: dict[str, Any] = cg.entry(_ok(root), "before")
    gate["skip"] = True
    listed = cg.write_list(tmp / "g.json", str(root), [gate])
    return listed, "skip"


def _unknown_list_key(tmp: Path) -> tuple[Path, str]:
    root = tmp / "caller"
    root.mkdir()
    listed = tmp / "g.json"
    listed.write_text(
        f'{{"root": "{root}", "gates": [], "order": "mine"}}', encoding="utf-8"
    )
    return listed, "order"


def _unknown_phase(tmp: Path) -> tuple[Path, str]:
    root = tmp / "caller"
    listed = cg.write_list(tmp / "g.json", str(root), [cg.entry(_ok(root), "first")])
    return listed, "first"


def _duplicate_export(tmp: Path) -> tuple[Path, str]:
    root = tmp / "caller"
    listed = cg.write_list(
        tmp / "g.json",
        str(root),
        [
            cg.entry(_ok(root, "one.py"), "before", ["RUN_CALLER_TWICE"]),
            cg.entry(_ok(root, "two.py"), "after", ["RUN_CALLER_TWICE"]),
        ],
    )
    return listed, "RUN_CALLER_TWICE"


def _list_not_json(tmp: Path) -> tuple[Path, str]:
    listed = tmp / "g.json"
    listed.write_text("root = /somewhere\n", encoding="utf-8")
    return listed, "JSON"


def _list_not_json_later(tmp: Path) -> tuple[Path, str]:
    listed = tmp / "g.json"
    listed.write_text('{"root": "/somewhere",\n "gates": [,]}\n', encoding="utf-8")
    return listed, "line 2, column 12: Expecting value"


def _list_missing(tmp: Path) -> tuple[Path, str]:
    return tmp / "no-such-list.json", "cannot be read"


#: What the refusal of a root inside the package says, and a gate's never does.
ROOT_IN_PACKAGE = "is or lies inside the package"


def _root_in_package(where: Path, gate: str, names: str = ROOT_IN_PACKAGE) -> Case:
    def case(tmp: Path) -> tuple[Path, str]:
        listed = cg.write_list(tmp / "g.json", str(where), [cg.entry(gate, "before")])
        return listed, names

    return case


PACKAGE = run.HERE.parent


def _odd_path(path: str) -> Case:
    def case(tmp: Path) -> tuple[Path, str]:
        root = tmp / "caller"
        root.mkdir()
        listed = cg.write_list(tmp / "g.json", str(root), [cg.entry(path, "before")])
        return listed, "gates[0]"

    return case


def _raw(text: str, names: str) -> Case:
    def case(tmp: Path) -> tuple[Path, str]:
        listed = tmp / "g.json"
        listed.write_text(text.replace("ROOT", str(tmp)), encoding="utf-8")
        return listed, names

    return case


def _too_many(tmp: Path) -> tuple[Path, str]:
    root = tmp / "caller"
    gates = [cg.entry(_ok(root), "before") for _ in range(run.MAX_GATES + 1)]
    return cg.write_list(tmp / "g.json", str(root), gates), str(run.MAX_GATES)


def _bound(value: object) -> Case:
    def case(tmp: Path) -> tuple[Path, str]:
        root = tmp / "caller"
        gate = cg.entry(_ok(root), "before")
        gate["timeout_s"] = value
        return cg.write_list(tmp / "g.json", str(root), [gate]), "timeout_s"

    return case


def _export_with_newline(tmp: Path) -> tuple[Path, str]:
    root = tmp / "caller"
    gate = cg.entry(_ok(root), "before", ["RUN_CALLER_LINE\n"])
    return cg.write_list(tmp / "g.json", str(root), [gate]), "RUN_CALLER_LINE"


CASES: dict[str, Case] = {
    "a gate that is missing": _missing,
    "a gate that is not executable": _not_executable,
    "a gate outside the root by absolute path": _outside_by_absolute_path,
    "a gate outside the root by a parent step": _outside_by_parent_step,
    "a gate that is a link leaving the root": _link_leaving_root,
    "a relative root": _relative_root,
    "a root that is no folder": _root_not_a_folder,
    "an unknown key on a gate": _unknown_entry_key,
    "an unknown key on the list": _unknown_list_key,
    "an unknown phase": _unknown_phase,
    "a name two gates export": _duplicate_export,
    "a list that is not JSON": _list_not_json,
    "a list that stops being JSON after its first line": _list_not_json_later,
    "a list file that is not there": _list_missing,
    "a root that is the door's gate folder": _root_in_package(
        PACKAGE / "serving" / "gate-scripts", "06-step.py"
    ),
    "a root that is the package folder": _root_in_package(
        PACKAGE, "serving/gate-scripts/06-step.py"
    ),
    "a gate inside the package, under a root that holds it": _root_in_package(
        PACKAGE.parent, "mcgyvr/serving/gate-scripts/06-step.py", "gates[0]"
    ),
    "a bound too large to be a number of seconds": _bound(10**400),
    "a path carrying a NUL": _odd_path("a\x00b.py"),
    "a path carrying a lone surrogate": _odd_path("\udcff.py"),
    "JSON nested past any list": _raw("[" * 100_000 + "]" * 100_000, "the list"),
    "an integer of more digits than JSON reads": _raw(
        '{"root": ' + "9" * 5000 + ', "gates": []}', "the list"
    ),
    "a key given twice": _raw(
        '{"root": "ROOT", "root": "ROOT", "gates": []}', "'root'"
    ),
    "more gates than a list holds": _too_many,
    "a bound of zero": _bound(0),
    "a bound longer than the door holds a gate to": _bound(1e10),
    "a bound too long to wait on": _bound(1e308),
    "a bound that is not a number": _bound("5"),
    "a bound that is a truth value": _bound(True),
    "an export name ending in a newline": _export_with_newline,
}


@pytest.mark.parametrize("verb", ["serve", "read"])
@pytest.mark.parametrize("case", sorted(CASES))
def test_a_bad_gate_list_is_refused_naming_the_file_and_the_entry_before_any_gate(
    case: str,
    verb: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    cg.fake_door(tmp_path, monkeypatch, log)
    listed, names = CASES[case](tmp_path)
    if verb == "serve":
        compose = cg.compose_file(tmp_path / "compose.yaml")
        argv = cg.serve_argv(compose, "--gates", str(listed))
    else:
        argv = cg.read_argv("--gates", str(listed))

    status = run.main(argv)
    said = capsys.readouterr().err

    assert status == 2, said
    assert cg.log_lines(log) == [], (
        f"{case}: the door ran gates before refusing the list: {cg.log_lines(log)}"
    )
    assert str(listed) in said, f"{case}: the refusal does not name the list: {said}"
    assert names in said, f"{case}: the refusal does not name {names!r}: {said}"


def test_a_refusal_prints_no_control_character_of_the_list_raw(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A path in a list is the caller's text; the door's refusal escapes it."""
    cg.clean_door_env(monkeypatch)
    cg.fake_door(tmp_path, monkeypatch, tmp_path / "order.log")
    root = tmp_path / "caller"
    root.mkdir()
    listed = cg.write_list(
        tmp_path / "g.json", str(root), [cg.entry("a\x00b\x1b[2Jc.py", "before")]
    )

    assert run.main(cg.read_argv("--gates", str(listed))) == 2

    said = capsys.readouterr().err
    assert "\x00" not in said and "\x1b" not in said, repr(said)
    assert "\\x1b" in said, said


@pytest.mark.parametrize(
    "where", [PACKAGE / "serving" / "gate-scripts", PACKAGE], ids=["gates", "package"]
)
def test_a_root_inside_the_package_is_refused_as_the_root_not_as_a_gate(
    where: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    cg.fake_door(tmp_path, monkeypatch, log)
    listed = cg.write_list(
        tmp_path / "g.json", str(where), [cg.entry("06-step.py", "before")]
    )

    assert run.main(cg.read_argv("--gates", str(listed))) == 2

    said = " ".join(capsys.readouterr().err.split())
    assert f"root {where.resolve()} {ROOT_IN_PACKAGE}" in said, said
    assert "gates[0]" not in said, said
    assert cg.log_lines(log) == []


def test_a_list_named_from_a_working_folder_that_is_gone_is_refused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    cg.fake_door(tmp_path, monkeypatch, log)
    compose = cg.compose_file(tmp_path / "compose.yaml")
    gone = tmp_path / "gone"
    gone.mkdir()
    monkeypatch.chdir(gone)
    gone.rmdir()

    status = run.main(cg.serve_argv(compose, "--gates", "g.json"))

    said = capsys.readouterr().err
    assert status == 2, said
    assert "REFUSED" in said and "--gates g.json" in said, said
    assert cg.log_lines(log) == []
