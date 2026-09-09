# The run contract — a campaign is a stack of cells

Issue: #335 · Decision: [ADR-0038](decisions/0038-a-machine-has-no-role-and-the-question-approves-its-own-scope.md) · Date: 2026-08-22

Written after a four-agent design pass — three independent designers and a
verifier charged with attacking the brief they shared. Every claim about
current behaviour below was checked against the tree at `lane/286` and carries
its `file:line`.

## The contract in one sentence

> **One header per question. One process per cell. A cell asserts the machine
> matches the pre-state its header declared, records everything else, and
> leaves nothing behind.**

---

## 1. What a cell is

A cell is **one process, one host, one measurement, one directory**. It is the
smallest unit of work and the unit of failure. A cell that dies is cheap: rerun
that cell.

```
<evidence>/<campaign>/<cell-id>/
    run.json     the terminal record — the row, provenance, identity, pre-state, post-state
    run.jsonl    appended and fsynced per record, so a dead process leaves what it had
    run.log      stdout and stderr
```

**A cell is written once and never edited.** Everything that is true about a
cell is true at the moment it finished. This is the reason ADR-0038 D4 puts an
ignored difference on the contrast rather than on the cell: a cell taken up by
three later comparisons must still say exactly what it said when it ran.

**Existence is the state.** "Did this cell run" is `test -f
<evidence>/<campaign>/<cell-id>/run.json`. There is no separate tally, no
resume key, no reconciliation pass — the directory *is* the record, which is
the same argument `tools/bench/headers.py:216-218` already makes for the header
listing: a count that is derived cannot disagree with the directory it
describes.

## 2. What a header is

A header is **one question**. A question needs one or more cells; each cell is
one arm. The header names its arms in the `arms` key that
`tools/bench/headers.py:80` already defines.

A header is where the thinking happens. Compiling
`records/headers/2026-08-22-coresidency-matrix.json` required reading `/api/ps`
on both rigs, locating Finding 2c, discovering that `MAX_LOADED_MODELS=0` is
what permits the campaign at all, and catching a version skew between the rigs.
**None of that is per-cell work.** A header per cell would copy it N times or
omit it, and either way the header stops being an intent record and becomes a
config file — which is the failure #322 was rewritten to avoid.

There is a second, mechanical reason. `headers.py:71` sets `REVIEW_AFTER = 10`
and `:224` counts only headers carrying a `run` block. The register stands at
**1 of 10** today. A campaign of sixty per-cell headers takes it to 61 in one
night and fires the field review on ten copies of one question — and the
review's own rule (promote every field filled on all of them, drop every field
filled on none) would then **drop `cost`, `void_if`, `could_have_carried` and
`left_on_table`**, the four fields that are not answerable per cell. The
degradation would be ratified by code already written.

## 3. The pre-state rule

> **A cell asserts the machine matches the pre-state its header declared.**

**Not "clean and idle".** That phrasing was tested against the record and
fails: **15 of 17 D7 cells carry `yielded.vllm.card_idle: False`**, and every
one of those readings is the *previous* cell's footprint, cleared two seconds
later by `ollama.claim`'s own release (`tools/bench/serving/backends/ollama.py:348`).
A literal idle precondition refuses 15 of 17 cells over a card that is clean
moments afterwards.

It is also the wrong shape for the work. A co-residency question needs a card
that **already holds a named neighbour**. Empty is one declarable pre-state
among several, not the rule.

**The three states are ADR-0027 D2's, unchanged**: a value means obtained;
`null` with a reason means asked and refused; an absent key means the record
predates the contract. And ADR-0027 D3 governs the check: a parameter the guard
cannot read is a **refusal, not a match** — because two records agreeing by
shared absence is the defect that rule exists to catch.

**Two rules, not one:**

1. **What the header declares must match, or the cell refuses.** Narrow on
   purpose — only the conditions the question depends on.
2. **Everything else is recorded, never ignored.** The harness already reads
   temperature, power draw, SM clock and throttle reasons
   (`contract.py:515,524-527`), the load on both machines, the driver, the card,
   and the serving build (`calibrate.py:96-132`). All of it is captured before
   the cell starts, so a strange number months later can be traced to a
   throttling card instead of guessed at. This is ADR-0026 lens 1 — record the
   unrecoverable — and ADR-0015's rider: failing closed is a policy about
   effect, not permission to lie in the ledger.

