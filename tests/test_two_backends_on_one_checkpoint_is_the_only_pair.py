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
``2026-08-24-knob-surface/surface.md`` — against an AWQ checkpoint, which is the
kernel rejecting uint4 rather than the flag being absent; the flag itself is in
v0.26.0 with ``exllama`` among its choices. And srv1 holds no GPTQ file at all,
so B2 sits behind a fetch and may still not come up. So a test that demands a B2
ladder could only be made green by faking a row: **a reasoned refusal is a
result.**

Which is a claim about what the file *says*, not about what it omits. Guideline
8 buys B2 an exemption from the CONFIG rules its partner obeys, and the price of
that exemption is a REFUSED row that names the quant format it was offered,
carries the reason, and was believed only after three attempts. An arm that is
simply missing has paid nothing and is read as a gap, not a result.

The pool matters too. Under ``--gpu-memory-utilization`` the KV cache is whatever
survives the weights, so if the two kernels' scratch buffers differ the pools
differ, the width gate drops different rungs, and the comparison is between two
schedulers rather than two kernels.
"""

from __future__ import annotations

import pytest

from tests.sweeprows import Row, owed

VLLM = "srv1-vllm-arms.tsv"
HELD = ("model", "weights_sha256", "img", "util", "len", "seqs", "kv")


def a_recorded_refusal(row: Row) -> None:
    """Guideline 8's bar, and the only thing that stands in for a CONFIG row.

    A ``CONFIG`` row is printed after a launch and a warm-up; an engine that
    never came up cannot honestly produce one, and a ``kernel_observed=`` on it
    would be a value for a kernel that never ran. So B2 is allowed to have no
    CONFIG — but only by saying so on a row of its own. Silence is not a
    refusal: a driver that dropped the arm, a fetch that never finished and a
    kernel that cannot implement the layer all leave an identical hole.
    """
    assert len(" ".join(row.tail)) > 40, f"line {row.lineno}: refused, reason lost"
    assert row.fields.get("checkpoint_quant"), (
        f"line {row.lineno}: a refusal that does not name the quant format it "
        "was offered cannot distinguish 'wrong checkpoint' from 'no kernel'"
    )
    assert int(row.fields.get("tries", "1")) >= 3, (
        f"line {row.lineno}: believed after {row.fields.get('tries')} attempt(s). "
        "Two REFUSED rows on 2026-09-01 turned out to be a dangling HF-blob "
        "symlink read as a capability limit."
    )


@pytest.mark.xfail(strict=True, reason="2026-09-02: owed — vLLM pair unrun")
def test_the_two_arms_hold_everything_but_the_kernel_fixed() -> None:
    """Held fixed across the pair — but only where there is a pair to hold.

    B1 must launch: Marlin is the path this card is known to take, and without
    it there is no baseline and no contrast. B2 may not, and guideline 8 says
    that is a result. So the seven held fields are compared when both arms
    produced a CONFIG row, and a B2 that produced none must have produced a
    refusal instead, to that refusal's own standard.
    """
    sweep = owed(VLLM)
    configs = {r.fields.get("arm", "?"): r for r in sweep.of_kind("CONFIG")}
    refusals = {r.fields.get("arm", "?"): r for r in sweep.of_kind("REFUSED")}
    assert "B1" in configs, (
        f"only {sorted(configs)} launched. B1 is the default Marlin path; if it "
        "did not come up there is nothing to hold fixed and nothing to contrast."
    )
    assert "B2" in configs or "B2" in refusals, (
        "B2 has neither a CONFIG row nor a REFUSED row. A dropped arm and a "
        "refused arm leave the same hole in a file, and only one of them is a "
        "result — guideline 8 exempts a refusal from CONFIG, not from the record."
    )
    if "B2" not in configs:
        a_recorded_refusal(refusals["B2"])
        return
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
    a cache key, and silently ignored under the V2 runner.

    Read from the engine's own line — ``Using {Marlin,Exllama}LinearKernel for
    AutoGPTQLinearMethod`` — so an arm that never came up has no value to read
    and is skipped rather than assigned one. That skip is guideline 8's, not a
    loophole: the arm it excuses has already been made to produce a REFUSED row
    by ``test_the_two_arms_hold_everything_but_the_kernel_fixed``."""
    sweep = owed(VLLM)
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
    sweep = owed(VLLM)
    levels = [r for r in sweep.levels() if r.fields.get("arm") == "B2"]
    refusals = [r for r in sweep.of_kind("REFUSED") if r.fields.get("arm") == "B2"]
    assert levels or refusals, "B2 appears nowhere — it was dropped, not measured"
    for row in refusals:
        a_recorded_refusal(row)


@pytest.mark.xfail(strict=True, reason="2026-09-02: owed — vLLM pair unrun")
def test_the_hypothesis_is_answered_by_a_row_that_exists() -> None:
    sweep = owed(VLLM)
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
