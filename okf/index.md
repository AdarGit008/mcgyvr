# okf — what is known, and what it obliges

Two hand-authored trees live here beside the generated concept bundle.

| path | read it when |
|---|---|
| `must-read/always.md` | every session start |
| `must-read/reading-results.md` | going over run results |
| `must-read/touching-rigs.md` | any action on srv1 or srv2 |
| `must-read/touching-models.md` | choosing, comparing or deleting a checkpoint |
| `must-read/touching-engine.md` | before turning an engine, quant or kernel flag |
| `config/vllm.md` | before turning a vLLM knob |
| `config/llama.cpp.md` | before turning a llama.cpp knob |

Claims are atomic and carry a path. **The path is where the reasoning lives, not
where the authority lives** — a claim is true because something was measured,
and the archive is how you check that, not something to defer to.

## Archive

| what | where |
|---|---|
| board rulings, 3 seats, 10 contested items | `archive/docs/board-findings-2026-08-31.md` |
| next-run plan (vLLM n=16/32, co-residency, MoE) | `archive/docs/serving-vllm-n32-plan-2026-08-31.md` |
| rig inventory + vLLM offload measurements | `records/evidence/2026-08-31-inventory/` |
| the 2026-08-30 concurrency grid + runbook | `records/evidence/serving-2026-08-30/` |
| MoE expert-offload sweep | `records/evidence/2026-08-25-moe-expert-offload/` |
| earlier claim verification (generated concepts) | `records/evidence/2026-08-26-claim-verification/` |

## The generated bundle

`okf/serving/**` is a machine-built concept store, rebuilt by
`records/evidence/2026-08-26-claim-verification/build_okf.py`. Query it with
`python3 tools/okf/query.py --list`. Every concept there is signed
`machine:claude-opus-5`, so `get_knowledge()` **abstains on all of them by
design** — the trust gate refuses machine findings until a human signs. Use
`--raw` to read, `--sign` to promote. Approvals survive regeneration.

These two trees are hand-authored and are not rebuilt. `okf/` is gitignored as a
generated artifact; `index.md`, `config/` and `must-read/` are un-ignored so
they are tracked.