**Stop adding idle gates.** The tree already computes three idle readings that
no production code reads: `snapshot()["gpu_idle"]` (`contract.py:458`), the
`release()` return that `vllm._start` discards (`vllm.py:588`), and
`gpu_compute_apps` (`contract.py:438`, its only appearance in the tree). The
pathology is not a missing gate — it is that readings keep being minted and
never wired. The pre-state check must **consume** these, not add a fourth.

## 4. The post-state rule

> **A cell leaves nothing behind.**

Four clauses, in check order: no process of ours; no container of ours; no
model resident; the card back to its declared floor.

**The second clause is narrowed to *running*** — the correction at the end of
this section, dated 2026-08-23 (#352). The sentence above is left exactly as it
was written; this pointer is beside it so a reader who acts on the list does not
have to reach the correction first.

This clause exists **because of `keep_alive: -1`**. Both rigs now declare
`OLLAMA_KEEP_ALIVE=-1` and `OLLAMA_MAX_LOADED_MODELS=0`, so ollama never evicts
anything on its own. A cell that dies between loading a neighbour and tearing
it down pins a model on the card **indefinitely**. `run.py:816-821` says this in
its own words, and its answer was to move teardown to the end of the campaign —
up to 4 h 53 m later.

**Three failure cases, three owners:**

| case | who cleans up |
|---|---|
| the process dies, the box lives | the cell itself — `try/finally` plus a SIGTERM handler, in-process |
| the box dies | nobody, in flight. The **next cell's pre-state check** is the recovery: it reads the machine, not the history |
| a cell refuses | it refuses, it does not repair. Clearing is `launch.py --release`, which already exists (`launch.py:215-247`) |

**A cell never repairs a machine it found wrong.** A cell that silently clears
a card it was supposed to find in a declared state cannot tell you the card was
wrong.

**The honest cost.** Every cell pays its own teardown — ~30 s of ssh with
compiled-in sleeps (`ollama.py:188-268`, `vllm.py:231-315`) — and much of it
duplicates the release the next cell's `claim` performs anyway. Measured, the
per-cell fixed cost is ~45-50 s, so a 60-cell campaign spends ~48 min on
overhead: **about 9%, not the 1% first estimated.** That is the price of the
guarantee and it is worth stating rather than hiding.

### Correction, 2026-08-23 — the container clause is narrowed to running, and the stopped one is recorded instead

The clause list above says **no container of ours**. The reading that implements
it is `docker ps --filter ancestor=<image>`, and bare `docker ps` lists
**running** containers only. The phase-0 footprint campaign
(`records/evidence/2026-08-23-phase0-footprint/`) ended with every post-state
reading clean on both rigs — `card=1 MiB`, `compute_apps=[]`, no resident
models, no vLLM process, zero containers counted — and srv2 nonetheless holding

```
mcgyvr-vllm   Exited (1)
```

Nothing was broken, and nothing has been: `_start` runs `docker rm -f
mcgyvr-vllm` before every launch (`vllm.py:1218`), so a stopped container never
blocks the next cell. What was wrong is narrower and is the shape this lane
keeps meeting — **a clause stated a property and the check that implemented it
read something smaller.** An operator shown `own_containers_remaining: 0`
(`vllm.py:581`) who then finds `mcgyvr-vllm Exited (1)` on the box has been
answered truthfully and not asked-truthfully.

**Narrowed rather than widened — the owner's ruling, 2026-08-23.** The clause in
force is **no container of ours is running**. A stopped container holds nothing
this rule protects: no card, no port, no process, and no claim on the next cell,
which removes it before it launches. Requiring its absence would have made the
contract's cheapest guarantee turn on a state that costs nothing to leave behind.

**Because it costs nothing and carries something, it is recorded instead of
required absent.** `readings()` takes `docker ps -a` (`vllm.py:475`), so an
exited container built from this engine's image appears in the record with its
status, and the `docker inspect` that follows recovers the argv it died on —
demonstrated the moment `-a` went in: srv2's `mcgyvr-vllm` gave back the refit
cell's whole argument list, `--kv-cache-memory-bytes 1610612736` included.

**Three corrections the first live reading forced, and they are why this is
worth writing down.** (1) **srv1 was in the same state** — it holds
`vllm-nemotron-4b Exited (1) 13 days ago`. The issue named srv2 alone because
srv2 was where somebody happened to look. (2) **srv2 holds four, not one**, and
only one of the four is ours: the `ancestor=` filter selects by image, and
`mcgyvr-vllm` is the only name `_start` gives a container. The count beside it
is nonetheless called `own_containers_remaining`, which is the same defect one
level down and is **#355**, fixed in the correction below. (3) **The `Exited (1)` this
issue was filed on no longer exists.** srv2's `mcgyvr-vllm` now reads
`Exited (0) About an hour ago` — the refit campaign's last cell replaced it. The
evidence a defect was filed on was destroyed by the mechanism the defect
describes, one cell later, which is the argument for the log capture below
stated by the machine rather than by us. The gate is
untouched and stays running-only (`vllm.py:570`): the record sees more than the
gate acts on, and that asymmetry is the answer rather than a leftover. The two
other `docker ps` reads keep their running-only form for reasons of their own —
`release()` stops only what is running (`vllm.py:530`), and the `max-num-seqs`
read wants the live container's argv, where `-a` would answer with the width of
the run that failed (`vllm.py:1361`).

**A failed cell's container is removed at once, because its reason is read
first.** The third question was whether a container that failed should survive
until somebody has looked at it. It should not: a campaign runs unattended for
hours, and a launch that depends on a human having been there is not a launch.
What was missing was the other half. `_start` now reads the engine's own last
`LAUNCH_LOG_LINES` lines on the failure path and carries them, scrubbed, in the
refusal (`vllm.py:109`, `vllm.py:1109`, `vllm.py:1264`) — where before it named
two places to go and look, both of which the next cell destroys. The campaign
paid for that once, re-running a cell byte-identically to recover an engine
refusal reason `docker rm -f` had already taken. **The pip rig lost it the same
way and nobody had noticed**: the launch redirects `> /tmp/vllm-serving.log`, so
the next cell truncates the previous cell's log rather than appending to it.
Both launchers are read.

The scrubbing claimed is the one every host reading here carries and not a
stronger one — credential URLs, home-directory prefixes and the published token
shapes. An arbitrary `KEY=value` an operator invented is redacted by nothing in
this tree, and the check below says so rather than implying otherwise.

**Checks**, all in `tests/test_serving.py`:

- `test_a_stopped_container_of_ours_is_in_the_record_and_out_of_the_gate`
- `test_canary_the_running_only_reading_calls_the_same_host_empty`
- `test_the_width_read_off_a_container_ignores_the_one_that_exited`
- `test_a_launch_that_never_became_ready_carries_the_log_the_next_cell_destroys`
- `test_the_engine_log_is_read_only_where_it_is_about_to_be_lost`
- `test_a_log_the_host_would_not_give_up_is_a_reason_and_not_a_silence`
- `test_the_engine_log_goes_through_the_same_scrubber_as_every_other_reading`

Seven mutants, one edit each — the record back to running-only, the gate widened
instead, `-a` swept into the width read, the log not read, the log read on every
launch, an unreadable log left silent, the tail written unscrubbed. **All seven
were killed.**

### Correction, 2026-08-23 (second) — "ours" was never what the reading tested (#355)

The block above says the count beside the container reading is called
`own_containers_remaining`, and files that as #355. It is fixed here, and the
fix turned out to be larger than the name.

**The reading was never about ownership, and neither was the one beside it.**
`--filter ancestor=` selects by image; `pgrep -cf '[v]llm serve|…'` selects by
process pattern. Both match anything of this engine on the host, ours or a
stranger's, and both were called `own_`. That is the right SCOPE for an
exclusion gate — anything of this engine that is up holds the card the next
entry would be measured on, which is E8's finding and is unchanged — and it is
not ownership. Renamed to `engine_processes_remaining` and
`engine_containers_remaining` on both backends (`vllm.py:649`,
`ollama.py:264`), with `our_containers_remaining` beside them
(`vllm.py:653`) for the one thing that is genuinely ours: the single container
name `_start` assigns, `mcgyvr-vllm` (`vllm.py:922`).

ollama's is renamed rather than narrowed, and the reason is a fact about that
engine: it spawns the `llama-server` child, chooses its port at load time and
gives it no name this project sets, so **nothing on the host distinguishes a
child we caused from one we did not.** `engine_` is the whole of what can be
true there.

**The defect with teeth was not the name.** The release step fed the
image-filtered list to `xargs -r docker stop`. On srv2 that list is four
containers, one of them ours — so a release would have stopped three servers
belonging to somebody else. A cell never repairs a machine it found wrong (§4
above), and killing another user's server is further from repair than anything
that clause was written about. Release now stops exactly `mcgyvr-vllm`
(`vllm.py:585`); what is up and not ours shuts the gate instead, which is the
correct answer to finding a machine in a state we did not create.

**The tag pin does not do what the reading needs, and E8 said so first.**
`--filter ancestor=<tag>` matches by resolved image **ID**. Measured on both
rigs 2026-08-23: `:latest` and `:v0.26.0` are both `ffb2d59b1c05`, so the pinned
filter returned the `:latest` containers too and the two filters gave
byte-identical sets. E8 recorded that coincidence in 2026-08-19 and pinned the
tag to fix a different failure; the coincidence is still live and still
load-bearing. Pull a newer `:latest` and every container of it goes invisible
while `released` keeps reporting True — E8's exact failure arriving from the
other direction. The readings now match the **repository** (`vllm.py:489`,
`vllm.py:630`), which does not depend on two ids agreeing.

**The stated limit.** A vLLM served from an image with another name — a local
build, a fork, a mirror — is not matched by a repository string and would still
hold the card. It is out of reach of a name-and-repository reading by
construction. Where such a server shows is `card_used_mib`, recorded beside
`released` and deliberately not part of it, because consulting the card there
made a backend holding nothing report failure whenever another engine held the
card and refused the very engine it was about to measure.

Verified live on both rigs after the change: `engine_containers_remaining: 0`,
`our_containers_remaining: 0`, `released: true`, card 1 MiB, with srv1's one and
srv2's four stopped containers in the record and their image tags beside them.

**Checks:** `tests/test_serving.py::test_a_stranger_of_this_engine_shuts_the_gate_and_is_not_counted_as_ours`
· `…::test_release_stops_the_container_this_module_started_and_no_other`
· `…::test_the_other_tag_is_seen_because_the_repository_is_matched_not_the_pin`
· `…::test_a_container_of_an_unrelated_image_is_not_counted_and_that_is_the_limit`
· `…::test_canary_ours_is_told_from_a_stranger_by_the_one_thing_that_differs`
· `…::test_neither_backend_still_calls_a_scope_reading_an_ownership_one`.
Seven mutants, one edit each; all seven killed.

## 5. The comparison check

Per [ADR-0038](decisions/0038-a-machine-has-no-role-and-the-question-approves-its-own-scope.md) D3-D5:

- **The check is deliberately unaware.** Two cells are comparable when every
  recorded parameter is equal except the one under test. It does not know which
  differences are harmless and is not to be taught.
- **A failure may be ignored, and the ignore is a record on the contrast** —
  never on the cell.
- **A one-armed cell is first class.** A capability question has no contrast and
  needs none. It is checked, stored and logged identically, and may later be
  taken up as one arm of a comparison nobody planned.

**Ignoring is the normal path for a cross-machine claim.** Two cells on
different hosts always differ in card, driver and hostname, so the check fails
every time and the ignore-list is populated every time. That is intended: a
standing, explicit list of what a claim overlooked beats a check clever enough
to pass those silently. It is what K7 and K9 found as one-off defects, made into
a rule.

## 6. What must not be in a cell

1. **More than one host.** E14 makes cross-host concurrency a measurement error
   (`launch.py:250-262`). A cross-*host contrast* is two cells, one per host —
   which is exactly what ADR-0038 permits and ADR-0024 clause 2 forbade.
2. **More than one measurement.** No cross-product, no matrix. The matrix moves
   to whatever *generates* headers and cells.
3. **Resume.** No resume key, no reconciliation. `run.json` existing is the
   state; "retry" is `rm -r <cell>`.
4. **Repair.** See §4.
5. **A second instrument.** ADR-0030 clause 1 stands: a throughput question is
   answered by re-running the rig measurement, not by new apparatus under
   `tools/bench/`. This contract restructures how the existing harness is
   driven and adds nothing that measures.

## 7. Defects this contract must fix, each as a named check

Found during the design pass, each verified in the tree. Under ADR-0037 each is
a check, not a paragraph.

| # | defect | evidence |
|---|---|---|
| 1 | **The neighbour's placement is never computed**, so the co-residency `void_if` is unevaluable. A neighbour that fell to CPU reads as "neighbour cost". | `_placement` runs for the model under test only (`ollama.py:839-851`); the neighbour's `size_vram` is read from `/api/ps` and discarded |
| 2 | **`vllm.claim` has no card-idle term.** Its `ok` is `model in served and allocation_present and weights-match`. ollama has one (`ollama.py:474`, `is True`). | `vllm.py:588` calls `release(host)` as a bare statement, discarding `card_idle` |
| 3 | **A refused saturation leaves `outcome: "ok"`,** so the cell counts as done and is un-retryable by the flag whose job is retrying. The two drivers disagree: `calibrate._succeeded` treats `saturation_refused` as not-an-answer. | `run.py:520` writes the block and never downgrades; `run.py:158` filters on `outcome == "ok"` |
| 4 | **No label-uniqueness guard.** Two D7 entries share `"id": "qwen2.5-coder:3b"` and differ only by label, while the loop keys on `label or id`. | `run.py:300`; the only uniqueness test reads a different config (`tests/test_serving.py:607`) |
| 5 | **`vllm.residents()` does not exist,** so a vLLM co-residency cell records an `AttributeError` as its evidence. | `run.py:564` calls it; only `ollama.py:647` defines it |

**2026-08-22 — defect 1 is closed (#335).** `ollama._placements` computes the
placement of every row `/api/ps` returns, `claim` records it on each attempt as
`resident_placements`, and the survey's post-ramp verdict carries
`coresidency_after.placements` beside the `held` it could not previously
support — a neighbour that stayed and spilled is still listed by name, so the
name list catches the neighbour that LEFT and nothing else. Both are recorded
and neither is gated: a spilled neighbour is the frontier the campaign exists
to map, and a claim that refused it would refuse its own question. The named
checks are

- `tests/test_serving.py::test_the_placement_of_every_resident_is_recorded_not_only_the_model_under_test`
- `tests/test_serving.py::test_a_resident_whose_row_carries_no_usable_size_is_named_without_a_fraction`
- `tests/test_serving.py::test_the_post_ramp_coresidency_verdict_says_where_each_neighbour_sat`
- `tests/test_serving.py::test_a_backend_that_cannot_report_placement_writes_null_and_not_a_number`

and the sink's own conformance check now reads the fraction through
`SURVEY_ROW_DISPOSITION` and `LOAD_ROW_DISPOSITION`, so the field cannot be
added to a producer and dropped by a sink.

**2026-08-23 — defect 5 is closed (#345, ADR-0040).** `vllm.residents()` and
`vllm.placements()` exist, so `run.py:568` no longer records an `AttributeError`
as a vLLM cell's evidence, and phase 0's vLLM arm — 3 cells on srv1, 4 on srv2 —
can run.

**The fraction is refused, not computed.** ollama reports `size_vram / size`
because llama.cpp spills; vLLM takes its whole allocation or refuses to start,
so there is no denominator. Every vLLM placement row carries `fraction: null`
with its reason and the MiB the driver attributes to the process — never the
`1.0` that is true by this engine's contract and would be read beside an ollama
`0.068` as one measurement (ADR-0038 D4). **The frontier therefore carries two
kinds of cell by construction**, and a contrast across them states which it used.

The join had to be measured. vLLM renames its GPU worker with `setproctitle`, so
the process `nvidia-smi` attributes the memory to has a command line of exactly
`VLLM::EngineCore` — no model on it. The model is on the immediate parent, in
both deployment shapes (pip on srv1, container on srv2, differing only in the
path to the binary). Measured on both rigs 2026-08-22 at the declared serve
block of `q15-vllm-s8`: 3,126 MiB on srv1 against a 3,130 MiB card, 3,174 MiB on
srv2 against 3,183 MiB — **a per-process figure is not the card**, and the two
are recorded as two fields. The named checks are

- `tests/test_serving.py::test_a_vllm_placement_reports_the_card_it_holds_and_refuses_the_fraction`
- `tests/test_serving.py::test_the_pid_that_holds_the_card_names_no_model_so_the_owner_is_the_parent`
- `tests/test_serving.py::test_a_card_holder_this_engine_cannot_name_is_a_row_and_not_a_silence`
- `tests/test_serving.py::test_a_served_model_the_driver_attributed_nothing_to_is_recorded_as_unplaced`
- `tests/test_serving.py::test_an_unread_card_is_refused_and_never_an_empty_placement_list`
- `tests/test_serving.py::test_a_vllm_claim_records_where_everything_on_the_card_sits_and_gates_on_none_of_it`
- `tests/test_serving.py::test_the_compute_apps_reading_is_declared_once_and_has_a_consumer`

**§3's warning is honoured by subtraction.** `gpu_compute_apps` was one of the
three readings this tree minted and never read; it is now declared once as
`contract.COMPUTE_APPS_COMMAND` and read by two callers — `snapshot`, which
records the line, and `vllm.placements`, which computes from it. **Two idle
readings remain**: `snapshot()["gpu_idle"]` and the `release()` return that
`vllm._start` discards.

**What defect 5's closure does NOT buy.** `residents()` answers about its own
engine on both backends, so a neighbour served by the other engine is absent
from both lists and a mixed-engine cell still reads `held: false` after its ramp.
That is #343, #344 and #346.

**2026-08-22 — the cross-engine harness changes are filed.** They were carried
as prose in this lane's records and are now four issues, each with its evidence
verified in the tree: **#343** (`run.py:353-358` releases every other backend
with no per-cell opt-out), **#344** (`ollama.py:486` gates on
`card_idle_before_load is True`, so a declared shared card is refused by
construction), **#345** (defect 5 — and the reporting shape is a decision, not a
stub: vLLM never spills, so `size_vram / size` has no analogue for it), **#346**
(`ollama.py:361-378` is the only neighbour loader and it can only speak ollama,
in the wrong layer). Build order **#345 → #343 → #344 → #346**; #345 pays off
alone, because it unblocks phase 0's vLLM arm. Feasibility is not in question —
cross-engine co-residency was demonstrated by hand on both rigs 2026-08-22.

