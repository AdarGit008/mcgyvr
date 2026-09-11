"""llama.cpp answers ``/v1/models`` with a path, and the ladder declares a name.

RED, and two failures in one file — the residency check as it stands is wrong
about the fleet it was written for, and absent from the only path that matters.

**1. The comparison is a string equality between two different vocabularies.**
``AvailabilityVerdict.models`` is what the endpoint said, and llama.cpp says the
**path it was given**::

    "id": "/models/dense/Qwen2.5-Coder-3B-Instruct-Q4_K_M.gguf"

recorded on this fleet at ``records/evidence/serving-2026-08-30/lcpp-srv1.json``
lines 784-789. The emitted ``compose.srv1.yml`` passes
``--model /home/.../Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf`` with **no ``--alias``**,
and the live config declares ``model: "Qwen3.6-35B-A3B-UD-IQ3_XXS"``. Those two
strings are not equal, so ``Availability.not_serving`` reports srv1's **ceiling
rung** as not resident against a rig that is serving it perfectly well, and
tells the operator to wake a card that is up. vLLM is unaffected: its served id
is the ``--model`` argument, which is the repository id the config names.

The fix is not to compare loosely. It is to know what the other vocabulary *is*:
a served id that is a **path whose file name, minus the weights suffix, is the
declared model** is that model, and a path that names some other model is not.
Everything else is unchanged, including every way of saying nothing.

**2. ``mcgyvr run`` never asks — and after this file it still does not.**
``cli._climb`` builds its pool with no probe ("Structural resolution, no
probe"), and only ``mcgyvr pool --probe`` passes one, so a dispatch aimed at a
rung whose weights are not resident still reaches llama.cpp and is still
answered from the wrong weights. Closing that means opening a socket before
dispatch, which was written on 2026-09-09 and **backed out the same day**: the
sleep/wake specs name ``http://srv2:8001``, a hostname that resolves to the
actual rig on the machine this suite runs on, so the probe pointed the test
suite at production and failed four of the nineteen approved specs by doing it.
The run-path section below pins the property that revert restored — a run
resolves its ladder without touching the network — and the comment at
``cli._climb``'s ``source_map`` call carries the two ways to close the hole
without breaking it.

**The discipline this file pins throughout, because a fix here can only fail
one way.** Only an explicit, parseable, non-empty listing may take a rung out of
service. A source that did not answer, answered 404, answered something
unreadable or listed nothing claims nothing. A probe that failed closed on an
unreadable answer would empty the ladder the day it landed.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from mcgyvr.availability import Availability, AvailabilityVerdict
from mcgyvr.config import parse
from mcgyvr.pool import Endpoint, source_map
from tests import livejournal as lj

#: The name the live config declares for srv1's ceiling rung.
DECLARED = "Qwen3.6-35B-A3B-UD-IQ3_XXS"
#: What the emitted compose file passes as ``--model``, and therefore what
#: llama.cpp lists — the recorded shape, from
#: ``records/evidence/serving-2026-08-30/lcpp-srv1.json:784-789``.
SERVED = f"/home/adaramir/models/{DECLARED}.gguf"
#: The other model that rig alternates with, as a path.
OTHER = "/home/adaramir/models/deepseek-coder-v2-16b.gguf"

LADDER = f"""
version: 1
sources:
  srv1_big:
    base_url: "http://srv1:8080"
    api: openai
ladder:
  tiers:
    - name: local_big
      source: srv1_big
      model: "{DECLARED}"
