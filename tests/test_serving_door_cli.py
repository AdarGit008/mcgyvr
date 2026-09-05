"""The door refuses before it acts, and what it starts cannot leave it.

``python -m mcgyvr.serving.run`` is the one access point to the rigs. Pinned
here, from the outside, the way an operator meets it:

* an ambient ``RUN_*`` or ``DOCKER_*`` variable is refused by name before any
  gate — the door mints its own vocabulary;
* ``--help`` shows no ``--skip``, ``--force`` or ``--no-`` anything, and
  ``--step`` is optional (the shipped default step);
* a step argument that would write outside the envelope is refused before
  gate 1, as the archived door refused it (archive/runs/run.sh,
  ``check_step_args``), and one naming a path inside it is admitted;
* the ``ssh`` and ``docker`` on the PATH the door exports are shims: outside
  the door they exit 2 naming it, under it they become the real binary
  pointed at the door's host and nothing else;
* every gate script run by hand exits 2;
* an interrupt during the step still runs gates 7 and 8, then exits 130.

No test here reaches a rig: every door invocation has a stub ``ssh`` and a
stub ``docker`` on PATH behind the shims, and the interrupt path is driven
through fake gates that export what the real ones declare.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from mcgyvr.serving import run
from tests.test_serving_gatelib import (
    DOOR,
    SSH,
    clean_env,
    executable,
    fake_door,
    under,
)

REPO = Path(__file__).resolve().parent.parent
GATE_SCRIPTS = REPO / "src" / "mcgyvr" / "serving" / "gate-scripts"
BIN = GATE_SCRIPTS / "bin"
SHIM_SSH = BIN / SSH
DOCKER = "docker"
SHIM_DOCKER = BIN / DOCKER
RUN_DATE = "2026-09-02"

GATES = sorted(p.name for p in GATE_SCRIPTS.glob("*.py"))


def stubs(where: Path) -> Path:
    """An ``ssh`` that refuses and a ``docker`` that logs, both behind the shims."""
    executable(
        where / SSH,
        "#!/usr/bin/env bash\n"
        f"printf '%s\\n' \"$*\" >> '{where / 'ssh.log'}'\n"
        "echo 'no rig is reachable from a test' >&2\n"
        "exit 1\n",
    )
    executable(
        where / DOCKER,
        "#!/usr/bin/env bash\n"
        f"printf '%s\\n' \"$*\" >> '{where / 'docker.log'}'\n"
        "exit 0\n",
    )
    return where


def door(
    argv: list[str], env: dict[str, str], cwd: Path = REPO
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "mcgyvr.serving.run", *argv],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    return clean_env(stubs(tmp_path / "stubs"))


@pytest.fixture
def step(tmp_path: Path) -> Path:
    return executable(
        tmp_path / "1-probe.sh", "#!/usr/bin/env bash\n# RUN_ARTIFACTS: probe.tsv\n"
    )


def base_argv(step: Path, campaign: str = "alpha-cli-test") -> list[str]:
    return [
        "--host",
        "srv1",
        "--campaign",
        campaign,
        "--model",
        "/models/x.gguf",
        "--step",
        str(step),
        "--date",
        RUN_DATE,
    ]


# --------------------------------------------------------------------------
# before any gate: the environment, the arguments
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["RUN_ID", "RUN_HOST", "DOCKER_HOST"])
def test_an_ambient_variable_is_refused_by_name_before_any_gate(
    env: dict[str, str], step: Path, tmp_path: Path, name: str
) -> None:
    env[name] = "x"
    result = door(base_argv(step), env)
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert name in result.stderr, result.stderr
    assert "unset it and rerun; the door mints its own vocabulary" in result.stderr
    assert not (tmp_path / "stubs" / "ssh.log").exists(), "a gate reached ssh"


def test_help_offers_no_way_past_a_gate(env: dict[str, str]) -> None:
    result = door(["--help"], env)
    assert result.returncode == 0, result.stderr
    for hole in ("--skip", "--force", "--no-"):
        assert hole not in result.stdout, f"--help names {hole}"
    assert "[--step" in result.stdout, "--step is no longer optional"
    assert "--host" in result.stdout


def test_the_default_step_is_taken_when_none_is_named(
    env: dict[str, str], step: Path
) -> None:
    argv = [a for a in base_argv(step) if a not in ("--step", str(step))]
    result = door(argv, env)
    assert result.returncode == 2, (result.stdout, result.stderr)
    if run.DEFAULT_STEP.is_file():
        assert "the default step is missing" not in result.stderr, result.stderr
    else:
        assert "the default step is missing" in result.stderr, result.stderr
        assert str(run.DEFAULT_STEP.relative_to(run.ROOT)) in result.stderr


ESCAPES = (
    ["--out", "/tmp/elsewhere.tsv"],
    ["--out=/tmp/elsewhere.tsv"],
    ["--out-dir", "/tmp/elsewhere"],
    ["--out-dir=/tmp/elsewhere"],
    ["--force"],
    ["--out", "records/evidence/2026-09-01-other/x.tsv"],
    ["--out", "../outside.tsv"],
)


@pytest.mark.parametrize(
    "args", ESCAPES, ids=[a[0].split("=")[0] + str(i) for i, a in enumerate(ESCAPES)]
)
def test_a_step_argument_that_leaves_the_envelope_is_refused_before_any_gate(
    env: dict[str, str], step: Path, tmp_path: Path, args: list[str]
) -> None:
    result = door([*base_argv(step), "--", *args], env)
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "step argument" in result.stderr, result.stderr
    assert args[0].split("=")[0] in result.stderr, result.stderr
    assert f"{RUN_DATE}-alpha-cli-test" in result.stderr, result.stderr
    assert not (REPO / "records" / "evidence" / f"{RUN_DATE}-alpha-cli-test").exists()
    assert not (tmp_path / "stubs" / "ssh.log").exists(), "a gate reached ssh"


def test_a_step_argument_inside_the_envelope_is_admitted(
    env: dict[str, str], step: Path
) -> None:
    inside = f"records/evidence/{RUN_DATE}-alpha-cli-test/probe.tsv"
    result = door([*base_argv(step), "--", "--out", inside], env)
    # It goes on to gate 1 (or 2, where the stub refuses); it is not the
    # argument check that stopped it.
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "step argument" not in result.stderr, result.stderr


def test_check_step_args_reads_the_archived_rule() -> None:
    envelope = run.ROOT / "records" / "evidence" / "2026-09-02-alpha"
    assert run._check_step_args([], envelope) is None
    assert (
        run._check_step_args(["--model", "/models/x.gguf", "-n", "8"], envelope) is None
    )
    assert run._check_step_args(["--out", str(envelope / "a.tsv")], envelope) is None
    for tokens in (["--out"], ["--out="], ["--out-dir", "/tmp"], ["--force"]):
        rule = run._check_step_args(tokens, envelope)
        assert rule is not None and "step argument" in rule, tokens


def test_run_docker_is_gone_from_the_vocabulary() -> None:
    assert "RUN_DOCKER" not in run.EXPORTED
    source = (run.HERE / "run.py").read_text(encoding="utf-8")
    assert "RUN_DOCKER" not in source
    assert "RUN_DOCKER" not in (GATE_SCRIPTS / "rig-snapshot.sh").read_text("utf-8")


# --------------------------------------------------------------------------
# the manifest: shims are part of the door
# --------------------------------------------------------------------------


def test_the_shims_are_shipped_executable() -> None:
    for shim in (SHIM_SSH, SHIM_DOCKER):
        assert shim.is_file(), shim
        assert os.access(shim, os.X_OK), f"{shim} is not executable"
        assert shim.read_text(encoding="utf-8").startswith("#!/usr/bin/env python3")


@pytest.mark.parametrize("missing", [SSH, DOCKER])
def test_the_manifest_requires_both_shims(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    copy = tmp_path / "gate-scripts"
    shutil.copytree(GATE_SCRIPTS, copy, ignore=shutil.ignore_patterns("__pycache__"))
    monkeypatch.setattr(run, "GATE_SCRIPTS", copy)
    monkeypatch.setattr(run, "BIN", copy / "bin")
    run._check_manifest()  # complete: admitted
    (copy / "bin" / missing).chmod(0o644)
    with pytest.raises(run.RefusedError) as refused:
        run._check_manifest()
    assert refused.value.status == 2
    assert missing in refused.value.rule and "shim" in refused.value.rule
    (copy / "bin" / missing).unlink()
    with pytest.raises(run.RefusedError):
        run._check_manifest()


# --------------------------------------------------------------------------
# the shims themselves
# --------------------------------------------------------------------------


def test_the_ssh_shim_outside_the_door_exits_2_naming_the_door(
    env: dict[str, str], tmp_path: Path
) -> None:
    result = subprocess.run(
        [str(SHIM_SSH), "other"], env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 2, result.stderr
    assert DOOR in result.stderr, result.stderr
    assert "other" in result.stderr
    assert not (tmp_path / "stubs" / "ssh.log").exists(), "the shim fell through"


@pytest.mark.parametrize(
    "argv",
    [["-o", "X", "user@srv1", "cmd"], ["-p", "22", "srv1"], ["--", "srv1", "true"]],
    ids=["option-and-user", "port", "double-dash"],
)
def test_the_ssh_shim_names_the_host_it_parsed(
    env: dict[str, str], argv: list[str]
) -> None:
    result = subprocess.run(
        [str(SHIM_SSH), *argv], env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 2, result.stderr
    assert "to srv1 refused" in result.stderr, result.stderr


def test_the_ssh_shim_under_the_door_becomes_the_next_ssh_with_batchmode(
    tmp_path: Path,
) -> None:
    stub_dir = tmp_path / "stubs"
    log = stub_dir / "ssh.log"
    executable(
        stub_dir / SSH,
        f"#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> '{log}'\nexit 0\n",
    )
    env = clean_env(BIN, stub_dir)
    env["RUN_HOST"] = "srv1"
    result = under(fake_door(tmp_path), [SSH, "-o", "X", "user@srv1", "cmd"], env)
    assert result.returncode == 0, result.stderr
    assert log.read_text(encoding="utf-8").splitlines() == [
        "-o BatchMode=yes -o ConnectTimeout=10 -o X user@srv1 cmd"
    ]


def test_the_ssh_shim_under_the_door_refuses_another_host(tmp_path: Path) -> None:
    stub_dir = stubs(tmp_path / "stubs")
    env = clean_env(BIN, stub_dir)
    env["RUN_HOST"] = "srv1"
    result = under(
        fake_door(tmp_path), [SSH, "--", "srv2", "docker", "system", "dial-stdio"], env
    )
    assert result.returncode == 2, result.stderr
    assert "srv1" in result.stderr and "srv2" in result.stderr, result.stderr
    assert not (stub_dir / "ssh.log").exists()


def test_the_docker_shim_outside_the_door_exits_2(
    env: dict[str, str], tmp_path: Path
) -> None:
    result = subprocess.run(
        [str(SHIM_DOCKER), "ps"], env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 2, result.stderr
    assert DOOR in result.stderr
    assert not (tmp_path / "stubs" / "docker.log").exists()


def test_the_docker_shim_under_the_door_points_at_the_rig(tmp_path: Path) -> None:
    stub_dir = stubs(tmp_path / "stubs")
    env = clean_env(BIN, stub_dir)
    env["RUN_HOST"] = "srv1"
    result = under(fake_door(tmp_path), [DOCKER, "ps", "-q"], env)
    assert result.returncode == 0, result.stderr
    log = (stub_dir / "docker.log").read_text(encoding="utf-8").splitlines()
    assert log == ["-H ssh://srv1 ps -q"]


@pytest.mark.parametrize(
    "named", [["-H", "tcp://x"], ["--host=tcp://x"], ["--context", "c"]]
)
def test_the_docker_shim_refuses_a_caller_naming_its_own_daemon(
    tmp_path: Path, named: list[str]
) -> None:
    stub_dir = stubs(tmp_path / "stubs")
    env = clean_env(BIN, stub_dir)
    env["RUN_HOST"] = "srv1"
    result = under(fake_door(tmp_path), [DOCKER, *named, "ps"], env)
    assert result.returncode == 2, result.stderr
    assert "names a daemon" in result.stderr
    assert not (stub_dir / "docker.log").exists()


# --------------------------------------------------------------------------
# the gates by hand
# --------------------------------------------------------------------------


@pytest.mark.parametrize("script", GATES)
def test_a_gate_run_by_hand_exits_2(env: dict[str, str], script: str) -> None:
    result = subprocess.run(
        [sys.executable, str(GATE_SCRIPTS / script)],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 2, (script, result.stdout, result.stderr)
    assert "started outside mcgyvr.serving.run" in result.stderr, result.stderr


def test_every_entry_in_sequence_is_a_shipped_script() -> None:
    """Every shipped .py under gate-scripts is a gate the door runs, or one of
    the door's own serve steps — nothing shipped there is reachable by no run."""
    steps = [path.name for path in run.SERVE_STEPS.values()]
    assert sorted([*(e.script for e in (*run.SEQUENCE, *run.ALWAYS)), *steps]) == GATES


