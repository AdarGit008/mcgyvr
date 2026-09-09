# Step 1.1 — adversarial review of the rewrite, and what it changed

One reviewer against the diff `544c2dff..e8ea2648`, read-only on the rigs, with
instructions to assume the author was fluent and that the remaining defects are
the ones fluency hides. It returned **7 blockers, 12 defects and 10 stale-prose
findings**, most demonstrated by running code rather than argued.

**All 7 blockers and all 12 defects are fixed.** One — DE-10 — was not a bug and
is resolved by a decision instead.

## The blockers

### BL-1 — D4 withdrew a gate and replaced it with nothing

`MIN_VRAM_FRACTION` was withdrawn on the stated grounds that `claim` already
refuses a card that was not idle before the load. Step 0.1 found that check read
this backend's own *process count* under that name; step 1 changed it to read the
card — **and left it out of `check["ok"]`**. It appeared only in the reason list,
which is built after `ok` is already false for some other cause, so it could never
refuse anything on its own. The `claim` docstring asserted the opposite in as many
words.

Demonstrated: a foreign **4,916 MiB** allocation before the load, the model placed
at `vram_fraction = 0.08` — this module's own docstring case, serving happily at a
twentieth of speed — and `ok: True`. With `MIN_VRAM_FRACTION` gone and the two MoE
entries carrying no floor *by design*, nothing in the campaign caught a
contaminated card for exactly the two entries D4 exists to make measurable.

Fixed, and **tested**: `and check["card_idle_before_load"] is True`. `is True`
rather than `is not False`, because a card whose reading failed is not evidence
that the card was clean.

### BL-2 — a ramp that measured nothing reported `saturation_n: 1`

With every level but n=1 dropped, `_max_speedup` is exactly 1.0 by construction,
the degenerate-curve guard was written `< 1.0`, and the plateau is the only level
there is. Demonstrated: levels 2/4/8/16 all erroring yields
`{"n": 1, "refused": null}` with the evidence of failure demoted to a sibling
field. Fixed: fewer than two clean levels is a refusal — a curve with one point is
not a curve.

### BL-3 — the `usage` fix covered the all-or-nothing case only

`counted` was consulted as `not row.get("counted")`, so it fired only when **zero**
replies were countable. Tokens are summed over the counted replies while the wall
is the wall of all `n`, so a level where 8 of 16 replies lacked `usage` reported
**exactly half** its true throughput, with `errors: 0`, and passed as clean.
Demonstrated at `tokens_per_s` halved and `levels_dropped: []`. Fixed: any level
with `counted != ok` is dropped.

### BL-4 — the truncated curve, and the timeout that would cause it

Two findings in one. Dropping a level from the **middle** is safe (verified: the
plateau is still found against the true peak). Dropping the **highest** level
truncates the curve and recomputes the peak on what is left, so the saturation
point comes back lower with no refusal — demonstrated at `n: 4` where the truth is
≥ 8.

And it was going to happen. `_one`'s per-request cap was a flat **600 s**, set when
`RAMP_TOKENS` was 128; **D3 raised the budget 3.7x to 475 and nobody revisited the
cap**. On a one-slot server — and srv2 reports `total_slots = 1` for all ten models
— a level of `n` needs `n × 475 / rate` seconds, so 600 s silently required 12.7
tok/s at n=16 and **19.0 at n=24**. Both deep-spill models sit near that line, and
D4's withdrawal is precisely what admits them to a ramp for the first time.

Fixed both ends: the cap now scales as
`RAMP_TIMEOUT_BASE_S + n × RAMP_TOKENS / RAMP_FLOOR_TOKENS_PER_S` (floor 4 tok/s,
deliberately below anything measured — the cap bounds a hung request, it does not
score a slow one), and a curve whose **highest offered level** was dropped is
refused rather than reported.

### BL-5 — the instance matcher never matched

