# ADR-0038 — a machine has no role, and the question approves its own scope

Status: Accepted
Supersedes: none
Superseded-by: none
Amends: ADR-0024 — clauses 1 and 2 are withdrawn. Clauses 3 and 4 stand and are
relied on here
Relates: ADR-0027 (D2's three states and D3's "a field the guard cannot read is
a refusal, not a match", reused verbatim by the comparison check below),
ADR-0015 (fail closed in effect, and the ledger still says what happened),
ADR-0026 (lens 1: record the unrecoverable), ADR-0030 (clause 1: no second
serving instrument is built), #335 (the run contract this record sits under),
#329 (the cross-rig claim ADR-0024 clause 2 forbade)
Date: 2026-08-22
Issue: #335

## Context

ADR-0024 gave the two rigs roles. srv2 was **the measurement rig** — "every
number that will be compared to another number is served from it" — and srv1
was **capacity**, whose "rates produced there are not compared across hosts".

That was correct when it was written, and its reason is stated in its own
clause 3: **the serving build is run identity.** The rigs ran different builds,
so a cross-host rate compared two instruments as if they were one. The roles
were a way of forbidding that comparison without having to detect it.

Three things have changed.

**The premise has partly dissolved.** On 2026-08-22 both rigs were brought to
one ollama build (0.32.15, from 0.32.4 and 0.32.5) and one vLLM container,
image digest `sha256:ffb2d59b1c059a5bd8d781320c9f5189de8293693b7d95da54befddaa54abf52`,
byte-identical on both. The two builds' declared surfaces were compared by
diffing `vllm serve --help=all`: 275 flags, 223 defaults, zero differences.
What still differs is the card (GTX 1660 SUPER against RTX 3060) and the driver
(580.173.02 against 595.84, which no container pins) — and those are the
*subject* of a cross-rig question, not a confound in it.

**The roles now forbid the work.** #329 exists to settle whether a width-16 gap
of 23% against 96% is hardware or configuration. That is a cross-host rate by
construction, and ADR-0024 clause 2 forbids it. A campaign of co-residency
questions is in the same position. A decision that forbids the question the
project is trying to answer has outlived its reason.

**A role is a static answer to a per-question fact.** Whether a comparison is
legitimate depends on what is being compared and on what differs between the
two measurements — not on which machine produced them. srv1's 6 GB card cannot
hold the 14B; that is a capability fact, discovered per question, and it needs
no role to be true.

## Decision

> **DECIDED (2026-08-22, owner).**
>
> **D1 — a machine has no role.** ADR-0024 clauses 1 and 2 are withdrawn. There
> is no measurement rig and no capacity rig. No host is barred from producing a
> number that is compared to another number, and no host is designated as the
> only one that may.
>
> **D2 — the question approves its own scope.** A run is alive only to answer
> its question. If the question is cross-machine — "which machine serves the
> 1.5B faster" — then the run is cross-machine, and the question is what
> authorises it. Scope is not granted by a standing rule about hosts.
>
> **D3 — the comparison check is deliberately unaware.** Two cells are
> comparable when every recorded parameter is equal except the one under test.
> The check does not know which differences are harmless and is not to be
> taught: a check that waves a difference through is a check that cannot report
> it. It fails on any difference beyond the declared one.
>
> **D4 — a failure may be ignored, and the ignore is a record.** The reader of
> a contrast may declare that a difference does not bear on it. That
> declaration names each ignored parameter, and it is written **on the
> contrast, never on the cell**. A cell is written once and never edited; a
> cell reused in three contrasts must still say exactly what it said when it
> ran.
>
> **D5 — a one-armed cell is first class.** A capability question — "can these
> two models co-reside on this card" — has no contrast and needs none. It is
> checked, stored and logged identically to an arm of a contrast, and it may
> later be taken up as one arm of a comparison nobody had planned. Contrasts
> are formed at reading time, not fixed at authoring time.
>
> **D6 — ADR-0024 clauses 3 and 4 stand, and are load-bearing here.** The
> serving build is run identity, and the recorder derives every identity field
> rather than a caller typing it. D3 is only meaningful because the parameters
> it compares were derived at the point of recording.

## Consequences

**Ignoring becomes the normal path for a cross-machine claim, not the
exception.** Two cells on different hosts always differ in card, driver and
hostname, so D3 fails on every cross-machine contrast and D4's list is
populated every time. That is the intended shape. A standing, explicit list of
what a claim overlooked is stronger than a check clever enough to pass those
differences silently — and it is exactly the defect K7 and K9 recorded as
one-off findings, now a rule.

**A contrast becomes a record type.** D4 and D5 together mean the comparison is
a thing with its own file: which cells, which parameter is under test, what was
ignored and by whom. Nothing in the tree records this today.

**The capability table keeps its job.** `data/capability-table.json` and a
config's `hosts` still say which model fits which card. D1 withdraws *roles*,
not *facts*: srv1 still cannot hold the 14B, and a question that needs it is
answered on srv2 because of the card, not because of a designation.

**This builds no second instrument.** ADR-0030 clause 1 stands: a throughput
question is answered by re-running the rig measurement, not by a new benchmark
under `tools/bench/`. The run contract restructures how the existing harness is
driven and adds no measuring apparatus.

**The refusal semantics are ADR-0027's, unchanged.** A parameter the check
cannot read is a refusal and not a match (D3 there), and a value is one of
three states: obtained, `null` with a reason, or an absent key that predates the
contract. This record adds no fourth idiom.

## Rejected: teach the check which differences are harmless

The obvious alternative is a check that knows a hostname never affects
throughput and waves it through, failing only on differences that matter. It
was rejected for the reason D3 states: the knowledge required is exactly the
knowledge under test. A check that already knows which hardware differences are
harmless has assumed the answer to every question this project asks about
hardware — and it reports nothing, because the differences it waved through
never appear in the record. The dumb check is more work per claim and produces
a list; the clever check is less work and produces silence.

## Rejected: keep the roles and permit exceptions

Amending ADR-0024 to allow cross-host comparison "when builds match" was
considered and rejected as the same mistake one level up. It replaces a
standing rule about hosts with a standing rule about builds, when the real
predicate is per-question and per-parameter — which is what D3 already
computes. The exception list would drift from the check.

## Checks

- `tests/test_run_contract.py::test_a_contrast_refuses_when_any_unremarked_parameter_differs`
- `tests/test_run_contract.py::test_an_ignored_difference_is_named_on_the_contrast_and_not_on_the_cell`
- `tests/test_run_contract.py::test_a_one_armed_cell_is_stored_and_checked_like_any_other`
- `tests/test_run_contract.py::test_no_host_is_barred_from_a_cross_host_contrast`
