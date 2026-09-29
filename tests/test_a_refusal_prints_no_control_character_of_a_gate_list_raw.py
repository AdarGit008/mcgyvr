"""Nothing the door prints about a caller's gate carries a control character raw.

A gate's path and its ``why`` are the caller's text. A terminal escape, a NUL
or a line break in them is printed as its escape wherever the door names the
gate. Seven of the texts that name one are held here: a gate that refuses
before the step, an ``always`` gate that refuses, a gate that exports a name
its list does not declare, one that exports a value holding a NUL, one that
writes a line that is not ``KEY=VALUE``, one that admits without its
declared export, and an ``always`` gate ended by a signal to the door.
"""

from __future__ import annotations

import signal
import time
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
    "exports a value holding a NUL": (
        "os.write(fd, b'RUN_CALLER_X=a\\x00b\\n')",
        "before",
        ["RUN_CALLER_X"],
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


def test_an_always_gate_ended_by_a_signal_is_named_escaped(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    log = work / "order.log"
    root = work / "caller"
    cg.executable(
        root / NAME,
        "#!/usr/bin/env python3\nimport time\n"
        f"open({str(log)!r}, 'a').write('caller:named\\n')\n"
        "time.sleep(60)\n",
    )
    gate = cg.entry(NAME, "always", why=WHY)
    gate["timeout_s"] = 120
    listed = cg.write_list(work / "gates.json", str(root), [gate])
    compose = cg.compose_file(work / "compose.yaml")
    door = cg.driven_door(work, log, cg.serve_argv(compose, "--gates", str(listed)))
    try:
        deadline = time.monotonic() + 60
        while "caller:named" not in cg.log_lines(log):
            assert door.poll() is None, door.communicate()
            assert time.monotonic() < deadline, cg.log_lines(log)
            time.sleep(0.1)
        door.send_signal(signal.SIGTERM)
        _, said = door.communicate(timeout=60)
    finally:
        cg.stop_door(door)

    assert "\x1b" not in said and "\x00" not in said, repr(said)
    named = [line for line in said.splitlines() if "was ended by a signal" in line]
    assert named, said
    assert "esc\\x1b[2Jnew\\nline.py" in named[0], repr(named[0])
    assert "why\\x1b[31m\\x00\\nred" in named[0], repr(named[0])
