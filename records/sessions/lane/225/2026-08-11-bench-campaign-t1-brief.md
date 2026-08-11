# Bench campaign generation brief — lane/225 Phase 4, tranche 1 (2026-08-11)

You are authoring paired benchmark problems for mcgyvr's permanent bench
(#225). Design of record: `docs/bench-design-2026-08-10.md`. Every problem
you write will be judged by `tools/bench/admit.py` — the gate is the
arbiter, and this brief exists so your first pass survives it.

**What changed since the pilot (Phase 3):** the calibration read
size→difficulty as steeper than steered — g1, aimed just above d3-class,
landed AT d3-class (~17%), and g3/g4 read ~0. The Phase 4 steering decision
(owner, 2026-08-11): a new easier band **g0** (ts 20–30 reference lines,
d2-class unit of work, aimed at 30–50% on the floor tier) joins the ladder,
and **g4 is not generated further** — its pilot problems stay pinned. The
campaign's measured strata are g0/g1/g2/g3.

## What one problem is

One problem = two arms of the SAME problem, same id, plus one sidecar:

```
tools/bench/tasks/ts/<id>/contract.yaml   reference.ts   accept.mjs   meta.json
tools/bench/tasks/py/<id>/contract.yaml   reference.py   accept.py
```

- id matches `^b\d{3}-[a-z0-9]+(-[a-z0-9]+)*$` (e.g. `b047-ring-router`).
  Directory name == contract `id` in BOTH arms. Your ids are assigned below;
  you choose the slug (2–3 short words, specific to the problem).
- The `task:` prose states the same problem in both arms, identical except
  the target symbol's idiomatic name (`parseDuration` in ts / `parse_duration`
  in py). Interfaces/types are the language-specific rendering.
- `meta.json` lives ONLY in the ts arm.

Templates to read before writing anything (copy their conventions exactly):
- `tools/problems/tasks/ts/p001-parse-duration/` + `tools/problems/tasks/py/p001-parse-duration/` — function_implementation
- `tools/problems/tasks/ts/p007-free-windows/` + `tools/problems/tasks/py/p007-free-windows/` — bug_fix

Size calibration for your band — read one or two ADMITTED bench problems
near your band before writing (`tools/bench/tasks/ts/`): `b002-option-pairs`
or `b007-cent-split` (g1), `b013-region-totals` (g2), `b022-allocate-cents`
(g3). For g0 there is no exemplar yet: aim smaller than b002's reference by
about a third. NEVER reuse their prose, domains-of-the-day, or assertion
text — the near-duplicate screen compares you against every admitted
problem.

## contract.yaml — exact shape

`function_implementation`:

```yaml
id: b0NN-your-slug
task_type: function_implementation
task: >-
  Implement <name>. <Precise, self-contained statement: inputs, outputs,
  edge cases, and every rejection the checker will assert, enumerated.>
target: solution.ts            # solution.py in the py arm
target_content: |              # ONLY when the steering row says scaffold=yes
  <partial file: helpers/skeleton present, target NOT solved>
interface: "export function yourName(x: string): number"
stop_conditions:
  - <one genuine boundary the task text leaves unstated>
acceptance: ["node accept.mjs"]   # ["python accept.py"] in the py arm
risk: low                         # or medium
scope:
  allow: ["solution.ts"]          # ["solution.py"] in the py arm
```

`bug_fix`: same, plus `target_content: |` carrying the COMPLETE buggy file
(must differ from the reference and must FAIL the checker), and
`demonstration: ["node accept.mjs"]` / `["python accept.py"]` INSTEAD of
`acceptance` (copy p007). The task prose describes the defect behaviourally,
states what to fix and what validation to add, and ends with
"Return the complete fixed file."

Do not add fields not shown here (no `limits`, no `version`, no `deps`).

## meta.json (ts arm only)

```json
{
  "file_shape": "single_definition",
  "shape": "iteration",
  "steering_band": "g0"
}
```

- `file_shape`: `single_definition` | `multi_symbol` (from your steering row).
- `shape`: exactly one of `recursion`, `iteration`, `string`, `numeric`,
  `data_structure`, `error_handling` (from your row) — it must honestly name
  the problem's primary mechanism. If your written problem drifted, relabel
  honestly rather than keeping the assigned label.
