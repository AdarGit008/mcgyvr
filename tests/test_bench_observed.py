"""The `observed` block records what the server holds, never what we set (#286).

The one check here is the half of "observed, never set" that a probe cannot
prove: no runner in this tree sends a seed.
"""

from __future__ import annotations

import json

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


def test_no_runner_in_this_tree_sends_a_seed() -> None:
    """The half of "observed, never set" that a probe cannot prove.

    Built rather than grepped: what matters is the payload that leaves the
    process, and a payload assembled from a dict is not something a pattern
    over the source can be trusted about.
    """
    from mcgyvr.local_pool import Endpoint, Protocol
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
