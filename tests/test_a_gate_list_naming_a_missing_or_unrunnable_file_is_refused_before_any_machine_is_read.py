"""A gate list the door cannot hold a run to is refused before any gate runs.

A gate list is input the door does not trust. A gate that is missing or not
executable, a path that leaves the list's root (by name or through a link), a
root that is not an absolute folder, a key or a phase the door does not know,
and a name two gates both export: each is refused before the door runs its
first gate, and the refusal names the list file and the entry at fault.
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
            cg.entry(_ok(root, "one.py"), "before", ["RUN_LAB_TWICE"]),
            cg.entry(_ok(root, "two.py"), "after", ["RUN_LAB_TWICE"]),
        ],
    )
    return listed, "RUN_LAB_TWICE"


def _list_not_json(tmp: Path) -> tuple[Path, str]:
    listed = tmp / "g.json"
    listed.write_text("root = /somewhere\n", encoding="utf-8")
    return listed, "JSON"


def _list_missing(tmp: Path) -> tuple[Path, str]:
    return tmp / "no-such-list.json", "cannot be read"


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
    "a list file that is not there": _list_missing,
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
