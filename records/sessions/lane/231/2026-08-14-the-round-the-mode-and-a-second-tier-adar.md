---
record: session/8
lane: 231
agent: adar
started: 2026-08-14
---

## Did

**Closed checks 3 and 6 of the commissioning gate, and dispatched check 5's
battery against the 7B.** Re-derive with
`uv run --no-sync python tools/bench/product.py` (the round and the tree it
pins), `tools/bench/null.py`, and `tools/bench/control.py`.

### Check 3 — the round is the unit, and the refusal is where it bites

The bench pinned `tasks_sha256` (the task set) and `bundle_sha256` (which hashes
`prompt.system` and nothing else). **Everything between them was unpinned** —
the user-message render, the reply parser, the runner, and the whole of
`Gate.run` that decides pass or fail. Two arms measured a week apart could be
scored by two different bars and laid in one table, and no manifest on disk
would have said so. That is the failure ADR-0018 names: a winning arm silently
re-baselines its own siblings.

`tools/bench/product.py` digests a declared **product surface** — every module
under `src/mcgyvr`, plus `tools/breadth/measure.py`, `tools/bundle/measure.py`,
`tools/bench/score.py`, `matrix.py` and `matrix.json`, and the digest module
itself. `tools/bench/rounds.json` is append-only and its last entry is the open
round; **`r1-commissioning`** opened 2026-08-14 at `ed508e61…` over 56 files.

Three places it acts, and only one of them is new discipline:

1. **`record_run` stamps** `round` and `product_sha256` into every bench
   manifest. Bench tiers only — a round is ADR-0018's unit for the bench, where
   arms are compared against each other; `d1`–`d3` and `pool-*` are other
   instruments, and stamping a revision they never compare across would refuse
   their resumes for a boundary that does not apply to them.
2. **`record_run` refuses** to dispatch a bench arm from a tree that has drifted
   off the open round. This is the check's teeth. A stamp records what happened;
   the refusal is what makes *"an adopted change lands at the round boundary,
   never mid-flight"* a property rather than a promise in a document. It fires
   before a token is spent, and it names which surface files moved.
3. **`report.COMPARABLE` gains both fields**, so a table spanning two revisions
   is refused where the confound would actually land.

**Two choices worth stating, because both could have gone the other way.**

*The surface is coarse rather than curated.* The obvious design is a list of the
modules a bench dispatch touches. That is the shape `COMPARABLE` already failed
at once — it named five fields, and a manifest mutated in the sixth produced a
byte-identical report with the headline unchanged. A guard that names a subset
does not refuse what it omits; it permits it silently, which reads as having
checked. The cost is real and is the one ADR-0018 admitted: an unrelated edit to
`src/` closes a round. A missed edit corrupting a contrast is not recoverable,
and a false boundary is.

*A content digest, not `git rev-parse HEAD`.* Every measurement here is
dispatched from a working directory. A commit id on a dirty tree names a
revision that was not the one under test, which is worse than naming none.

**Not asserted: that this tree matches its open round.** A round opens when a
campaign begins; between campaigns the product moves. Requiring the two to agree
at all times would mean opening a round per commit, which makes the boundary
meaningless. What is asserted at all times is that the open round says which
revision it pins, when, and why. `tools/bench/tasks/` is deliberately outside
the surface — `tasks_sha256` already pins it per run, and folding it in would
close a round every time a problem is authored, which is corpus work.

### Check 6 — the mode is recorded, not asserted

The single-tier sentence was a **string literal in two reports**, and absent
from seven other tools that produce bench figures. A literal is a claim the code
cannot check: it stays "single-tier" through the change that adds escalation,
and it is right by luck until it is silently wrong.

`tools/bench/mode.py` renders the declaration from a recorded field; the rigs
record what they did (`"mode": "single-tier"` — they dispatch one worker and
have never escalated); eight tools now declare it, and the round beside it.
`full-ladder` is declared with nothing producing it, so that whoever adds
escalation widens data rather than designing a vocabulary under time pressure.

**`test_every_figure_tool_is_classified` discovers rather than names.** Every
`*.py` under `tools/bench/` and `tools/power/` must appear in either `CHECKED`
or `NOT_A_FIGURE` with a reason. A tool added later fails the suite until
someone says which it is — the default is "must declare", not "was forgotten".

A manifest written before the field is **answered, not guessed**: no rig in this
tree has an escalation path in any revision, so `single-tier` is derivable from
the code, and the caveat is printed. The product revision is the opposite case
and is treated oppositely — `mode` is adopted forward onto an old manifest,
`product_sha256` is not, because a run measured against a revision nobody
recorded must not have today's stamped onto it.

