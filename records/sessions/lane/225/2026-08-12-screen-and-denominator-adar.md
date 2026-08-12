---
record: session/1
lane: 225
agent: adar
started: 2026-08-12
---

## Did

A review before tranche 11, at the owner's direction: challenge the campaign's
assumptions, look for prior art, explore alternatives. **No problems were
authored and the brief was not touched.** Three findings, one of which moves a
figure ADR-0021 states.

Everything below is re-derivable:

    uv run python tools/bench/redundancy.py

New in this session: `tools/bench/redundancy.py` and `tests/test_redundancy.py`.
No measurement was run — the reads are over the responsiveness run of
2026-08-11 and `admissions.jsonl`, both already in the tree.

### 1. The 8.2pp figure counts problems that are never swept

**This is the finding that matters, and it is arithmetic, not judgement.**

`split.py` sends each admitted problem to the bench half or the reserve half by
a salted hash of its id. `docs/bench-design-2026-08-10.md` states the reserve is
**"never swept in this lane: its representativeness comes from the
construction, its difficulty is never measured here, and no rig tier serves
it."** ADR-0021 says the same from the other side — *"the bench never depends on
it"* — and #222 consumes it as training material.

`f1` stands at **280 authored: 149 bench, 131 reserve (53.2% bench).** The
responsiveness run swept 135 bench-half ids and no reserve ids. So an authored
problem enters the statistic only if the split sent it to the bench.

ADR-0021's 2026-08-12 amendment fixed the `ts`/`py` denominator — 400 problems
are 800 paired cells — and **did not reach this one.** It counted both halves.
Counting only what is swept:

| authored | bench half | swept cells | MDE @ `psi_draw` = 0.659 |
|---:|---:|---:|---:|
| 280 (today) | 149 | 298 | **13.4pp** |
| 360 | 192 | 384 | 12.0pp |
| **400 (the plan)** | **213** | **426** | **11.3pp** |
| 800 | 426 | 852 | 8.0pp |

The two errors nearly cancel: doubling for arms without halving for the split
returns almost exactly the **11.8pp** alarm the amendment was believed to have
answered. **The finished 400 misses D5's +5 to +8pp rather than sitting at its
edge**, and 800 swept cells needs roughly **790 authored problems**, not 400.

This is the third instance of one defect in one chain. ADR-0021 exists because
D5 *"stated the number without stating its denominator"*; its own amendment
records that the ambiguity *"survived one level down"*. It survived two.

**Not decided here.** ADR-0021 states 8.2pp as a consequence and that figure is
now wrong as written. Whether the record is amended a third time, and whether
the 400 is re-read as 400 *bench-half* problems, is the owner's.

### 2. The sibling screen's premise, tested for the first time

The 0.70 refusal was bought by a real failure — `b080`/`b090`/`b168` were one
problem three times, `b168` scoring 0.74 of `b080`'s shape, and the gate's prose
screen could not see it. What was never checked is the premise underneath:
**that shape similarity predicts measurement redundancy.**

Over **18,090 within-arm pairs** from the responsiveness run:

- **Pearson r = −0.0126** between skeleton similarity and divergence of sampled
  pass rate, against a 95% CI of ±0.0146 around zero.
- Pairs at ≥ 0.55 diverge as much as pairs below it — 0.321 vs 0.341, with the
  difference at [−0.119, +0.078].

Of the 30 warn-band pairs tested individually with Fisher's exact test, **8 are
demonstrably different cells** and 22 prove nothing either way. The clearest is
`b340-case-flip` / `b392-cap-after` at **0.64 similarity, 8/8 against 0/8,
p < 0.001** — two problems the screen calls near-siblings and the instrument
separates completely. They differ by one loop-carried variable, a few tokens
against 84.

**Two limits, and they bind in opposite directions.**

The read is **censored at the refusal line** — no admitted pair scores ≥ 0.70,
so this says nothing about what a refused twin would have done. It bears on the
0.55 warn band, which costs an author a read every time it fires (13 times in
tranche 10). **It is not grounds for moving the refusal, and the refusal should
stay**: it catches the case that actually burned us, and it is cheap.

And the test is **one-sided**. 83 of 270 cells are pinned at 0/8 and every one
reads identically whether it is a twin or unrelated. The corpus's highest-scoring
measured pair, `b353-strip-tags` / `b425-tag-count` at 0.68, is 0/8 against 0/8
— the instrument is blindest exactly where suspicion is highest. **It can refute
redundancy for a pair. It can never establish it.** So the corpus cannot be
certified clean by this or any read we have.

### 3. Authoring is not the wall — the finish line is

Nearest-earlier-sibling score by `f1` tranche, admitted problems only:

| tranche | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---:|---:|---:|---:|---:|---:|---:|
| mean | 0.364 | 0.420 | 0.470 | 0.522 | 0.527 | 0.524 | **0.528** |
| ≥ 0.55 | 1 | 1 | 9 | 15 | 20 | 17 | 13 |

