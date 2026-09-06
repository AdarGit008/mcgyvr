"""The evidence goes where ``$MCGYVR_RUN_ROOT`` says, and nowhere else.

The door computes its root from its own file — four levels up from
``src/mcgyvr/serving/run.py`` — and files every run's envelope under
``<root>/records/evidence/``. From a checkout that root is the repository, and
the envelope lands beside the code that produced it. From an installed wheel
the same arithmetic lands in ``site-packages/``, and a run's evidence would be
written into the interpreter's library directory: the one line that makes a
production install have to be a git checkout.

What must be observably true:

* with ``MCGYVR_RUN_ROOT`` set to an existing directory, the envelope is made
  under it, the gates read their declarations (the round, ``hosts.json``, the
  campaigns) from it, and nothing lands under the checkout the door runs from;
* with it unset, everything is exactly as today: the checkout is the root;
* a value naming a path that is not an existing directory is refused before
  any gate — nothing checked, nothing made, no rig read — and the refusal names
  the variable and the rule. A root the door made silently is how evidence goes
  missing: the operator meant one directory, typed another, and a run filed
  itself where nobody looks.

The serve run is the same door with a second sequence, so the same rule is
stated for it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests import onedoor

RUN_ROOT_VAR = "MCGYVR_RUN_ROOT"
CAMPAIGN = "root-probe"


def _probe(root: Path, env_file: Path) -> onedoor.Scenario:
    """A campaign step under ``root`` that records the run it was handed."""
    step = onedoor.add_step(root, CAMPAIGN, "1-probe.sh", onedoor.probe_step(env_file))
    return onedoor.Scenario(campaign=CAMPAIGN, step=str(step))


def test_the_envelope_lands_under_the_named_run_root(tmp_path: Path) -> None:
    """The measured case: the door runs from one tree and files under another."""
    checkout = onedoor.fixture_repo(tmp_path / "checkout")
    run_root = onedoor.fixture_repo(tmp_path / "run-root")
    env_file = tmp_path / "env.txt"
    done = onedoor.door(
        checkout,
        _probe(run_root, env_file),
        env_extra={RUN_ROOT_VAR: str(run_root)},
    )
    assert done.returncode == 0, done.stderr[-1500:]

    envelope = onedoor.envelope(run_root, CAMPAIGN)
    assert (envelope / "probe.tsv").is_file(), (
        f"the step's artifact is not under {RUN_ROOT_VAR}={run_root}: "
        f"{onedoor.written_under_records(run_root)}"
    )
    handed = onedoor.read_env_file(env_file)
    assert handed["RUN_OUT_DIR"] == str(envelope), handed
    assert onedoor.written_under_records(checkout) == [], (
        "the checkout the door runs from is not the run root, and got written to"
    )


def test_without_the_variable_the_checkout_is_the_root(tmp_path: Path) -> None:
    """The direction that must not break: nothing named, nothing moves."""
    checkout = onedoor.fixture_repo(tmp_path / "checkout")
    env_file = tmp_path / "env.txt"
    done = onedoor.door(checkout, _probe(checkout, env_file))
    assert done.returncode == 0, done.stderr[-1500:]
    envelope = onedoor.envelope(checkout, CAMPAIGN)
    assert (envelope / "probe.tsv").is_file()
    assert onedoor.read_env_file(env_file)["RUN_OUT_DIR"] == str(envelope)


def test_a_root_that_does_not_exist_is_refused_and_not_made(tmp_path: Path) -> None:
    """A typo in the variable is a refusal, never a directory."""
    checkout = onedoor.fixture_repo(tmp_path / "checkout")
    missing = tmp_path / "no-such-root"
    done = onedoor.door(
        checkout,
        _probe(checkout, tmp_path / "env.txt"),
        env_extra={RUN_ROOT_VAR: str(missing)},
    )
    assert done.returncode == 2, (done.returncode, done.stderr[-1500:])
    assert RUN_ROOT_VAR in done.stderr, done.stderr
    assert "existing directory" in done.stderr, done.stderr
    assert not missing.exists(), "the door made the root it should have refused"
    assert onedoor.written_under_records(checkout) == [], (
        "a refused run wrote under the checkout"
    )
    assert onedoor.ssh_log(checkout) == [], "a refused run reached the rig"


def test_a_root_that_is_a_file_is_refused(tmp_path: Path) -> None:
    checkout = onedoor.fixture_repo(tmp_path / "checkout")
    not_a_dir = tmp_path / "root-file"
    not_a_dir.write_text("", encoding="utf-8")
    done = onedoor.door(
        checkout,
        _probe(checkout, tmp_path / "env.txt"),
        env_extra={RUN_ROOT_VAR: str(not_a_dir)},
    )
    assert done.returncode == 2, (done.returncode, done.stderr[-1500:])
    assert RUN_ROOT_VAR in done.stderr and "existing directory" in done.stderr


def test_the_serve_run_refuses_a_missing_root_the_same_way(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """``serve up`` is the same door: the root is settled before the compose
    file is even read, so the refusal names the variable and not the file."""
    from mcgyvr.serving import run

    missing = tmp_path / "no-such-root"
    monkeypatch.setenv(RUN_ROOT_VAR, str(missing))
    status = run.main(
        ["serve", "up", "--host", "srv1", "--compose", str(tmp_path / "compose.yaml")]
    )
    err = capsys.readouterr().err
    assert status == 2, err
    assert RUN_ROOT_VAR in err and "existing directory" in err, err
    assert not missing.exists()