**2026-08-23 — #343, #344 and #346 are PARKED, and so is the build order above.**
Owner ruling: the bench stands up first. Around 90% of the measurements this
instrument owes — levers, configs, the four commissioning cells — put one model,
one engine and one family on a card, and multi-model residency is bench
*hardening*, which is post-bench and post-trunk. The three issues stay open with
their evidence intact; what moved is when they are built, not whether they are
real. Recorded in `docs/plans/302/parked.md` and in a dated block on
`records/headers/2026-08-22-coresidency-matrix.json`.

**What survives the parking is the whole of what phase 0 needs, which is
nothing.** A solo load onto an idle card clears every gate the three issues name,
so the footprint table — the one output every later phase is predicted from — is
runnable today on both rigs.

**And two of the four are not about mixed engines.** `#344`'s gate fires on a
second *ollama* model loading onto a card its sibling already holds, and `#347`'s
precondition fires on a second *vLLM* instance on a second port. A ruling that
had named cross-engine alone would have left both standing; parking multi-model
is what actually retires them for now.

## 8. What this does not answer

**Every cell is a cold start.** `contract.drop_page_cache` (`contract.py:665`)
forces it, deliberately. So this harness cannot answer "what does this rig serve
in production", where nothing is ever cold. That is correct for calibration and
must be stated, or these numbers will eventually be quoted as serving numbers.

**Two cost terms are still unmeasured**: a single ollama load has never been
timed in isolation (per-attempt `seconds` landed with #326, after D7), and a
cold vLLM container start on srv1 has never been timed at all.