- `steering_band`: your band, verbatim (`g0`..`g3`).
- For `multi_symbol` ONLY, add per-arm targets, each of which MUST appear
  among that arm's interface declarations:

```json
  "target_symbol": {"ts": "resolveRoute", "py": "resolve_route"}
```

## file_shape semantics

- `single_definition`: the interface declares EXACTLY ONE function per arm
  (the gate counts `function <name>` / `def <name>` matches in the interface
  string — one and only one). The reference may still use helpers nested
  inside the function or (ts) non-exported module-level `function helper()`s
  not mentioned in the interface.
- `multi_symbol`: the interface declares 2–4 functions (one signature per
  line), the file implements all of them, and `meta.json`'s `target_symbol`
  names the one the task is really about. This is the "large file, small
  named target" case (#126): make the target a modest slice of the file,
  with real implemented neighbours. The checker must assert the TARGET's
  behaviour directly (most assertions on it) and touch each other declared
  symbol at least once. For g0's small files, two declared symbols is
  enough — the case is "target is a slice", not "file is huge".

## Mandated declaration forms (the gate degrades the target mechanically)

- ts reference: the target symbol MUST be declared as
  `export function <name>(` and that literal string must appear EXACTLY ONCE
  in the file (don't repeat it in a comment). Every interface-declared
  function is `export function`. No arrow-function exports for declared
  symbols. Node runs `accept.mjs` importing `./solution.ts` with type
  stripping: use only erasable TypeScript (annotations, interfaces, type
  aliases) — NO enums, NO namespaces, NO parameter properties.
- py reference: every interface-declared symbol is a plain module-level
  `def <name>(...)`. No module-level executable code besides defs and
  constants (the gate appends a shadowing stub at EOF; imports resolve at
  call time). No `if __name__` block needed.
- accept.mjs: `import assert from "node:assert/strict";` then
  `import { name } from "./solution.ts";` and `assert.equal/deepEqual/throws`
  with a message per assertion; end with `console.log("ok")`.
- accept.py: `from solution import name` then bare `assert` statements with
  messages; a final `print("ok")` is fine.

## The gate you must survive (run it yourself — see Workflow)

1. Structure: both arms complete, ids match, arms agree on `task_type`,
   meta.json valid.
2. Contract loads via the strict schema (`mcgyvr.contract.load`).
3. Selftest: the reference passes its own checker in a fresh directory
   (checker + solution file only — the checker may import nothing else).
4. bug_fix failing-first: `target_content` fails the checker.
5. Anti-triviality: the reference with ONLY the target symbol degraded (a
   no-op stub and an echo-first-arg stub, helpers intact) must FAIL the
   checker — both stubs, both arms. A checker that any stub passes is
   measuring nothing: assert real behaviour, not just "returns something".
6. Checker floor: ≥ 5 occurrences of the substring `assert` per arm (aim for
   your band's target, far above the floor).
7. Front-door blocklist: NO declared function (either arm) may share a
   normalised name (lowercased, underscores stripped) with HumanEval's 164
   or MBPP+'s 378 entry points. Interview-canon names (`sortArray`,
   `isPrime`, `fibonacci`, `reverseString`, `countVowels`, `commonChars`,
   `maxSubarray`…) are exactly what's blocked — use two-word, domain-specific
   names and you will clear it.
8. Near-duplicate screen: word-set Jaccard of your `task:` prose vs the
   pool's 499 problems, the retired sets, the 40 pilot problems (both
   halves), and every other candidate; ≥ 0.55 rejects. Defence: write prose
   specific to YOUR domain and mechanics; never reuse a template paragraph
   across your problems.

## Checker discipline (this is the instrument; be strict)

