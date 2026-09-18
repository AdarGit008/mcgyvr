# okf — what is known, and what it obliges

Rules and gotchas for working this fleet.

**What an entry here is.**

- **General.** It holds across a hardware swap, a rebuild or a re-lock. It cites
  no commit, no run and no date.
- **Leading.** It names a flag, says what it does and which way to move it. It
  does not carry the value — you derive that against the rig as it is now.
- **Gotchas.** Traps, time savers and workarounds for the tools, the rigs and
  the models. Not a tour of the code.
- **Enforcing.** Where this project has settled something, the entry is a rule,
  not a consideration.

**The numbers are not here.** Measured values live in `records/`, in
`tools/runs/derived.json` and in the run journals, which is where you go to check a claim or to get a figure. An entry
that needs a number tells you how to derive or measure it. Copying a number out
of this store into a config is the mistake this store exists to prevent — the
rigs swap hardware, and a value that was right on one afternoon is not a rule.

| path | read it when |
|---|---|
| `must-read/always.md` | every session start |
| `must-read/reading-results.md` | going over run results |
| `must-read/touching-rigs.md` | any action on a rig |
| `must-read/touching-models.md` | choosing, comparing or deleting a checkpoint |
| `must-read/touching-engine.md` | before turning an engine, quant or kernel flag |
| `config/vllm.md` | before turning a vLLM knob |
| `config/llama.cpp.md` | before turning a llama.cpp knob |
| `models/` | sizing a checkpoint against a card — why a cliff fires, what sparsity buys |

## `models/` — sizing concepts

Thirteen atomic concepts on what makes a checkpoint fit and go fast. `a-*` are
model-shaped, `b-*` hardware-shaped.

**They are mechanism, not measurement.** They say *why* a cliff exists, never
where one sits on a card here. Size a checkpoint with them, then measure. Where
one contradicts a measured entry, the measurement wins.
→ `must-read/reading-results.md`

## Where the archive is

Superseded prose, plans, session logs and retired code live in the lab repo
under the paths they would have here. They are not opened unasked and are not
an authority when they are → `must-read/always.md`.

## Querying the store

`tools/okf/query.py --src <okf_rag src>` walks `models/` as a concept store. The
trust gate returns a strong answer only for a concept signed by a human, so it
abstains on everything here by design — that is the gate working, not a failure.
Read one with `--raw`. `--sign` only rewrites an existing `verified:` line, and
no concept here carries one.

Frontmatter is parsed as YAML and one bad value takes down the whole listing,
not just its own file — a `title` or `description` containing `: ` must be
quoted.

`okf/*` is gitignored; `index.md`, `config/`, `must-read/` and `models/` are
un-ignored so they are tracked. All of it is hand-authored and none of it is
rebuilt.
