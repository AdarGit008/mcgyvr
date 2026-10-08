"""A caller's gate can add a refusal and never take one away.

Owner, 2026-10-08 (design 2b): the gates a caller adds, by ``--gates`` or
from ``$MCGYVR_DOOR_GATES``, run inside the door's order and never in place
of a door gate. So a door gate that refuses ends the run whatever the
caller's gates say: one that exits 0 in every phase it may run in does not
admit the run, does not bring the step on, and does not change the run's
status; the lease is released all the same. A refusal in the door's gates 7
and 8 is not undone by a caller's ``always`` gate that admits either.

Every machine here is invented and stands behind the door's shims.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.serving import run
from tests import callergates as cg
from tests import onedoor, usermode

#: Each verb, a door gate of it that refuses, and the phases its list may name.
REFUSALS = [
    ("step", "02-rig.py", ("before", "after", "always")),
    ("step", "03-image.py", ("before", "after", "always")),
    ("step", "05-envelope.py", ("before", "after", "always")),
    ("serve", "02-rig.py", ("before", "after", "always")),
    ("serve", "05-envelope.py", ("before", "after", "always")),
    ("read", "read-02-rig.py", ("before", "after")),
    ("link", "link-01-time.py", ("before",)),
]


def _argv(verb: str, tmp_path: Path, *extra: str) -> list[str]:
    if verb == "step":
        return cg.step_argv(tmp_path, *extra)
    if verb == "serve":
        return cg.serve_argv(cg.compose_file(tmp_path / "compose.yaml"), *extra)
    if verb == "read":
        return cg.read_argv(*extra)
    return cg.link_argv(*extra)


def _order(log: Path) -> list[str]:
    return [line.split()[0] for line in cg.log_lines(log)]


def _admitting_list(where: Path, log: Path, phases: tuple[str, ...]) -> Path:
    """One gate per phase, each exiting 0."""
    root = where.parent / "admitting"
    gates = []
    for phase in phases:
        cg.executable(root / f"{phase}.py", cg.gate_text(log, f"caller:{phase}"))
        gates.append(cg.entry(f"{phase}.py", phase))
    return cg.write_list(where, str(root), gates)


@pytest.mark.parametrize("source", ["--gates", "environment"])
@pytest.mark.parametrize(("verb", "refusing", "phases"), REFUSALS)
def test_a_door_gate_that_refuses_ends_the_run_whatever_the_callers_gates_say(
    verb: str,
    refusing: str,
    phases: tuple[str, ...],
    source: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    cg.fake_door(tmp_path, monkeypatch, log, statuses={refusing: 2})
    folder = tmp_path / "lists"
    listed = _admitting_list(folder / f"{verb}.json", log, phases)
    if source == "environment":
        monkeypatch.setenv(run.GATES_ENV, str(folder))
        argv = _argv(verb, tmp_path)
    else:
        argv = _argv(verb, tmp_path, "--gates", str(listed))

    assert run.main(argv) == 2

    order = _order(log)
    assert f"door:{refusing}" in order
    assert "door:06-step.py" not in order
    after_refusal = order[order.index(f"door:{refusing}") + 1 :]
    # Nothing a caller added ran after the door said no, and nothing of the
    # door's own order did either, but the teardown of a run that minted one
    # and the lease's release.
    assert not any(name in ("caller:before", "caller:after") for name in after_refusal)
    assert all(
        name in ("door:07-teardown.py", "door:08-parse.py", "caller:always")
        or name == f"door:{run.LEASE_RELEASE.script}"
        for name in after_refusal
    ), order
    if verb in ("step", "serve"):
        assert order[-1] == f"door:{run.LEASE_RELEASE.script}"


@pytest.mark.parametrize("failing", ["07-teardown.py", "08-parse.py"])
@pytest.mark.parametrize("verb", ["step", "serve"])
def test_an_always_gate_that_admits_does_not_clear_a_teardown_or_parse_finding(
    verb: str, failing: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    cg.fake_door(tmp_path, monkeypatch, log, statuses={failing: 1})
    listed = _admitting_list(tmp_path / "lists" / "x.json", log, ("always",))

    assert run.main(_argv(verb, tmp_path, "--gates", str(listed))) == 1

    assert "caller:always" in _order(log)


def test_a_rig_the_door_refuses_is_refused_with_every_callers_gate_admitting(
    tmp_path: Path,
) -> None:
    """The real gates: the rig no longer holds what the rig file records, and
    a caller's list that admits in every phase changes nothing of that."""
    usermode.save_rig()
    smaller = usermode.scan_payload(cards=((0, "Invented Card 8G", 8192),))
    stubs = usermode.machine(tmp_path, scan=smaller, pending=())
    log = tmp_path / "callers.log"
    folder = tmp_path / "lists"
    _admitting_list(folder / "step.json", log, ("before", "after", "always"))
    record = tmp_path / "record.txt"
    script = usermode.step_script(tmp_path, record)

    done = usermode.door(
        usermode.step(script),
        stubs=stubs,
        run_root=usermode.install_root(tmp_path),
        cwd=tmp_path,
        env_extra={
            "MCGYVR_CONFIG": str(usermode.dev_setup(tmp_path)),
            run.GATES_ENV: str(folder),
        },
    )

    said = done.stdout + done.stderr
    assert done.returncode == 2, said
    assert "no longer fits" in said
    assert "02-rig.py" in said
    assert not record.exists(), "the step ran on a rig the door refused"
    assert _order(log) == ["caller:before"]
    assert onedoor.read_lease(tmp_path) is None
    assert usermode.door_logs(usermode.home()) == []