- Shape-strict: assert exact values / exact structures, not truthiness.
- Cover: normal cases, boundaries (empty, zero, single element, ties,
  saturation), and EVERY rejection the prose enumerates. Rejections: ts uses
  `assert.throws(() => fn(bad), Error, "message")`; py uses the pool's
  idiom — a local `def rejects(...)` helper returning True when the call
  raises, then `assert rejects(bad), "message"` per case (see the p001
  template's accept.py).
- Both arms assert the SAME behaviour (same cases, same expected values) —
  they are one problem.
- The reference must genuinely pass; the stubs and (bug_fix) the buggy file
  must genuinely fail. Verify by running, not by inspection.

## Steering bands (this is what makes your batch a band)

Sizes are TOTAL file lines of the reference; asserts are per arm (count of
`assert` substrings). These are steering targets the calibration sweep will
check — land inside them.

| band | ts reference | py reference | asserts/arm | intent |
|---|---|---|---|---|
| g0 | 20–30 lines | 15–23 | 7–11 | d2-class unit of work, clearly above the cliff edge |
| g1 | 30–45 | 22–35 | 10–14 | just above d3-class |
| g2 | 45–60 | 34–46 | 13–17 | lower gap |
| g3 | 60–80 | 45–62 | 16–20 | upper gap |

Difficulty comes from unit-of-work (more required behaviour, more cases,
more state), NEVER from puzzle-trickiness or obscure algorithms. A g3
problem is a bigger honest job, not a riddle — and a g0 problem is a small
honest job, not a one-liner: one clearly stated behaviour with real edge
cases, the kind of function a practitioner writes in one sitting. Every
reference must be code a careful practitioner writes: idiomatic, no dead
code, no padding to hit line counts.

- scaffold=yes (fn_impl only): `target_content` carries a partial file —
  imports/constants/helpers implemented or stubbed with TODO, the target
  visibly incomplete. It must NOT be a working solution. Same idea in both
  arms.
- bug_fix: plant 1–2 related, realistic defects in the target symbol (logic,
  boundary, or missing-validation class), never syntax errors. The prose
  describes symptoms and required behaviour, not the patch.

## Workflow (per agent)

1. Read this brief, then all four template directories.
2. Author your 5 assigned problems (both arms + meta.json each), exactly per
   your steering rows.
3. Self-gate from the repo root, EXPLICIT ids only (never bare — other
   agents' half-written candidates are in the same tree):

   ```
   cd /home/adaramir/claude/mcgyvr && uv run --no-sync python tools/bench/admit.py b0NN-slug b0NN-slug ...
   ```

4. Fix and re-run until every one of your ids prints ADMIT. A near-duplicate
   rejection means replace the problem's idea, not its wording. NEVER pass
   `--pin`. NEVER touch ids outside your batch, `tools/problems/`, or any
   file outside `tools/bench/tasks/`.
5. If an id is unsalvageable after ~3 rewrites, delete both arm directories
   and report it as failed.

## The steering table

Tranche 1 is five band-batches of 20: **A + B are g0** (b041–b060,
b061–b080), **C is g1** (b081–b100), **D is g2** (b101–b120), **E is g3**
(b121–b140). Within a band-batch no domain repeats; across band-batches
domains recur deliberately — your problem must still be its own idea.

### band-batch A — g0, ids b041–b060

| id | band | domain | task_type | file_shape | shape | scaffold |
|---|---|---|---|---|---|---|
| b041 | g0 | strings/text-processing | function_implementation | single_definition | string | no |
| b042 | g0 | parsing/tokenizing | function_implementation | multi_symbol | string | yes |
| b043 | g0 | intervals/scheduling | function_implementation | single_definition | iteration | yes |
| b044 | g0 | graphs/ordering | bug_fix | single_definition | data_structure | - |
| b045 | g0 | trees/hierarchies | function_implementation | multi_symbol | recursion | no |
| b046 | g0 | dynamic programming | function_implementation | single_definition | iteration | no |
| b047 | g0 | numeric/precision | bug_fix | multi_symbol | numeric | - |
| b048 | g0 | dates/durations | function_implementation | single_definition | numeric | yes |
| b049 | g0 | encodings/serialization | function_implementation | single_definition | string | no |
| b050 | g0 | validation/normalization | bug_fix | single_definition | error_handling | - |
| b051 | g0 | state machines/protocols | function_implementation | single_definition | data_structure | no |
| b052 | g0 | collections/iterators | function_implementation | multi_symbol | iteration | yes |
| b053 | g0 | geometry/grids | function_implementation | single_definition | numeric | no |
| b054 | g0 | searching/selection | bug_fix | single_definition | iteration | - |
| b055 | g0 | caching/memoization | function_implementation | multi_symbol | data_structure | no |
| b056 | g0 | diff/merge/undo | function_implementation | single_definition | error_handling | no |
| b057 | g0 | tabular data/aggregation | bug_fix | multi_symbol | data_structure | - |
| b058 | g0 | bit manipulation | function_implementation | single_definition | string | yes |
| b059 | g0 | randomless simulation | function_implementation | single_definition | recursion | no |
| b060 | g0 | pattern matching | bug_fix | single_definition | error_handling | - |

### band-batch B — g0, ids b061–b080

| id | band | domain | task_type | file_shape | shape | scaffold |
|---|---|---|---|---|---|---|
| b061 | g0 | state machines/protocols | bug_fix | single_definition | data_structure | - |
| b062 | g0 | collections/iterators | function_implementation | multi_symbol | recursion | no |
| b063 | g0 | geometry/grids | function_implementation | single_definition | iteration | no |
| b064 | g0 | searching/selection | bug_fix | multi_symbol | numeric | - |
| b065 | g0 | caching/memoization | function_implementation | single_definition | numeric | yes |
| b066 | g0 | diff/merge/undo | function_implementation | single_definition | string | no |
| b067 | g0 | tabular data/aggregation | bug_fix | single_definition | error_handling | - |
| b068 | g0 | bit manipulation | function_implementation | single_definition | data_structure | no |
| b069 | g0 | randomless simulation | function_implementation | multi_symbol | iteration | yes |
| b070 | g0 | pattern matching | function_implementation | single_definition | numeric | no |
| b071 | g0 | inventory/stock-tracking | bug_fix | single_definition | iteration | - |
| b072 | g0 | rate limiting/quotas | function_implementation | multi_symbol | data_structure | no |
| b073 | g0 | versioning/ordering | function_implementation | single_definition | error_handling | no |
| b074 | g0 | text layout/wrapping | bug_fix | multi_symbol | data_structure | - |
| b075 | g0 | units/conversion | function_implementation | single_definition | string | yes |
| b076 | g0 | filesystem paths/globbing | function_implementation | single_definition | recursion | no |
| b077 | g0 | queues/buffers | bug_fix | single_definition | error_handling | - |
| b078 | g0 | layered configuration/precedence | function_implementation | single_definition | string | no |
| b079 | g0 | checksums/integrity | function_implementation | multi_symbol | string | yes |
| b080 | g0 | templating/substitution | function_implementation | single_definition | iteration | yes |

### band-batch C — g1, ids b081–b100

| id | band | domain | task_type | file_shape | shape | scaffold |
|---|---|---|---|---|---|---|
| b081 | g1 | inventory/stock-tracking | bug_fix | multi_symbol | numeric | - |
| b082 | g1 | rate limiting/quotas | function_implementation | single_definition | numeric | yes |
| b083 | g1 | versioning/ordering | function_implementation | single_definition | string | no |
| b084 | g1 | text layout/wrapping | bug_fix | single_definition | error_handling | - |
| b085 | g1 | units/conversion | function_implementation | single_definition | data_structure | no |
| b086 | g1 | filesystem paths/globbing | function_implementation | multi_symbol | iteration | yes |
| b087 | g1 | queues/buffers | function_implementation | single_definition | numeric | no |
| b088 | g1 | layered configuration/precedence | bug_fix | single_definition | iteration | - |
| b089 | g1 | checksums/integrity | function_implementation | multi_symbol | data_structure | no |
| b090 | g1 | templating/substitution | function_implementation | single_definition | error_handling | no |
| b091 | g1 | strings/text-processing | bug_fix | multi_symbol | data_structure | - |
| b092 | g1 | parsing/tokenizing | function_implementation | single_definition | string | yes |
| b093 | g1 | intervals/scheduling | function_implementation | single_definition | recursion | no |
| b094 | g1 | graphs/ordering | bug_fix | single_definition | error_handling | - |
| b095 | g1 | trees/hierarchies | function_implementation | single_definition | string | no |
| b096 | g1 | dynamic programming | function_implementation | multi_symbol | string | yes |
| b097 | g1 | numeric/precision | function_implementation | single_definition | iteration | yes |
| b098 | g1 | dates/durations | bug_fix | single_definition | data_structure | - |
| b099 | g1 | encodings/serialization | function_implementation | multi_symbol | recursion | no |
| b100 | g1 | validation/normalization | function_implementation | single_definition | iteration | no |

### band-batch D — g2, ids b101–b120

| id | band | domain | task_type | file_shape | shape | scaffold |
|---|---|---|---|---|---|---|
| b101 | g2 | dynamic programming | bug_fix | single_definition | error_handling | - |
| b102 | g2 | numeric/precision | function_implementation | single_definition | data_structure | no |
| b103 | g2 | dates/durations | function_implementation | multi_symbol | iteration | yes |
| b104 | g2 | encodings/serialization | function_implementation | single_definition | numeric | no |
| b105 | g2 | validation/normalization | bug_fix | single_definition | iteration | - |
| b106 | g2 | state machines/protocols | function_implementation | multi_symbol | data_structure | no |
| b107 | g2 | collections/iterators | function_implementation | single_definition | error_handling | no |
| b108 | g2 | geometry/grids | bug_fix | multi_symbol | data_structure | - |
| b109 | g2 | searching/selection | function_implementation | single_definition | string | yes |
| b110 | g2 | caching/memoization | function_implementation | single_definition | recursion | no |
| b111 | g2 | diff/merge/undo | bug_fix | single_definition | error_handling | - |
| b112 | g2 | tabular data/aggregation | function_implementation | single_definition | string | no |
| b113 | g2 | bit manipulation | function_implementation | multi_symbol | string | yes |
| b114 | g2 | randomless simulation | function_implementation | single_definition | iteration | yes |
| b115 | g2 | pattern matching | bug_fix | single_definition | data_structure | - |
| b116 | g2 | inventory/stock-tracking | function_implementation | multi_symbol | recursion | no |
| b117 | g2 | rate limiting/quotas | function_implementation | single_definition | iteration | no |
| b118 | g2 | versioning/ordering | bug_fix | multi_symbol | numeric | - |
| b119 | g2 | text layout/wrapping | function_implementation | single_definition | numeric | yes |
| b120 | g2 | units/conversion | function_implementation | single_definition | string | no |

### band-batch E — g3, ids b121–b140

| id | band | domain | task_type | file_shape | shape | scaffold |
|---|---|---|---|---|---|---|
| b121 | g3 | diff/merge/undo | function_implementation | single_definition | numeric | no |
| b122 | g3 | tabular data/aggregation | bug_fix | single_definition | iteration | - |
| b123 | g3 | bit manipulation | function_implementation | multi_symbol | data_structure | no |
| b124 | g3 | randomless simulation | function_implementation | single_definition | error_handling | no |
| b125 | g3 | pattern matching | bug_fix | multi_symbol | data_structure | - |
| b126 | g3 | inventory/stock-tracking | function_implementation | single_definition | string | yes |
| b127 | g3 | rate limiting/quotas | function_implementation | single_definition | recursion | no |
| b128 | g3 | versioning/ordering | bug_fix | single_definition | error_handling | - |
| b129 | g3 | text layout/wrapping | function_implementation | single_definition | string | no |
| b130 | g3 | units/conversion | function_implementation | multi_symbol | string | yes |
| b131 | g3 | filesystem paths/globbing | function_implementation | single_definition | iteration | yes |
| b132 | g3 | queues/buffers | bug_fix | single_definition | data_structure | - |
| b133 | g3 | layered configuration/precedence | function_implementation | multi_symbol | recursion | no |
| b134 | g3 | checksums/integrity | function_implementation | single_definition | iteration | no |
| b135 | g3 | templating/substitution | bug_fix | multi_symbol | numeric | - |
| b136 | g3 | strings/text-processing | function_implementation | single_definition | numeric | yes |
| b137 | g3 | parsing/tokenizing | function_implementation | single_definition | string | no |
| b138 | g3 | intervals/scheduling | bug_fix | single_definition | error_handling | - |
| b139 | g3 | graphs/ordering | function_implementation | single_definition | data_structure | no |
| b140 | g3 | trees/hierarchies | function_implementation | multi_symbol | iteration | yes |
