"""A failed lock-fleets start files its exit cause; a failed retry gets a diagnostic.

Owner ruling, 2026-09-15: "Fix PR, then one diagnostic start". ``rig-id-relock``'s
srv2-01 (unit ``srv2_35b_256k``) exited before ``/health`` said ok, and so did its
one retry, srv2-01-retry1, 42 s in. The retry's whole docker log
(``records/evidence/2026-09-15-lock-fleets/``
``rig-id-relock-srv2-c1-srv2_35b_256k-retry1.srv2_35b_256k.docker.log``) ends at
"warming up the model" and ``[expert cache] io_uring_queue_init failed``, a line
known to be non-fatal: the process died with no stated cause. ``_unit.sh``'s
``finish()`` removed the container, so its exit code, OOMKilled, State.Error and
the rig's kernel log were never filed, and the retry ruling gives no second retry.

* A unit step that fails after ``docker run`` files, before anything removes the
  container, its ``docker inspect`` State (through the door's docker shim) and
  the rig's kernel log from START to now (``journalctl -k``, through the door's
  ssh shim) in the artifact's ``exit``, and its ``failure`` names the exit code
  and OOMKilled. A kernel log that cannot be read is filed as data, never a stop.
* A logged failed retry of a unit entry gets ONE diagnostic start, ``plan.py
  diagnose``: ``<entry>-diag1`` with its own wrapper and artifact, listed under
  ``diagnostics`` in ``<use>/retries.json`` and placed right after the failed
  retry. The retry's re-check passes as diagnosed and the diagnostic runs next.
  A passing diagnostic stands in for the failed entry as a passing retry would;
  it gets no retry, re-run or second diagnostic.

No rig is reached: the step runs under a stand-in door against stubs.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from tests import onedoor
from tests.lockfleets_window import (
    LLAMA_IMAGE_ID,
    REPO,
    USE,
    WINDOW_DATE,
    Window,
    assemble_module,
    context,
    frozen_window,
    make_tree,
    plan_module,
    snapshot,
)

CAMPAIGN = REPO / "tools" / "runs" / "campaigns" / "lock-fleets"
STEPS = f"tools/runs/campaigns/lock-fleets/{USE}"
REASON = "the retry died at warm-up with no stated cause"
SRV2_DIAG_REASON = (
    "retry died at warm-up with no stated cause (exit code, OOMKilled and kernel "
    "log not filed); owner 2026-09-15: fix PR, then one diagnostic start"
)
RUN_ID = f"{WINDOW_DATE}-lock-fleets-{USE}-alpha-c1-a_pair"
NAME = f"{RUN_ID}-a_pair"
KERNEL = (
    "2026-09-16T10:00:41.000000+00:00 alpha kernel: llama-server invoked oom-killer\n"
    "2026-09-16T10:00:41.100000+00:00 alpha kernel: Out of memory: Killed process "
    "4242 (llama-server)\n"
)
UNREADABLE = "No journal files were opened due to insufficient permissions."
OUT_LINES = [f"load step {n}" for n in range(1, 21)]

Change = Callable[[dict[str, Any]], None]

#: The door's docker shim, as the step finds it under RUN_BIN: every call is
#: logged, the image resolves to the fixture's digest, and the container's State
#: and Running flag are the test's.
DOCKER = """\
#!/usr/bin/env bash
set -u
RIG=$(cd "$(dirname "$0")/.." && pwd)
printf 'docker: %s\\n' "$*" >> "$RIG/calls.log"
case ${1:-} in
  image) printf '[{"Id": "@IMAGE@", "RepoDigests": []}]\\n' ;;
  run) echo c0ffee0000aa ;;
  inspect)
    case "$*" in
      *"{{json .State}}"*) cat "$RIG/state.json" ;;
      *".State.Running"*) cat "$RIG/running.txt" ;;
      *) echo 0 ;;
    esac ;;
  logs) cat "$RIG/stdout.txt" ;;
