# ADR-0033 — the bar, the prompt and the weights are hashed where they are resolved

Status: Accepted
Supersedes: none
Superseded-by: none
Amends: ADR-0027 (D6, whose "keyed within a condition" was being read as "in
`KEY`"; and `unfingerprinted`/`drift`, which read the key through a default
argument and so could not demote a record the way D8 says they do)
Relates: ADR-0026 (three fields change from a name to content), ADR-0025 (the
bar is the project's, and the tool that applies it is part of the instrument),
ADR-0024 (two builds are two instruments), #276 (the admission rule), ADR-0032
(the round pin now covers the bar's configuration)
Date: 2026-08-17
Issue: #285

## Context

ADR-0026 decided the principle: three fields change from a **name** to
**content** — the bar, the model and the condition. ADR-0027 decided the record
shape, declared 27 fields in four groups, and shipped the module. **Nothing
wrote the content.**

Ten of the 27 had no writer anywhere in the repository. The cost is not
cosmetic: `identity.PENDING` held fifteen fields, and a field was in it either
because #276's rule had not admitted it *or because nothing computed it* — two
different states wearing one name. Until a digest exists, #276's perturbation
rule has nothing to perturb, and a list that cannot say which of the two it
means reads as though the work were merely queued.

What the three names fail to discriminate, measured on this tree:

| field | what it records | what it cannot tell apart |
|---|---|---|
| `gate_rungs` | five names, and **both arms write the same five** | a Python bar of **250** resolved ruff rules from a JS/TS bar of 66 eslint ones (the first measured here on the staged `bench-py` workspace under ruff 0.16.1 and again under 0.16.2; the second is ADR-0025's figure. A count only means something with the tool that resolved it, which is why the version is in the digest) |
| `bundle_sha256` | `sha256(prompt.system)` | `stock`, `norule`, `noscaffold` and `planonly` — **one digest across all four** on `bench-py`'s 257 contracts, because every one of those levers edits the *user* message |
| `model` | a mutable tag | any two things ollama will answer to that name |

The `bundle_sha256` row is the sharp one. ADR-0026 measured that the bar
reverses which arm leads; the prompt is the largest measured effect in the
literature this campaign surveyed, up to 76pp; and the field on disk does not
move when the thing under test moves. Eight run directories were mislabelled
that way before a reader noticed.

## Decision

> **DECIDED (2026-08-17, owner).**
>
> 1. **Each digest is a function in `tools/bench/identity.py`, and the runner
>    supplies raw material only** (ADR-0027 D4). A runner that assembles a hash
>    and passes it in is `--condition` with a longer hex string.
> 2. **`bar_sha256` is the resolved rule set, per language, asked of the
>    checkers themselves** — `ruff check --show-settings` for
>    `linter.rules.enabled`, `eslint --print-config <file>` for the file the arm
>    writes — plus every resolving tool's version, plus the rungs.
> 3. **`prompt_sha256` is the system and user halves of every task the run will
>    dispatch, keyed by task id.** Not the first task's, and not the system half.
> 4. **`model_sha256` is the manifest digest `/api/tags` already returns**, with
>    its over-sensitivity stated in the docstring rather than papered over;
>    `vocabulary_sha256`, `merges_sha256` and `template_sha256` come from
>    `/api/show` with `verbose: true`.
> 5. **`null` carries its reason in one sibling block, `identity_refusals`**,
>    keyed by field name. Never a sentinel string (D2), and never an absent key
>    on a run made from here on.
> 6. **A digest absent from an older directory is adopted forward on resume; a
>    digest that was `null` and is now answered is drift and refuses.**
> 7. **`identity.PENDING_REASON` is complete and says which of the two reasons
>    each pending field is pending for**, held to the tree by test.

### Why the bar is asked of the checkers rather than derived from the config

Expanding `E, F, W, I, N, UP, B, SIM, RUF` into concrete rules is ruff's
resolution. It changes between releases — which is exactly why ADR-0025 makes
the toolchain version part of the instrument — and a second implementation of it
here would drift from the one that actually scores. The same holds for eslint,
where a flat config resolves **per file**, so asking for "the rules" without
naming one is asking a question the tool does not answer.

Only `linter.rules.enabled` is taken from `--show-settings`. The rest of that
output carries `linter.project_root`, an absolute path, and a digest that moves
when the repository is checked out somewhere else describes the machine.

**The workspace is staged by the caller**, because the bench's bar is not this
repository's `make lint` bar: it is whatever `score.stage_dir` puts in a
workspace — a `pyproject.toml` rendered from the project's `[tool.ruff]` and
`eslint.config.mjs` beside a linked `node_modules`. Resolving the repository's
own settings instead would digest a bar no candidate is ever scored against.

**Per language, and never pooled.** ADR-0026's rule is that no figure pools
across a stratum where the effect is heterogeneous, and the two arms' bars are
the case it was written from. One digest over both would restate `gate_rungs`'
defect with more hex.

**A resolver that will not answer makes the field `null`, not a digest over the
half that did.** Half a bar is not the bar and would read as having recorded
one. On a real dispatch this cannot fire — `score.require_toolchain` refuses a
run with a missing rung tool before the first candidate — so the `null` path is
for off-rig callers, which is exactly who should not get a confident answer.

### Why the model digest is the over-sensitive one

`/api/tags` returns a digest and `src/mcgyvr/detect.py` throws it away. It is the
sha256 of ollama's **manifest file**, which lists five layers, so it moves when
the template, the system prompt or the licence layer changes and the weights do
not. The separable weights identity is the **model layer** digest; `/api/show`
and `/api/tags` do not expose it, and reading it needs manifest parsing on the
serving host, which a dispatch cannot do.

Over-sensitive is the safe direction for a comparability guard: it refuses a
contrast that would have been sound and never permits one that is not.

The unsafe direction is the one this cannot close. `model_info` and `tensors`
carry name, shape and dtype rather than weight values, so **a fine-tune has
identical shapes**. Different digest implies a different model; the same digest
does not imply the same model — and the gap sits exactly where identity matters
most, since #189 was a fine-tune contrast. `vocabulary_sha256` and
`merges_sha256` are why the model group has six fields rather than one: they are
the model's own content out of the GGUF header where the manifest digest is
ollama's addressing of it, so two records disagreeing on `model_sha256` while
agreeing on both of those are a re-tag rather than a different tokenizer — a
distinction a reader can make only because both are recorded.

`template_sha256` is in the **server** group and not the model group. `template`
is ollama's rendering on top of the GGUF, not the GGUF; the same weights served
under two templates are two instruments, which is `serving_build`'s argument one
level in.

**`verbose: true` is load-bearing and is encoded in the probe, not in a
comment.** Without it `/api/show` returns the tokenizer arrays as `null` rather
than omitting them — measured on `qwen2.5-coder:1.5b`, 0 against 151,936 tokens.
A probe that left the flag off would record "unobtainable" while the answer was
one flag away, which reads as having checked.

## Two corrections to #285

Both are places where the issue compressed a decision into something that would
have been wrong to build.

**1. `prompt_sha256` does not enter `KEY`, and must not.** #285's acceptance box
reads *"`prompt_sha256` is in `KEY`"*. ADR-0027 D6 says the prompt is *"keyed
**within a condition**"*, and the difference is the bench. The ablation changes
the render on purpose — `stock` and `norule` differ in this field by
construction — so a global key entry would refuse **every contrast the bench
exists to draw**. The mechanism D6 asks for is `require_comparable`'s
per-condition loop, and it was already written when ADR-0027 landed; what was
missing is only the writer. The box's second half — *"two cells naming one
condition with different rendered prompts are refused, proven by a test"* — is
satisfied, and is now testing a field something writes.

**2. There is no "fresh run" on the second runner.** #285's first acceptance box
asks for the digests *"written by both runners on a fresh run"*.
`tools/bundle/measure.py`'s `record_run` calls `instruments.refuse_to_measure`
as its first statement, and both of its arms — `bundle-ts` and `bundle-py` —
were retired by #240 on 2026-08-10. It refuses every call it is given. Wiring
digests into it would be unreachable code justified by a checkbox, and ADR-0020
retired those sets permanently rather than temporarily, so it is not
future-proofing either. `tools/breadth/measure.py` is the runner that can write,
and it does.

## A defect this found

`unfingerprinted` and `drift` took the comparability key as a **default
argument** — `fields: tuple[str, ...] = KEY` — which binds when the function is
defined. So `tag()` read the key frozen at import, and ADR-0027 D8's stated
property, that a `verified` record demotes on its own when the key widens, could
not be exercised without reimporting the module.

It held in practice, because admitting a field means editing the literal and the
default rebinds on the next import. It was untestable, and one refactor away
from being false. Both now resolve the key at call time, and the demotion is
proven by a test that actually widens the key rather than by waiting for the day
it happens. This is the second instance of the shape in two days: the first cost
`product._open_cli` a round entry whose digest and file map described two
different trees (#291, ADR-0032).

## Consequences

- **#262 can proceed against `bar_sha256` without further negotiation**, which
  was its blocking condition.
- **Every run made from here on carries all six fields**, `null` with a reason
  where the world would not answer. Records already on disk keep an absent key,
  which is the correct statement about them: they predate the contract.
- **A `null` that becomes a value refuses a resume.** A directory whose endpoint
  would not name its weights holds rows measured under weights nobody recorded;
  appending rows measured under weights somebody did would put both in one
  denominator and let the manifest describe only the second half. The cost is
  that an endpoint which flakes once makes its directory un-resumable, and that
  is the intended trade — loud beats mixed.
- **None of these fields is admitted to `KEY` by this change.** #276's rule
  admits, and nothing else does; they are recorded now and keyed when
  perturbation says so. The six `verified` manifests therefore stay `verified`
  today and demote the moment one is admitted, which is D8 working rather than
  D8 pending.
- **The model group is written against the API shape the #276 survey verified
  and has not been exercised against a live endpoint in this lane** — there is
  no ollama reachable from where this was written. The refusal paths are tested;
  the success path is tested against stubbed responses carrying the survey's own
  key names. First rig contact will confirm or correct it, and is the honest
  place for that to happen.
- **`bar_sha256` costs a subprocess pair per run.** `ruff --show-settings` and
  `eslint --print-config` run once in `record_run`, not per candidate.
- **`prompt_sha256` renders every task in the tier.** 257 contracts in 0.1 s on
  this machine, once per run, against hours of dispatch.

## Fan-out

| what | owner |
|---|---|
| `quantization`, `context_length`, `concurrency`, `seed` — the probe set, captured comprehensively and compared by nothing | #286 |
| the two runners' resume drift checks still carry their own key lists | #287 |
| admitting any of these to `KEY` — needs a perturbation run under #276's rule | #276, #231 |
| the model **layer** digest, which needs manifest parsing on the serving host rather than an API call | unowned |
