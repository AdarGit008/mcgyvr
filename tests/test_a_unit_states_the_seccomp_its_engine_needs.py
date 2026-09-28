"""A unit states the seccomp profile its engine needs, and both launch paths apply it.

Owner ruling: allow io_uring. The Lidenburg llama.cpp fork's MoE expert cache
calls ``abort()`` when ``io_uring_queue_init`` fails
(``ggml/src/ggml-backend.cpp``) — there is no fallback and no env var disables
the tier — and docker's default seccomp profile blocks the io_uring syscalls,
so under a plain ``docker run`` the call returns EPERM and a unit on that image
(``srv2_35b_256k``) dies at start with exit 139
(``records/evidence/2026-09-15-lock-fleets/``
``rig-id-relock-srv2-c1-srv2_35b_256k-diag1.json``).

* A unit's ``launch`` may state ``seccomp:``, a profile file beside the fleet
  file. The stated profile is docker's default plus only the io_uring
  syscalls — never ``unconfined``, never ``--privileged``.
* Both launch paths apply it: lock-fleets' ``_unit.sh`` (``run_args``) and the
  product's live path (``mcgyvr emit``, which renders ``security_opt`` and
  writes the profile beside the compose file it names).
* A unit that states none launches with no profile of its own, and a stated
  profile that is not there is refused by name before any rig is touched.
* A unit whose LAUNCH changed gets ONE fresh cold start, ``plan.py relaunch``,
  after its failed diagnostic start.

No rig is reached: every profile here is a file in a throw-away tree.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from mcgyvr.emit import LockedLaunchError, emit_locked
from tests.lockfleets_window import (
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
    steps_module,
)

STEPS = f"tools/runs/campaigns/lock-fleets/{USE}"
REASON = "the launch now states the seccomp its engine needs"

#: Where a unit's profile sits, as its ``launch.seccomp`` spells it: a path
#: relative to the directory holding fleet.yaml.
PROFILE = "seccomp/io-uring.json"
#: The committed profile of the fleet this repo locks.
COMMITTED = REPO / "fleet-setup" / PROFILE

#: The three syscalls docker's default profile blocks and this one allows.
IO_URING = ["io_uring_enter", "io_uring_register", "io_uring_setup"]

#: sha256 of the profile with its last syscalls block dropped, canonically
#: dumped — i.e. of docker's default profile as the file vendored it. Moby's
#: ``profiles/seccomp/default.json`` at ``moby/profiles``
#: ``3c28324314729dbade8287e868eef6338c42807a``; the raw bytes hash
#: ``536529b665dd0972c37bfb569f5d4ac8a53592e7b00752bc39ff063ca9864c74``.
BASE_DIGEST = "9da637d2ab0a204fcbd91bd88f1be9e004a3acab61c571a9f5b8870e588a17d2"

#: The owner's words on the fresh start.
SAID = "Fix PR: allow io_uring"
SRV2_RELAUNCH_REASON = (
    "the launch states the seccomp its engine needs (docker's default plus the "
    "io_uring syscalls); owner 2026-09-16: fix PR, allow io_uring"
)


def base_digest(doc: dict[str, Any]) -> str:
    """``doc`` with its last syscalls block dropped, canonically dumped."""
    rest = dict(doc)
    rest["syscalls"] = doc["syscalls"][:-1]
    return hashlib.sha256(
        json.dumps(rest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


# --------------------------------------------------------------------------
# the profile itself
# --------------------------------------------------------------------------


def test_the_profile_allows_io_uring_and_otherwise_is_dockers_default() -> None:
    doc = json.loads(COMMITTED.read_text(encoding="utf-8"))
    # Not a hole: everything the default refuses, this refuses.
    assert doc["defaultAction"] == "SCMP_ACT_ERRNO"
    added = doc["syscalls"][-1]
    assert sorted(added["names"]) == IO_URING
    assert added["action"] == "SCMP_ACT_ALLOW"
    # Every other block is docker's default, byte for byte once canonicalised.
    assert base_digest(doc) == BASE_DIGEST
    # The base blocked them, so the last block is the whole of the difference.
    earlier = [n for b in doc["syscalls"][:-1] for n in (b.get("names") or [])]
    assert not [n for n in earlier if "io_uring" in n]


def test_the_profile_says_where_it_came_from_and_what_was_added() -> None:
    readme = (COMMITTED.parent / "README.md").read_text(encoding="utf-8")
    assert "moby/profiles" in readme
    assert "3c28324314729dbade8287e868eef6338c42807a" in readme
    assert "891241e7e7" in readme
    for name in IO_URING:
        assert name in readme


def test_the_unit_that_cannot_start_states_the_profile_and_no_other_does() -> None:
    fleet = yaml.safe_load((REPO / "fleet-setup" / "fleet.yaml").read_text("utf-8"))
    stated = {
        name: (unit.get("launch") or {}).get("seccomp")
        for name, unit in fleet["units"].items()
        if (unit.get("launch") or {}).get("seccomp")
    }
    assert stated == {"srv2_35b_256k": PROFILE}
    # Never a hole, and never the whole machine.
    assert "unconfined" not in json.dumps(fleet)
    assert "privileged" not in json.dumps(fleet)


# --------------------------------------------------------------------------
# the fixture fleet
# --------------------------------------------------------------------------


def _doc() -> dict[str, Any]:
    """The committed profile, as a fixture tree may copy it."""
    doc: dict[str, Any] = json.loads(COMMITTED.read_text(encoding="utf-8"))
    return doc


def _fleet(profile: str = PROFILE) -> dict[str, Any]:
    fleet = fleet_doc()
    fleet["units"]["a_pair"]["launch"]["seccomp"] = profile
    return fleet


def _tree(
    tmp_path: Path, *, profile: str = PROFILE, written: bool = True, doc: Any = None
) -> Path:
    """A throw-away tree whose ``a_pair`` states ``profile``."""
    root = make_tree(tmp_path, fleet=_fleet(profile))
    if written:
        path = root / "fleet-setup" / profile
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(_doc() if doc is None else doc, indent=2) + "\n"
        path.write_text(text, encoding="utf-8")
    return root


def _door(**override: str) -> Any:
    values = {
        "host": "alpha",
        "run_id": "2026-09-16-lock-fleets-x",
        "model": "/models/a_pair.gguf",
        "parallel": "2",
        "ctx_per_slot": "4096",
        "ubatch": "512",
        **override,
    }
    return steps_module().Door(**values)


def _refusals(root: Path, name: str = "a_pair") -> list[str]:
    lf = steps_module()
    _unit, refused = lf.unit_refusals(root, lf.load(root), name, _door())
    return list(refused)


def _run_args(root: Path, name: str = "a_pair") -> list[str]:
    """The argv ``_unit.sh`` hands the door's shim, as the step reads it."""
    said = steps_module()._run_args_nul(root, name, f"r-{name}", "img@sha256:x")
    return [arg for arg in said.split("\0") if arg]