esac
exit 0
"""

#: The door's ssh shim: the rig's reading (the second fails when the test says
#: so, which is END's), its vmstat, and its kernel log as the test gives it.
SSH = """\
#!/usr/bin/env bash
set -u
RIG=$(cd "$(dirname "$0")/.." && pwd)
shift
cmd="$*"
printf 'ssh: %s\\n' "$(printf '%s' "$cmd" | tr '\\n' ' ')" >> "$RIG/calls.log"
case $cmd in
  "bash -s")
    cat >/dev/null
    n=$(cat "$RIG/readings" 2>/dev/null || echo 0)
    echo $((n + 1)) > "$RIG/readings"
    if [ "$n" -ge 1 ] && [ -f "$RIG/end.fails" ]; then exit 1; fi
    cat "$RIG/snapshot.txt" ;;
  *"cat >>"*) cat >/dev/null ;;
  *vmstat*) printf 'pswpout 10\\npgmajfault 5\\n' ;;
  *journalctl*)
    cat "$RIG/kernel.out"
    cat "$RIG/kernel.err" >&2
    exit "$(cat "$RIG/kernel.exit")" ;;
esac
exit 0
"""

#: The step's own clock, when a test needs 900 s to pass: every epoch it reads
#: is 60 s after the last. Any other format is the real date's.
DATE = """\
#!/usr/bin/env bash
clock="$(dirname "$0")/clock"
case "$*" in
  "+%s" | "-u +%s" | "+%s.%N")
    now=$(( $(cat "$clock") + 60 ))
    echo "$now" > "$clock"
    case "$*" in *%N) echo "$now.000000000" ;; *) echo "$now" ;; esac ;;
  *)
    for real in /usr/bin/date /bin/date; do
      [ -x "$real" ] && exec "$real" "$@"
    done
    exit 1 ;;
esac
"""

CURL = """\
#!/usr/bin/env bash
[ -f "$(dirname "$0")/healthy" ] && { echo ok; exit 0; }
exit 7
"""


def _state(code: int, oom: bool, *, running: bool = False) -> dict[str, Any]:
    """A container's State as ``docker inspect`` prints it."""
    return {
        "Status": "running" if running else "exited",
        "Running": running,
        "Paused": False,
        "Restarting": False,
        "OOMKilled": oom,
        "Dead": False,
        "Pid": 4242 if running else 0,
        "ExitCode": code,
        "Error": "",
        "StartedAt": "2026-09-16T10:00:00.100000000Z",
        "FinishedAt": (
            "0001-01-01T00:00:00Z" if running else "2026-09-16T10:00:42.500000000Z"
        ),
    }


