# ADR-0041 — placement is semantic until a placement null shows it neutral

Status: Accepted
Supersedes: none
Superseded-by: none
Amends: none — `tools/bench/serving/fingerprint.py` carried a classification
with no decision record behind it; this record replaces the classification
and is the first decision on the question
Relates: ADR-0037 (a finding is a check; closing without fixing is a dated
xfail — behaviour 10 stays one, on a measurement now), ADR-0040 (D5: a
one-armed cell is first class — a floor measured at one `ncmoe` is a cell,
not a comparison), ADR-0027 (a null carries the reason it is null),
srv1-kernel-arms PLAN.md behaviours 9 and 10
Date: 2026-09-03
Issue: srv1-kernel-arms step 6 (PR #402, the measurement; the PR carrying
this record, the retirement)

## Context

`fingerprint.py` splits a serving configuration into a semantic half (what
the model emits) and an operational half (how fast, where). Two runs are
comparable on output only if their semantic digests match. Since the module
existed, four placement keys — `n_gpu_layers`, `n_cpu_moe`, `threads`,
`mmap` — sat in the operational half under one argument:

> Placement and parallelism: WHERE a tensor is computed, not WHAT is emitted.
> ... None of them alters the token distribution, so none belongs in the
> semantic pin — and putting them there would declare two cells of one model
> at two offload settings "incomparable on output", which is exactly the
> comparison this campaign exists to make.

That is a fiat: nothing had measured it. The ncmoe floor programme (step 9,
behaviour 9) rests on it — a floor is the lowest `--n-cpu-moe` at which a
model serves on the card, and it is worth quoting only if the outputs at the
floor are the outputs off it. Behaviour 10's test was written to demand the
measurement and parked as a dated xfail until it existed (ADR-0037).

**Measured 2026-09-02** (`records/evidence/2026-09-02-srv1-kernel-arms/placement-null.json`,
through the door under round r2-02-09-2026): Ling-3.0-tiny on the L3 build,
the 257-cell bench-py tier, `ncmoe=0` against `ncmoe=99`, same prompts, same
sampler, greedy read.

| pair | flips / cells | bytes changed |
|---|---|---|
| `ncmoe=0` twice (the build's own null) | 0 / 257, bound 1.47pp | — |
| `ncmoe=0` vs `ncmoe=99` | 9 / 257 = 3.50pp | 27 / 257 |

Acceptance drift 0 in both: identical bytes never scored differently, so the
gate is stable and the 9 are the model. The chance that 9 of 257 is noise at
the top of the null's interval is 1.5%; Fisher's exact test on 0/257 against
9/257 gives 0.4%.

A second pass at `ncmoe=99` would tighten the noise estimate for that one
value and say nothing about `ncmoe=6`, `24`, or `-ngl 20`. The fiat claims
all of them at once, from no measurement; one measurement against it is
enough to retire it, and no number of measurements at one value would
reinstate it.

## Decision

> **DECIDED (2026-09-03, owner).** The placement fiat is retired. A placement
> key is **semantic** until a placement null on that build has shown it
> neutral; none has.
>
> 1. **`n_gpu_layers`, `n_cpu_moe`, `threads` and `mmap` move to
>    `fingerprint.SEMANTIC`.** Two cells of one model at two offload settings
>    are incomparable on output by digest, because they were measured to be.
>    The argument that put them in the operational half was one argument for
>    all four and is false for the one value measured; the other three are
>    unmeasured, and unmeasured is not neutral.
> 2. **Neutrality is earned per key, per build, by a placement null** — the
>    instrument step 6 already is: two identical passes for the bound, one
>    pass at the other setting, `flips` counted by `null.py`. A key whose
>    null shows 0 flips inside the bound may move back, for that build, with
>    the file named. There is no other way back.
> 3. **An ncmoe floor is a configuration, not a placement.** Behaviour 9's
>    floor rows stand as measurements of fit and throughput at their own
>    `ncmoe`; any claim that the floor "costs nothing" on output is refused
>    until rule 2 has been paid for that floor.
> 4. **An engine that cannot read a placement key reports the gap, not a
>    classification.** llama.cpp's `/props` reports none of the four;
>    `backends/llamacpp.py` records them under `uncovered_by_digest` and says
>    that two cells differing only in offload share its digest and are not
>    comparable on output. It does not type the launch flags into the digest.
> 5. **Behaviour 10 stays a strict, dated xfail** whose reason is the
>    measurement (ADR-0037). It turns green when placement is shown to agree
>    on the build it names, never by editing the classification.

## Consequences

- **Existing semantic digests do not change.** No recorded configuration in
  `records/` reached `fingerprint()` with a placement key in it: the llama.cpp
  backend held them out, and the vLLM backend has none. New runs that pass
  one will digest differently from old ones — which is the point.
- **Step 9's floors are unquoted on output.** The 2026-09-01 "srv2's
  `--n-cpu-moe` floor is 6, worth ~2.4x" is a fit-and-throughput claim; the
  "cost nothing" half is open until a null at `ncmoe=6` on that build.
- **The comparison the fiat protected is still possible**, one null per cell:
  the price of comparing two placements on output is measuring that they
  agree, which is 35 minutes of srv1 per setting.

## Checks

- `tests/test_placement_is_not_declared_output_neutral_without_a_measurement.py::test_the_fiat_is_retired_and_placement_is_semantic`
  — rule 1: the fiat text is gone, the four keys are semantic, two placements
  of one model digest differently.
- `tests/test_placement_is_not_declared_output_neutral_without_a_measurement.py::test_the_llamacpp_backend_no_longer_calls_the_gap_a_classification`
  — rule 4.
- `tests/test_placement_is_not_declared_output_neutral_without_a_measurement.py::test_two_offload_settings_of_one_model_are_shown_to_agree`
  — rule 5: strict xfail on the measurement.
- `tests/test_serving.py::test_no_key_is_both_semantic_and_operational` — the
  move left no key in both sets.