# --------------------------------------------------------------------------
# lock-fleets: the unit run
# --------------------------------------------------------------------------


def test_a_unit_that_states_a_profile_launches_with_it_under_lock_fleets(
    tmp_path: Path,
) -> None:
    root = _tree(tmp_path)
    assert _refusals(root) == []
    args = _run_args(root)
    assert "--security-opt" in args
    stated = args[args.index("--security-opt") + 1]
    assert stated.startswith("seccomp=")
    # The docker CLI runs where the step runs and reads the file itself, so the
    # path it is given is absolute and is the file in this tree.
    where = Path(stated.removeprefix("seccomp="))
    assert where.is_absolute() and where.is_file()
    assert where == (root / "fleet-setup" / PROFILE)
    assert json.loads(where.read_text("utf-8")) == _doc()
    # It is passed to docker, not to the engine: before the image, never after.
    assert args.index("--security-opt") < args.index("img@sha256:x")


def test_a_unit_that_states_no_profile_launches_exactly_as_before(
    tmp_path: Path,
) -> None:
    root = _tree(tmp_path)
    lf = steps_module()
    plain = _run_args(root, "a_solo")
    assert "--security-opt" not in plain
    assert plain[:6] == ["--name", "r-a_solo", *lf.RUN_FLAGS]
    # And the same unit in a tree where nobody states one is the same argv.
    bare = make_tree(tmp_path / "bare")
    assert _run_args(bare, "a_solo") == plain


def test_a_stated_profile_that_is_not_there_is_refused_before_the_rig(
    tmp_path: Path,
) -> None:
    root = _tree(tmp_path, written=False)
    refused = _refusals(root)
    assert any(PROFILE in why for why in refused), refused
    assert any("seccomp" in why for why in refused), refused
    # Refused, not launched: no argv is built for it at all.
    lf = steps_module()
    with pytest.raises(lf.StepRefusedError, match="seccomp"):
        _run_args(root)