def _unit_step(
    tmp_path: Path,
    *,
    unit: str = "a_pair",
    state: dict[str, Any] | None = None,
    running: bool = False,
    kernel: tuple[str, str, int] = (KERNEL, "", 0),
    healthy: bool = False,
    end_fails: bool = False,
    clock: bool = False,
) -> tuple[subprocess.CompletedProcess[str], dict[str, Any], list[str]]:
    """``_unit.sh`` under a stand-in door, on the fixture fleet's rig ``alpha``,
    with the door's shims standing in for a rig; its artifact and the calls."""
    root = make_tree(tmp_path / "tree")
    shutil.copy(REPO / "tools" / "runs" / "_common.sh", root / "tools" / "runs")
    rig = tmp_path / "rig"
    onedoor.executable(
        rig / "bin" / "docker", DOCKER.replace("@IMAGE@", LLAMA_IMAGE_ID)
    )
    onedoor.executable(rig / "bin" / "ssh", SSH)
    for name in ("rig-snapshot.sh", "rig-units.sh"):
        (rig / name).write_text("# the stub rig answers for it\n", "utf-8")
    reading = "".join(f"{k}={v}\n" for k, v in snapshot("alpha").items())
    (rig / "snapshot.txt").write_text(reading, "utf-8")
    (rig / "stdout.txt").write_text("".join(f"{x}\n" for x in OUT_LINES), "utf-8")
    (rig / "state.json").write_text(json.dumps(state or _state(1, False)), "utf-8")
    (rig / "running.txt").write_text(f"{json.dumps(running)}\n", "utf-8")
    (rig / "kernel.out").write_text(kernel[0], "utf-8")
    (rig / "kernel.err").write_text(kernel[1], "utf-8")
    (rig / "kernel.exit").write_text(f"{kernel[2]}\n", "utf-8")
    if end_fails:
        (rig / "end.fails").write_text("", "utf-8")
    path = tmp_path / "path"
    onedoor.executable(path / "curl", CURL)
    onedoor.executable(path / "sleep", "#!/usr/bin/env bash\nexit 0\n")
    if healthy:
        (path / "healthy").write_text("", "utf-8")
    if clock:
        onedoor.executable(path / "date", DATE)
        (path / "clock").write_text("1789552800\n", "utf-8")
    envelope = tmp_path / "envelope"
    envelope.mkdir()
    env = {k: v for k, v in os.environ.items() if not k.startswith(("RUN_", "DOCKER_"))}
    env["PATH"] = os.pathsep.join(
        [str(path), str(Path(sys.executable).parent), env.get("PATH") or os.defpath]
    )
    env.update(
        RUN_ROOT=str(root),
        RUN_REPO=str(REPO),
        RUN_BIN=str(rig / "bin"),
        RUN_HOST="alpha",
        RUN_ID=RUN_ID,
        RUN_OUT_DIR=str(envelope),
        RUN_ROUND="r-fixture",
        RUN_PRODUCT_SHA256="0" * 64,
        RUN_MODEL="/models/a_pair.gguf",
        RUN_PARALLEL="2",
        RUN_CTX_PER_SLOT="4096",
        RUN_UBATCH="512",
    )
    done = subprocess.run(
        [
            sys.executable,
            str(onedoor.fake_door(tmp_path)),
            "bash",
            str(CAMPAIGN / "_unit.sh"),
            "u.json",
            unit,
        ],
        cwd=REPO,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    log = rig / "calls.log"
    calls = log.read_text("utf-8").splitlines() if log.is_file() else []
    artifact = envelope / "u.json"
    assert artifact.is_file(), (done.returncode, done.stderr[-2000:])
    return done, json.loads(artifact.read_text("utf-8")), calls


def _index(calls: list[str], *words: str) -> int:
    """The first call that holds every one of ``words``."""
    found = [i for i, call in enumerate(calls) if all(w in call for w in words)]
    assert found, (words, calls)
    return found[0]


def _filed_before_removal(calls: list[str]) -> str:
    """The State and the kernel log were read after the container started and
    before its last removal; returns the kernel log's command as run."""
    started = _index(calls, "docker: run -d")
    removed = max(i for i, call in enumerate(calls) if call == f"docker: rm -f {NAME}")
    inspected = _index(calls, "docker: inspect", "{{json .State}}", NAME)
    read = _index(calls, "ssh: ", "journalctl -k")
    assert started < inspected < removed, calls
    assert started < read < removed, calls
    return calls[read].removeprefix("ssh: ").strip()


@pytest.mark.parametrize(
    ("code", "oom"), [(1, False), (137, True)], ids=["exited-1", "oom-killed"]
)
def test_a_unit_that_exited_before_health_files_its_state_and_kernel_log_first(
    tmp_path: Path, code: int, oom: bool
) -> None:
    state = _state(code, oom)
    done, doc, calls = _unit_step(tmp_path, state=state)
    assert done.returncode == 1, (done.stdout, done.stderr[-2000:])
    cause = doc["exit"]
    assert (cause["state"], cause["state_error"]) == (state, None)
    assert (cause["kernel_log"], cause["kernel_log_error"]) == (KERNEL, None)
    command = _filed_before_removal(calls)
    assert cause["kernel_log_command"] == command
    since = re.search(r"--since @(\d+) --until now\b", command)
    assert since, command
    moment = datetime.fromtimestamp(int(since.group(1)), UTC)
    assert cause["kernel_log_since"] == moment.strftime("%Y-%m-%dT%H:%M:%SZ")
    assert doc["started_at"] <= cause["kernel_log_since"]
    failure = doc["failure"]
    assert f"exit code {code}, OOMKilled {json.dumps(oom)}" in failure, failure
    # The #487 ruling still holds: the whole log is kept, and named.
    assert f"{NAME} exited before /health said ok: " in failure, failure
    assert "u.a_pair.docker.log" in failure
    assert (tmp_path / "envelope" / "u.a_pair.docker.log").is_file()


def test_a_unit_that_never_said_ok_in_900_s_files_its_state_and_kernel_log_first(
    tmp_path: Path,
) -> None:
    state = _state(0, False, running=True)
    done, doc, calls = _unit_step(tmp_path, state=state, running=True, clock=True)
    assert done.returncode == 1, (done.stdout, done.stderr[-2000:])
    failure = doc["failure"]
    assert f"{NAME} did not say ok on /health in 900 s" in failure, failure
    assert "exit code 0, OOMKilled false" in failure, failure
    assert doc["exit"]["state"] == state
    assert doc["exit"]["kernel_log"] == KERNEL
    _filed_before_removal(calls)


def test_a_failure_after_health_while_the_container_exists_files_its_exit_cause(
    tmp_path: Path,
) -> None:
    state = _state(0, False, running=True)
    done, doc, calls = _unit_step(
        tmp_path, state=state, running=True, healthy=True, end_fails=True
    )
    assert done.returncode == 1, (done.stdout, done.stderr[-2000:])
    assert doc["wake_s"] is not None
    failure = doc["failure"]
    assert failure.startswith("alpha could not be read for the END marker"), failure
    assert "exit code 0, OOMKilled false" in failure, failure
    assert doc["exit"]["state"] == state
    _filed_before_removal(calls)


def test_a_kernel_log_that_cannot_be_read_is_filed_as_data_and_is_no_stop(
    tmp_path: Path,
) -> None:
    state = _state(1, False)
    done, doc, calls = _unit_step(
        tmp_path, state=state, kernel=("", f"{UNREADABLE}\n", 1)
    )
    assert done.returncode == 1, (done.stdout, done.stderr[-2000:])
    cause = doc["exit"]
    assert cause["state"] == state and cause["kernel_log"] is None
    error = cause["kernel_log_error"]
    assert "exited 1" in error and UNREADABLE in error, error
    failure = doc["failure"]
    assert f"{NAME} exited before /health said ok: " in failure, failure
    assert "exit code 1, OOMKilled false" in failure, failure
    assert doc["container_id"] == "c0ffee0000aa"
    _filed_before_removal(calls)


def test_a_step_refused_before_its_container_starts_files_no_exit_cause(
    tmp_path: Path,
) -> None:
    done, doc, calls = _unit_step(tmp_path, unit="no_such_unit")
    assert done.returncode == 2, (done.stdout, done.stderr[-2000:])
    assert doc["exit"] is None
    assert not [c for c in calls if "journalctl" in c or "{{json .State}}" in c]


# --------------------------------------------------------------------------
# one diagnostic start per failed retry
# --------------------------------------------------------------------------


def _failed(payload: dict[str, Any]) -> None:
    """A campaign run that failed: its step said so and measured nothing."""
    doc = payload["doc"]
    doc["failure"] = "the unit exited before /health said ok"
    if "harness" in doc:
        doc["harness"] = {"error": "the unit never served"}
    if "stamps" in doc:
        doc["stamps"]["t2"] = {}


def _window_to(
    tmp_path: Path, last: str, change: dict[str, Change] | None = None
) -> Window:
    """A frozen window written, entry by entry, up to and including ``last``."""
    window = frozen_window(tmp_path)
    for entry in window.runs.entries:
        window.write(entry, (change or {}).get(entry.id))
        if entry.id == last:
            break
    return window


def _failed_retry(tmp_path: Path) -> Window:
    """alpha-02 failed, and so did its one retry, both logged."""
    window = _window_to(tmp_path, "alpha-02", {"alpha-02": _failed})
    window.retry("alpha-02", _failed)
    return window


def test_a_diagnostic_start_is_a_wrapper_and_artifact_of_its_own_after_the_retry(
    tmp_path: Path,
) -> None:
    window = _failed_retry(tmp_path)
    plan = plan_module()
    made = plan.diagnose(
        window.root, USE, "alpha-02-retry1", REASON, journal=str(window.journal)
    )
    step = f"{STEPS}/02-{USE}-alpha-c1-a_pair-diag1.sh"
    artifact = f"{USE}-alpha-c1-a_pair-diag1.json"
    assert made == {
        "entry": "alpha-02-retry1",
        "reason": REASON,
        "diagnostic_entry": "alpha-02-diag1",
        "artifact": artifact,
        "step": step,
    }
    listed = window.root / "records/measurements/lock-fleets" / USE / "retries.json"
    doc = json.loads(listed.read_text("utf-8"))
    assert doc["diagnostics"] == [made] and len(doc["retries"]) == 1
    ruling = doc["diagnostic_ruling"]
    assert (ruling["by"], ruling["on"], ruling["said"]) == (
        "owner",
        "2026-09-15",
        "Fix PR, then one diagnostic start",
    )
    wrapper = window.root / step
    text = wrapper.read_text("utf-8")
    assert os.access(wrapper, os.X_OK)
    assert re.findall(r"^# RUN_ARTIFACTS: (.*)$", text, re.M) == [artifact]
    assert f'/../_unit.sh" {artifact} a_pair "$@"' in text

    runs = plan.read_runs(window.root, USE)
    alpha = [e.id for e in runs.entries if e.rig == "alpha"]
    assert alpha[:5] == [
        "alpha-01",
        "alpha-02",
        "alpha-02-retry1",
        "alpha-02-diag1",
        "alpha-03",
    ]
    base, retry = runs.entry("alpha-02"), runs.entry("alpha-02-retry1")
    diagnostic = runs.entry("alpha-02-diag1")
    assert (diagnostic.kind, diagnostic.fleet, diagnostic.units, diagnostic.run) == (
        "unit",
        "two",
        ("a_pair",),
        "c1",
    )
    assert (diagnostic.diagnostic_of, diagnostic.retry_of, diagnostic.rerun_of) == (
        "alpha-02-retry1",
        "",
        "",
    )
    assert (diagnostic.artifact, diagnostic.wrapper, diagnostic.rig) == (
        artifact,
        step,
        "alpha",
    )
    assert [a for a in diagnostic.argv if a != step] == [
        a for a in base.argv if a != base.wrapper
    ]
    assert [a for a in diagnostic.argv if a != step] == [
        a for a in retry.argv if a != retry.wrapper
    ]
    assert diagnostic.run_id(WINDOW_DATE) == (
        f"{WINDOW_DATE}-lock-fleets-{USE}-alpha-c1-a_pair-diag1"
    )
    assert runs.diagnostic_for("alpha-02-retry1") == diagnostic
    assert runs.diagnostic_for("alpha-02") is None


REFUSALS = [
    ("unlogged", "alpha-02-retry1", "alpha-02-retry1 has no log row"),
    ("passed", "alpha-02-retry1", "alpha-02-retry1 passes its check"),
    ("failed", "alpha-02", "alpha-02 is not a retry"),
    (
        "diagnosed",
        "alpha-02-retry1",
        "alpha-02-retry1 already has a diagnostic start, alpha-02-diag1",
    ),
    ("diagnosed", "alpha-02-diag1", "alpha-02-diag1 is itself a diagnostic start"),
    ("move", "alpha-07-retry1", "only a failed retry of a unit entry"),
]


@pytest.mark.parametrize(
    ("retry", "entry", "said"),
    REFUSALS,
    ids=["unlogged", "passed", "not-a-retry", "diagnosed", "a-diagnostic", "a-move"],
)
def test_diagnose_refuses_an_entry_the_ruling_does_not_diagnose(
    tmp_path: Path, retry: str, entry: str, said: str
) -> None:
    if retry == "move":
        window = _window_to(tmp_path, "alpha-07", {"alpha-07": _failed})
        window.retry("alpha-07", _failed)
    else:
        window = _window_to(tmp_path, "alpha-02", {"alpha-02": _failed})
        change = None if retry == "passed" else _failed
        window.retry("alpha-02", change, log=retry != "unlogged")
    if retry == "diagnosed":
        window.diagnose("alpha-02-retry1", _failed)
    plan = plan_module()
    with pytest.raises(plan.PlanRefusedError, match=re.escape(said)):
        plan.diagnose(window.root, USE, entry, REASON, journal=str(window.journal))


def test_a_diagnostic_start_gets_no_retry_rerun_or_second_one_and_stops_on_failure(
    tmp_path: Path,
) -> None:
    window = _failed_retry(tmp_path)
    window.diagnose("alpha-02-retry1", _failed)
    asm = assemble_module()
    ctx = context(window)
    assert asm.check(ctx, "alpha", "alpha-02-retry1") == []
    reasons = asm.check(ctx, "alpha", "alpha-02-diag1")
    assert any("the step failed" in why for why in reasons), reasons
    plan = plan_module()
    for give in (plan.retry, plan.rerun, plan.diagnose):
        with pytest.raises(
            plan.PlanRefusedError, match="alpha-02-diag1 is itself a diagnostic start"
        ):
            give(
                window.root, USE, "alpha-02-diag1", REASON, journal=str(window.journal)
            )


def test_diagnose_reads_a_log_kept_in_another_tree_and_writes_the_same_bytes(
    tmp_path: Path,
) -> None:
    window = _failed_retry(tmp_path / "window")
    plan = plan_module()
    checkout = make_tree(tmp_path / "checkout")
    plan.freeze(checkout, USE)
    listed = f"records/measurements/lock-fleets/{USE}/retries.json"
    for rel in (listed, f"{STEPS}/02-{USE}-alpha-c1-a_pair-retry1.sh"):
        shutil.copy2(window.root / rel, checkout / rel)
    diagnose = ["diagnose", "--use", USE, "--entry", "alpha-02-retry1"]
    diagnose += ["--reason", REASON, "--journal", str(window.journal)]
    elsewhere = ["--log-from", str(window.root)]
    assert plan.main(["--root", str(checkout), *diagnose, *elsewhere]) == 0
    assert plan.main(["--root", str(window.root), *diagnose]) == 0
    assert plan.read_runs(checkout, USE).log == []
    for rel in (listed, f"{STEPS}/02-{USE}-alpha-c1-a_pair-diag1.sh"):
        assert (checkout / rel).read_bytes() == (window.root / rel).read_bytes(), rel


def _said(module: Any, argv: list[str], capsys: pytest.CaptureFixture[str]) -> Any:
    code = module.main(argv)
    return code, capsys.readouterr().out


def test_the_recheck_passes_a_diagnosed_retry_and_its_diagnostic_runs_next(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """What drive.sh asks before a start, through the commands it runs: every
    logged entry of the rig is checked again, and the first unlogged one runs."""
    window = _failed_retry(tmp_path)
    plan, asm = plan_module(), assemble_module()
    root = ["--root", str(window.root)]
    journal = ["--journal", str(window.journal)]

    def order() -> list[str]:
        _, listed = _said(
            plan, [*root, "entries", "--use", USE, "--rig", "alpha"], capsys
        )
        return [line.split("\t")[0] for line in listed.splitlines()]

    def logged(entry: str) -> bool:
        return bool(plan.main([*root, "logged", "--use", USE, "--entry", entry]) == 0)

    def recheck() -> list[tuple[str, int, str]]:
        return [
            (entry, *_said(asm, [*root, "check", "--use", USE, "--host", "alpha",
                                 "--entry", entry, *journal], capsys))
            for entry in order()
            if logged(entry)
        ]  # fmt: skip

    before = recheck()
    assert [(e, code) for e, code, _ in before] == [
        ("alpha-01", 0),
        ("alpha-02", 0),
        ("alpha-02-retry1", 1),
    ]
    diagnose = ["diagnose", "--use", USE, "--entry", "alpha-02-retry1"]
    assert plan.main([*root, *diagnose, "--reason", REASON, *journal]) == 0
    capsys.readouterr()
    after = recheck()
    assert [(e, code) for e, code, _ in after] == [
        ("alpha-01", 0),
        ("alpha-02", 0),
        ("alpha-02-retry1", 0),
    ]
    assert "alpha-02-retry1 failed, diagnosed by alpha-02-diag1" in after[2][2]
    assert next(e for e in order() if not logged(e)) == "alpha-02-diag1"
    _, argv = _said(
        plan, [*root, "argv", "--use", USE, "--entry", "alpha-02-diag1"], capsys
    )
    assert f"{STEPS}/02-{USE}-alpha-c1-a_pair-diag1.sh" in argv.split("\0")


# --------------------------------------------------------------------------
# assembly
# --------------------------------------------------------------------------


def test_a_passing_diagnostic_stands_in_for_the_failed_entry_as_a_passing_retry(
    tmp_path: Path,
) -> None:
    retried = frozen_window(tmp_path / "retried")
    retried.write_all({"alpha-02": _failed})
    retried.retry("alpha-02")
    diagnosed = frozen_window(tmp_path / "diagnosed")
    diagnosed.write_all({"alpha-02": _failed})
    diagnosed.retry("alpha-02", _failed)
    made = diagnosed.diagnose("alpha-02-retry1")
    asm = assemble_module()
    want, _, _ = asm.assemble(context(retried))
    evidence, runs, _ = asm.assemble(context(diagnosed))
    assert evidence == want
    kept = runs["runs"]
    assert set(kept) == {e.id for e in diagnosed.runs.entries}
    assert kept["alpha-02"]["retried_by"] == "alpha-02-retry1"
    assert kept["alpha-02-retry1"]["diagnosed_by"] == made["diagnostic_entry"]
    assert any("the step failed" in why for why in kept["alpha-02-retry1"]["check"])
    assert kept["alpha-02-diag1"]["diagnostic_of"] == "alpha-02-retry1"


@pytest.mark.parametrize(
    ("diagnostic", "said"),
    [
        ("failed", "alpha-02-diag1 fails its check: the step failed"),
        ("unlogged", "a frozen entry is missing: alpha-02-diag1 has no log row"),
    ],
)
def test_assembly_refuses_a_diagnosed_retry_whose_diagnostic_did_not_pass(
    tmp_path: Path, diagnostic: str, said: str
) -> None:
    window = frozen_window(tmp_path)
    window.write_all({"alpha-02": _failed})
    window.retry("alpha-02", _failed)
    change = _failed if diagnostic == "failed" else None
    window.diagnose("alpha-02-retry1", change, log=diagnostic != "unlogged")
    asm = assemble_module()
    with pytest.raises(asm.AssemblyRefusedError, match=re.escape(said)):
        asm.assemble(context(window))


def test_srv2_01_retry1_of_rig_id_relock_has_its_one_diagnostic_start_committed() -> (
    None
):
    plan = plan_module()
    runs = plan.read_runs(REPO, "rig-id-relock")
    srv1 = [e.id for e in runs.entries if e.rig == "srv1"]
    srv2 = [e.id for e in runs.entries if e.rig == "srv2"]
    assert (len(srv1), len(srv2)) == (16, 30)
    assert srv2[:5] == [
        "srv2-01",
        "srv2-01-retry1",
        "srv2-01-diag1",
        "srv2-01-relaunch1",
        "srv2-02",
    ]
    retry = runs.entry("srv2-01-retry1")
    derived, text = plan.derive_diagnostic("rig-id-relock", retry)
    assert derived == {
        "diagnostic_entry": "srv2-01-diag1",
        "artifact": "rig-id-relock-srv2-c1-srv2_35b_256k-diag1.json",
        "step": "tools/runs/campaigns/lock-fleets/rig-id-relock/"
        "16-rig-id-relock-srv2-c1-srv2_35b_256k-diag1.sh",
    }
    listed = REPO / "records/measurements/lock-fleets/rig-id-relock/retries.json"
    doc = json.loads(listed.read_text("utf-8"))
    assert doc["diagnostics"] == [
        {"entry": "srv2-01-retry1", "reason": SRV2_DIAG_REASON, **derived}
    ]
    ruling = doc["diagnostic_ruling"]
    assert (ruling["by"], ruling["on"], ruling["said"]) == (
        "owner",
        "2026-09-15",
        "Fix PR, then one diagnostic start",
    )
    assert (REPO / derived["step"]).read_text("utf-8") == text
    assert os.access(REPO / derived["step"], os.X_OK)
    diagnostic = runs.entry("srv2-01-diag1")
    assert diagnostic.diagnostic_of == "srv2-01-retry1"
    assert [a for a in diagnostic.argv if a != derived["step"]] == [
        a for a in retry.argv if a != retry.wrapper
    ]