The child's command line carries `--model .../blobs/sha256-<hex>` and **never the
tag**, so matching by model name or by any stem of it cannot fire. Every success
came from the sole-instance fallback — which means the one case the function was
written for, two children on one card, returned `None` with a reason that was
*factually false*: "no resident child process" while two were resident. So the
co-residency entry, which runs on **both** hosts, would have lost `declared_slots`
and `serving_config` entirely. R1 is why that matters: `total_slots` is per model,
not per host, so a fallback would have been wrong there anyway.

Fixed: `blob_path()` reads the blob a tag resolves to from
`ollama show --modelfile`, and that blob appears verbatim in the command line.

### BL-6 — the co-resident neighbour would have left mid-measurement

Neighbours were loaded `keep_alive: "10m"` and then received **no traffic at all**
while the model under test was described and ramped. The D3 ramp at 475 tokens is
~8 min for the *smallest* model on the *faster* rig, before describe and the second
repeat. The neighbour was evicted part way through essentially every run, and
nothing re-read residency afterwards — so D7 item 4 would have produced a solo
measurement with `coresidency_arranged: true` written beside it.

Fixed: `keep_alive: -1`, and residency is re-read **after** the ramp; a neighbour
that left turns the row into `ramp_failed` with
`coresidency_lapsed_during_measurement`.

### BL-7 — D6's instrumentation was not implemented

D7 item 7 asks for it "throughout", and the campaign is the only chance to collect
it. Missing: the **losing ramp repeat** (discarded by `max`, when the bias `max`
introduces is on the *peak*, which is the denominator of `saturation_n`'s whole
definition — and the loser is already paid for), the **vLLM start duration**, and
the **digest duration against model size**. Per-attempt load outcomes were already
recorded.

Fixed: `ramp` returns every repeat plus a `repeat_spread` summary, `_start` returns
`start_seconds`, and `weights_sha256` returns `digest_seconds`. Zero rig time,
unrecoverable afterwards.

## The defects, in one line each

| | fix |
|---|---|
| **DE-1** the gate was `<` where D1 and its own docstring say `>` | `<=`, so a peak equal to the single-request rate is excluded as D1's table says |
| **DE-2** `readings()` computed on the *unfiltered* levels, so a row could say `saturation_n: 4` and `throughput_plateau_n: 16` about one measurement | one `usable()` definition, used by both, and `readings` states which levels it used |
| **DE-3** the `outcome` vocabulary was not the one D8 decided | `ok` / `launch_failed` / `ramp_failed` / `refused`, with the stage stated rather than inferred from which field is missing |
| **DE-4** reason codes were built and then joined into the prose | `RefusedError` carries `.reasons` as a list; `run.py` records a structured `refusal` |
| **DE-5** `ramp_repeats` missing from the conditions | added — `max` over repeats changes the peak, so the count is not decoration |
| **DE-6** `placement` had no unknown-key guard while `expect` did | whitelisted and **tested**; a typo'd `min_vram_fraction` is now a refusal, not silence |
| **DE-7** a vLLM entry declaring `placement` died on `TypeError` | `**declared`, with what it ignored written down rather than dropped |
| **DE-8** `LOAD_TIMEOUT_S` 2400 wrapped a `curl -m 3600`, so attempt 2 stacked on a still-running load | one number, with the remote cap strictly below the ssh budget |
| **DE-9** `calibrate --phase ramp` never released vLLM at the end | `finally: vllm.release(host)` — this is *exactly* the leftover step 0.1 found holding 4954 MiB |
| **DE-11** an entry naming a host outside the run was silently skipped | validated up front; a typo'd affinity was the same silent-nothing E6 exists to prevent |
| **DE-12** the sleep phase computed a verdict field and called it an assertion | the enabled arm sets `failed` when the card did not actually drop |

## DE-10 — not a defect, a decision