def test_a_stated_profile_does_not_move_the_unit_id_its_digests_hashed(
    tmp_path: Path,
) -> None:
    """``digests-<rig>.json`` hashes argv and env, and not every launch key —
    ``launch.volumes`` is not hashed either. So stating a profile leaves the
    unit_id, and the combination records named from it, where they are."""
    root = _tree(tmp_path)
    lf = steps_module()
    assert lf.launch_refusals(root, lf.launch(lf.load(root), "a_pair")) == []
    digests = json.loads((root / "fleet-setup" / "digests-alpha.json").read_text())
    assert "seccomp" not in digests["units"]["a_pair"]["fields"]


def test_a_move_cannot_deliver_a_profile_and_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``_move.sh``'s stopwatch runs docker ON the rig, so a path on the
    operator's disk is not one the rig's client can read. It is refused by
    name rather than started without the profile."""
    root = _tree(tmp_path)
    for key, value in {
        "RUN_HOST": "alpha",
        "RUN_ID": "2026-09-16-lock-fleets-m",
        "RUN_MODEL": "/models/a_pair.gguf",
        "RUN_PARALLEL": "2",
        "RUN_CTX_PER_SLOT": "4096",
        "RUN_UBATCH": "512",
    }.items():
        monkeypatch.setenv(key, value)
    state = tmp_path / "state"
    state.mkdir(exist_ok=True)
    said = steps_module()._move_facts(root, state, "alpha", "one", "two", "")
    refused = dict(line.split("=", 1) for line in said.splitlines() if "=" in line).get(
        "MOVE_REFUSED", ""
    )
    assert "a_pair" in refused and "seccomp" in refused, refused


# --------------------------------------------------------------------------
# the product's live path: the emitted compose
# --------------------------------------------------------------------------


def _emit(root: Path, out: Path) -> dict[str, Any]:
    fleet = steps_module().load(root)
    emit_locked(fleet, out, root / "fleet-setup")
    doc = yaml.safe_load((out / "compose.alpha.two.yml").read_text("utf-8"))
    return dict(doc["services"])


def test_the_emitted_compose_carries_the_profile_and_the_file_beside_it(
    tmp_path: Path,
) -> None:
    root = _tree(tmp_path)
    out = tmp_path / "compose"
    services = _emit(root, out)
    assert services["a_pair"]["security_opt"] == ["seccomp=io-uring.json"]
    # Compose resolves the path against the project directory — the compose
    # file's own — and reads it itself, so the profile is written beside it.
    beside = out / "io-uring.json"
    assert beside.is_file()
    assert json.loads(beside.read_text("utf-8")) == _doc()
    assert beside.read_text("utf-8") == (root / "fleet-setup" / PROFILE).read_text(
        "utf-8"
    )


def test_a_unit_that_states_none_renders_no_security_opt(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    out = tmp_path / "compose"
    _emit(root, out)
    solo = yaml.safe_load((out / "compose.alpha.one.yml").read_text("utf-8"))
    assert "security_opt" not in solo["services"]["a_solo"]
    # A fleet where nobody states one writes the same bytes as before and no
    # profile beside it.
    bare = make_tree(tmp_path / "bare")
    plain = tmp_path / "plain"
    emit_locked(steps_module().load(bare), plain, bare / "fleet-setup")
    assert sorted(p.name for p in plain.iterdir()) == [
        "compose.alpha.one.yml",
        "compose.alpha.two.yml",
        "compose.beta.one.yml",
        "compose.beta.two.yml",
    ]


def test_emit_refuses_a_stated_profile_that_is_not_there(tmp_path: Path) -> None:
    root = _tree(tmp_path, written=False)
    out = tmp_path / "compose"
    with pytest.raises(LockedLaunchError, match="seccomp"):
        emit_locked(steps_module().load(root), out, root / "fleet-setup")
    # Every refusal is raised before the first file is written.
    assert not out.exists() or not any(out.iterdir())


def test_the_committed_setup_emits_the_profile_it_states(tmp_path: Path) -> None:
    setup = REPO / "fleet-setup"
    fleet = steps_module().load(REPO)
    out = tmp_path / "compose"
    emit_locked(fleet, out, setup)
    solo = yaml.safe_load((out / "compose.srv2.a-solo.yml").read_text("utf-8"))
    service = solo["services"]["srv2_35b_256k"]
    assert service["security_opt"] == ["seccomp=io-uring.json"]
    assert (out / "io-uring.json").read_bytes() == COMMITTED.read_bytes()
    # b-small is what live serves and states none: its file keeps its shape.
    small = yaml.safe_load((out / "compose.srv2.b-small.yml").read_text("utf-8"))
    for name in ("srv2_3b", "srv2_7b"):
        assert "security_opt" not in small["services"][name]


# --------------------------------------------------------------------------
# the fresh start a changed launch gets
# --------------------------------------------------------------------------


def _failed(payload: dict[str, Any]) -> None:
    """A campaign run that failed: its step said so and measured nothing."""
    doc = payload["doc"]
    doc["failure"] = "the unit exited before /health said ok"
    if "harness" in doc:
        doc["harness"] = {"error": "the unit never served"}
    if "stamps" in doc:
        doc["stamps"]["t2"] = {}


def _window_to(tmp_path: Path, last: str) -> Window:
    window = frozen_window(tmp_path)
    for entry in window.runs.entries:
        window.write(entry, _failed if entry.id == "alpha-02" else None)
        if entry.id == last:
            break
    return window


def _diagnosed(tmp_path: Path) -> Window:
    """alpha-02 failed, its retry failed, and so did its diagnostic start."""
    window = _window_to(tmp_path, "alpha-02")
    window.retry("alpha-02", _failed)
    window.diagnose("alpha-02-retry1", _failed)
    return window


def test_a_changed_launch_gets_one_fresh_start_after_its_diagnostic(
    tmp_path: Path,
) -> None:
    window = _diagnosed(tmp_path)
    plan = plan_module()
    made = plan.relaunch(
        window.root, USE, "alpha-02-diag1", REASON, journal=str(window.journal)
    )
    step = f"{STEPS}/02-{USE}-alpha-c1-a_pair-relaunch1.sh"
    artifact = f"{USE}-alpha-c1-a_pair-relaunch1.json"
    assert made == {
        "entry": "alpha-02-diag1",
        "reason": REASON,
        "relaunch_entry": "alpha-02-relaunch1",
        "artifact": artifact,
        "step": step,
    }
    listed = window.root / "records/measurements/lock-fleets" / USE / "retries.json"
    doc = json.loads(listed.read_text("utf-8"))
    assert doc["relaunches"] == [made]
    ruling = doc["relaunch_ruling"]
    assert (ruling["by"], ruling["on"], ruling["said"]) == ("owner", "2026-09-16", SAID)
    # The three rulings before it are untouched.
    assert len(doc["retries"]) == 1 and len(doc["diagnostics"]) == 1

    wrapper = window.root / step
    text = wrapper.read_text("utf-8")
    assert os.access(wrapper, os.X_OK)
    assert re.findall(r"^# RUN_ARTIFACTS: (.*)$", text, re.M) == [artifact]
    assert f'/../_unit.sh" {artifact} a_pair "$@"' in text

    runs = plan.read_runs(window.root, USE)
    alpha = [e.id for e in runs.entries if e.rig == "alpha"]
    assert alpha[:6] == [
        "alpha-01",
        "alpha-02",
        "alpha-02-retry1",
        "alpha-02-diag1",
        "alpha-02-relaunch1",
        "alpha-03",
    ]
    base = runs.entry("alpha-02")
    fresh = runs.entry("alpha-02-relaunch1")
    assert (fresh.kind, fresh.fleet, fresh.units, fresh.run) == (
        "unit",
        "two",
        ("a_pair",),
        "c1",
    )
    assert (fresh.relaunch_of, fresh.retry_of, fresh.rerun_of, fresh.diagnostic_of) == (
        "alpha-02-diag1",
        "",
        "",
        "",
    )
    assert (fresh.artifact, fresh.wrapper, fresh.rig) == (artifact, step, "alpha")
    # The same unit and the same cold start: only the step and artifact differ.
    assert [a for a in fresh.argv if a != step] == [
        a for a in base.argv if a != base.wrapper
    ]
    assert fresh.run_id(WINDOW_DATE) == (
        f"{WINDOW_DATE}-lock-fleets-{USE}-alpha-c1-a_pair-relaunch1"
    )
    assert runs.relaunch_for("alpha-02-diag1") == fresh
    assert runs.relaunch_for("alpha-02") is None


RELAUNCH_REFUSALS = [
    ("unlogged", "alpha-02-diag1", "alpha-02-diag1 has no log row"),
    ("passed", "alpha-02-diag1", "alpha-02-diag1 passes its check"),
    ("failed", "alpha-02-retry1", "alpha-02-retry1 is not a diagnostic start"),
    ("failed", "alpha-02", "alpha-02 is not a diagnostic start"),
    (
        "relaunched",
        "alpha-02-diag1",
        "alpha-02-diag1 already has a fresh start, alpha-02-relaunch1",
    ),
    (
        "relaunched",
        "alpha-02-relaunch1",
        "alpha-02-relaunch1 is itself a fresh start",
    ),
]


@pytest.mark.parametrize(
    ("state", "entry", "said"),
    RELAUNCH_REFUSALS,
    ids=["unlogged", "passed", "a-retry", "an-entry", "relaunched", "a-relaunch"],
)
def test_relaunch_refuses_an_entry_the_ruling_does_not_restart(
    tmp_path: Path, state: str, entry: str, said: str
) -> None:
    window = _window_to(tmp_path, "alpha-02")
    window.retry("alpha-02", _failed)
    if state == "unlogged":
        window.diagnose("alpha-02-retry1", _failed, log=False)
    elif state == "passed":
        window.diagnose("alpha-02-retry1", None)
    else:
        window.diagnose("alpha-02-retry1", _failed)
    plan = plan_module()
    if state == "relaunched":
        plan.relaunch(
            window.root, USE, "alpha-02-diag1", REASON, journal=str(window.journal)
        )
    with pytest.raises(plan.PlanRefusedError, match=re.escape(said)):
        plan.relaunch(window.root, USE, entry, REASON, journal=str(window.journal))


def test_a_fresh_start_gets_no_retry_rerun_diagnostic_or_second_one(
    tmp_path: Path,
) -> None:
    window = _diagnosed(tmp_path)
    plan = plan_module()
    plan.relaunch(
        window.root, USE, "alpha-02-diag1", REASON, journal=str(window.journal)
    )
    window.reload()
    window.write(window.runs.entry("alpha-02-relaunch1"), _failed)
    for give in (plan.retry, plan.rerun, plan.diagnose, plan.relaunch):
        with pytest.raises(
            plan.PlanRefusedError, match="alpha-02-relaunch1 is itself a fresh start"
        ):
            give(
                window.root,
                USE,
                "alpha-02-relaunch1",
                REASON,
                journal=str(window.journal),
            )


def test_the_recheck_passes_the_failed_diagnostic_and_the_fresh_start_runs_next(
    tmp_path: Path,
) -> None:
    window = _diagnosed(tmp_path)
    asm, plan = assemble_module(), plan_module()
    # Before the fresh start the failed diagnostic stops the driver.
    assert any(
        "the step failed" in why
        for why in asm.check(context(window), "alpha", "alpha-02-diag1")
    )
    plan.relaunch(
        window.root, USE, "alpha-02-diag1", REASON, journal=str(window.journal)
    )
    window.reload()
    ctx = context(window)
    assert asm.check(ctx, "alpha", "alpha-02-diag1") == []
    _reasons, said = asm.verdict(ctx, "alpha", "alpha-02-diag1")
    assert "alpha-02-diag1 failed, relaunched by alpha-02-relaunch1" in said
    # And it is the next entry the rig runs.
    order = [e.id for e in ctx.runs.entries if e.rig == "alpha"]
    unlogged = [e for e in order if ctx.runs.logged(e) is None]
    assert unlogged[0] == "alpha-02-relaunch1"


def test_a_passing_fresh_start_stands_in_for_the_entry_it_restarted(
    tmp_path: Path,
) -> None:
    retried = frozen_window(tmp_path / "retried")
    retried.write_all({"alpha-02": _failed})
    retried.retry("alpha-02")
    fresh = frozen_window(tmp_path / "fresh")
    fresh.write_all({"alpha-02": _failed})
    fresh.retry("alpha-02", _failed)
    fresh.diagnose("alpha-02-retry1", _failed)
    made = fresh.relaunch("alpha-02-diag1")
    asm = assemble_module()
    want, _, _ = asm.assemble(context(retried))
    evidence, runs, _ = asm.assemble(context(fresh))
    assert evidence == want
    kept = runs["runs"]
    assert set(kept) == {e.id for e in fresh.runs.entries}
    assert kept["alpha-02"]["retried_by"] == "alpha-02-retry1"
    assert kept["alpha-02-retry1"]["diagnosed_by"] == "alpha-02-diag1"
    assert kept["alpha-02-diag1"]["relaunched_by"] == made["relaunch_entry"]
    assert any("the step failed" in why for why in kept["alpha-02-diag1"]["check"])
    assert kept["alpha-02-relaunch1"]["relaunch_of"] == "alpha-02-diag1"


@pytest.mark.parametrize(
    ("fresh", "said"),
    [
        ("failed", "alpha-02-relaunch1 fails its check: the step failed"),
        ("unlogged", "a frozen entry is missing: alpha-02-relaunch1 has no log row"),
    ],
)
def test_assembly_refuses_a_fresh_start_that_did_not_pass(
    tmp_path: Path, fresh: str, said: str
) -> None:
    window = frozen_window(tmp_path)
    window.write_all({"alpha-02": _failed})
    window.retry("alpha-02", _failed)
    window.diagnose("alpha-02-retry1", _failed)
    window.relaunch(
        "alpha-02-diag1",
        _failed if fresh == "failed" else None,
        log=fresh != "unlogged",
    )
    asm = assemble_module()
    with pytest.raises(asm.AssemblyRefusedError, match=re.escape(said)):
        asm.assemble(context(window))


# --------------------------------------------------------------------------
# what the repo commits
# --------------------------------------------------------------------------


def test_srv2_01_diag1_of_rig_id_relock_has_its_one_fresh_start_committed() -> None:
    plan = plan_module()
    runs = plan.read_runs(REPO, "rig-id-relock")
    srv1 = [e.id for e in runs.entries if e.rig == "srv1"]
    srv2 = [e.id for e in runs.entries if e.rig == "srv2"]
    # srv1 does not move; srv2 gains the fresh start and srv2-03's retry.
    assert (len(srv1), len(srv2)) == (16, 31)
    assert srv2[:5] == [
        "srv2-01",
        "srv2-01-retry1",
        "srv2-01-diag1",
        "srv2-01-relaunch1",
        "srv2-02",
    ]
    diagnostic = runs.entry("srv2-01-diag1")
    derived, text = plan.derive_relaunch("rig-id-relock", diagnostic)
    assert derived == {
        "relaunch_entry": "srv2-01-relaunch1",
        "artifact": "rig-id-relock-srv2-c1-srv2_35b_256k-relaunch1.json",
        "step": "tools/runs/campaigns/lock-fleets/rig-id-relock/"
        "16-rig-id-relock-srv2-c1-srv2_35b_256k-relaunch1.sh",
    }
    listed = REPO / "records/measurements/lock-fleets/rig-id-relock/retries.json"
    doc = json.loads(listed.read_text("utf-8"))
    assert doc["relaunches"] == [
        {"entry": "srv2-01-diag1", "reason": SRV2_RELAUNCH_REASON, **derived}
    ]
    ruling = doc["relaunch_ruling"]
    assert (ruling["by"], ruling["on"], ruling["said"]) == ("owner", "2026-09-16", SAID)
    assert (REPO / derived["step"]).read_text("utf-8") == text
    assert os.access(REPO / derived["step"], os.X_OK)
    fresh = runs.entry("srv2-01-relaunch1")
    assert fresh.relaunch_of == "srv2-01-diag1"
    assert [a for a in fresh.argv if a != derived["step"]] == [
        a for a in diagnostic.argv if a != diagnostic.wrapper
    ]


def test_the_readme_no_longer_calls_the_io_uring_line_non_fatal() -> None:
    """The README does not call ``io_uring_queue_init failed`` non-fatal or say
    it fell back to the RAM tier: for this source the fork aborts, and the
    diagnostic start filed exit 139."""
    readme = (REPO / "records/measurements/lock-fleets/README.md").read_text(
        encoding="utf-8"
    )
    assert "known not to be fatal" not in readme
    assert "fell back to the RAM tier" not in readme
    assert "ggml-backend.cpp" in readme and "e85e4d9" in readme
    assert "139" in readme