### Check 5 — the battery re-ran, and the second tier came out uncommissioned

`qwen2.5-coder:7b` on **srv2** @ ollama 0.32.5 — the same host and build check 1
ran the 1.5B on. srv1 untouched. Greedy, cap 2048, 514 cells an arm:

| run | condition | purpose |
|---|---|---|
| `bench-null-gate-7b-a-2026-08-14` | stock | check 1 replicate A |
| `bench-null-gate-7b-b-2026-08-14` | stock | check 1 replicate B |
| `bench-control-norule-7b-2026-08-14` | norule | check 2's positive control |

1,542 dispatches over 2h10m, all six passes back to back in one script so the
two null replicates share **one backend session** — no unload, no build change,
no host change, which is what check 1's "one backend session" means. These are
the first measurements on disk carrying a round stamp. Rig health was clean on
every pass: zero truncations, zero parse refusals, zero dispatch losses.

**Checks 1 and 4 transfer. Check 2 does not.**

*The null:* `d` = **0 of 514** paired cells, acceptance drift zero, per-arm
Wilson upper **1.47pp**, both entries added to `reproducibility.json` as
measured here rather than transferred (ADR-0019 D2). They carry the same number
as the 1.5B's because both pairs measured `d` = 0 over 257 cells and the bound
is the interval's upper limit, not the point; they would have parted the moment
either pair flipped a cell.

> Against the expectation this pair was run under: the 7B is byte-identical on
> **97.9%** of cells to the 1.5B's 88.9%. The bigger model drifted *less* in
> text, not more. The prediction — a higher pass rate puts more cells near the
> acceptance boundary and therefore raises `d` — is not what governed at this
> tier, and it was stated in this lane before the pair ran.

*The control, inert on both arms:*

| arm | stock | norule | delta | m | p |
|---|---:|---:|---:|---:|---:|
| `bench-py` | 67/257 | 64/257 | −1.2pp *(inside the bound)* | 15 (6/9) | 0.61 |
| `bench-ts` | 51/257 | 55/257 | **+1.6pp** *(wrong direction)* | 10 (7/3) | 0.34 |
| pooled | 118/514 | 119/514 | +0.2pp | 25 (13/12) | 1.00 |

Correctness only (`Gate(adapters=())`, `lintless.py`) says the same thing, so
the full bar is not masking a correctness effect: py 138 → 133 (−1.9pp, m = 25,
p = 0.42), ts 127 → 136 (**+3.5pp**, m = 21, p = 0.078).

**This is a null, not a broken run and not an underpowered one.** The ablation
landed on all 257 cells per arm, each exactly −45 prompt tokens. m = 25
discordant pairs splitting 13/12 is balanced; the effect this control recovered
at the 1.5B — `bench-ts`, m = 40 splitting 34/6, −8.6pp — could not have hidden
in it.

**The mechanism says why: the rule's value decays with capability.**

| rung change (norule − stock) | 1.5B py | 1.5B ts | 7B py | 7B ts |
|---|---:|---:|---:|---:|
| lint findings | +43 | **+124** | +11 | +1 |
| any adapter finding | +34 | +42 | +7 | −5 |
| reached acceptance | −34 | −42 | −7 | **+5** |

The 7B emits conformant output without being told to. That is a finding about
**the control**, not about the bench: the instrument measured a real thing
precisely (its own null is zero at this tier), and what it found is that the
known effect is not present here to be found.

**So the second tier is uncommissioned** — the same status and the same cause as
`bench-py` at the 1.5B. The gate now has a positive control that works on
exactly **one of four** (tier × arm) cells. Acceptance item 5 is met as written:
the battery re-ran at a second tier with no design change, and the two tool
defects that would have forced a redesign were fixed rather than worked around.
The item's *purpose* — showing the instrument fit at a second tier — is not
achieved by this control, and no wording of item 5 could have been satisfied by
a control that is absent at the tier it is asked about.

### Three tool defects check 5 surfaced, all in the direction of looking checked

Every one of these is invisible until a second tier exists, which is the
argument for check 5 independent of what it measured.

1. **`control.py` named its three run directories as constants**, so a second
   tier meant forking the file — at which point "no design change" stops being
   something a reader can check. They are arguments now with the pre-registered
   runs as defaults. The pre-registration fixes the *design* (comparator is run
   A, run B is a sensitivity check, `m >= 6` or no p-value), and none of that
   moves with `--stock`. Same change to `lintless.py`, which additionally
   printed the 1.5B's full-bar figures as context beside whatever pair it was
   re-scoring.
