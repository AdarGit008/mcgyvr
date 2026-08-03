# reach-jsts-2026-08-03 — a candidate semantic resolver for JavaScript/TypeScript

Issue: [#133](https://github.com/AdarGit008/mcgyvr/issues/133), under
[#110](https://github.com/AdarGit008/mcgyvr/issues/110).
Corpus: `records/corpora/reach-2026-08-02/corpus.json`, the `immerjs/immer` frame
(27 accepted changes, 1 675 added source lines).
Tool: `tools/reach/count3_jsts.py`.
Rows: `count3-jsts-falsepos.jsonl`. Classification table: `diagnostic-codes.json`.

#129 measured a candidate resolver over the corpus's two Python frames and said
plainly what it could not do: "the JS/TS half of the launch languages has no
candidate measured" (`tools/reach/count3.py`). #123 was then sized on evidence
covering one of two launch languages. This closes that gap for the second.

## The survey

Nothing here was adopted on a description. Each candidate was checked against
its own source or its own documentation at a pinned revision, which is the step
[CLM-0006](../../claims/CLM-0006.json) exists to enforce — half of ghostcall's
inherited description turned out to be wrong, and the wrong half was the one
#123 was leaning on.

| Candidate | Verdict | Why |
| --- | --- | --- |
| **ghostcall** | not applicable | Parses Python with `ast` and resolves with `importlib`. There is no JS/TS in it. |
| **Hallucination Inspector** (arXiv:2604.20202) | rejected | Java/Android only. The authors: "We implemented the Hallucination Inspector in Python using the TreeSitter library for parsing and a custom-built indexer for the Android API level 35", and name their own scope limit as "the Android Java ecosystem". "Language-agnostic" is a property of the approach, not of the artifact. |
| **WM-SEMERU `Hallucinations-in-Code`** (arXiv:2601.19106) | rejected | Evaluated on Python over five libraries. TypeScript is named as somewhere the approach "generalizes", not as something demonstrated. Its knowledge base is built by *runtime introspection of imported libraries* — the same design as ghostcall, and for TypeScript source there is nothing to introspect until it is built. |
| **`eslint-plugin-import` → `import/named`** | rejected | Checks import and export **specifiers** only — `ImportDeclaration`, `ExportNamedDeclaration`, `VariableDeclarator` — never member access on a value. It returns early on `importKind === 'type'`, and the plugin disables the rule outright in its own `typescript` config. On a frame whose changes are largely type-level it is close to vacuous by construction. |
| **`tsd`** | rejected | Runs assertions you write in `.test-d.ts` files against declarations you own. It judges a hand-written test, not an arbitrary changed file. |
| **oxlint (type-aware)** | rejected as *lighter*; is the same thing | Its own documentation: type-aware rules run in `tsgolint`, which "Builds TypeScript programs using `typescript-go`". It requires TypeScript 7.0+, a `tsconfig.json`, resolved type information, dependencies installed, and dependent packages built so `.d.ts` files exist. It is a TypeScript compiler with a faster front-end, carrying the same environment cost. |
| **Biome** | rejected | Ships a custom type-inference engine rather than the compiler, explicitly trading accuracy for speed. A resolver whose parity with the type system is approximate is the wrong instrument for a check whose entire output is "this does not exist". |
| **a live-runtime resolver** (the direct ghostcall analogue) | rejected | Resolving `a.b.c` by importing and introspecting requires the TypeScript to be built first — immer builds with `tsup` — so the cost is a build per change *plus* every module's side effects at import. Strictly more expensive than the type-graph route it would be approximating. |
| **the TypeScript compiler API** | **adopted, and measured below** | `ts.createProgram` → `getSemanticDiagnostics`, verdict read from the diagnostic code. It is the only candidate that answers the question for arbitrary changed code in this language. |

The survey's structural result is worth stating separately from the numbers,
because it is what actually constrains #110: **for JavaScript/TypeScript, the
capability "does this name resolve?" is not available outside a type checker.**
The two research artifacts are other languages. The one lightweight static tool
covers imports and not members, and switches itself off for TypeScript. The
fastest production alternative embeds a port of the compiler and documents the
same prerequisites. There is no JS/TS equivalent of "four stdlib-only files".

## The candidate, and what it needs to run

`typescript` 5.9.3, pinned by the sha512 of its published tarball and verified in
the container before it is unpacked, failing closed on a mismatch — ADR-0011's
rule for a resolver that is staged rather than installed.

```
https://registry.npmjs.org/typescript/-/typescript-5.9.3.tgz
sha512-jl1vZzPDinLr9eUt3J/t7V6FgNEw9QjvBPdysz9KfQDD41fQrC2Y4vKQdiaUpFT4bXlb1RHhLpp8wtm6M5TgSw==
```

Unpacked it is 4.4 MB against ghostcall's four files, and it needs three things
ghostcall did not: the target's `tsconfig.json` for compiler options, the
target's `node_modules` for `@types` packages and dependency declarations, and a
program built over the whole import graph rather than one file at a time.

"Needs `node_modules`" is an assertion until it is a number, so it is an arm:

- **`target-ts`** — the frame's own `node_modules` installed, resolving with the
  frame's own `typescript` (5.0.2, the version its lockfile pins at every one of
  the 27 commits). Environment and checker both the target's, which is the
  arrangement [ADR-0006](../../../docs/decisions/0006-the-type-checker-is-the-target-repositorys.md)
  describes.
- **`staged-ts`** — the frame's `node_modules` installed, resolving with the
  staged 5.9.3. Environment the target's, checker ours. This arm tests version
  drift.
- **`bare`** — no `node_modules` at all, staged checker. What a rung that
  declined to provision the target would see.

Each row carries `environment` — `installed`, `stale` or `none` — so a verdict
produced against a tree whose install did not match the commit can be told from
one produced against a tree whose install did.

## Counting rules

Same as Counts 1–3, and the reasons are `tools/reach/count3.py`'s:

- **Per change, restricted to the lines the change added.** The rung judges
  added lines (`gate/changeset.py`), so a flag elsewhere is not a verdict it
  would render. The whole-file figure is recorded beside it.
- **Only the frame's own source.** A diagnostic inside `node_modules` or a test
  tree is not a verdict about the change. Folding it in would inflate every arm
  by the same ambient noise — the unfiltered run at the pinned commit reports
  nine `@types/babel__*` module-resolution errors that have nothing to do with
  any change measured here.
- **A flag on shipped code is a *presumptive* false positive.** Every file
  measured passed a declared, human-gated check. That is a proxy, not proof, so
  each flag is written out with its path, line, code and message for checking by
  hand.
- **Existence is counted separately from environment.** TypeScript spends
  distinct codes on the distinction ghostcall draws between `hallucinated` and
  `module_missing`: 2339/2304/2305 assert a named thing does not exist, while
  2307/2580/2688 report that the resolver could not see a module, a types
  package or a lib. `diagnostic-codes.json` carries the split, and the message
  template for each code is extracted by the driver **from the bytes of the
  resolver that produced the verdicts** rather than from documentation about it.
  The `class` column is this repository's assignment; the codes and messages are
  TypeScript's.

### The denominator does not transfer

[CLM-0009](../../claims/CLM-0009.json)'s 358 is *resolved call chains*, because
ghostcall resolves calls. A TypeScript diagnostic lands anywhere an expression
does — a type reference, a property access in a type position, an identifier in
a declaration — and immer's accepted changes are heavily type-level: the newest
change in the frame touches `src/types/types-external.ts` and contains **no call
expression at all**. Reporting "flags per call on added lines" for this frame
would divide by a number that has little to do with what was judged.

Three denominators are therefore recorded per change — call expressions
(including `new`), property accesses, and identifiers — and the rate is reported
against each. None of them is the "right" one; stating all three is what stops a
denominator being chosen after the numerator is known.

## Results

27 changes, 3 arms, 81 rows, all measured. No install failed, so no arm ran
against a `stale` tree.

**Existence verdicts on added lines: zero, in every arm.** The whole-file figure
is also zero, in every arm.

| Denominator on added lines | count | existence flags | rule-of-three upper bound (95%) |
| --- | ---: | ---: | ---: |
| call expressions (incl. `new`) | 338 | 0 | ~0.9% |
| property accesses | 360 | 0 | ~0.8% |
| identifiers | 2 576 | 0 | ~0.12% |

Whole-file, the same three denominators are 2 952 / 3 110 / 22 724, also with
zero existence flags.

### The zero is not a silent instrument

This is the check the headline depends on, and `count3.py` did not have to make
it because its Python arm produced non-zero flags off the added lines. Here
everything is zero, and a resolver that had quietly failed to build a program
would report exactly the same table.

`--control` writes a file of references that certainly do not exist into the
frame at its pinned commit, measures it through the same driver, and deletes it.
All three arms flag all four:

```
2305  Module '"./immer"' has no exported member 'nonExistentExport133'.
2304  Cannot find name 'nonExistentGlobalFunction133'.
2339  Property 'nonExistentStringMethod133' does not exist on type 'string'.
2551  Property 'lenght' does not exist on type 'string'. Did you mean 'length'?
```

The correct `produce(...)` call in the same file is not flagged by any arm. Full
output in `positive-control.json`.

### What the arms separate is cost, not accuracy

Flag counts are sums over changes and double-count a site in a file touched by
more than one change — the artefact CLM-0009 had to unpick by hand — so the
deduplicated site count is given beside each.

| Arm | environment flags | other diagnostics | existence |
| --- | ---: | ---: | ---: |
| `target-ts` — its `node_modules`, its `typescript` 5.0.2 | 0 | 0 | 0 |
| `staged-ts` — its `node_modules`, our `typescript` 5.9.3 | 0 | 153 (**36** sites) | 0 |
| `bare` — no `node_modules`, our `typescript` 5.9.3 | 146 (**21** sites) | 0 | 0 |

- **`target-ts` is completely clean.** Nothing in `src/` at any of the 27
  commits. This is the arrangement ADR-0006 describes, and on this frame it
  costs a `yarn install` and reports nothing false.
- **`staged-ts` turns 0 into 153 flags at 36 distinct sites.** Every one is a type-compatibility
  error — 2416 "Property 'keys' in type 'DraftMap' is not assignable to the same
  property in base type 'Map<any, any>'" and 2322 — on code that shipped, caused
  by nothing but running a compiler version the repository did not pin. None is
  an existence verdict, so a rung scoped as this one is stays unaffected; a rung
  that treated *any* semantic error as its signal would fail immer's accepted
  changes for a reason that is purely about which compiler we chose.
- **`bare` turns 0 into 146 at 21 distinct sites, and all of them are the same
  thing:** 2580, `Cannot find name 'process'`, on correctly-guarded code in
  `src/core/proxy.ts`, `src/utils/errors.ts`, `src/plugins/patches.ts` and
  `src/core/finalize.ts`. Declining to provision does not make the resolver
  quiet; it makes it wrong in one predictable direction.

Neither the 153 nor the 146 lands on a line any of these 27 changes added. That
is a fact about which lines this corpus happens to contain, not a property of the
resolver, and it should not be read as "the rung would not have seen them".

### What this predicts, tested rather than assumed

#133 asked whether the Python result transfers: ghostcall's every false positive
was platform-conditional code correct on the platform it guards, and the question
was whether a type-based resolver inherits an analogous failure mode.

It does not inherit that one — resolving from a type graph rather than a live
interpreter, this candidate has no notion of the running platform to be wrong
about, and produced no platform-conditional flag anywhere. It acquires two
different ones instead, and both are environment rather than authorship:
**compiler version drift** (`staged-ts`) and **unprovisioned dependencies**
(`bare`). Where ghostcall's mitigation was a property of the container's
platform, this candidate's is a property of *whose* compiler runs and *whether
the install ran* — which is a question about ADR-0006 and #114, not about the
resolver.

### One fact about the repository, not the resolver

immer declares **no type-check command** in `package.json` at any of the 27
commits, while pinning `typescript ^5.0.2` as a devDependency at all of them. A
rung that delegated to the target's *declared* type-checker would have had
nothing to run on this frame, even though the repository ships both a compiler
and a `tsconfig.json` for one to use. That is a data point for
[#114](https://github.com/AdarGit008/mcgyvr/issues/114) and
[#132](https://github.com/AdarGit008/mcgyvr/issues/132), and it is why the arms
above construct a program from the `tsconfig` rather than running a declared
command.

## What this does not establish

- **Not that the rung should adopt it.** This measured one candidate over one
  frame of one corpus. It says what the candidate costs and what it flags; the
  decision is #110's and #123's.
- **Not a rate for JavaScript.** immer is TypeScript. A `.js` frame with no
  types at all is a different instrument, and the resolver's behaviour there —
  where `allowJs` and inference replace declarations — is unmeasured.
- **Not a comparison with the Python figure.** CLM-0009's zero and anything here
  are different resolvers over different languages with different denominators.
  Putting them in one sentence as though one were larger would be the error this
  file is arranged to prevent.