# --------------------------------------------------------------------------
# the interrupt path: gates 7 and 8 run, then 130
# --------------------------------------------------------------------------


def fake_gates(where: Path, out_dir: Path, flag: Path) -> Path:
    """Gate scripts that export what SEQUENCE declares and record that they ran.

    The step touches ``flag`` and hangs; gate 7 writes ``teardown-ran`` with
    the environment it saw; gate 8 writes ``parse-ran``.
    """
    where.mkdir(parents=True)
    shutil.copytree(BIN, where / "bin")
    values = {"RUN_ID": "2026-09-02-alpha-probe", "RUN_OUT_DIR": str(out_dir)}
    for entry in (*run.SEQUENCE, *run.ALWAYS):
        lines = [
            "#!/usr/bin/env python3",
            "import os, sys, time",
            "from pathlib import Path",
        ]
        if entry.exports:
            lines.append("fd = int(os.environ['RUN_EXPORT_FD'])")
            for key in entry.exports:
                line = f"{key}={values.get(key, 'x')}\n"
                lines.append(f"os.write(fd, {line!r}.encode())")
        if entry.script == "06-step.py":
            lines += [f"Path({str(flag)!r}).touch()", "time.sleep(120)"]
        elif entry.script == "07-teardown.py":
            lines.append(
                f"Path({str(out_dir / 'teardown-ran')!r}).write_text("
                "os.environ['RUN_ID'] + '\\n' + os.environ['PATH'].split(os.pathsep)[0]"
                " + '\\n' + str('RUN_DOCKER' in os.environ) + '\\n')"
            )
        elif entry.script == "08-parse.py":
            lines.append(f"Path({str(out_dir / 'parse-ran')!r}).touch()")
        lines.append("sys.exit(0)")
        executable(where / entry.script, "\n".join(lines) + "\n")
    return where


@pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM], ids=["INT", "TERM"])
def test_a_signal_during_the_step_still_runs_gates_7_and_8_then_exits_130(
    tmp_path: Path, step: Path, sig: signal.Signals
) -> None:
    out_dir = tmp_path / "envelope"
    out_dir.mkdir()
    flag = tmp_path / "step-ran"
    gates = fake_gates(tmp_path / "gate-scripts", out_dir, flag)
    env = clean_env(stubs(tmp_path / "stubs"))
    code = (
        "import signal, sys\n"
        "from pathlib import Path\n"
        "from mcgyvr.serving import run\n"
        f"run.GATE_SCRIPTS = Path({str(gates)!r})\n"
        "run.BIN = run.GATE_SCRIPTS / 'bin'\n"
        "signal.signal(signal.SIGTERM, run._sigterm)\n"
        f"sys.exit(run.main({base_argv(step)!r}))\n"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", code],
        cwd=REPO,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 60
        while not flag.exists():
            assert proc.poll() is None, proc.communicate()
            assert time.monotonic() < deadline, "the step never reached its hang"
            time.sleep(0.05)
        os.killpg(proc.pid, sig)
        _, stderr = proc.communicate(timeout=120)
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
    assert proc.returncode == 130, (proc.returncode, stderr)
    assert "interrupted" in stderr, stderr
    assert (out_dir / "parse-ran").exists(), stderr
    seen = (out_dir / "teardown-ran").read_text(encoding="utf-8").splitlines()
    assert seen == ["2026-09-02-alpha-probe", str(gates / "bin"), "False"], seen


def test_the_run_environment_leads_with_the_shims_and_carries_no_docker_seam(
    tmp_path: Path, step: Path
) -> None:
    """Without a signal: the same fake gates, run to the end."""
    out_dir = tmp_path / "envelope"
    out_dir.mkdir()
    gates = fake_gates(tmp_path / "gate-scripts", out_dir, tmp_path / "flag")
    # A step that returns at once, so the run completes.
    executable(gates / "06-step.py", "#!/usr/bin/env python3\nraise SystemExit(0)\n")
    env = clean_env(stubs(tmp_path / "stubs"))
    code = (
        "import sys\n"
        "from pathlib import Path\n"
        "from mcgyvr.serving import run\n"
        f"run.GATE_SCRIPTS = Path({str(gates)!r})\n"
        "run.BIN = run.GATE_SCRIPTS / 'bin'\n"
        f"sys.exit(run.main({base_argv(step)!r}))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    seen = (out_dir / "teardown-ran").read_text(encoding="utf-8").splitlines()
    assert seen[1] == str(gates / "bin"), "gate-scripts/bin is not first on PATH"
    assert seen[2] == "False", "RUN_DOCKER reached a gate"
    assert seen[0] == "2026-09-02-alpha-probe"


@pytest.mark.parametrize(
    "model",
    [
        "/models/x.gguf; touch /tmp/pwned",
        "/models/x.gguf$(id)",
        "/models/x.gguf`id`",
        "/models/a b.gguf",
        "/models/x.gguf|id",
        "models/x.gguf",
        "/models/../etc/passwd",
        "/models//x.gguf",
    ],
)
def test_a_model_path_with_shell_characters_is_refused_before_any_gate(
    env: dict[str, str], step: Path, tmp_path: Path, model: str
) -> None:
    """--model is handed to a remote shell by data-20 and to container argv by
    the step; the door refuses anything but an absolute path of ordinary
    characters, before gate 1, so nothing is ever escaped in three places."""
    argv = [a for a in base_argv(step)]
    argv[argv.index("--model") + 1] = model
    result = door(argv, env)
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "--model" in result.stderr and "refused" in result.stderr, result.stderr
    assert not (tmp_path / "stubs" / "ssh.log").exists(), "a gate reached ssh"


def test_data_20_quotes_the_remote_path_even_so() -> None:
    """The second lock on the same door: the remote line data-20 builds leaves
    only `$HOME` bare, so a path that somehow carried a shell character is a
    file name on the rig and never a command."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "data_20_geometry",
        REPO / "src" / "mcgyvr" / "serving" / "gate-scripts" / "data-20-geometry.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    line = module.scan_command("QUJD", "/models/x.gguf; touch /tmp/pwned")
    assert line.endswith("""python3 - "$HOME"/models'/x.gguf; touch /tmp/pwned'"""), (
        line
    )
    assert module.scan_command("QUJD", "/models/moe/x.gguf").endswith(
        'python3 - "$HOME"/models/moe/x.gguf'
    )
    assert module.scan_command("QUJD", "/srv/blob.gguf").endswith(
        "python3 - /srv/blob.gguf"
    )
