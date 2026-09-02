---
record: session/2
lane: lane/276
agent: adar
started: 2026-08-16T09:00:00Z
---

# Session — lane/276 — 2026-08-16 — the identity survey

## Did

Surveyed what a run can observe against what it records, from the model probe
down to the leaves. The survey and its evidence are
`docs/identity-surface-2026-08-16.md`; the decisions are #276; the admission
rule is the sibling record, pre-registered before any perturbation.

**The finding that reframed the rest.** The question started as "what is our
model signature" and the honest answer was that the project has one
content-derived identity field — `serving_build` — and names everything else.
The pattern generalises: *what describes the corpus is fingerprinted; what
describes the instrument is named.*

**Four defects demonstrated rather than argued.**

- **`accept.py` is outside the task digest.** `tier_digests` hashes
  `bundle.dumps(task.contract)`, and `acceptance` carries the command string
  `python accept.py`. Appending a line to the file leaves the digest at
  `8cfc86051cdf5073`, unchanged. The per-task grader is mutable with no record,
  and `COMPARABLE` still declares the two runs comparable.
- **The user message is outside every digest**, and the asymmetry is the real
  finding: `norule` raises on a no-op (`matrix.py:215`) while `noscaffold` and
  `planonly` are silently identical on a contract without `target_content`.
  Message-stage levers are guarded; contract-stage levers rely on caller
  discipline. `record_run`'s docstring still promises the prompt is pinned
  through the task digests, which `ablate()` falsified.
- **The round pin does not cover the bar.** `product.SURFACE` excludes
  `pyproject.toml` and `eslint.config.mjs`, which `score.py` stages into every
  sandbox. Change one ruff rule and every verdict can move while
  `product_sha256` is identical. Also absent: `uv.lock`,
  `data/task-catalog.json`, `gate_rescore.py`, `lintless.py`. And
  `surface_files` globs `*.py` for directories, so `src/mcgyvr/prompts/*.md`
  sits outside the digest while `bundle_sha256` — which covers it per run — is
  not in `COMPARABLE`.
- **Ollama's `digest` is the manifest file's hash, not the weights'.**
  `sha256sum` of the manifest equals `/api/tags`'s value exactly, and `size` is
  the layer sum. The model layer is listed separately at 986,048,576 bytes and
  does not move when template, system or license change. **The separable weights
  identity already exists and did not need building** — it needs manifest
  parsing over ssh.

**The `verbose` trap, which would have broken the fix.** `/api/show` returns the
tokenizer keys as `null` unless `"verbose": true` is passed, at which point they
return 151,936 tokens and 151,387 merges. A probe written without it records
"unobtainable" while the answer is one flag away — ADR-0026 lens 3's exact
failure arriving inside the fix for it.

**The ordering was wrong and the owner corrected it.** I had the record shape
first and the observation second. A fingerprint's fields are a function of the
contrasts you intend to draw, so the shape cannot precede the observation. What
survives of the original position is narrower and load-bearing: **recording is
not keying**, and the recording half is urgent because runs made in the interval
are unrecoverable, while the key half can wait for evidence. #265 bundles both
halves and should be split along that line — its migration question in
particular is *not* observation-independent, because the first step reads the
old manifests' saved candidates.

**What 400 tasks buys, computed rather than assumed.** On the one stratum that
resolves today, n=257 → 7.0pp and n=400 → 5.5pp: about 1.3x, still short of 5pp,
and nothing at all for the seven strata where `delta <= psi` forecloses any n.
It is worth paying for only if the new material is more responsive than the old,
which is #224's unmeasured term. So the 400 sweep decouples from the identity
re-run rather than gating it.

**Two adversarial reviews, and what they cost me.** A correctness pass and a
completeness pass both ran over the plan. They converged independently on the
round boundary — `r1-commissioning` is open, #231 is open, and every identity
change alters `product_sha256`, so landing them piecemeal with runs in between
converts one re-run into several incomparable ones. That is now the sequencing
decision on #276.

Five of my own claims were wrong and are corrected in the survey rather than
quietly dropped: `norule` is guarded and is not a silent no-op; the bar is not
covered transitively by `product_sha256`; `GateReport` is `GateResult`;
`reference.py` is read by six modules and its disposition survives on the
better ground that `score.py:198` never stages it; and amending the manifest
count to 139 does not fix gap 18, because ADR-0024's 133 matches no commit-date
population and my "18 since" figure came from filesystem mtime rather than
provenance.

**`bound_flips` is a formula, not the constant I first wrote.** `bound_pp = 1.47`
reproduces as `z^2/(n+z^2)` at n=257. In flips the threshold looks invariant —
3.22 at n=20, 3.79 at n=257, 3.81 at n=400 — but only while the null observes
`d = 0`; one flip moves it to ~5.6. And `matching` does not key on `cells`, so
the rate transfers to subsets it never saw: ~7x too strict on a 34-cell set.

## Left open

- **#265 needs splitting**, and this lane did not do it. The encoding half
  (hashing convention, field placement, the three-valued unobtainable rule) is
  observation-independent and can start now; the key half and the migration
  answer are downstream of the perturbation runs.
- **The gap list is mapped to issues but nothing is implemented.** #276 carries
  25 gaps with dispositions; the fan-out is named in its Acceptance and the
  owning issues carry the context. No probe, digest or check exists yet.
- **Seven open issues remain unmapped to the plan** — #269, #257, #206, #207,
  #173, #254, #204. Each touches a field the plan records or a number it relies
  on, and #269 in particular means we would otherwise be digesting a grader
  whose discriminating power is unmeasured.
- **No test guards `product.SURFACE` itself.** It is a hand-maintained tuple,
  and four of the holes found today exist because nothing detects a file that
  should have been declared and never was. A test that walks what `score.py` and
  `breadth/measure.py` read at run time would close the class.
- **The `num_ctx` risk is live but not yet dangerous.** Nothing sends it and
  ollama truncates silently past it; today's maximum `prompt_tokens` is 1,479,
  safely under any default. `noscaffold` lengthens prompts and the corpus grows,
  so an assert per row is cheaper than the headroom argument.

next: split #265 along the encoding/key line, then land every identity change as one range so a single round boundary covers them
