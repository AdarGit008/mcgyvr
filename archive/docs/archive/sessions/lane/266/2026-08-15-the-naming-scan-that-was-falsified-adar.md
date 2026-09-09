---
record: session/4
lane: lane/266
agent: adar
started: 2026-08-15T08:00:00Z
---

# Session — lane/266 — 2026-08-15 — the naming scan, and being wrong twice about it

## Did

Two threads. The measurement thread is recorded in session/3 and session/5
(`responsive-fraction`, `gate-rescore`). This record covers the #267 thread,
because its instructive content is a method failure rather than a result.

**The scan the owner asked for.** #266's open items listed two: #267's body
predated the prior-art scans, and the naming vocabulary had no home in `docs/`.
Both were closed — the second by `docs/identifier-naming-prior-art-2026-08-15.md`
— and the first was then closed twice, wrongly, before it was closed correctly.

**Round 1: two figures that did not re-derive.** The 2026-08-14 session record
carried *"arXiv:2505.10443 measured renaming raising accuracy by +14pp on two
7B-class models"* and *"the evidence now favours misleading names by 3-6x."*
Neither survived. The renaming tables' largest rise is **+3.0pp**; the 3-6x
compares CodeCrash's 23.2% (misleading *NL comments*, output prediction) against
alpha-renaming's 4-7pp (identifiers, execution prediction) across two papers. On
that basis #267 was amended and its role as #231's fallback control **withdrawn**.

**Round 2: the owner's objection, which was correct.** *"The task type is
different for us than what was used in the research — they showed the LLM a code
snippet and asked for some explanation. We are asking the model to generate code
from scratch."* Verified against each paper's own setup: ClassEval-Obf is
summarization plus execution prediction; 2505.10443 asks the model to *"complete
a Python assertion, given the function signature and a test input"*; CodeCrash is
output prediction. All three show the model working code. This bench does the
reverse. The withdrawal was **retracted** — it had imported "renaming barely
moves Qwen2.5-Coder" as an estimate, and the import was invalid.

**The owner also supplied the missing control.** *"Do we have snake_case ->
camelCase refactors as an item to check as a lever on 267?"* We did not. It is
the lever's **negative control**: the existing self-check proves the transform
does not *break* the task; nothing proved it inert when it should be. Without it
every meaning-stripping figure confounds removing meaning with renaming at all.
Added as `style`, with the arm asymmetry noted — Python is snake_case and
TypeScript camelCase, so the same transform is off-convention on one arm.

**Round 3: the claim was escalated and then falsified.** Round 2's file said *"we
did not find a source…"*, which is defensible. In conversation it became
*"nobody has measured our case, so we'd be first"* — the absence claim this
project has a standing rule against. The owner rejected it and commissioned an
adversarial scan tasked to break it.

**It broke.** At least six studies occupy the cell: RADAR (TOSEM 2024,
arXiv:2211.15844) is the design already run — *"functional description and the
method signature"* -> body, HumanEval Pass@1, `Foo-Attack` replacing method names
with `foo`, baselines **18.9-22.0% on <=3B models**; plus ObfusEval (ICSE 2025),
BioCoder, ODEX, Yetistiren, and ReCode §3.4.

**The worst of it was self-inflicted.** ReCode was cited in round 2 and excluded
as meaning-preserving on a read of its *function-name* family alone. §3.4 carries
`VarRenamerNaive` (`VAR_0`), `VarRenamerRN` (random string) and `VarRenamerCB`
(natural-name control), on HumanEval and MBPP generation, nine models 1B-16B. The
recorded reason for not obtaining its figures — *"the ACL PDF did not extract"* —
was also false: it extracts to 82KB with fifteen occurrences of `VarRenamer`. One
failed fetch was treated as an exhausted search.

## What reversed

- The conditions **are** ordered in generation: natural < positional placeholder
  < random string. "Unordered" was true of comprehension data only.
- **`function_A` is the weakest published arm** (1.5-16.7%); random strings run
  9-55%. #267 proposed the bottom of the ladder.
- **A low baseline argues *for* the lever.** ReCode's InCoder-1B, the smallest
  model, takes the largest relative drop (54.84%). Round 2's regime-gap argument
  ran backwards.
- **Misleading > neutral is supported** by forty years of human evidence the scan
  never searched. The *3-6x number* stays unsupported; rejecting the **direction**
  was an over-correction. A true claim was dismissed on a wrong citation.

## The finding that changes the design most

Feitelson's mechanism: ***"time reflects difficulty, and the error rate reflects a
'surprise factor'."*** The human literature's effects live on **time** — 19%
slower comprehension, `dz=0.32` (Hofmeister n=72); 14%, `dz=0.27` (Schankin
n=88) — and where those studies measured *correctness* they mostly found nothing
(Schankin's fail rate `p=0.671`; Beniamini two nulls). **This bench measures only
errors.** Neutral anonymisation is a difficulty manipulation; misleading naming is
a surprise manipulation. The instrument is shaped to detect the second, and the
neutral arm #267 proposed is the one most likely to null.

And the `style` control the owner asked for is corroborated: ReCode's
`VarRenamerCB` **is** that arm, and it moves **-18.13 to +23%**. Renaming at all
is not free.

## Left open

- **#267's build is unchanged and was never in question** — the four-site reach,
  the silent-floor risk, the renamed-reference self-check. Only its design
  positions moved.
- The claim the record may now make is *no published work runs a HumanEval-scale,
  multi-model, generate-from-spec pass@k across the **full four-condition
  ladder***. A coverage gap, not a virgin cell.
- No figure in the scan file is vendored under #118. Any of them entering
  `records/claims/` must be pinned first.

## The method note, which is the point of this record

Six quoted figures failed re-derivation on 2026-08-15, and **two of them were my
own from earlier the same day**. Every one was caught by returning to the primary
source or the raw counts; none by reading more carefully. Four of the six share
one shape: **a number true of one slice — one model, one language, one experiment
— quoted as though true of everything.**

The escalation from *"we did not find"* to *"nobody has measured"* happened
between a document and a sentence spoken about it. The document was honest. The
summary was not, and nothing in the tooling would ever have caught it.

next: #272 owns whether `psi_draw` still earns rig time; the bar decision now
sits above #224's corpus work.
