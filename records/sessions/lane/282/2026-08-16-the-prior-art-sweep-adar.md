---
record: session/1
lane: lane/282
agent: adar
started: 2026-08-16T14:00:00Z
---

# Session — lane/282 — 2026-08-16 — the prior-art sweep

## Did

Swept the ten proposals of the hybrid-orchestration dig one by one: verified or
falsified each against its pinned source and against this repository, decided
each with the owner, and recorded the rejections. The evidence is
`docs/hybrid-orchestration-prior-art-2026-08-16.md`; the decisions are
ADR-0028 through ADR-0031; #282 is the anchor.

**Nothing was taken on the strength of a brief.** Every cited source path was
re-fetched at its pinned commit and read, every mcgyvr-side claim re-checked
against `d67dab86`, both cited abstracts read directly. Six of the ten verdicts
turned on something the briefs did not have — which is ADR-0004 doing exactly
what it was written for, on unusually good research.

**The measurement that decided proposal 8.** A pre-gate heuristic verifier
scores a reply's text — refusals, uncertainty, JSON validity, length — before
anything expensive runs. It is cheap, clean, and obviously useful in the product
it comes from. Rather than argue it, all 23,902 candidates this project has
recorded across 31 run directories were cross-tabulated, transport-level
`stop_reason` against the reply parser's `parse_error`:

| stop_reason | parse_error | n | share |
|---|---|---:|---:|
| complete | — | 23,483 | 98.25% |
| truncated | `incomplete-reply` | 386 | 1.62% |
| complete | `unterminated-fence` | 16 | 0.067% |
| complete | `no-fenced-block` | 10 | 0.042% |
| complete | `ambiguous-blocks` | 7 | 0.029% |

`truncated` and `incomplete-reply` are an **exact partition** — the same event
under two names, so the runner already reports it for free at the transport
layer. That leaves **33 rows, 0.138%**, as the whole ceiling of what a
reply-shape heuristic could newly catch, and **no refusal has ever occurred**
in 23,902 replies although refusal patterns are the proposed verifier's core.
Against #246's measured +13.7pp at the same pipeline stage, two orders of
magnitude. This is #212's verdict confirmed at scale from the other direction.

Worth naming the general move: a proposal about model output can be settled
against `records/measurements/` in one query, because this project keeps every
reply it scores. Do that before designing.

**What verification changed.** The keyword classifier is 1,974 lines, not a
small regex scorer, and its weights, tier boundaries and token thresholds carry
no accuracy or calibration figure anywhere — the same defect the briefs flagged
against its sibling and did not apply to it. The trained router's headline
figure ("22%") is in neither the repository nor either cited abstract; the real
figures are 60% and 40%. The serving bench already exists as CON-04/CON-05 in
the capability table. The contamination audit already exists in
`tools/problems/admit.py`, and screens at admission rather than at release, which
is earlier. Three issue references were wrong: #152 is the retry-rescue
re-verification rather than a retry-policy gap, and #22 and #153 are closed.

**The finding outside the ten.** All eleven briefs name this project's edge as
"a *measured* HumanEval+ capability table with provenance". ADR-0020 retired it
on 2026-08-10 — six days before the dig ran, five commits before the baseline it
read. The code half is #277; the half with no owner is that
`initialize.py:332` and `propose.py:370` still quote the figure to the user as
the reason for a binding, with "measured on" in the string. Added to #277 rather
than filed separately, because what replaces the ordering also replaces the
sentence.

**Filed:** #279 — `Availability` is probe-only, so no dispatch failure ever
reaches it and a source that passes the probe then fails everything is re-paid
once per contract; `capacity.py:77` already names the seam and has nothing on the
other side of it. #280 — three documents describe a ripgrep index that does not
exist in `src/`, one of them a founding boundary record.

**Commented:** #16 (keyword vocabularies as seed prior art, weights explicitly
excluded), #277, #69 (the price-table blocker is a provenance rule, not the
data), #254 (its real population is the 33 rows, 16 of them `unterminated-fence`),
#268 (the NFC + casefold + strip recipe as the exact-match floor under a
behavioural screen), #265 (emerge reached content-addressed run identity
independently — weak external evidence that the direction is ordinary).

**Nothing dispatched.** The freeze declared in lane/276 holds: `r1-commissioning`
is open and every identity change is still to land, so no run was started and no
rig was touched. This lane is docs only; `src/` and `tools/` are unchanged.

**ADR-0027 was yielded to lane/265**, which is in flight with the run-identity
contract and whose own record is dated two days before this lane's. The
collision was silent by construction: two ADRs numbered 0027 under different
filenames merge without a git conflict, so nothing would have reported it. This
lane's four records were renumbered 0028–0031. Worth noting as a gap in the
gate — the baseline checks branch placement and record discipline, and does not
check that a decision number is unique across open lanes.

## Left open

**The two survivors are unstarted.** #279 (the availability failure counter) and
#280 (the ripgrep drift) both carry their plan in the issue body and neither has
a lane.

**Three deferrals name their own trigger, and none is a dependency edge here.**
#16 waits on #233 before any risk floor is worth writing; #69 needs a provenance
rule for a price before the data is worth vendoring; a learned router waits on
`route.py`'s inspectability rule being revisited in its own record, which nothing
currently proposes.

**One question was raised and not answered.** ADR-0030 declines prefix-affinity
routing partly because CON-05's "should be substantially larger" is a projection
at our real ~2 KB prompt size. Measuring the hit rate at that size is a small rig
task that would turn the projection into a number, and it is not filed — because
under the freeze it cannot be scheduled, and after the freeze #272 and #224 have
the prior claim on rig time.

**The gate does not check what this lane nearly broke.** Decision-number
uniqueness across concurrent lanes is unenforced; filed upstream as
AdarGit008/baseline-skill#49, which also carries a second finding — the lane
rules SKIP on the `pull_request` event and only fire on `push`, so a PR-event
check can read green while the gate is red.

next: land the identity changes as one range per lane/276's sequencing, then open r2 — and work #272 before scheduling #224's S1/S2, since it decides whether they earn the rig time at all
