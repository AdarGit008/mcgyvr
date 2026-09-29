"""Nothing the door prints about a caller's gate carries a control character raw.

A gate's path and its ``why`` are the caller's text. A terminal escape, a NUL
or a line break in them is printed as its escape wherever the door names the
gate: a gate that refuses before the step, an ``always`` gate that refuses, a
gate that exports a name its list does not declare, one that writes a line
that is not ``KEY=VALUE``, and one that admits without its declared export.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.serving import run
from tests import callergates as cg

NAME = "esc\x1b[2Jnew\nline.py"
WHY = "why\x1b[31m\x00\nred"

#: What each gate does, its phase, and the names its list declares for it.
GATES = {
    "refuses before the step": ("sys.exit(2)", "before", []),
    "refuses in always": ("sys.exit(1)", "always", []),
    "exports an undeclared name": (
        "os.write(fd, b'RUN_CALLER_UNSAID=x\\n')",
        "before",
        [],
    ),
    "writes a line that is not KEY=VALUE": (
        "os.write(fd, b'not a fact\\n')",
        "before",
        [],
    ),
    "admits without its declared export": (
        "sys.exit(0)",
        "before",
        ["RUN_CALLER_OWED"],
    ),
}


@pytest.mark.parametrize("case", sorted(GATES))
def test_a_gate_named_with_control_characters_is_named_escaped(
    case: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    cg.fake_door(tmp_path, monkeypatch, log)
    root = tmp_path / "caller"
    body, phase, exports = GATES[case]
    cg.executable(
        root / NAME,
        "#!/usr/bin/env python3\nimport os, sys\n"
        "fd = int(os.environ['RUN_EXPORT_FD'])\n"
        f"{body}\n",
    )
    listed = cg.write_list(
        tmp_path / "gates.json",
        str(root),
        [cg.entry(NAME, phase, exports, why=WHY)],
    )
    compose = cg.compose_file(tmp_path / "compose.yaml")

    assert run.main(cg.serve_argv(compose, "--gates", str(listed))) != 0

    said = capsys.readouterr().err
    assert "\x1b" not in said and "\x00" not in said, repr(said)
    named = [line for line in said.splitlines() if "esc" in line]
    assert named, said
    for line in named:
        assert "esc\\x1b[2Jnew\\nline.py" in line, repr(line)
    assert not any(line.startswith(("line.py", "red")) for line in said.splitlines()), (
        said
    )
