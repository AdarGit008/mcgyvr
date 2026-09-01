"""If the vLLM arms differ in two things, they measure neither.

The question is a capability one and it is asked *inside vLLM only*: Marlin's
sm75 path is ``mma.sync`` tensor-core PTX, which TU116 executes microcoded, so
does vLLM offer this card a path that is not that, and what does it cost? The
clean contrast holds the checkpoint fixed and moves only the kernel.

The earlier reading that vLLM is 2.6x slower than llama.cpp on srv1 and 2.0x
faster on srv2 is **not** this hypothesis and is not evidence for it. The two
engines differ in scheduler, batching, KV management and quantisation format;
that ratio measures two stacks. No row in this file may be compared with a
llama.cpp row.

Two facts constrain the design. srv1 has already recorded
``--linear-backend exllama`` refusing —
``ExllamaLinearKernel cannot implement due to: Quant t...`` in
``2026-08-24-knob-surface/surface.md`` — against an AWQ checkpoint, and exllama
is a GPTQ kernel. And srv1's only GPTQ file is ``Qwen1.5-MoE-A2.7B-Chat-GPTQ-Int4``,
a *MoE*, for which exllama has no fused path. So a test that demands a B2 ladder
could only be made green by faking a row: **a reasoned refusal is a result.**

The pool matters too. Under ``--gpu-memory-utilization`` the KV cache is whatever
survives the weights, so if the two kernels' scratch buffers differ the pools
differ, the width gate drops different rungs, and the comparison is between two
schedulers rather than two kernels.
"""

from __future__ import annotations

import pytest

from tests.sweeprows import RUN, artifact

BEHAVIOUR = "run tools/runs/srv1-vllm-arms.sh"
VLLM = RUN / "srv1-vllm-arms.tsv"
HELD = ("model", "weights_sha256", "img", "util", "len", "seqs", "kv")


@pytest.mark.xfail(strict=True, reason="2026-09-02: owed — vLLM pair unrun")
def test_the_two_arms_hold_everything_but_the_kernel_fixed() -> None:
    sweep = artifact(VLLM, BEHAVIOUR)
    configs = {r.fields.get("arm", "?"): r for r in sweep.of_kind("CONFIG")}
    assert {"B1", "B2"} <= set(configs), f"only {sorted(configs)} launched"
    for field in HELD:
        assert configs["B1"].fields.get(field) == configs["B2"].fields.get(field), (
            f"{field}: B1 {configs['B1'].fields.get(field)!r} vs B2 "
            f"{configs['B2'].fields.get(field)!r}. Two arms that differ in two "
            "things measure neither."
        )


@pytest.mark.xfail(strict=True, reason="2026-09-02: owed — vLLM pair unrun")
def test_the_engine_log_names_the_kernel_that_actually_ran() -> None:
    """A flag that parses is not a kernel that ran. This repo has already been
    burned by ``--cpu-offload-params experts``, which vLLM accepted, hashed into
    a cache key, and silently ignored under the V2 runner."""
    sweep = artifact(VLLM, BEHAVIOUR)
    configs = {r.fields.get("arm", "?"): r for r in sweep.of_kind("CONFIG")}
    for arm, expected in (("B1", "marlin"), ("B2", "exllama")):
        if arm not in configs:
            continue
        observed = configs[arm].fields.get("kernel_observed", "")
        assert expected in observed.lower(), (
            f"{arm}: the engine log reports kernel {observed!r}, not {expected!r}"
        )


@pytest.mark.xfail(strict=True, reason="2026-09-02: owed — vLLM pair unrun")
def test_a_refusal_is_recorded_as_the_result_it_is() -> None:
    sweep = artifact(VLLM, BEHAVIOUR)
    levels = [r for r in sweep.levels() if r.fields.get("arm") == "B2"]
    refusals = [r for r in sweep.of_kind("REFUSED") if r.fields.get("arm") == "B2"]
    assert levels or refusals, "B2 appears nowhere — it was dropped, not measured"
    for row in refusals:
        assert len(" ".join(row.tail)) > 40, f"line {row.lineno}: refused, reason lost"
        assert row.fields.get("checkpoint_quant"), (
            f"line {row.lineno}: a refusal that does not name the quant format it "
            "was offered cannot distinguish 'wrong checkpoint' from 'no kernel'"
        )


@pytest.mark.xfail(strict=True, reason="2026-09-02: owed — vLLM pair unrun")
def test_the_hypothesis_is_answered_by_a_row_that_exists() -> None:
    sweep = artifact(VLLM, BEHAVIOUR)
    verdict = sweep.stamp("VERDICT")
    assert verdict.get("hypothesis") == "tensor-core-emulation"
    assert verdict.get("status") in {"supported", "refuted", "unresolved"}
    cited = int(verdict.get("cited_line", "0"))
    assert any(r.lineno == cited for r in sweep.rows), (
        f"the verdict cites line {cited}, which is not a row. A claim with no "
        "artifact is not a finding."
    )
    refused = any(r.fields.get("arm") == "B2" for r in sweep.of_kind("REFUSED"))
    assert not (refused and verdict["status"] == "supported"), (
        "B2 never launched and the file calls the hypothesis supported. A backend "
        "that cannot implement the layer is evidence that the alternative is "
        "unavailable here, not that emulation is the cause."
    )
