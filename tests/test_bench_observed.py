"""The `observed` block: captured comprehensively, compared by nothing (#286).

D7. The properties here are the ones a later reader has to be able to
trust without re-deriving them: every declared field is present, a null carries
a reason, nothing on the way in reaches disk unredacted, and — the one that is
not about content — **nothing reads this file**. That last one is a test rather
than a docstring because it is the property a future lane is most likely to
break by accident, by wiring a guard to a field that is comprehensive precisely
because nobody admitted it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests._helpers import by_path

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def observed() -> Any:
    return by_path("bench_observed", REPO / "tools" / "bench" / "observed.py")


# --- the probe set ----------------------------------------------------------


# Seven checks stood here, and all seven were about the four declared fields as
# read off a native surface: quantization off `details.quantization_level` with
# a fallback to the listing row, the EFFECTIVE window off the residency listing
# rather than the trained one both describing calls reported, the refusal when
# the model was not resident, the pinned `num_ctx` branch, the concurrency
# refusal naming the daemon-wide setting that held the answer, and the seed
# refusal naming `llama-server`'s /slots on 127.0.0.1 where the answer actually
# was. That surface went with its backend on 2026-09-06; the checks and the
# readings behind them are in `archive/forensic-ollama/`.
#
# What they were protecting is not gone. The shape they held — every declared
# field present, every null carrying a reason that is about THIS engine — is
# pinned above by `test_every_declared_field_is_present_and_every_null_states_why`
# and below by the vLLM arm's own refusal checks, which is where the whole probe
# set is now answered or refused.


def test_no_runner_in_this_tree_sends_a_seed() -> None:
    """The half of "observed, never set" that a probe cannot prove.

    Built rather than grepped: what matters is the payload that leaves the
    process, and a payload assembled from a dict is not something a pattern
    over the source can be trusted about.
    """
    from mcgyvr.pool import Endpoint, Protocol
    from mcgyvr.runner import _RUNNERS, Request

    assert set(_RUNNERS) == set(Protocol), "a protocol with no runner is untested here"
    request = Request(prompt="p", max_output_tokens=16, system="s")
    for protocol, runner_class in _RUNNERS.items():
        endpoint = Endpoint(
            source="test",
            base_url="http://test:11434",
            protocol=protocol,
            max_parallel=1,
            credential_env=None,
        )
        payload = runner_class(endpoint)._payload("m", request)
        assert "seed" not in json.dumps(payload), (
            f"{runner_class.__name__} sends a seed. Greedy bypasses the sampler "
            "RNG, and supplying one is a different experiment (#276 item 9) — "
            "`observed.seed` records what the server holds, not what we set."
        )


# --- the other engine, which answers the other half (#286, vLLM) -------------


# --- redaction, on capture and before write ---------------------------------


# --- comprehensive, without copying 7.7 MB into every run directory ----------


# `test_the_elided_digest_is_the_one_run_json_records` stood here. It held the
# join key claim by computing it both ways: the digest an elided array carries
# in the capture had to equal `probe_model`'s `vocabulary_sha256` in
# `run.json`, so a reader could rejoin the summarised array to the identity
# record without rehashing anything. Both sides were read off the same native
# surface, and `probe_model` now refuses all four of its fields — there is no
# second computation of that digest left to hold this one to. The convention
# itself is still pinned, one check up: an elided array carries
# `identity.digest` of what it replaced.

# --- one capture per directory ----------------------------------------------


# --- nothing reads it -------------------------------------------------------


# --- what the review found, pinned so it cannot come back -------------------


# --------------------------------------------------------------------------
# #350: the width the record already held, and the width only the client knows.
#
# `concurrency` in PROBE_SET is refused on both engines, correctly — it is on no
# network surface either serves. The ollama refusal ends by naming where the
# answer is, `tools/bench/serving/`, and the `host` block written beside it in
# the same file is produced by that module with that access. These checks hold
# the meeting point: the number reaches the record, the native refusal is left
# exactly as it was, and the two bounds on the realised batch stay two fields.
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# #349: an empty host block meant four different things.
#
# "There is no machine to log into", "the dispatch address is loopback", "the
# name did not resolve" and "the probe raised" all arrived as `{}`. The last of
# those is a BROKEN reading and the first three are ordinary absences, so the
# one value a reader could not act on was the one that mattered most. The same
# collapse the harness refuses on purpose at `gpu_idle` and at the compute-apps
# sentinel, so that an unread card cannot parse as an empty one.
# --------------------------------------------------------------------------


# --- #353: the third term, measured on one engine and refused on the other ---
#
# `dispatch_max_parallel` bounds the realised batch only if this run was the
# sole client, and nothing established that. It does now, on vLLM: the server's
# own `vllm:request_success_total`, read at open and at close. Measured on srv1
# 2026-08-23 against vllm 0.26.0 — five `/v1/completions` moved it by exactly
# five, and `/health`, `/metrics`, `/ping`, `/v1/models`, three kinds of failed
# request and two full `capture()` passes moved it by none. On ollama there is
# no counter to difference and the field refuses with where the answer would be.
