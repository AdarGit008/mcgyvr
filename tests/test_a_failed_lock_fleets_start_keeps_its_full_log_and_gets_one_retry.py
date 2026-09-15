"""A failed lock-fleets start keeps its container's full log, and gets one retry.

Owner ruling, 2026-09-15: "Fix PR, then retry srv2". ``rig-id-relock``'s srv2-01
started its unit, which died while loading before ``/health`` said ok;
``_unit.sh`` filed eight tail lines of ``docker logs`` and removed the container,
so the error line was lost. The driver stopped and could not go on: a logged
entry is never run again, and a failed one stops every re-check.

* A container a step started that exited, or never said healthy, has its whole
  ``docker logs`` (stdout and stderr, every line, through the door's shim) filed
  in the envelope as ``<artifact stem>.<unit>.docker.log`` before anything
  removes it, and the artifact's ``failure`` names that file.
* A logged failed entry gets ONE retry, ``plan.py retry``: its own wrapper and
  artifact, listed in ``<use>/retries.json`` and placed right after it in its
  rig's order. The failed run is kept as a data point and the retry counts in
  its place. A failed retry stops, and gets no second one.

No rig is reached: the steps run under a stand-in door against stubs.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
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
    fleet_doc,
    frozen_window,
    make_tree,
    plan_module,
    snapshot,
)

CAMPAIGN = REPO / "tools" / "runs" / "campaigns" / "lock-fleets"
STEPS = f"tools/runs/campaigns/lock-fleets/{USE}"
REASON = "the unit died before /health said ok"
SRV2_01_REASON = (
    "container died before /health (14:41:45Z); full log not kept; "
    "owner 2026-09-15: fix PR, then retry"
)
#: What the stub container printed, in order: its stdout, with one stderr line
#: in the middle that an eight-line tail never shows.
CAUSE = "llama_model_load: error loading model: out of memory"
OUT_LINES = [f"load step {n}" for n in range(1, 41)]
WHOLE_LOG = [*OUT_LINES[:20], CAUSE, *OUT_LINES[20:]]

Change = Callable[[dict[str, Any]], None]

#: The door's docker shim, as the step finds it under RUN_BIN: every call is
#: logged, the image resolves to the digest the fixture's digests file records,
#: and the container it starts is never running.
DOCKER = """\
#!/usr/bin/env bash
set -u
RIG=$(cd "$(dirname "$0")/.." && pwd)
printf 'docker: %s\\n' "$*" >> "$RIG/calls.log"
case ${1:-} in
  image) printf '[{"Id": "@IMAGE@", "RepoDigests": []}]\\n' ;;
  run) echo c0ffee0000aa ;;
  inspect) echo false ;;
  logs)
    case " $* " in
      *" --tail "*) tail -n 8 "$RIG/stdout.txt" ;;
      *)
        head -n 20 "$RIG/stdout.txt"
        echo "@CAUSE@" >&2
        tail -n +21 "$RIG/stdout.txt" ;;
    esac ;;
esac
exit 0
"""

#: The door's ssh shim: the rig's reading, its vmstat, and the move's shells —
#: the source's exit and the stopwatch's are the test's.
SSH = """\
#!/usr/bin/env bash
set -u
RIG=$(cd "$(dirname "$0")/.." && pwd)
shift
cmd="$*"
printf 'ssh: %s\\n' "$(printf '%s' "$cmd" | tr '\\n' ' ')" >> "$RIG/calls.log"
case $cmd in
  "bash -s") cat >/dev/null; cat "$RIG/snapshot.txt" ;;
  *"cat >>"*) cat >/dev/null ;;
  *vmstat*) printf 'pswpout 10\\npgmajfault 5\\n' ;;
  *"st t0"*) cat "$RIG/timed.out"; exit "$(cat "$RIG/timed.exit")" ;;
  *"docker run -d"*) exit "$(cat "$RIG/source.exit")" ;;
