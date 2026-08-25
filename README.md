# mcgyvr

Offload scoped coding work from your agent to a configurable worker ladder —
deterministic tools, local models, API models — and get back a gated,
verified change.

mcgyvr is a **skill** you install into a TUI/CLI agent harness (Claude CLI,
hermes, pi). Your agent stays the orchestrator of your session; mcgyvr owns
everything below the task contract: decomposition, execution on whatever
workers you have, a deterministic acceptance gate, verification, and a PR.

**North star: value per token.** Not "percent offloaded". The cheapest tier
that can actually do the job.

> **Status:** pre-v1, under construction. Scope of record is the
> [issue tree](https://github.com/AdarGit008/mcgyvr/issues); forks and
> rationale are in [`docs/decisions/`](docs/decisions/). Functionality is
> read from code, never from docs.

## How it works

```
your agent (any harness)
      │  prompt + repo, or contracts directly
      ▼
  orchestrator ── deterministic index (ripgrep + tree-sitter, zero tokens)
      │           targeted reads → task contracts
      ▼
  worker ladder ── deterministic tools → local models → API models
      │            (source pool: multi-endpoint, concurrent, backend-neutral)
      ▼
  sandbox ─────── one container per task, torn down after
      │            worker writes → acceptance gate → verification
      ▼
  branch → PR
```

Two ways in:

- **Delegated** — your agent forwards a prompt and a repo; mcgyvr decomposes
  it into contracts itself.
- **Direct** — your agent writes task contracts and hands them over. The
  contract schema is public API.

Either way the orchestrator always runs its deterministic exploration first;
context your agent supplies is an accelerator on top of that, never a
substitute for it.

## Install

Not yet installable. See the issue tree.

## Configure

One file, written for you by `mcgyvr init` — it detects your hardware and
proposes worker bindings from a shipped capability table
([`data/capability-table.json`](data/capability-table.json)); it does not
benchmark your machine. Edit it after.

No API key is required. Without one, mcgyvr runs local-only: deterministic
tools and local models, with the gate as the acceptance bar.

## Requirements

- Python 3.12+
- Docker (recommended — one sandbox per task; falls back to an ephemeral
  temp directory when absent)
- At least one worker: a local inference endpoint (Ollama, vLLM,
  llama.cpp/llama-server, LM Studio, TGI) and/or an API provider

## Repo layout

| Path | Purpose |
|------|---------|
| `src/mcgyvr/` | The package |
| `data/` | Capability table and its provenance |
| `docs/config-reference.md` | Every config key — generated from the schema, not hand-written |
| `docs/decisions/` | Decision records — forks and rationale only |
| `records/` | Session records, judgments, claims, measurements |

## Prior work

mcgyvr supersedes [`AdarGit008/local-ai`](https://github.com/AdarGit008/local-ai),
an MVP that answered the questions this design rests on:
worker context policy, the acceptance-gate check set, the single-file worker
output protocol, and the model measurements now vendored in `data/`.

## License

MIT — see [LICENSE](LICENSE).
