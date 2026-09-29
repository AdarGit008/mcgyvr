"""Whatever a caller's gate exports, the door still releases the machine's lease.

A value a gate exports enters the environment every later process starts
with. A value holding a NUL, which no process can start with, is refused
where it is read, as a refusal by the gate that wrote it; so is a gate that
writes more on its export descriptor than the door reads (it is ended with
its process group), and so are bytes that are not UTF-8, which would grow
when the door carried them on. A refusal quotes only the start of a
caller's line it cannot read, and says how long the line was. The door goes
on to release the lease. The release itself starts with the door's own
names only, never with a value a caller's gate exported. The edges hold:
a gate may write exactly as much as the door reads, and not a byte more.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from mcgyvr.serving import run
from tests import callergates as cg

RELEASE = f"door:{run.LEASE_RELEASE.script}"


def _bad_value_gate(root: Path, log: Path) -> None:
    cg.executable(
        root / "nul.py",
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import os",
                f"open({str(log)!r}, 'a').write('caller:nul\\n')",
                "fd = int(os.environ['RUN_EXPORT_FD'])",
                "os.write(fd, b'RUN_CALLER_BAD=a\\x00b\\n')",
                "",
            ]
        ),
    )


@pytest.mark.parametrize("phase", ["after", "always"])
def test_a_value_no_process_can_start_with_is_refused_and_the_lease_released(
    phase: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    cg.fake_door(tmp_path, monkeypatch, log)
    root = tmp_path / "caller"
    _bad_value_gate(root, log)
    listed = cg.write_list(
        tmp_path / "gates.json",
        str(root),
        [cg.entry("nul.py", phase, ["RUN_CALLER_BAD"])],
    )
    compose = cg.compose_file(tmp_path / "compose.yaml")

    status = run.main(cg.serve_argv(compose, "--gates", str(listed)))

    said = capsys.readouterr().err
    assert status != 0, said
    order = [line.split()[0] for line in cg.log_lines(log)]
    assert "caller:nul" in order
    assert order[-1] == RELEASE, order
    assert "RUN_CALLER_BAD" in said and "nul.py" in said, said


def test_the_release_starts_with_no_value_a_callers_gate_exported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    cg.fake_door(tmp_path, monkeypatch, log, show=("RUN_CALLER_MARK",))
    root = tmp_path / "caller"
    cg.executable(
        root / "mark.py",
        cg.gate_text(log, "caller:mark", exports={"RUN_CALLER_MARK": "seen"}),
    )
    listed = cg.write_list(
        tmp_path / "gates.json",
        str(root),
        [cg.entry("mark.py", "before", ["RUN_CALLER_MARK"])],
    )
    compose = cg.compose_file(tmp_path / "compose.yaml")

    assert run.main(cg.serve_argv(compose, "--gates", str(listed))) == 0

    lines = {line.split()[0]: line for line in cg.log_lines(log)}
    assert "RUN_CALLER_MARK=seen" in lines["door:02-rig.py"]
    assert "RUN_CALLER_MARK=-" in lines[RELEASE], lines[RELEASE]


#: Far more than the door reads from one gate, and more than one value in an
#: environment may hold on any system the door runs on.
FLOOD = 1024 * 1024


@pytest.mark.parametrize(
    ("case", "body"),
    [
        (
            "a value larger than the door reads",
            f"os.write(fd, b'RUN_CALLER_BIG=' + b'x' * {FLOOD} + b'\\n')",
        ),
        (
            "a long line that is not KEY=VALUE",
            f"os.write(fd, b'y' * {FLOOD // 32} + b'\\n')",
        ),
    ],
    ids=["too much", "a long line"],
)
def test_a_gate_that_floods_its_exports_is_refused_by_name_and_the_lease_released(
    case: str,
    body: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    cg.fake_door(tmp_path, monkeypatch, log)
    root = tmp_path / "caller"
    cg.executable(
        root / "flood.py",
        "#!/usr/bin/env python3\nimport os\n"
        f"open({str(log)!r}, 'a').write('caller:flood\\n')\n"
        "fd = int(os.environ['RUN_EXPORT_FD'])\n"
        f"{body}\n",
    )
    listed = cg.write_list(
        tmp_path / "gates.json",
        str(root),
        [cg.entry("flood.py", "after", ["RUN_CALLER_BIG"])],
    )
    compose = cg.compose_file(tmp_path / "compose.yaml")

    status = run.main(cg.serve_argv(compose, "--gates", str(listed)))

    said = capsys.readouterr().err
    assert status == 2, (case, said[:2000])
    refusal = [line for line in said.splitlines() if "REFUSED" in line]
    assert refusal and "flood.py" in refusal[0], (case, said[:2000])
    assert "could not be started" not in said, (case, said[:2000])
    assert len(said) < 4096, (case, len(said))
    order = [line.split()[0] for line in cg.log_lines(log)]
    assert order[-1] == RELEASE, order


def _writer(root: Path, log: Path, data: bytes, *, then: str = "") -> None:
    """A caller's gate that logs its pid, writes ``data`` on its exports, then
    runs ``then``."""
    cg.executable(
        root / "writer.py",
        "#!/usr/bin/env python3\nimport os, time\n"
        f"open({str(log)!r}, 'a').write(f'caller:writer pid={{os.getpid()}}\\n')\n"
        "fd = int(os.environ['RUN_EXPORT_FD'])\n"
        f"os.write(fd, {data!r})\n"
        f"{then}\n",
    )


def _run_writer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, data: bytes, then: str = ""
) -> tuple[int, Path]:
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    cg.fake_door(tmp_path, monkeypatch, log)
    root = tmp_path / "caller"
    _writer(root, log, data, then=then)
    listed = cg.write_list(
        tmp_path / "gates.json",
        str(root),
        [cg.entry("writer.py", "after", ["RUN_CALLER_BIG"])],
    )
    compose = cg.compose_file(tmp_path / "compose.yaml")
    return run.main(cg.serve_argv(compose, "--gates", str(listed))), log


def _refusal(said: str) -> str:
    lines = [line for line in said.splitlines() if "REFUSED" in line]
    assert lines, said[:2000]
    return lines[0]


def test_bytes_that_are_not_utf8_are_refused_by_the_gates_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    status, log = _run_writer(
        tmp_path, monkeypatch, b"RUN_CALLER_BIG=" + b"\xff" * 50_000 + b"\n"
    )

    said = capsys.readouterr().err
    assert status == 2, said[:2000]
    assert "writer.py" in _refusal(said), said[:2000]
    assert "could not be started" not in said, said[:2000]
    assert cg.log_lines(log)[-1].startswith(RELEASE), cg.log_lines(log)


def test_a_gate_over_the_export_cap_is_ended_with_its_group(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    status, log = _run_writer(
        tmp_path,
        monkeypatch,
        b"RUN_CALLER_BIG=" + b"x" * run.MAX_EXPORT_BYTES + b"\n",
        then="time.sleep(60)",
    )

    said = capsys.readouterr().err
    assert status == 2, said[:2000]
    assert "writer.py" in _refusal(said), said[:2000]
    pid = next(
        int(found.group(1))
        for line in cg.log_lines(log)
        if (found := re.match(r"caller:writer pid=(\d+)", line))
    )
    assert not cg.alive(pid), pid
    assert cg.log_lines(log)[-1].startswith(RELEASE), cg.log_lines(log)


@pytest.mark.parametrize(
    ("written", "admitted"),
    [(run.MAX_EXPORT_BYTES, True), (run.MAX_EXPORT_BYTES + 1, False)],
    ids=["exactly the cap", "one byte over"],
)
def test_a_gate_may_write_as_much_as_the_door_reads_and_not_a_byte_more(
    written: int,
    admitted: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    head = b"RUN_CALLER_BIG="
    data = head + b"x" * (written - len(head) - 1) + b"\n"
    assert len(data) == written
    status, _ = _run_writer(tmp_path, monkeypatch, data)

    said = capsys.readouterr().err
    if admitted:
        assert status == 0, said[:2000]
    else:
        assert status == 2, said[:2000]
        assert "writer.py" in _refusal(said), said[:2000]


def test_one_value_the_environment_cannot_hold_is_refused_by_the_callers_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """128 KiB: what Linux lets one environment string hold, with 4 KiB pages."""
    status, _ = _run_writer(
        tmp_path, monkeypatch, b"RUN_CALLER_BIG=" + b"x" * 131_072 + b"\n"
    )

    said = capsys.readouterr().err
    assert status == 2, said[:2000]
    assert "writer.py" in _refusal(said), said[:2000]
    assert "could not be started" not in said, said[:2000]


def test_a_long_line_is_quoted_by_its_start_and_its_length(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    status, _ = _run_writer(tmp_path, monkeypatch, b"y" * 32_769 + b"\n")

    said = capsys.readouterr().err
    assert status == 2, said[:2000]
    refusal = _refusal(said)
    assert "(32769 characters)" in refusal, refusal
    quoted = re.search(r"wrote ('y+')", refusal)
    assert quoted and len(quoted.group(1)) <= 82, refusal
