# Bench pilot generation brief — lane/225 Phase 3 (2026-08-10)

You are authoring paired benchmark problems for mcgyvr's permanent bench
(#225). Design of record: `docs/bench-design-2026-08-10.md`. Every problem
you write will be judged by `tools/bench/admit.py` — the gate is the
arbiter, and this brief exists so your first pass survives it.

## What one problem is

One problem = two arms of the SAME problem, same id, plus one sidecar:

```
tools/bench/tasks/ts/<id>/contract.yaml   reference.ts   accept.mjs   meta.json
tools/bench/tasks/py/<id>/contract.yaml   reference.py   accept.py
```

- id matches `^b\d{3}-[a-z0-9]+(-[a-z0-9]+)*$` (e.g. `b007-ring-router`).
  Directory name == contract `id` in BOTH arms. Your ids are assigned below;
  you choose the slug (2–3 short words, specific to the problem).
- The `task:` prose states the same problem in both arms, identical except
  the target symbol's idiomatic name (`parseDuration` in ts / `parse_duration`
  in py). Interfaces/types are the language-specific rendering.
- `meta.json` lives ONLY in the ts arm.

Templates to read before writing anything (copy their conventions exactly):
- `tools/problems/tasks/ts/p001-parse-duration/` + `tools/problems/tasks/py/p001-parse-duration/` — function_implementation
- `tools/problems/tasks/ts/p007-free-windows/` + `tools/problems/tasks/py/p007-free-windows/` — bug_fix

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
  "steering_band": "g2"
}
```

- `file_shape`: `single_definition` | `multi_symbol` (from your steering row).
- `shape`: exactly one of `recursion`, `iteration`, `string`, `numeric`,
  `data_structure`, `error_handling` (from your row) — it must honestly name
  the problem's primary mechanism. If your written problem drifted, relabel
  honestly rather than keeping the assigned label.
- `steering_band`: your band, verbatim (`g1`..`g4`).
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
  symbol at least once.

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
   pool's 499 problems, the retired sets, and every other bench candidate;
   ≥ 0.55 rejects. Defence: write prose specific to YOUR domain and
   mechanics; never reuse a template paragraph across your problems.

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
| g1 | 30–45 lines | 22–35 | 10–14 | just above d3-class |
| g2 | 45–60 | 34–46 | 13–17 | lower gap |
| g3 | 60–80 | 45–62 | 16–20 | upper gap |
| g4 | 80–120 | 60–95 | 18–26 | pool-class and past it |

Difficulty comes from unit-of-work (more required behaviour, more cases,
more state), NEVER from puzzle-trickiness or obscure algorithms. A g4
problem is a bigger honest job, not a riddle. Every reference must be code
a careful practitioner writes: idiomatic, no dead code, no padding to hit
line counts.

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

band g1 — ids b001–b010; band g2 — b011–b020; band g3 — b021–b030;
band g4 — b031–b040.

| id | band | domain | task_type | file_shape | shape | scaffold |
|---|---|---|---|---|---|---|
| b001 | g1 | strings/text-processing | function_implementation | single_definition | string | no |
| b002 | g1 | parsing/tokenizing | function_implementation | multi_symbol | string | yes |
| b003 | g1 | intervals/scheduling | function_implementation | single_definition | iteration | yes |
| b004 | g1 | graphs/ordering | bug_fix | single_definition | data_structure | — |
| b005 | g1 | trees/hierarchies | function_implementation | multi_symbol | recursion | no |
| b006 | g1 | dynamic programming | function_implementation | single_definition | iteration | no |
| b007 | g1 | numeric/precision | bug_fix | multi_symbol | numeric | — |
| b008 | g1 | dates/durations | function_implementation | single_definition | numeric | yes |
| b009 | g1 | encodings/serialization | function_implementation | single_definition | string | no |
| b010 | g1 | validation/normalization | bug_fix | single_definition | error_handling | — |
| b011 | g2 | state machines/protocols | function_implementation | single_definition | data_structure | no |
| b012 | g2 | collections/iterators | function_implementation | multi_symbol | iteration | yes |
| b013 | g2 | geometry/grids | function_implementation | single_definition | numeric | yes |
| b014 | g2 | searching/selection | bug_fix | single_definition | iteration | — |
| b015 | g2 | caching/memoization | function_implementation | multi_symbol | data_structure | no |
| b016 | g2 | diff/merge/undo | function_implementation | single_definition | string | no |
| b017 | g2 | tabular data/aggregation | bug_fix | multi_symbol | data_structure | — |
| b018 | g2 | bit manipulation | function_implementation | single_definition | numeric | yes |
| b019 | g2 | randomless simulation | function_implementation | single_definition | iteration | no |
| b020 | g2 | pattern matching | bug_fix | single_definition | recursion | — |
| b021 | g3 | graphs/ordering | function_implementation | single_definition | data_structure | no |
| b022 | g3 | numeric/precision | function_implementation | multi_symbol | numeric | yes |
| b023 | g3 | strings/text-processing | function_implementation | single_definition | string | yes |
| b024 | g3 | encodings/serialization | bug_fix | single_definition | error_handling | — |
| b025 | g3 | intervals/scheduling | function_implementation | multi_symbol | data_structure | no |
| b026 | g3 | validation/normalization | function_implementation | single_definition | error_handling | no |
| b027 | g3 | trees/hierarchies | bug_fix | multi_symbol | recursion | — |
| b028 | g3 | dynamic programming | function_implementation | single_definition | iteration | yes |
| b029 | g3 | parsing/tokenizing | function_implementation | single_definition | string | no |
| b030 | g3 | dates/durations | bug_fix | single_definition | numeric | — |
| b031 | g4 | searching/selection | function_implementation | single_definition | iteration | no |
| b032 | g4 | bit manipulation | function_implementation | multi_symbol | numeric | yes |
| b033 | g4 | state machines/protocols | function_implementation | single_definition | data_structure | yes |
| b034 | g4 | diff/merge/undo | bug_fix | single_definition | string | — |
| b035 | g4 | pattern matching | function_implementation | multi_symbol | recursion | no |
| b036 | g4 | collections/iterators | function_implementation | single_definition | data_structure | no |
| b037 | g4 | randomless simulation | bug_fix | multi_symbol | iteration | — |
| b038 | g4 | caching/memoization | function_implementation | single_definition | data_structure | yes |
| b039 | g4 | tabular data/aggregation | function_implementation | single_definition | data_structure | no |
| b040 | g4 | geometry/grids | bug_fix | single_definition | numeric | — |
