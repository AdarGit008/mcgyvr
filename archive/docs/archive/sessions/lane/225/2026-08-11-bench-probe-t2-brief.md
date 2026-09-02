# Bench probe generation brief — lane/225 Phase 4, tranche 2 (2026-08-11)

You are authoring paired benchmark problems for mcgyvr's permanent bench
(#225). Design of record: `docs/bench-design-2026-08-10.md`. Every problem
you write will be judged by `tools/bench/admit.py` — the gate is the
arbiter, and this brief exists so your first pass survives it.

**What this tranche is (read this — it shapes every problem you write).**
The campaign is paused on a measurement question: band g0 (ts 20–30 lines,
9–12 asserts) was aimed at a 30–50% pass rate on the floor model and read
4.3% ts / 21.7% py. Two knobs could explain the miss — reference SIZE and
EDGE-CASE LOAD — and this tranche isolates them. It is two cells of 40,
each changing exactly ONE knob relative to g0, everything else held:

- **Cell `g0a` — smaller only.** Reference roughly half g0's size; the
  checker load stays at g0's level (9–12 assert statements per arm, 3–6
  enumerated rejections). A tiny function, checked as thoroughly as g0.
- **Cell `g0b` — lighter checker only.** Reference stays at g0's size; the
  checker load halves (5–8 assert statements per arm, at most 2 enumerated
  rejections). Because less validation is demanded, the core behaviour must
  be honestly meatier to fill the same size band — never padded.

Because this is an isolation experiment, EVERY problem in this tranche is
`function_implementation` + `single_definition`. No bug_fix, no
multi_symbol — a mix difference would confound the comparison. The
baseline both cells are read against is g0's matching subset, already
measured: 1/16 ts, 3/16 py.

## What one problem is

One problem = two arms of the SAME problem, same id, plus one sidecar:

```
tools/bench/tasks/ts/<id>/contract.yaml   reference.ts   accept.mjs   meta.json
tools/bench/tasks/py/<id>/contract.yaml   reference.py   accept.py
```

- id matches `^b\d{3}-[a-z0-9]+(-[a-z0-9]+)*$`. Directory name == contract
  `id` in BOTH arms. Your ids are assigned below; you choose the slug (2–3
  short words, specific to the problem).
- The `task:` prose states the same problem in both arms, identical except
  the target symbol's idiomatic name (`parseDuration` in ts /
  `parse_duration` in py). Interfaces/types are the language-specific
  rendering.
- `meta.json` lives ONLY in the ts arm.

Templates to read before writing anything (copy their conventions exactly):
- `tools/problems/tasks/ts/p001-parse-duration/` + `tools/problems/tasks/py/p001-parse-duration/` — function_implementation
- For size feel: `tools/bench/tasks/ts/b041-trim-caption/` and
  `b046-rest-harvest` are admitted g0 problems (20–30 ts lines). `g0a`
  aims at roughly HALF that reference; `g0b` matches it. NEVER reuse their
  prose, domains-of-the-day, or assertion text — the near-duplicate screen
  compares you against every admitted problem.

## contract.yaml — exact shape

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

Do not add fields not shown here (no `limits`, no `version`, no `deps`).

## meta.json (ts arm only)

```json
{
  "file_shape": "single_definition",
  "shape": "iteration",
  "steering_band": "g0a"
}
```

- `file_shape` is `single_definition` for every problem in this tranche:
  the interface declares EXACTLY ONE function per arm (the gate counts
  `function <name>` / `def <name>` matches in the interface string). The
  reference may still use helpers nested inside the function or (ts)
  non-exported module-level `function helper()`s not mentioned in the
  interface.
- `shape`: exactly one of `recursion`, `iteration`, `string`, `numeric`,
  `data_structure`, `error_handling` (from your row) — it must honestly
  name the problem's primary mechanism. If your written problem drifted,
  relabel honestly rather than keeping the assigned label.
- `steering_band`: your cell, verbatim (`g0a` or `g0b`).

## Mandated declaration forms (the gate degrades the target mechanically)

