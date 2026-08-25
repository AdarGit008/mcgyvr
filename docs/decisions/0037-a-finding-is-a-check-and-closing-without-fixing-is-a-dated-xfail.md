# ADR-0037 — a finding is a check, closing without fixing is a dated xfail, and the record names its check

Status: Accepted
Supersedes: none
Superseded-by: none
Amends: none — no prior decision changes; this record names a mechanism the
four-lenses record and the `## Left open` convention already imply and nothing
enforces
Relates: ADR-0026 (lens 3: a record states the property it contains, or it is
worse than dead weight; lens 1: record the unrecoverable), #286 (the lane that proved the mechanism), #322
(the run-intent header this record's rule-3 sits beside)
Date: 2026-08-21
Issue: #323 (sub-issue of #286)

## Context

Two patterns surfaced on lane/286 in one session, 2026-08-20, and they are one
disease.

**Pattern 1 — the instrument measures the right thing and loses it at the
moment of writing it down.** Six independent instances on the D7 campaign:
`start_seconds` computed on every vLLM launch and its return value never
assigned; `repeat_spread` computed for every ramp and not named by the row
builder; `declared_slots` readable from `/props` and `null` on every ollama
ramp row; a phase duration printed to a log and not a journal; two card
readings taken and only the flattering one kept; a probe-set field answered
host-side and dropped when columns were chosen. None is "we failed to
measure". Every one is "we measured, and the value did not survive the
hand-off to the record". The guard that existed — `launch.py`'s MARKERS table
— asserted that a *source file contains a string*. It confirmed the
thermometer was installed and could not notice that nobody wrote the
temperature down; its entry `'"repeats": attempts'` passed on the campaign
that discarded `repeats`.

**Pattern 2 — findings arrive faster than the issue structure can hold them.**
Twenty-nine findings in one session; #322 alone would have swallowed
thirteen. The owner diagnosed it as three things at once — drain rate,
placement has no rule, and volume per container — and not as a visibility
problem. A standing findings register was proposed and **rejected**:

> "just another issue tree and it's reasoned over, not the fix that will
> ease my mind."

and the shape the owner asked for instead:

> "I can accept learning new items during flight, no amount of planning will
> fix this, and I don't want it to be a reasoning thing that will drift
> again. I'm thinking describing issues as DoDs or something verifiable,
> behavior oriented."

Both patterns are **a claim about the system that nothing mechanically
verifies.** "We record `start_seconds`" was asserted by a source-text check
and was true about the code and false about the record. "This finding is
open" was asserted in prose and verified by nobody, so knowing its state
required re-reasoning, and re-reasoning drifts.

The owner's ruling was to prove the mechanism on one bucket before writing
this record. That happened: `tests/test_sink_conformance.py` was written
before any fix and, as a positive control, named three of the six defects
unprompted (`contract.ramp() returns ['method', 'repeat_spread', 'repeats',
'speedup_vs_n1'] and _one_ramp does not say what becomes of them`; a ramp
that raised indistinguishable from one that finished). A sweep of eight
deliberate mutations was then applied and reverted; the check caught seven,
and the eighth — a launch fixture that compared the disposition to a
hand-written copy of what `vllm.claim` returns, the disease one level out —
was fixed in `8a20a4cb`. 8 of 8.

## Decision

> **DECIDED (2026-08-22, owner).** Accepted in principle 2026-08-20 and
> written 2026-08-21 after the mechanism was proved on bucket A; ruled
> 2026-08-22, on the day rule 3 refused ADR-0038 for naming four checks the
> suite did not hold. The rule was enforced against the next record written
> under it before it was ratified, which is the strongest evidence available
> that it is a mechanism rather than a preference.
>
> 1. **A finding is a check, not a paragraph.** A finding about the system
>    becomes a named test with an expected state. Red means the defect is
>    present; green means it is gone. "Is this still open?" is answered by
>    running the suite, never by reading a record. This rule is
>    review-enforced, and the reason there is no check is priced here: a
>    finding is prose until someone writes its test, and no linter can tell
>    a finding from a remark. The same clause-5 idiom as ADR-0036.
> 2. **Closing without fixing is an `xfail` with a dated reason.** A finding
>    not fixed keeps its check, marked
>    `pytest.mark.xfail(strict=True, reason="YYYY-MM-DD: ...")` — never a
>    skip, never a deleted test. Two reason grammars, both dated:
>    `owed — <the question the investigation must answer>` while the owner
>    has not ruled, and `decided — <the decision>` once they have. `strict`
>    is what makes the check live: an accidental fix turns XPASS and fails
>    the suite until the marker comes off, and a worsening stays red under
>    it. A parked finding is live without being work. Enforced by
>    `tests/test_finding_is_a_check.py::test_every_xfail_in_the_suite_is_strict_and_carries_a_dated_reason`.
> 3. **The append-only record names its check.** A decision record, a dated
>    block, or an issue's definition of done carries what was considered and
>    what was rejected, as before. It gains one line: the check that enforces
>    it, in the form `tests/<file>::<test>`. Prose and predicate are bound,
>    so neither drifts alone. Enforced, for decision records, by
>    `tests/test_finding_is_a_check.py::test_every_check_a_decision_record_names_resolves_to_a_test_in_the_suite`.
>    The resolver's population is `docs/decisions/0*.md` only; session
>    records and evidence READMEs are history and are not resolved, and the
>    price is that a check named in one of them can go stale unnoticed. The
>    trigger for extending the resolver to `records/sessions/**` dated on or
>    after this record's `Date` is the first such stale name found.
> 4. **A sink is conformed to its producer, not to a hand-written list.** For
>    every producer→sink pair that writes a journal row, every key the
>    producer returns is accounted for in the row — carried, flattened, or
>    declared dropped with a reason — and the disposition lives beside the
>    sink. A test that carried its own copy of the answer is a second
>    hand-written field list, which is the defect. The first instances are
>    `RAMP_ROW_DISPOSITION` and `LAUNCH_ROW_DISPOSITION` in
>    `tools/bench/serving/calibrate.py`, enforced by
>    `tests/test_sink_conformance.py`.
> 5. **Coverage of rule 4 is mechanical, not counted.** A discovery check
>    enumerates every sink and fails when one has no disposition — the shape
>    the #302 plan already uses for figure-printing tools. Until it exists,
>    the number of covered sinks is stated in the record that names it, never
>    implied.

## Consequences

- **Placement has a rule.** A finding lives in exactly one place: its check.
  The reasoning lives in the append-only record that names it. An issue is
  opened to schedule work, not to hold a finding.
- **Volume per container stops mattering.** The unit is one check, one
  behaviour. Twenty-nine checks are fine; checks are run, not read.
- **The drain stops.** A parked finding is `xfail`'d, the suite stays green,
  and the backlog stops being a debt that is re-reasoned every session.
- **Mid-flight discovery costs minutes.** A new finding is a new check. No
  planning prevents the discovery, and none is needed to record it.
- **A check cannot drift.** It is red or green. A record that names it can
  go stale in its prose and is corrected by the check, not the reverse.
- **The price is a test per finding**, and a test that can be shown to
  reject: a check that cannot be demonstrated red is the MARKERS table again.
  Mutation sweeps are how that is shown, and the sweep is recorded where the
  check is introduced.

## Checks

- `tests/test_sink_conformance.py::test_the_sink_declares_a_disposition_for_every_field_the_ramp_produces`
  and
  `tests/test_sink_conformance.py::test_the_launch_sink_declares_a_disposition_for_every_field_claim_returns`
  — rule 4, on the ramp and launch sinks; the eight-mutation sweep, 8 of 8,
  is recorded in `records/sessions/lane/286/2026-08-20-131600-claude.md`.
- `tests/test_finding_is_a_check.py::test_every_check_a_decision_record_names_resolves_to_a_test_in_the_suite`
  — rule 3, on this record first.
- `tests/test_finding_is_a_check.py::test_every_xfail_in_the_suite_is_strict_and_carries_a_dated_reason`
  — rule 2.
- `tests/test_decisions.py::test_each_number_is_claimed_once_and_titles_agree` — this record's
  header and number.
- The sink census (rule 5) is #324 and names its check there.

## Amendment — 2026-08-22 (#328, owner ruling): rule 2 grows a third grammar, `measurement owed`

Rule 2 named two reason grammars and both are about the owner: `owed — <the
question>` while they have not ruled, `decided — <the decision>` once they
have. Clearing lane/286's owed set surfaced a third state the two words cannot
express.

**The instance.** `tests/test_cross_rig_claim.py::test_the_2026_08_20_cross_rig_claim_holds_only_on_a_journal_with_identity_rows`
asks whether the width-16 gap between the rigs is hardware or configuration.
No ruling settles that. The journal it was read off names no card, no engine
build and no weights on any row, so the answer is not in the tree and cannot be
reasoned to — #329's rig arm writes one width-16 ramp and one launch row per
host, and the answer arrives with the journal. Under the two-word grammar the
marker read `owed —`, which says *the owner owes a decision*, and so it was
put in front of the owner every session as one.

**The third grammar.** `measurement owed — <what a rig run must answer>`, dated
like the others. A reason now says **who** owes the finding: the owner, the
keyboard, or the rigs. `grep ': owed — '` answers exactly one question — what
is waiting on the owner — which is what #328's definition of done greps for,
and what made the mislabel visible in the first place.

**Not a third state: a decision recorded somewhere else.** The same sweep found
three markers in `tests/test_run_contract.py` reading `owed — ADR-0038 D3/D4/D5
is decided and unimplemented`. Their own text refutes their word. The owner had
ruled — ADR-0038 was Accepted the same day — and what was owed was #335's
harness code. Those are reworded to `decided —` naming the implementing issue,
not to `measurement owed`. A finding whose decision lives in another record is
`decided`, and the record it lives in is named in the reason.

**A marker may be repointed when the field it names is not the field the tree
writes.** K6 asked every ramp row for `engine_version`; nothing emits that key
and nothing ever did — the emitted name is `identity.serving_build`
(`tools/bench/serving/calibrate.py`). A check that cannot be satisfied by a
correct run is not a live finding, it is a typo with a marker on it. Repointing
it is an edit to the check, recorded in the append-only block that names the
check, and it changes the wording of the issue that introduced it — which is
why it carries the owner's sign-off rather than a session's judgement.

**Enforcement is unchanged and needs no code.**
`tests/test_finding_is_a_check.py::test_every_xfail_in_the_suite_is_strict_and_carries_a_dated_reason`
asserts `strict=True` and an ISO-date prefix (`_DATED`); it never parsed the
word after the date, so the third grammar costs nothing to admit. That the
grammar is unenforced is the honest state: it is a convention the greps rely
on, and the day a grep is wired into a definition of done is the day it earns a
check.

Rules 1, 3, 4 and 5 are unchanged.