2. **`control.py` carried `BOUND_PP = 1.47`**, which is the 1.5B's bound.
   Annotating a 7B contrast "INSIDE the declared bound" with it is exactly the
   borrowing ADR-0019 D2 forbids. It is looked up per (model, tier,
   `gate_rungs`, `serving_build`) now, and a tier with no null declared gets
   **no annotation at all** rather than a borrowed one. Verified unchanged on
   the 1.5B: −3.1pp, m = 14 on `bench-py`.
3. **`tools/power/report.py` served the superseded null as the answer.** Its
   `BENCH_REPLICATES` still pointed at the 2026-08-12 pair, measured under the
   acceptance command alone — `Gate.run` short-circuits, so a lint-rejected
   candidate never ran its test and that figure cannot be recomputed into this
   bar. It read `d` = 1 at 70/257 against `d` = 0 at 23/257, in the tool
   ADR-0019's D2 numbers are read from. Now the gate-scored pairs, both tiers,
   with the superseded pair named rather than deleted.

   Fixing it exposed a fourth: the pooled row keyed its maps on the **arm
   alone** (`bench-py/b002`), so the 7B's cells overwrote the 1.5B's and the row
   silently became the 7B's under a label claiming it was everything. Pooling a
   null across tiers is what D2 forbids to begin with; it is one pooled row per
   model now, and `test_the_power_reports_bench_null_pools_within_a_tier_not_across`
   fails if they ever collide again.

Merging #251 (which landed on `main` mid-lane) added a fifth, and it is this
lane's own code: `STOCK` and `NORULE` were defined in **both** `control.py` and
`lintless.py`, so repointing the control at a second tier and forgetting the
re-scorer would have re-scored one model's candidates under another's heading —
and the output would have looked fine, because both runs exist and both parse.
`STOCK` also collided with `tools/breadth/measure.py`'s *condition* name
`STOCK = "stock"`: one word for the render the matrix dispatches and for the
directory a render was measured into. The run names are `STOCK_RUN`,
`NORULE_RUN`, `SENSITIVITY_RUN` now, owned by `control.py` and imported by the
re-scorer. ADR-0026 lens 3 caught new code on its first day, which is the
argument for the lens.

And one gap in the check-4 declaration: `null.py` printed the **pooled**
interval while `reproducibility.json` keys a bound to one arm, so the two
entries on disk were computed by hand off-screen with nothing tying them to the
rows. It prints the per-arm Wilson interval now and reproduces both shipped
entries at 1.47pp exactly;
`test_the_declared_bound_is_re_derivable_from_the_runs_it_names` walks from the
declaration back to the directories it names and recomputes cells, flips and the
bound.

## Left open

- **The gate needs a positive control that survives above the floor unit, and
  this is now the only thing standing between #231 and closed.** Checks 1, 3, 4,
  5 and 6 are met; check 2 holds on one of four (tier × arm) cells. The
  output-shape rule is the wrong instrument for this: it is a *floor-unit*
  effect, and the measurement above is the evidence, not a suspicion. A control
  chosen for the 7B has to be an effect a 7B can still be missing.
- **Not `#246`** as that control, for the reason the 2026-08-13 amendment
  already gives — its +13.7pp is a *bar* effect, working by satisfying style
  rules the gate rejects on. The 7B result strengthens that: the whole
  adapter-rung mechanism is what shrank between tiers.
- **No 7B arm result is quotable** until such a control exists, on the rule this
  lane already applied to `bench-py` at the 1.5B. That is not a bar the 7B
  failed; it is a control that was never demonstrated to work there.
- **`bench-py` remains uncommissioned at the 1.5B** (2026-08-13 amendment),
  untouched by any of this.
- **The scope matcher (#248) is still unowned and still fails open.** Unrelated
  to the gate, unchanged by today.
- Whether `r1-commissioning` should be closed and re-opened now that the tools
  under `tools/bench/` have moved is a **no**: none of `control.py`,
  `lintless.py`, `null.py`, `mode.py` or `power/report.py` is in the product
  surface, and none of them can change what a worker is sent or how a candidate
  is scored. The digest is unchanged at `ed508e61`, and today's six runs all
  carry it.

next: check 2 needs a control that is present above the floor — that choice is
the owner's, and it is what #231 is now waiting on.