- ts reference: the target symbol MUST be declared as
  `export function <name>(` and that literal string must appear EXACTLY
  ONCE in the file (don't repeat it in a comment). No arrow-function
  exports for declared symbols. Node runs `accept.mjs` importing
  `./solution.ts` with type stripping: use only erasable TypeScript
  (annotations, interfaces, type aliases) — NO enums, NO namespaces, NO
  parameter properties.
- py reference: the interface-declared symbol is a plain module-level
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
4. Anti-triviality: the reference with ONLY the target symbol degraded (a
   no-op stub and an echo-first-arg stub, helpers intact) must FAIL the
   checker — both stubs, both arms. This binds `g0b` especially: even a
   light checker must assert real behaviour, not "returns something".
5. Checker floor: ≥ 5 occurrences of the substring `assert` per arm. For
   `g0b`'s py arm this means the 5-statement end of the band is the legal
   minimum — never go below 5 assert statements in py.
6. Front-door blocklist: NO declared function (either arm) may share a
   normalised name (lowercased, underscores stripped) with HumanEval's 164
   or MBPP+'s 378 entry points. Use two-word, domain-specific names and
   you will clear it.
7. Near-duplicate screen: word-set Jaccard of your `task:` prose vs the
   pool's 499 problems, the retired sets, the 140 admitted bench problems
   (both halves), and every other candidate; ≥ 0.55 rejects. Defence:
   write prose specific to YOUR domain and mechanics; never reuse a
   template paragraph across your problems.

## Checker discipline (this is the instrument; be strict)

- Shape-strict: assert exact values / exact structures, not truthiness.
- Both arms assert the SAME behaviour (same cases, same expected values) —
  they are one problem. Count assert STATEMENTS the same in both arms;
  the ts import line's substring hits don't count toward your band.
- Rejections: ts uses `assert.throws(() => fn(bad), Error, "message")`; py
  uses a local `def rejects(...)` helper returning True when the call
  raises, then `assert rejects(bad), "message"` per case (see p001's
  accept.py).
- The reference must genuinely pass; the stubs must genuinely fail.
  Verify by running, not by inspection.

## The two cells (this is what makes the tranche an experiment)

Sizes are TOTAL file lines of the reference; asserts are STATEMENTS per
arm. Land inside them — a probe that drifts out of band measures nothing.

| cell | ts reference | py reference | assert statements/arm | enumerated rejections | intent |
|---|---|---|---|---|---|
| g0a | 12–20 lines | 9–15 | 9–12 | 3–6 | half the size, full checker load |
| g0b | 20–30 lines | 15–23 | 5–8 | 0–2 | full size, half the checker load |

- `g0a`: one small, sharply stated behaviour — but checked as hard as g0:
  boundaries, ties, empties, and 3–6 explicit rejection cases, all
  enumerated in the prose. The reference is small because the JOB is
  small, not because validation was silently skipped: whatever the prose
  demands, the reference handles.
- `g0b`: an honestly meatier core behaviour filling g0's size band, but
  the contract demands little defensiveness: at most 2 rejection cases
  (0 is fine — total functions over well-typed input are welcome), and a
  checker of 5–8 assert statements covering the main behaviour and a
  couple of boundaries. No padding, no dead code: the size comes from
  real required behaviour.
- Difficulty comes from unit-of-work, NEVER from puzzle-trickiness or
  obscure algorithms, in both cells.
- scaffold=yes: `target_content` carries a partial file — imports/
  constants/helpers implemented or stubbed with TODO, the target visibly
  incomplete. It must NOT be a working solution. Same idea in both arms.

## Workflow (per agent)

1. Read this brief, then the template directories and size exemplars.
2. Author your 5 assigned problems (both arms + meta.json each), exactly
   per your steering rows.
3. Self-gate from the repo root, EXPLICIT ids only (never bare — other
   agents' half-written candidates are in the same tree):

   ```
   cd /home/adaramir/claude/mcgyvr && uv run --no-sync python tools/bench/admit.py b1NN-slug b1NN-slug ...
   ```

4. Fix and re-run until every one of your ids prints ADMIT, then verify
   your references' line counts and assert-statement counts sit inside
   your cell's bands (both arms). A near-duplicate rejection means replace
   the problem's idea, not its wording. NEVER pass `--pin`. NEVER touch
   ids outside your batch, `tools/problems/`, or any file outside
   `tools/bench/tasks/`.
5. If an id is unsalvageable after ~3 rewrites, delete both arm
   directories and report it as failed.

## The steering table

Four band-batches of 20: **A1 + A2 are cell g0a** (b141–b160, b161–b180),
**B1 + B2 are cell g0b** (b181–b200, b201–b220). Within a band-batch no
domain repeats; across band-batches domains recur deliberately — your
problem must still be its own idea.

### band-batch A1 — g0a, ids b141–b160

| id | band | domain | task_type | file_shape | shape | scaffold |
|---|---|---|---|---|---|---|
| b141 | g0a | encodings/serialization | function_implementation | single_definition | string | no |
| b142 | g0a | validation/normalization | function_implementation | single_definition | iteration | yes |
| b143 | g0a | state machines/protocols | function_implementation | single_definition | data_structure | no |
| b144 | g0a | collections/iterators | function_implementation | single_definition | numeric | no |
| b145 | g0a | geometry/grids | function_implementation | single_definition | string | yes |
| b146 | g0a | searching/selection | function_implementation | single_definition | iteration | no |
| b147 | g0a | caching/memoization | function_implementation | single_definition | error_handling | no |
| b148 | g0a | diff/merge/undo | function_implementation | single_definition | recursion | yes |
| b149 | g0a | tabular data/aggregation | function_implementation | single_definition | data_structure | no |
| b150 | g0a | bit manipulation | function_implementation | single_definition | numeric | no |
| b151 | g0a | randomless simulation | function_implementation | single_definition | string | yes |
| b152 | g0a | pattern matching | function_implementation | single_definition | iteration | no |
| b153 | g0a | inventory/stock-tracking | function_implementation | single_definition | error_handling | no |
| b154 | g0a | rate limiting/quotas | function_implementation | single_definition | data_structure | yes |
| b155 | g0a | versioning/ordering | function_implementation | single_definition | numeric | no |
| b156 | g0a | text layout/wrapping | function_implementation | single_definition | string | no |
| b157 | g0a | units/conversion | function_implementation | single_definition | iteration | yes |
| b158 | g0a | filesystem paths/globbing | function_implementation | single_definition | recursion | no |
| b159 | g0a | queues/buffers | function_implementation | single_definition | data_structure | no |
| b160 | g0a | layered configuration/precedence | function_implementation | single_definition | error_handling | yes |

### band-batch A2 — g0a, ids b161–b180

| id | band | domain | task_type | file_shape | shape | scaffold |
|---|---|---|---|---|---|---|
| b161 | g0a | versioning/ordering | function_implementation | single_definition | iteration | no |
| b162 | g0a | text layout/wrapping | function_implementation | single_definition | error_handling | no |
| b163 | g0a | units/conversion | function_implementation | single_definition | recursion | yes |
| b164 | g0a | filesystem paths/globbing | function_implementation | single_definition | data_structure | no |
| b165 | g0a | queues/buffers | function_implementation | single_definition | numeric | no |
| b166 | g0a | layered configuration/precedence | function_implementation | single_definition | string | yes |
| b167 | g0a | checksums/integrity | function_implementation | single_definition | iteration | no |
| b168 | g0a | templating/substitution | function_implementation | single_definition | error_handling | no |
| b169 | g0a | strings/text-processing | function_implementation | single_definition | data_structure | yes |
| b170 | g0a | parsing/tokenizing | function_implementation | single_definition | numeric | no |
| b171 | g0a | intervals/scheduling | function_implementation | single_definition | string | no |
| b172 | g0a | graphs/ordering | function_implementation | single_definition | iteration | yes |
| b173 | g0a | trees/hierarchies | function_implementation | single_definition | recursion | no |
| b174 | g0a | dynamic programming | function_implementation | single_definition | data_structure | no |
| b175 | g0a | numeric/precision | function_implementation | single_definition | error_handling | yes |
| b176 | g0a | dates/durations | function_implementation | single_definition | string | no |
| b177 | g0a | encodings/serialization | function_implementation | single_definition | iteration | yes |
| b178 | g0a | validation/normalization | function_implementation | single_definition | data_structure | no |
| b179 | g0a | state machines/protocols | function_implementation | single_definition | numeric | no |
| b180 | g0a | collections/iterators | function_implementation | single_definition | string | yes |

### band-batch B1 — g0b, ids b181–b200

| id | band | domain | task_type | file_shape | shape | scaffold |
|---|---|---|---|---|---|---|
| b181 | g0b | graphs/ordering | function_implementation | single_definition | string | yes |
| b182 | g0b | trees/hierarchies | function_implementation | single_definition | iteration | no |
| b183 | g0b | dynamic programming | function_implementation | single_definition | error_handling | no |
| b184 | g0b | numeric/precision | function_implementation | single_definition | data_structure | yes |
| b185 | g0b | dates/durations | function_implementation | single_definition | numeric | no |
| b186 | g0b | encodings/serialization | function_implementation | single_definition | string | no |
| b187 | g0b | validation/normalization | function_implementation | single_definition | iteration | yes |
| b188 | g0b | state machines/protocols | function_implementation | single_definition | recursion | no |
| b189 | g0b | collections/iterators | function_implementation | single_definition | data_structure | no |
| b190 | g0b | geometry/grids | function_implementation | single_definition | error_handling | yes |
| b191 | g0b | searching/selection | function_implementation | single_definition | string | no |
| b192 | g0b | caching/memoization | function_implementation | single_definition | iteration | yes |
| b193 | g0b | diff/merge/undo | function_implementation | single_definition | data_structure | no |
| b194 | g0b | tabular data/aggregation | function_implementation | single_definition | numeric | no |
| b195 | g0b | bit manipulation | function_implementation | single_definition | string | yes |
| b196 | g0b | randomless simulation | function_implementation | single_definition | iteration | no |
| b197 | g0b | pattern matching | function_implementation | single_definition | error_handling | no |
| b198 | g0b | inventory/stock-tracking | function_implementation | single_definition | recursion | yes |
| b199 | g0b | rate limiting/quotas | function_implementation | single_definition | data_structure | no |
| b200 | g0b | versioning/ordering | function_implementation | single_definition | numeric | no |

### band-batch B2 — g0b, ids b201–b220

| id | band | domain | task_type | file_shape | shape | scaffold |
|---|---|---|---|---|---|---|
| b201 | g0b | bit manipulation | function_implementation | single_definition | string | no |
| b202 | g0b | randomless simulation | function_implementation | single_definition | iteration | yes |
| b203 | g0b | pattern matching | function_implementation | single_definition | recursion | no |
| b204 | g0b | inventory/stock-tracking | function_implementation | single_definition | data_structure | no |
| b205 | g0b | rate limiting/quotas | function_implementation | single_definition | error_handling | yes |
| b206 | g0b | versioning/ordering | function_implementation | single_definition | string | no |
| b207 | g0b | text layout/wrapping | function_implementation | single_definition | iteration | yes |
| b208 | g0b | units/conversion | function_implementation | single_definition | data_structure | no |
| b209 | g0b | filesystem paths/globbing | function_implementation | single_definition | numeric | no |
| b210 | g0b | queues/buffers | function_implementation | single_definition | string | yes |
| b211 | g0b | layered configuration/precedence | function_implementation | single_definition | iteration | no |
| b212 | g0b | checksums/integrity | function_implementation | single_definition | error_handling | no |
| b213 | g0b | templating/substitution | function_implementation | single_definition | recursion | yes |
| b214 | g0b | strings/text-processing | function_implementation | single_definition | data_structure | no |
| b215 | g0b | parsing/tokenizing | function_implementation | single_definition | numeric | no |
| b216 | g0b | intervals/scheduling | function_implementation | single_definition | string | yes |
| b217 | g0b | graphs/ordering | function_implementation | single_definition | iteration | no |
| b218 | g0b | trees/hierarchies | function_implementation | single_definition | error_handling | no |
| b219 | g0b | dynamic programming | function_implementation | single_definition | data_structure | yes |
| b220 | g0b | numeric/precision | function_implementation | single_definition | numeric | no |

## Addendum — mid-run spend-limit pause (2026-08-11)

The monthly spend limit killed 13 of 16 agents mid-run. Three of those had
already finished authoring (b151–b154, b156–b160, b166–b170 all ADMIT on
an explicit gate run); **b155 was lost mid-write** (empty arm directories,
no files) and is **retired, never reused**, per the campaign's pause
doctrine. Its steering row re-issues under a fresh id:

| id | band | domain | task_type | file_shape | shape | scaffold |
|---|---|---|---|---|---|---|
| b221 | g0a | versioning/ordering | function_implementation | single_definition | numeric | no |

A second pause struck the resumed run before any of its agents finished.
**b176–b180 and b186 were also lost mid-write** (empty or one-armed
directories, removed) and join b155 as retired-never-reused. Their rows
re-issue under fresh ids:

| id | band | domain | task_type | file_shape | shape | scaffold | replaces |
|---|---|---|---|---|---|---|---|
| b221 | g0a | versioning/ordering | function_implementation | single_definition | numeric | no | b155 |
| b222 | g0a | dates/durations | function_implementation | single_definition | string | no | b176 |
| b223 | g0a | encodings/serialization | function_implementation | single_definition | iteration | yes | b177 |
| b224 | g0a | validation/normalization | function_implementation | single_definition | data_structure | no | b178 |
| b225 | g0a | state machines/protocols | function_implementation | single_definition | numeric | no | b179 |
| b226 | g0a | collections/iterators | function_implementation | single_definition | string | yes | b180 |
| b227 | g0b | encodings/serialization | function_implementation | single_definition | string | no | b186 |

Retired ids are never reused: b155, b176–b180 and b186 will not appear in
the bench under any content. The cells still close at 40 each — g0a from
b141–b175 plus b221–b226, g0b from b181–b185, b187–b220 plus b227.
