"""`mcgyvr recommend` can choose any candidate it assembled, on any host.

The plan is one placement picked from candidates assembled per rig, and a
candidate is known by its name: two under one name are taken for one listed
twice, and only the first is kept. Two things broke that:

* the names were not unique. A local checkpoint was named only by its
  speculative head (`llama.cpp:no speculative head`), and a catalog pick only
  by engine and model, so the same name stood for a checkpoint on every rig,
  and for every checkpoint in a store, and most candidates could never be
  placed;
* the placement said nothing about the rig it was for, so even the candidate
  picked could not be told apart from its twin on another rig.

So: every candidate's name is its own, every candidate is reachable by its
name, and every placement says which host it is on. The rigs are invented
and answer through the read-only ssh seam; the pick is replaced at
`mcgyvr.recommend._deterministic_pick` by one that takes each candidate in
turn.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from mcgyvr import recommend as recommend_module
from mcgyvr import scan as scan_module
from tests.test_recommend import (
    CHECKPOINT,
    FAKE_CATALOG,
    HOST,
    OTHER,
    STORE_DIR,
    RecordedSsh,
    fake_header,
    run_and_parse,
)

#: Invented rigs: no such machines exist.
HOSTS = ("rig-a.invalid", "rig-b.invalid")


class Picks:
    """A stand-in for ``recommend._deterministic_pick`` that takes the candidate
    it is told, and records the names it was offered."""

    def __init__(self) -> None:
        self.pick = 0
        self.options: list[tuple[str, ...]] = []

    def __call__(
        self, candidates: tuple[recommend_module.Candidate, ...]
    ) -> recommend_module.Candidate:
        self.options.append(tuple(candidate.name for candidate in candidates))
        return candidates[self.pick]


@pytest.fixture
def picks(monkeypatch: pytest.MonkeyPatch) -> Picks:
    """A pick that takes the candidate ``Picks.pick`` points at."""
    chooser = Picks()
    monkeypatch.setattr(recommend_module, "_deterministic_pick", chooser)
    return chooser


def _ssh(monkeypatch: pytest.MonkeyPatch, *hosts: str) -> RecordedSsh:
    ssh = RecordedSsh(*hosts)
    monkeypatch.setattr(scan_module, "_ssh", ssh)
    return ssh


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
    hosts: tuple[str, ...],
    *model_stores: str,
) -> tuple[tuple[str, ...], dict[str, tuple[Any, ...]]]:
    """Take each candidate in turn; return the names and where each landed."""
    code, plan = run_and_parse(capsys, "code", "single", *model_stores, hosts=hosts)
    assert code == 0, plan
    options = picks.options[-1]
    placed = {options[0]: _where(plan["placement"])}
    for index in range(1, len(options)):
        picks.pick = index
        code, plan = run_and_parse(capsys, "code", "single", *model_stores, hosts=hosts)
        assert code == 0, plan
        assert picks.options[-1] == options
        placed[options[index]] = _where(plan["placement"])
    return options, placed


def test_two_checkpoints_on_one_rig_are_each_their_own_choice(
    picks: Picks,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One rig, two checkpoints that fit, with and without the MTP head: four
    names, and naming each places a different one."""
    _ssh(monkeypatch, HOST).ggufs = [CHECKPOINT, OTHER]

    options, placed = _every_pick(capsys, picks, (HOST,), STORE_DIR)

    assert len(set(options)) == len(options) == 4, options
    assert set(placed.values()) == {
        (HOST, "llama.cpp", checkpoint, mtp)
        for checkpoint in (CHECKPOINT, OTHER)
        for mtp in (False, True)
    }


def test_the_mtp_head_and_the_plain_path_are_two_choices(
    picks: Picks,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A checkpoint with a grafted MTP head is offered twice under two names:
    one launches the head, the other does not."""
    assert fake_header(CHECKPOINT)["nextn_blocks"], "the header must carry a head"
    _ssh(monkeypatch, HOST)

    options, placed = _every_pick(capsys, picks, (HOST,), STORE_DIR)

    assert len(set(options)) == len(options) == 2, options
    assert sorted(placed.values()) == [
        (HOST, "llama.cpp", CHECKPOINT, False),
        (HOST, "llama.cpp", CHECKPOINT, True),
    ]


def test_every_local_checkpoint_on_every_rig_is_its_own_choice(
    picks: Picks,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Two rigs x two checkpoints x (with, without the MTP head) = 8 choices."""
    _ssh(monkeypatch, *HOSTS).ggufs = [CHECKPOINT, OTHER]

    options, placed = _every_pick(capsys, picks, HOSTS, STORE_DIR)

    assert len(set(options)) == len(options) == 8, options
    assert set(placed.values()) == {
        (host, "llama.cpp", checkpoint, mtp)
        for host in HOSTS
        for checkpoint in (CHECKPOINT, OTHER)
        for mtp in (False, True)
    }


def test_every_catalog_pick_on_every_rig_is_its_own_choice(
    picks: Picks,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The catalog's one fitting model, two engines, two rigs = 4 choices."""
    _ssh(monkeypatch, *HOSTS)
    one_model = {"models": [dict(FAKE_CATALOG["models"][0], size_bytes=10**9)]}
    monkeypatch.setattr(recommend_module, "load_catalog", lambda *a, **k: one_model)
    model_id = one_model["models"][0]["model_id"]

    options, placed = _every_pick(capsys, picks, HOSTS)

    assert len(set(options)) == len(options) == 4, options
    assert set(placed.values()) == {
        (host, engine, model_id, False)
        for host in HOSTS
        for engine in ("llama.cpp", "vllm")
    }


def test_a_store_named_twice_offers_each_checkpoint_once(
    picks: Picks,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Two spellings of one store list the same file: one placement, one name."""
    _ssh(monkeypatch, HOST)

    code, plan = run_and_parse(
        capsys, "code", "single", STORE_DIR, STORE_DIR + "/", hosts=(HOST,)
    )

    assert code == 0, plan
    assert len(picks.options[-1]) == 2, picks.options[-1]


def test_a_deterministic_placement_also_names_its_host(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The fixed rule picks, and the pick still says where."""
    _ssh(monkeypatch, *HOSTS)

    code, plan = run_and_parse(capsys, "code", "single", STORE_DIR, hosts=HOSTS)

    assert code == 0, plan
    assert plan["decision"] == "deterministic"
    assert plan["placement"]["host"] in HOSTS
