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

## 8. What this does not answer

**Every cell is a cold start.** `contract.drop_page_cache` (`contract.py:665`)
forces it, deliberately. So this harness cannot answer "what does this rig serve
in production", where nothing is ever cold. That is correct for calibration and
must be stated, or these numbers will eventually be quoted as serving numbers.

**Two cost terms are still unmeasured**: a single ollama load has never been
timed in isolation (per-attempt `seconds` landed with #326, after D7), and a
cold vLLM container start on srv1 has never been timed at all.
