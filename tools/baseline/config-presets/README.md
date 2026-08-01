# Config presets

Ready-made `baseline.config.json` starting points. Pick the closest, copy it to your
repo root as `baseline.config.json`, then tune the paths/commands to your repo.

```bash
cp config-presets/node-service.json  /path/to/repo/baseline.config.json
```

Each preset only sets the keys that matter for its scenario and relies on sensible
defaults for the rest. The `_preset` / `_<key>` fields are inline notes — the runner
ignores any key starting with `_`. The full key reference lives in `../config.example.json`.

| Preset | `project_type` | For | Notable |
|---|---|---|---|
| [`node-service`](node-service.json) | `service` | A Node/TS web service or app | Auto-enables the OPS rules (health check, structured logs, graceful shutdown, runbook) |
| [`python-library`](python-library.json) | `library` | An installable Python package | Build/test/quality/repro; no OPS; add `advanced` for SBOM/scanning |
| [`internal-tool`](internal-tool.json) | `node` | A CLI/script/utility with no claims | Lean; CLAIM-* and OPS off |
| [`product-with-claims`](product-with-claims.json) | `service` | A product/launch that makes competitive or novelty claims | Turns CLAIM-* discipline **on** (build-state, blast-radius, dated prior-art pass) |

## Descriptor presets — `baseline.repo.json` (posture)

The files above are **config** presets (`baseline.config.json` — tuning: paths, commands,
thresholds). The `*.repo.json` files below are **descriptor** presets — the repo's *identity
and posture* (`baseline.repo.json`, schema [`../schema/repo.schema.json`](../schema/repo.schema.json)):
what the repo is and which agent-workflow contract it runs. A repo carries **both** — the
descriptor declares identity, the config tunes the checks — and the descriptor's `type`
supersedes filesystem auto-detection.

```bash
cp config-presets/multi-lane-agents.repo.json  /path/to/repo/baseline.repo.json
```

| Preset | `workflow` | For | Notable |
|---|---|---|---|
| [`multi-lane-agents`](multi-lane-agents.repo.json) | `multi-lane` | The V2 default — one dev or a fleet running N parallel agent lanes | Lane namespaces, 7-day leases, `anchoring: strict` |
| [`readiness-only`](readiness-only.repo.json) | `single-lane` | Just the readiness score, no workflow contract (V1-equivalent) | Minimal descriptor; `anchoring: off`, no lanes block |

Copying a descriptor preset is adoption's first act; absent one, `DESC-01` warns and names this copy as the fix.

After copying a preset, run a first score:

```bash
node /path/to/skill/check.mjs --repo /path/to/repo
```

Two dials worth knowing:
- **`makes_external_claims`** — `false` skips all CLAIM-* rules (most internal repos); `true` requires per-claim records under `records/claims/` (a legacy `docs/CLAIMS.json` monolith migrates via `baseline gen migrate-claims` — see `../MIGRATION.md`).
- **Opt-in `*_globs`** (`freshness_globs`, `generated_globs`, `grounding_docs`) — empty by default so those rules stay silent until you adopt the convention; switch them on with your real paths.
