"""`mcgyvr recommend` can choose any candidate it assembled, on any host.

The plan is one placement picked from candidates assembled per rig. The pick
is a name: the bound Jev unit answers with one of the candidates' names, and
the plan places the candidate of that name. Two things broke that:

* the names were not unique. A local checkpoint was named only by its
  speculative head (`llama.cpp:no speculative head`), and a catalog pick only
  by engine and model, so the same name stood for a checkpoint on every rig,
  and for every checkpoint in a store. The lookup by name kept the last one,
  so most candidates could never be chosen;
* the placement said nothing about the rig it was for, so even the candidate
  picked could not be told apart from its twin on another rig.

So: every candidate's name is its own, every candidate is reachable by its
name, and every placement says which host it is on. The rigs are invented
and answer through the read-only ssh seam; the decision is faked at
`mcgyvr.decision.classify` and names each option in turn.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import availability, decision
from mcgyvr import recommend as recommend_module
from mcgyvr import scan as scan_module
from mcgyvr.availability import AvailabilityVerdict
from tests.test_recommend import (
    CHECKPOINT,
    FAKE_CATALOG,
    OTHER,
    STORE_DIR,
    RecordedSsh,
    run_and_parse,
)

#: Invented rigs: no such machines exist.
HOSTS = ("rig-a.invalid", "rig-b.invalid")

#: A setup that binds a Jev unit, so the decision is asked. Invented.
JEV_CONFIG = """\
units:
  judge:
    address: http://localhost:18009
    model: example-judge:1b
    rig: local
ladder:
- judge
jev:
  unit: judge
"""


class Picks:
    """A stand-in for ``decision.classify`` that names the option it is told."""

    def __init__(self) -> None:
        self.pick = 0
        self.options: list[tuple[str, ...]] = []

    def __call__(
        self,
        endpoint: Any,
        model: str,
        state: Any,
        questions: Mapping[str, Any],
        *,
        timeout_s: float,
    ) -> decision.Decision:
        options = tuple(questions["placement"].options)
        self.options.append(options)
        chosen = options[self.pick]
        return decision.Decision(
            answers={
                "placement": decision.ChoiceAnswer(
                    choice=chosen, probabilities={chosen: 1.0}, confidence=1.0
                )
            }
        )


@pytest.fixture
def setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[str, RecordedSsh, Picks]:
    config = tmp_path / "mcgyvr.yaml"
    config.write_text(JEV_CONFIG, encoding="utf-8")
    ssh = RecordedSsh(*HOSTS)
    monkeypatch.setattr(scan_module, "_ssh", ssh)
    picks = Picks()
    monkeypatch.setattr(decision, "classify", picks)

    def live(endpoint: Any, timeout_s: float = 2.0) -> AvailabilityVerdict:
        return AvailabilityVerdict(
            source=endpoint.source, live=True, reason="stub", how="stub", elapsed_s=0.0
        )

    monkeypatch.setattr(availability, "probe_endpoint", live)
    return str(config), ssh, picks


def _where(placement: Mapping[str, Any]) -> tuple[Any, ...]:
    """What tells one placement from another: rig, engine, weights, head."""
    return (
        placement["host"],
        placement["engine"],
        placement["checkpoint"] or placement["model_id"],
        "--spec-type" in placement["flags"],
    )


def _every_pick(
    capsys: pytest.CaptureFixture[str],
    picks: Picks,
    config: str,
    *model_stores: str,
) -> tuple[tuple[str, ...], set[tuple[Any, ...]]]:
    """Name each option in turn; return the options and where each landed."""
    code, plan = run_and_parse(
        capsys, "coding", "single", *model_stores, hosts=HOSTS, config=config
    )
    assert code == 0, plan
    options = picks.options[-1]
    placed = {_where(plan["placement"])}
    for index in range(1, len(options)):
        picks.pick = index
        code, plan = run_and_parse(
            capsys, "coding", "single", *model_stores, hosts=HOSTS, config=config
        )
        assert code == 0, plan
        assert plan["decision"] == "model"
        placed.add(_where(plan["placement"]))
    return options, placed


def test_every_local_checkpoint_on_every_rig_is_its_own_choice(
    setup: tuple[str, RecordedSsh, Picks], capsys: pytest.CaptureFixture[str]
) -> None:
    """Two rigs x two checkpoints x (with, without the MTP head) = 8 choices."""
    config, ssh, picks = setup
    ssh.ggufs = [CHECKPOINT, OTHER]

    options, placed = _every_pick(capsys, picks, config, STORE_DIR)

    assert len(options) == 8, options
    assert placed == {
        (host, "llama.cpp", checkpoint, mtp)
        for host in HOSTS
        for checkpoint in (CHECKPOINT, OTHER)
        for mtp in (False, True)
    }


def test_every_catalog_pick_on_every_rig_is_its_own_choice(
    setup: tuple[str, RecordedSsh, Picks],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The catalog's one fitting model, two engines, two rigs = 4 choices."""
    config, _ssh, picks = setup
    one_model = {"models": [dict(FAKE_CATALOG["models"][0], size_bytes=10**9)]}
    monkeypatch.setattr(recommend_module, "load_catalog", lambda: one_model)
    model_id = one_model["models"][0]["model_id"]

    options, placed = _every_pick(capsys, picks, config)

    assert len(options) == 4, options
    assert placed == {
        (host, engine, model_id, False)
        for host in HOSTS
        for engine in ("llama.cpp", "vllm")
    }


def test_a_deterministic_placement_also_names_its_host(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No Jev bound: the fixed rule picks, and the pick still says where."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(scan_module, "_ssh", RecordedSsh(*HOSTS))

    code, plan = run_and_parse(capsys, "coding", "single", STORE_DIR, hosts=HOSTS)

    assert code == 0, plan
    assert plan["decision"] == "deterministic"
    assert plan["placement"]["host"] in HOSTS
