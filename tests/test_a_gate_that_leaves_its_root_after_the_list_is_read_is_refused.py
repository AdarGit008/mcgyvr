"""A caller's gate that has left its root by the time it runs is refused, not run.

The door checks each gate's path when it reads the list, and checks again
just before it starts the gate. A gate file turned into a link out of the
root in between is refused, the file it now points at never runs, and the
lease is still released. The door starts the file its second check
resolved, not the listed name again: a link on the listed path re-pointed
out of the root after that check does not change what runs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.serving import run
from tests import callergates as cg


def test_a_gate_swapped_for_a_link_out_of_the_root_is_refused_when_its_turn_comes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    cg.fake_door(tmp_path, monkeypatch, log)
    root = tmp_path / "caller"
    outside = cg.executable(
        tmp_path / "elsewhere" / "outside.py", cg.gate_text(log, "outside")
    )
    later = cg.executable(root / "later.py", cg.gate_text(log, "caller:later"))
    cg.executable(
        root / "swap.py",
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import os",
                f"open({str(log)!r}, 'a').write('caller:swap\\n')",
                f"os.unlink({str(later)!r})",
                f"os.symlink({str(outside)!r}, {str(later)!r})",
                "",
            ]
        ),
    )
    listed = cg.write_list(
        tmp_path / "gates.json",
        str(root),
        [cg.entry("swap.py", "before"), cg.entry("later.py", "after")],
    )
    compose = cg.compose_file(tmp_path / "compose.yaml")

    status = run.main(cg.serve_argv(compose, "--gates", str(listed)))

    said = capsys.readouterr().err
    assert status == 2, said
    order = [line.split()[0] for line in cg.log_lines(log)]
    assert "outside" not in order and "caller:later" not in order, order
    assert order[-1] == f"door:{run.LEASE_RELEASE.script}", order
    assert "later.py" in said, said


def test_the_door_starts_the_file_it_checked_not_the_name_again(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    cg.fake_door(tmp_path, monkeypatch, log)
    root = tmp_path / "caller"
    cg.executable(root / "real" / "gate.py", cg.gate_text(log, "caller:inside"))
    cg.executable(tmp_path / "elsewhere" / "gate.py", cg.gate_text(log, "OUTSIDE"))
    (root / "via").symlink_to(root / "real")
    listed = cg.write_list(
        tmp_path / "gates.json", str(root), [cg.entry("via/gate.py", "before")]
    )
    compose = cg.compose_file(tmp_path / "compose.yaml")
    checked = run._outside
    calls: list[Path] = []

    def check_then_repoint(target: Path, where: Path) -> tuple[str | None, Path]:
        result = checked(target, where)
        calls.append(target)
        if len(calls) == 2:  # the check just before the spawn has passed
            (root / "via").unlink()
            (root / "via").symlink_to(tmp_path / "elsewhere")
        return result

    monkeypatch.setattr(run, "_outside", check_then_repoint)

    status = run.main(cg.serve_argv(compose, "--gates", str(listed)))

    said = capsys.readouterr().err
    assert status == 0, said
    order = [line.split()[0] for line in cg.log_lines(log)]
    assert "caller:inside" in order and "OUTSIDE" not in order, order