Flat for three tranches while refusals climbed 0/2/4/3/6/9. That is
**truncation, not exhaustion**: the draft distribution is shifting up, the
admitted mean stalls under the cap, rejection absorbs the difference.
Extrapolating the refusal rate (7.0% → 13.0% → 18.4%) puts the last 120
problems at roughly **172 drafts**. Costly, survivable.

Reference size does not drive collisions (flat across all four size quartiles);
shape does, mildly — `iteration` collides most at 30%, `string` least at 18%.

So the question was never whether the last 120 can be written. It is what they
buy: **2.1pp, from 13.4 to 11.3, without crossing the bar at either end.**

## Prior art

`docs/bench-shape-prior-art-2026-08-11.md` covers problem *shape*. Two
literatures it does not cover bear on this session, searched 2026-08-12 —
stated as what this search surfaced, not as a claim about the field.

**Paired-test power.** Only discordant pairs carry information; concordant pairs
must be enrolled and pay nothing ([PASS/NCSS][ncss], [Stata][stata]). That is
ADR-0019's `m >= 6` wall restated. And repeated draws per cell make it a
**clustered** design needing an intracluster-correlation adjustment, where
accuracy "is compromised for large intracluster correlation and small proportion
of discordant pairs" ([Yang et al.][icc]). **This is a caution against the
"buy draws not authoring" fallback recorded on 2026-08-12** — replication
changes the estimator, not only `n`.

**Synthetic corpus construction.** [OSS-Instruct/Magicoder][magicoder] seeds
generation from sampled open-source snippets specifically to break the
distributional bias of self-generated data; Evol-Instruct evolves difficulty
along five declared axes; [OpenCodeInstruct][oci] and Genetic-Instruct carry
dedup and decontamination as named pipeline stages. All are **training** corpus
methods. See "the reserve" below — that is where they would apply, if anywhere.

The closest mature formalism for what this campaign is hand-rolling is **item
response theory**: item *discrimination* is the neighbour of `psi`, and the test
information function is what `tools/power/` computes a special case of. Items far
above the ability range contribute ≈ 0 information — which is our 83 pinned-fail
cells in another vocabulary. Recorded as a lead, not adopted.

## Left open

**The reserve is the largest open question and it was raised here, not settled.**
`docs/bench-sourcing-2026-08-10.md` justifies adopt-nothing by the bench's role:
*"The bench is a **measurement instrument**: contamination does not merely
confound a training signal... instrument material must additionally be non-public
by construction."* The reserve is **not** an instrument — it is never swept, and
it is #222's training material. It has nonetheless been authored to the
instrument's bar, at **47% of every tranche's cost**, for a consumer that is
blocked on #231 and #221 and that states it "does not start at all" if the route
is do-not-train.

Assigning the remaining problems to the bench half would take 400 authored from
11.3pp to **10.0pp**, and the 8pp bar from ~790 authored to ~560. The cost is
real and must be stated with it: the halves would stop being exchangeable, which
is the "difficulty-representative by construction" property #222 wanted. A
prospective, content-blind, declared change — but made *after* a measurement,
which is the ordering `split.py`'s docstring exists to protect.

**Also open, in the order they should be answered:**

1. **#231** — the real per-lever `psi`. `psi_draw` = 0.659 is resampling
   sensitivity and the contrasts that matter run greedy, which is deterministic.
   At `psi` = 0.35 the same 400 problems resolve ~8.2pp and this session's first
   finding stops binding. It costs rig time, which is the spare axis. **Nothing
   about the campaign's future should be decided before it reports.**
2. **A behaviour-aware re-score.** The screen erases identifiers to `v` over a
   45-token allowlist, so it cannot represent the distinction the instrument
   measures — `b340`/`b392` is the proof. Re-scoring the corpus under a skeleton
   that keeps loop-carried state, branch count and early-exit structure would
   show whether the thinning is a property of the material or of the encoding.
   No rig time.
3. **The 0.55 warn band.** No measured support in the range it fires. The 0.70
   refusal keeps its justification and should stay.
4. **ADR-0021's third amendment**, if the owner wants the 8.2pp consequence
   corrected in the record rather than only here.

**Authoring stays paused.** `f1` is at 280 of 400, the brief is untouched, and
nothing in this session re-aims it.

next: #231 — and it needs a base. `tools/bench/` does not exist on `origin/main`
at all (`2ab4c988`); the whole bench, gate, emitter, split rule and both
measurement tools are this lane's 38 commits. #231 cannot commission a bench
that is not there, so it branches off a landed `lane/225` rather than off `main`
as it stands.

[ncss]: https://www.ncss.com/wp-content/themes/ncss/pdf/Procedures/PASS/Tests_for_Two_Correlated_Proportions-McNemar_Test.pdf
[stata]: https://www.stata.com/manuals/pss-2powerpairedproportions.pdf
[icc]: https://pubmed.ncbi.nlm.nih.gov/30288765/
[magicoder]: https://arxiv.org/pdf/2312.02120
[oci]: https://arxiv.org/pdf/2504.04030