The reviewer measured the config at **17 host×entry cells, every one with a full
ramp**, against D7's pricing of item 1 as a survey *without* ramps — roughly twice
the priced rig time.

**Decision E13.** Concurrency stays on for every entry: per-model saturation on
both hosts *is* the cross-host replication D7 item 6 asks for, and the owner set
completeness rather than the clock as the binding constraint. But the ladder stops
at **12** for `gpt-oss:20b` and `qwen3-coder:30b`. ollama on srv2 reports
`total_slots = 1` for every model, so levels 16 and 24 are pure queueing well past
where the saturation point is found, and at those rates each costs 6–9 minutes per
repeat. This also interacts with BL-4's new rule: the curve must be measured to its
end or it is refused, so a ladder whose top a model cannot reach would refuse the
whole ramp rather than truncate it.

**The honest revised estimate: the ollama ramps alone compute to ~5.5 h** across all
cells at measured solo rates, on top of D7's ~4.7 h of vLLM matrices and ~1–1.5 h of
survey overhead. **~11–12 h, not the 8–9 h D7 estimated.** The owner set no limit;
this is stated so the number is not a surprise.

## The stale prose, which this tree counts as defects

Several of the decisions being implemented exist *because* a record said something
the code did not do, so these are not cosmetic.

- The `saturation` docstring's measured table still gave ollama's plateau as **6**;
  that was computed at 0.95, and **D2 moved the constant to 0.92 in this same
  rewrite**, where the same curve reads **4**. Corrected, with the dependency
  stated — the number is a function of the fraction, which is why the fraction
  travels with every emitted value. The `note` written into every emitted record
  repeated the same stale 6; rewritten.
- `RAMP_TOKENS` said **one** model spends the budget differently. R4 established
  **two**, and the second is on both rigs' rosters. Also corrected: 475 is an
  *interpolation* between the 128 and 512 columns, not a measured point — which is
  exactly why D7 item 6 re-runs srv1 at it.
- `calibrate.py` still carried the comment crediting the `CUDA_HOME` env block with
  fixing ten failed launches, **six lines above the E10 comment establishing that
  attribution is false**. The stale comment had outlived the fix it was the reason
  for. Removed.
- The instance matcher's comment described a match that never fired (BL-5).
- The readiness loop's new budget had no margin: `//15` gives 900 s of loop against
  a 1020 s ssh budget, which a 2 s `nvidia-smi` on a loading box is enough to
  overrun — reinstating, smaller, the mismatch the fix was for. Now `//20`.

## The coverage gap, closed

The reviewer noted that the two riskiest new behaviours — the `card_idle_before_load`
gate and the `coresident_with` path — **had no test at all**, and that one test each
would have caught both blockers. Four were added.

**They were then mutation-tested, and the first version was worthless.** Deleting
the gate under test left them passing, because the fake host matched the literal
string `"llama-server"` while the real command is `pgrep -af '[l]lama-server'` — the
bracket that stops pgrep matching itself also removes the substring. The stub
returned no children, every test refused on `no_server_child`, and the assertions
were `in` rather than `==`, so a refusal for any reason satisfied them. Fixed on
both counts, and re-verified: **deleting either gate now fails its test and only
its test.**

## What the review confirmed holds

E8 (the container filter, step 0.1's top-ranked silent failure — genuinely closed),
E9 (the `sudo` kill, with the suppressed-EPERM lie gone), E11 (`residency_contradicts_card`,
enforced rather than merely recorded), E10 (`CUDA_HOME` dropped rather than
repaired), E6 (host affinity end to end: srv1 gets 6 rows, srv2 gets 11, and the
five large models never reach srv1's 6 GB card), the `_start` readiness assertion
with its scrubbed message, D5's elision (no escape and no false positive found
across nested and unnamed cases), the fail-safe exclusion gate, the per-PID digest
script, the env-key validation, and all 11 pinned digests as well-formed with the
two cross-checkable ones matching the record.
