"""``C`` steps once an expert block is on the host, and holds after that.

``C`` is not the same at every placement. On srv2, deepseek-coder-v2-16b
(``records/measurements/measuring-gaps-2026-09-10/`` Q4 and Q6), ``C`` reads
lower at ncmoe 0 than at 13 and 26, which agree. The engine's own ``CUDA0
compute buffer size`` accounts for the difference: it roughly doubles as soon as
one expert is on the host, and is flat after. llama.cpp's op offload copies a
host-stored expert tensor into the device compute buffer for a large batch; with
``--no-op-offload`` the step is gone, and that flag is banned for what it costs
prefill.

The invariance tests in ``tests/test_serving_vramfit.py`` (KAT and nemotron)
hold because every one of their placements keeps experts on the host. A probe
reads ``C`` for the placements on its own side of that step, and a probe taken
with every expert on the card under-states every placement that offloads.
"""

from __future__ import annotations

from mcgyvr.serving import vramfit


def test_vramfit_no_longer_says_one_probe_at_any_placement_fixes_the_constant() -> None:
    """The docstring is the rule a caller probes by, so it has to be the true one."""
    module = vramfit.__doc__ or ""
    probe = vramfit.constant_from_probe.__doc__ or ""
    assert "does not move with" not in module
    assert "at any placement" not in module
    assert "op offload" in module
    assert "on the host" in probe, (
        "constant_from_probe must say a probe is taken with an expert on the host"
    )
