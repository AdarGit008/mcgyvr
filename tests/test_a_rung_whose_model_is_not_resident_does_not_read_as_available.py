"""A port that answers is not a port serving *your* model.

RED. ``mcgyvr.availability`` probes a **source**, and a source is a URL. It reads
the HTTP status of ``/v1/models`` and throws the body away, so the one fact that
listing exists to carry — *which weights are behind this port right now* — is
never read. Every rung on a source that answered is marked live.

**Why that is a hole and not a simplification.** Two rungs that alternate on one
card are two models and one launch spec each, and only one of them is ever up.
Probe the one that is up and the answer is 200; probe the one that is down and,
under port-per-model, the answer is *also* 200 the moment its alternative has
been brought up on a URL the ladder still points a rung at. llama.cpp does not
check: ``/v1/chat/completions`` with a ``model`` field naming weights it is not
holding is answered from the weights it *is* holding, with no error anywhere. So
a dispatch aimed at the sleeping rung reaches a server holding the other model
and the run records an answer from a rung that was never up. That is O3, and it
is the failure this file exists to prevent: **wrong weights, silently.**

Card contention makes it ordinary rather than exotic. Since the discriminator
became the card
(``tests/test_card_contention_and_not_the_port_decides_who_alternates.py``), any
two units whose figures do not sum onto the card they share alternate — srv2's
vLLM pair against the 80B, srv1's DeepSeek against Qwen3.6 — and each of them is
a rung the ladder still names while its model is not resident.

**What this file pins**

1. A rung whose model the endpoint does not list is **not available**, and the
   reason names the model and what was found instead.
2. A rung whose model *is* listed is available exactly as before.
3. **An endpoint that does not say claims nothing.** A 404 on the listing, a
   body that is not JSON, a body of another shape, a listing that is empty — all
   of them leave every rung available, because the model-list path is optional
   and half this fleet's servers do not publish a usable one. This is the same
   discipline ``servelib.sleeping`` takes for ``/is_sleeping`` (``b4e9ea8e``):
   only an explicit answer may take a rung out of service, because a probe that
   failed closed on an unreadable one would empty the ladder the day it landed.
4. The probe is still **one request per source**. The model check reads the body
   that request already fetched; it does not add a round trip, and a source
   serving four rungs is still probed once.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from mcgyvr.availability import Availability, AvailabilityVerdict
from mcgyvr.config import parse
from mcgyvr.pool import Endpoint, source_map

RESIDENT = "qwen3.6-35b-a3b"
SLEEPING = "deepseek-coder-v2-16b"

LADDER = f"""
version: 1
sources:
  srv1_lite:
    base_url: "http://srv1:8080"
    api: openai
  srv1_big:
    base_url: "http://srv1:8081"
    api: openai
ladder:
  tiers:
    - name: local_lite
      source: srv1_lite
      model: "{SLEEPING}"
    - name: local_big
      source: srv1_big
      model: "{RESIDENT}"
"""


def answering(models: tuple[str, ...] | None) -> Availability:
    """An availability whose every source answers 200 and lists ``models``.

    ``None`` is the endpoint that did not say — a 404 on the listing, or a body
    nothing could read. It is the ordinary case on this fleet and it must leave
    every rung alone.
    """

    def probe(endpoint: Endpoint, timeout_s: float) -> AvailabilityVerdict:
        return AvailabilityVerdict(
            source=endpoint.source,
            live=True,
            reason="",
            how="GET /v1/models answered 200 (stub)",
            elapsed_s=0.0,
            models=models,
        )

    return Availability(probe=probe)


def rungs_of(probe: Availability) -> tuple[Sequence[str], Mapping[str, str]]:
    resolved = source_map(parse(LADDER), probe=probe)
    return (
        [rung.name for rung in resolved.rungs],
        {skip.name: skip.reason for skip in resolved.skipped},
    )


def test_a_rung_whose_model_the_endpoint_does_not_list_is_not_available() -> None:
    """The hole, closed. One model is resident and the other is not.

    Both ports answer — that is the whole difficulty, and it is why the status
    code cannot decide this. What separates the two rungs is which weights the
    server says it is holding, and it says so in the body of the request the
    probe already made.
    """
    kept, skipped = rungs_of(answering((RESIDENT,)))

    assert kept == ["local_big"], (kept, skipped)
    assert "local_lite" in skipped, skipped
    why = skipped["local_lite"]
    assert SLEEPING in why, why
    assert RESIDENT in why, (
        "the reason did not say what the port is holding instead. A rung "
        "skipped for a model that is not there sends an operator to the wrong "
        "repair unless they are told which model *is*"
    )


def test_a_rung_whose_model_is_listed_is_available_exactly_as_before() -> None:
    """The other side of it, so the check cannot be satisfied by skipping all."""
    kept, skipped = rungs_of(answering((RESIDENT, SLEEPING)))

    assert kept == ["local_lite", "local_big"], (kept, skipped)
    assert skipped == {}


def test_an_endpoint_that_does_not_say_takes_no_rung_out_of_service() -> None:
    """Only an explicit answer may shorten the ladder (``b4e9ea8e``'s rule).

    A small server may implement ``/v1/chat/completions`` and never implement
    ``/v1/models`` — the 404 arm this module's own docstring is asymmetric for —
    and a probe that read silence as "your model is not here" would empty every
    such ladder the day it landed.
    """
    for said in (None, ()):
        kept, skipped = rungs_of(answering(said))
        assert kept == ["local_lite", "local_big"], (said, kept, skipped)
        assert skipped == {}, (said, skipped)


def test_the_model_check_adds_no_second_request() -> None:
    """One probe per source, still. The body was already fetched.

    A per-rung probe would be one round trip per rung on a dead host, which is
    exactly the cost this module was written to stop paying — three rungs on one
    dead host being three timeouts for one fact.
    """
    asked: list[str] = []

    def probe(endpoint: Endpoint, timeout_s: float) -> AvailabilityVerdict:
        asked.append(endpoint.source)
        return AvailabilityVerdict(
            source=endpoint.source,
            live=True,
            reason="",
            how="GET /v1/models answered 200 (stub)",
            elapsed_s=0.0,
            models=(RESIDENT,),
        )

    source_map(parse(LADDER), probe=Availability(probe=probe))

    assert sorted(asked) == ["srv1_big", "srv1_lite"], asked
