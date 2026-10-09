"""The evidence goes where ``$MCGYVR_RUN_ROOT`` says, and nowhere else.

The door files every run's envelope under ``<root>/records/evidence/``. A root
computed from the door's own file is the repository from a checkout and
``site-packages/`` from an installed wheel, so the root is ``$MCGYVR_RUN_ROOT`` when
that is set.

What must be observably true:

* with ``MCGYVR_RUN_ROOT`` set to an existing directory, the envelope is made
  under it, the gates read their declarations (the round, ``hosts.json``, the
  campaigns) from it, and nothing lands under the checkout the door runs from;
* with it unset, the checkout is the root;
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


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("relative/runs", id="relative"),
        pytest.param("~nosuchuser-mcgyvr/runs", id="unexpanded-user"),
        pytest.param("", id="empty"),
    ],
)
def test_a_value_the_door_cannot_judge_is_refused_not_traced_back(
    value: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A relative path lands somewhere different per working directory; a
    ``~user`` the shell did not expand raises inside ``expanduser``; an empty
    value names nothing. Each is exit 2 naming the variable, never a
    traceback."""
    from mcgyvr.serving import run

    monkeypatch.setenv(RUN_ROOT_VAR, value)
    status = run.main(["step", "--host", "srv1", "--campaign", CAMPAIGN, "--step", "x"])
    err = capsys.readouterr().err
    assert status == 2, err
    assert RUN_ROOT_VAR in err and "absolute" in err, err