"""


def answering(*models: str) -> Availability:
    def probe(endpoint: Endpoint, timeout_s: float) -> AvailabilityVerdict:
        return AvailabilityVerdict(
            source=endpoint.source,
            live=True,
            reason="",
            how="GET /v1/models answered 200 (stub)",
            elapsed_s=0.0,
            models=models or None,
        )

    return Availability(probe=probe)


def rungs_of(*models: str) -> tuple[Sequence[str], Mapping[str, str]]:
    resolved = source_map(parse(LADDER), probe=answering(*models))
    return (
        [rung.name for rung in resolved.rungs],
        {skip.name: skip.reason for skip in resolved.skipped},
    )


def test_a_served_path_whose_stem_is_the_declared_model_is_resident() -> None:
    """srv1's ceiling rung, against srv1 serving it. It must not be skipped.

    This is the regression the routing fix introduced: a healthy rig, the right
    weights loaded, and the rung taken out of service because the server spells
    the model as the file it was handed.
    """
    kept, skipped = rungs_of(SERVED)

    assert kept == ["local_big"], (kept, skipped)
    assert skipped == {}


def test_a_served_path_that_names_another_model_still_takes_the_rung_out() -> None:
    """The hole stays closed. A path is read, not ignored."""
    kept, skipped = rungs_of(OTHER)

    assert kept == [], (kept, skipped)
    assert "local_big" in skipped
    why = skipped["local_big"]
    assert DECLARED in why and "deepseek-coder-v2-16b" in why, why


def test_a_sharded_gguf_is_the_model_it_names() -> None:
    """A quant too big for one file is the same weights, in two.

    ``llama-server --model X-00001-of-00002.gguf`` loads the whole set and
    lists the first shard's path. Reading that as "some other model" would take
    the rung out of service for a naming convention.
    """
    kept, _ = rungs_of(f"/home/adaramir/models/{DECLARED}-00001-of-00002.gguf")

    assert kept == ["local_big"]


def test_a_path_stem_is_only_read_out_of_something_shaped_like_a_path() -> None:
    """A served id that is a plain name is compared as a plain name.

    vLLM's served id is its ``--model`` argument, which is a repository id with
    slashes in it and no suffix to strip. The path reading must not turn
    ``org/model.v2`` into ``org/model``, which would call a rung resident on a
    checkpoint it does not hold.
    """
    kept, skipped = rungs_of(f"{DECLARED}.v2")

    assert kept == [], (kept, skipped)


def test_a_listing_that_says_nothing_or_names_it_among_others_keeps_the_rung() -> None:
    """Two ways a rung stays: nothing was said, and it was said among others.

    The empty arm is the fail-open rule — a server that publishes no usable
    listing takes no rung out of service. The second is the ordinary llama.cpp
    answer on a rig holding more than one set of weights: the declared model is
    in the list, spelled as a path, beside another that is not this rung's.
    """
    for said in ((), (SERVED, OTHER)):
        kept, skipped = rungs_of(*said)
        assert kept == ["local_big"], (said, kept, skipped)


# --- the run path -------------------------------------------------------------
#
# **The second half of the hole is still open, and this section is what keeps it
# honest rather than what closes it.** `cli._climb` builds its pool with no
# probe, so a dispatch aimed at a rung whose weights are not resident is still
# answered from whatever is behind the port. Closing it there means opening a
# socket before dispatch, and that was written on 2026-09-09 and backed out the
# same day for a reason the tests themselves demonstrate: the sleep/wake specs
# name `http://srv2:8001`, which on a developer's machine resolves through
# Tailscale to the actual rig, so the probe sent this repository's own test
# suite at production and took four of the nineteen approved sleep/wake specs
# with it. `mcgyvr.wake`'s doctrine says the same thing from the design side —
# "fail-first, never probe-first", a card that is up must cost nothing extra.
#
# So what is pinned here is the property that revert restored: **a run resolves
# its ladder without touching the network**. Anything that breaks it breaks
# every spec that names a rig by hostname, and it will break it by talking to
# the rig. The two ways to close the hole without breaking it are written up in
# the comment at `cli._climb`'s `source_map` call.


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "home").mkdir(exist_ok=True)
    lj.clean_env(monkeypatch, tmp_path / "home")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "s1")
    lj.claude_transcript(tmp_path / "home", "s1")
    return tmp_path / "home"


def test_a_run_resolves_its_ladder_without_reaching_a_single_endpoint(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No probe before the dispatch, and the dispatch is the only wire touched.

    Asserted at ``availability.probe_endpoint``, which is where every probe in
    this tool eventually goes, so a caller that built its own
    :class:`Availability` is caught as surely as one that reached for the
    module function.
    """
    import mcgyvr.availability as availability

    asked: list[str] = []

    def probe(endpoint: Endpoint, timeout_s: float) -> AvailabilityVerdict:
        asked.append(endpoint.source)
        raise AssertionError(
            f"`mcgyvr run` probed {endpoint.source!r} at {endpoint.base_url!r} "
            "before dispatching. A run that opens a socket to resolve its "
            "ladder sends every test that names a rig by hostname at the rig"
        )

    monkeypatch.setattr(availability, "probe_endpoint", probe)

    sent = lj.scripted(monkeypatch, lj.GOOD_REPLY)
    repo = lj.make_repo(tmp_path / "repo")
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=tmp_path / "journal")
    contract = lj.make_contract(tmp_path / "impl.yaml")

    code = lj.main(lj.run_args(contract, repo, config))
    said = capsys.readouterr()

    assert asked == [], asked
    assert code == 0, said
    assert len(sent) == 1, sent


def test_the_recorded_llama_cpp_body_is_read_as_the_model_it_holds() -> None:
    """The evidence, end to end: a real body through the real parser.

    ``records/evidence/serving-2026-08-30/lcpp-srv1.json`` holds what this
    fleet's llama.cpp actually answered ``/v1/models`` with. Reading the shape
    off a recorded body rather than a hand-written one is what keeps this honest
    about the vocabulary the server uses rather than the one we remember.
    """
    from mcgyvr.availability import _listed

    body = json.dumps(
        {
            "object": "list",
            "data": [
                {
                    "id": "/models/dense/Qwen2.5-Coder-3B-Instruct-Q4_K_M.gguf",
                    "object": "model",
                    "owned_by": "llamacpp",
                }
            ],
        }
    ).encode("utf-8")

    listed = _listed(body)
    assert listed == ("/models/dense/Qwen2.5-Coder-3B-Instruct-Q4_K_M.gguf",)

    ladder = LADDER.replace(DECLARED, "Qwen2.5-Coder-3B-Instruct-Q4_K_M")
    resolved = source_map(parse(ladder), probe=answering(*listed))
    assert [rung.name for rung in resolved.rungs] == ["local_big"], resolved.skipped