esac
exit 0
"""


def _step(
    tmp_path: Path,
    argv: list[str],
    run_id: str,
    *,
    source_exit: int = 0,
    timed_exit: int = 0,
) -> tuple[subprocess.CompletedProcess[str], Path, list[str]]:
    """One lock-fleets step body under a stand-in door, on the fixture fleet's
    rig ``alpha``, with the door's shims standing in for a rig."""
    root = make_tree(tmp_path / "tree")
    shutil.copy(REPO / "tools" / "runs" / "_common.sh", root / "tools" / "runs")
    rig = tmp_path / "rig"
    docker = DOCKER.replace("@IMAGE@", LLAMA_IMAGE_ID).replace("@CAUSE@", CAUSE)
    onedoor.executable(rig / "bin" / "docker", docker)
    onedoor.executable(rig / "bin" / "ssh", SSH)
    for name in ("rig-snapshot.sh", "rig-units.sh"):
        (rig / name).write_text("# the stub rig answers for it\n", "utf-8")
    reading = "".join(f"{k}={v}\n" for k, v in snapshot("alpha").items())
    (rig / "snapshot.txt").write_text(reading, "utf-8")
    (rig / "stdout.txt").write_text("".join(f"{x}\n" for x in OUT_LINES), "utf-8")
    (rig / "source.exit").write_text(f"{source_exit}\n", "utf-8")
    (rig / "timed.exit").write_text(f"{timed_exit}\n", "utf-8")
    (rig / "timed.out").write_text(
        "t0 100.0\nrc_stop 0\nrc_drop 0\nrc_run 0\nt1 101.0\ntimeout a_pair\n",
        "utf-8",
    )
    path = tmp_path / "path"
    onedoor.executable(path / "curl", "#!/usr/bin/env bash\nexit 7\n")
    onedoor.executable(path / "sleep", "#!/usr/bin/env bash\nexit 0\n")
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
        RUN_ID=run_id,
        RUN_OUT_DIR=str(envelope),
        RUN_ROUND="r-fixture",
        RUN_PRODUCT_SHA256="0" * 64,
        RUN_MODEL="/models/a_pair.gguf",
        RUN_PARALLEL="2",
        RUN_CTX_PER_SLOT="4096",
        RUN_UBATCH="512",
    )
    done = subprocess.run(
        [sys.executable, str(onedoor.fake_door(tmp_path)), "bash", *argv],
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
    return done, envelope, calls


def test_a_unit_that_exited_before_health_files_its_whole_log_before_removal(
    tmp_path: Path,
) -> None:
    run_id = f"{WINDOW_DATE}-lock-fleets-{USE}-alpha-c1-a_pair"
    name = f"{run_id}-a_pair"
    done, envelope, calls = _step(
        tmp_path, [str(CAMPAIGN / "_unit.sh"), "u.json", "a_pair"], run_id
    )
    assert done.returncode == 1, (done.stdout, done.stderr[-2000:])
    kept = envelope / "u.a_pair.docker.log"
    assert kept.is_file(), sorted(p.name for p in envelope.iterdir())
    assert kept.read_text("utf-8").splitlines() == WHOLE_LOG
    failure = json.loads((envelope / "u.json").read_text("utf-8"))["failure"]
    assert f"{name} exited before /health said ok: " in failure, failure
    assert OUT_LINES[-1] in failure and kept.name in failure, failure
    whole = calls.index(f"docker: logs {name}")
    assert f"docker: rm -f {name}" in calls[whole:], calls


@pytest.mark.parametrize(("side", "unit"), [("source", "a_solo"), ("target", "a_pair")])
def test_a_move_whose_container_never_said_healthy_files_its_whole_log_first(
    tmp_path: Path, side: str, unit: str
) -> None:
    run_id = f"{WINDOW_DATE}-lock-fleets-{USE}-alpha-r1-one-to-two"
    name = f"{run_id}-{unit}"
    done, envelope, calls = _step(
        tmp_path,
        [str(CAMPAIGN / "_move.sh"), "m.json", "alpha", "one", "two"],
        run_id,
        source_exit=int(side == "source"),
        timed_exit=int(side == "target"),
    )
    kept = envelope / f"m.{unit}.docker.log"
    assert kept.is_file(), (sorted(p.name for p in envelope.iterdir()), done.stderr)
    assert kept.read_text("utf-8").splitlines() == WHOLE_LOG
    failure = json.loads((envelope / "m.json").read_text("utf-8"))["failure"]
    assert failure and kept.name in failure, failure
    starter = "st t0" if side == "target" else "docker run -d"
    started = next(
        i for i, c in enumerate(calls) if c.startswith("ssh: ") and starter in c
    )
    removed = [i for i, c in enumerate(calls) if i > started and "rm -f" in c]
    assert removed, calls
    assert started < calls.index(f"docker: logs {name}") < removed[0], calls


# --------------------------------------------------------------------------
# one retry per failed entry
# --------------------------------------------------------------------------


def _failed(payload: dict[str, Any]) -> None:
    """A campaign run that failed: its step said so and measured nothing."""
    doc = payload["doc"]
    doc["failure"] = "the unit exited before /health said ok"
    if "harness" in doc:
        doc["harness"] = {"error": "the unit never served"}
    if "stamps" in doc:
        doc["stamps"]["t2"] = {}


def _serve_up_failed(payload: dict[str, Any]) -> None:
    payload["step"]["compose_up_exit"] = 1


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


def test_a_retry_is_a_wrapper_and_artifact_of_its_own_right_after_its_entry(
    tmp_path: Path,
) -> None:
    window = _window_to(tmp_path, "alpha-02", {"alpha-02": _failed})
    plan = plan_module()
    made = plan.retry(window.root, USE, "alpha-02", REASON, journal=str(window.journal))
    step = f"{STEPS}/02-{USE}-alpha-c1-a_pair-retry1.sh"
    artifact = f"{USE}-alpha-c1-a_pair-retry1.json"
    assert made == {
        "entry": "alpha-02",
        "reason": REASON,
        "retry_entry": "alpha-02-retry1",
        "artifact": artifact,
        "step": step,
    }
    listed = window.root / "records/measurements/lock-fleets" / USE / "retries.json"
    doc = json.loads(listed.read_text("utf-8"))
    assert doc["use"] == USE and doc["retries"] == [made]
    assert "2026-09-15" in json.dumps(doc["ruling"])
    wrapper = window.root / step
    text = wrapper.read_text("utf-8")
    assert os.access(wrapper, os.X_OK)
    assert re.findall(r"^# RUN_ARTIFACTS: (.*)$", text, re.M) == [artifact]
    assert f'/../_unit.sh" {artifact} a_pair "$@"' in text

    runs = plan.read_runs(window.root, USE)
    alpha = [e.id for e in runs.entries if e.rig == "alpha"]
    assert alpha[:4] == ["alpha-01", "alpha-02", "alpha-02-retry1", "alpha-03"]
    failed, retry = runs.entry("alpha-02"), runs.entry("alpha-02-retry1")
    assert (retry.kind, retry.fleet, retry.units, retry.run) == (
        "unit",
        "two",
        ("a_pair",),
        "c1",
    )
    assert (retry.artifact, retry.wrapper, retry.retry_of) == (
        artifact,
        step,
        "alpha-02",
    )
    assert [a for a in retry.argv if a != step] == [
        a for a in failed.argv if a != failed.wrapper
    ]
    assert retry.run_id(WINDOW_DATE) == (
        f"{WINDOW_DATE}-lock-fleets-{USE}-alpha-c1-a_pair-retry1"
    )
    assert runs.retry_for("alpha-02") == retry
    assert runs.retry_for("alpha-01") is None


REFUSALS = [
    ("alpha-02", "alpha-03", False, "alpha-03 has no log row"),
    ("alpha-02", "alpha-01", False, "alpha-01 passes its check"),
    ("alpha-02", "alpha-02", True, "alpha-02 already has a retry, alpha-02-retry1"),
    ("alpha-02", "alpha-02-retry1", True, "alpha-02-retry1 is itself a retry"),
    ("beta-02", "beta-02", False, "only a campaign unit or move run"),
]


@pytest.mark.parametrize(
    ("last", "entry", "retried", "said"),
    REFUSALS,
    ids=["unlogged", "passed", "retried", "a-retry", "serve-up"],
)
def test_retry_refuses_an_entry_the_ruling_does_not_retry(
    tmp_path: Path, last: str, entry: str, retried: bool, said: str
) -> None:
    window = _window_to(
        tmp_path, last, {"alpha-02": _failed, "beta-02": _serve_up_failed}
    )
    if retried:
        window.retry("alpha-02", _failed)
    plan = plan_module()
    with pytest.raises(plan.PlanRefusedError, match=re.escape(said)):
        plan.retry(window.root, USE, entry, REASON, journal=str(window.journal))


def test_retry_reads_a_log_kept_in_another_tree_and_writes_the_same_bytes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    window = _window_to(tmp_path / "window", "alpha-02", {"alpha-02": _failed})
    plan = plan_module()
    checkout = make_tree(tmp_path / "checkout")
    plan.freeze(checkout, USE)
    retry = ["retry", "--use", USE, "--entry", "alpha-02", "--reason", REASON]
    retry += ["--journal", str(window.journal)]
    elsewhere = ["--log-from", str(window.root)]
    assert plan.main(["--root", str(checkout), *retry, *elsewhere]) == 0
    assert plan.main(["--root", str(window.root), *retry]) == 0
    assert plan.read_runs(checkout, USE).log == []
    for rel in (
        f"records/measurements/lock-fleets/{USE}/retries.json",
        f"{STEPS}/02-{USE}-alpha-c1-a_pair-retry1.sh",
    ):
        assert (checkout / rel).read_bytes() == (window.root / rel).read_bytes(), rel

    fleet = fleet_doc()
    fleet["fleets"]["one"]["next"] = []
    other = make_tree(tmp_path / "other", fleet=fleet)
    plan.freeze(other, USE)
    capsys.readouterr()
    assert plan.main(["--root", str(other), *retry, *elsewhere]) == 2
    assert "another frozen order" in capsys.readouterr().err


def _said(module: Any, argv: list[str], capsys: pytest.CaptureFixture[str]) -> Any:
    code = module.main(argv)
    return code, capsys.readouterr().out


def test_a_failed_entry_stops_the_recheck_until_retried_and_its_retry_runs_next(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """What drive.sh asks before a start, through the commands it runs: every
    logged entry of the rig is checked again, and the first unlogged one runs."""
    window = _window_to(tmp_path, "alpha-02", {"alpha-02": _failed})
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
    assert [(e, code) for e, code, _ in before] == [("alpha-01", 0), ("alpha-02", 1)]
    assert "the step failed" in before[1][2]

    retry = ["retry", "--use", USE, "--entry", "alpha-02", "--reason", REASON]
    assert plan.main([*root, *retry, *journal]) == 0
    capsys.readouterr()
    after = recheck()
    assert [(e, code) for e, code, _ in after] == [("alpha-01", 0), ("alpha-02", 0)]
    assert "alpha-02 failed, retried by alpha-02-retry1" in after[1][2]
    assert next(e for e in order() if not logged(e)) == "alpha-02-retry1"
    _, argv = _said(
        plan, [*root, "argv", "--use", USE, "--entry", "alpha-02-retry1"], capsys
    )
    assert f"{STEPS}/02-{USE}-alpha-c1-a_pair-retry1.sh" in argv.split("\0")


def test_a_failed_retry_stops_and_gets_no_second_retry(tmp_path: Path) -> None:
    window = _window_to(tmp_path, "alpha-02", {"alpha-02": _failed})
    window.retry("alpha-02", _failed)
    asm = assemble_module()
    ctx = context(window)
    assert asm.check(ctx, "alpha", "alpha-02") == []
    reasons = asm.check(ctx, "alpha", "alpha-02-retry1")
    assert any("the step failed" in why for why in reasons), reasons
    plan = plan_module()
    with pytest.raises(plan.PlanRefusedError, match="is itself a retry"):
        plan.retry(
            window.root, USE, "alpha-02-retry1", REASON, journal=str(window.journal)
        )


# --------------------------------------------------------------------------
# assembly
# --------------------------------------------------------------------------


@pytest.mark.parametrize("failed", ["alpha-02", "alpha-07"], ids=["unit", "move"])
def test_assembly_counts_a_retry_in_place_of_its_failed_entry_and_keeps_both(
    tmp_path: Path, failed: str
) -> None:
    window = frozen_window(tmp_path)
    window.write_all({failed: _failed})
    made = window.retry(failed)
    evidence, runs, _ = assemble_module().assemble(context(window))
    kept = runs["runs"]
    assert set(kept) == {e.id for e in window.runs.entries}
    assert made["retry_entry"] in kept
    assert kept[failed]["retried_by"] == made["retry_entry"]
    assert any("the step failed" in why for why in kept[failed]["check"])
    assert kept[made["retry_entry"]]["retry_of"] == failed
    pair = next(c for c in evidence["combinations"] if c["slots"][0][0] == "a_pair")
    assert pair["card_peak_mib"] == {"a_pair": 4200}
    assert len(evidence["moves"]) == 4


def test_assembly_with_a_retry_still_refuses_fewer_valid_runs_than_k(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    window = frozen_window(tmp_path)
    window.write_all({"alpha-01": _failed})
    window.retry("alpha-01")
    monkeypatch.setattr(plan_module(), "K", 4)
    asm = assemble_module()
    with pytest.raises(
        asm.AssemblyRefusedError,
        match="one on alpha has 3 valid runs, and the lock needs 4",
    ):
        asm.assemble(context(window))


@pytest.mark.parametrize(
    ("retry", "said"),
    [
        ("none", "alpha-02 fails its check: the step failed"),
        ("failed", "alpha-02-retry1 fails its check: the step failed"),
        ("unlogged", "a frozen entry is missing: alpha-02-retry1 has no log row"),
    ],
)
def test_assembly_refuses_a_failed_entry_without_a_retry_that_passed(
    tmp_path: Path, retry: str, said: str
) -> None:
    window = frozen_window(tmp_path)
    window.write_all({"alpha-02": _failed})
    if retry != "none":
        change = _failed if retry == "failed" else None
        window.retry("alpha-02", change, log=retry != "unlogged")
    asm = assemble_module()
    with pytest.raises(asm.AssemblyRefusedError, match=re.escape(said)):
        asm.assemble(context(window))


def test_srv2_01_of_rig_id_relock_has_its_one_retry_committed() -> None:
    plan = plan_module()
    runs = plan.read_runs(REPO, "rig-id-relock")
    srv2 = [e.id for e in runs.entries if e.rig == "srv2"]
    assert srv2[:2] == ["srv2-01", "srv2-01-retry1"]
    derived, text = plan.derive_retry("rig-id-relock", runs.entry("srv2-01"))
    assert derived == {
        "retry_entry": "srv2-01-retry1",
        "artifact": "rig-id-relock-srv2-c1-srv2_35b_256k-retry1.json",
        "step": "tools/runs/campaigns/lock-fleets/rig-id-relock/"
        "16-rig-id-relock-srv2-c1-srv2_35b_256k-retry1.sh",
    }
    listed = REPO / "records/measurements/lock-fleets/rig-id-relock/retries.json"
    doc = json.loads(listed.read_text("utf-8"))
    assert doc["retries"] == [{"entry": "srv2-01", "reason": SRV2_01_REASON, **derived}]
    assert (REPO / derived["step"]).read_text("utf-8") == text
    assert os.access(REPO / derived["step"], os.X_OK)
