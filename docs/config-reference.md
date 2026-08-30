<!-- Code generated from src/mcgyvr/config.py by `make docs`. DO NOT EDIT. -->

# Configuration reference

Every key `mcgyvr.yaml` accepts.

This page is generated from `SCHEMA` in `src/mcgyvr/config.py` — the same
declaration the loader validates against. It is not a description of the
config format kept alongside one; it is a projection of it, so a documented
key and a validated key cannot disagree.

Three properties hold across every key here, because the loader enforces
them rather than documenting them and hoping:

- **Unknown keys fail.** A typo'd key that is ignored is a config that
  silently does something other than what it says.
- **No silent defaults for things that must be bound.** A default ships only
  when it is a real working value. Anything else is absent, and its absence
  surfaces at the point of use naming the key and how to bind it.
- **Credentials are never values.** Keys that would hold a secret take the
  *name* of an environment variable. Writing a key in directly is rejected
  by name, not with a generic error.

## Value types

| Type | Accepted |
| --- | --- |
| number | A whole number. `true` is not a number, even though Python says it is. |
| text | A non-empty string. An empty value is rejected rather than treated as unset — remove the key instead. |
| URL | Text that carries a scheme: it must start with `http://` or `https://`. |
| boolean | `true` or `false`, unquoted. |
| one of ... | Text drawn from a fixed set. Anything else is rejected, with the valid values named. |
| env var name | The **name** of an environment variable (e.g. `ANTHROPIC_API_KEY`), never the value. Credentials are never written into this file; the orchestrator resolves the name at point of use and a task sandbox never sees the result. |
| list of text | A YAML list of non-empty strings. |
| block | A nested mapping with a fixed set of keys, documented in its own section. |
| block map | A mapping whose keys you choose; every entry takes the same fixed set of keys. |
| list of blocks | An ordered YAML list; every entry takes the same fixed set of keys. |

## Top-level keys

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `version` | number (min 1) | **yes** | — | Config schema version. Currently 1; bumped only by a breaking change to this file's shape. |
| `sources` | block map | **yes** | — | Where model work is executed, keyed by a name you choose. A source is an endpoint with a capacity and a wire protocol — nothing above the execution seam knows which host or backend served a request. |
| `ladder` | block | **yes** | — | The rungs work climbs, and what each is bound to. |
| `orchestrator` | block | no | — | The role that turns a prompt plus a repository into contracts. Only used in delegated mode; direct mode authors contracts itself. |
| `verifier` | block | no | — | The role that reads an applied diff in fresh context. |
| `sandbox` | block | no | — | Where a task's commands run. |
| `delivery` | block | no | — | How accepted work gets back to you. |
| `budgets` | block | no | — | The ceilings that bound one task's cost. |

## `sources`

Where model work is executed, keyed by a name you choose. A source is an endpoint with a capacity and a wire protocol — nothing above the execution seam knows which host or backend served a request.

Each entry takes these keys:

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `base_url` | URL | **yes** | — | Where the source answers, including scheme and port. To bind it: e.g. http://localhost:11434. |
| `api` | one of `ollama`, `openai` | **yes** | — | Wire protocol. `openai` covers vLLM, llama-server, LM Studio and TGI, so adding a backend is a protocol question, not an integration. |
| `max_parallel` | number (min 1) | no | `1` | How many requests this source may run at once. Concurrency is capacity, not a preference: measured, three models ran concurrently on one card in 23.6 s against ~44 s serial. |
| `api_key_env` | env var name | no | unset | NAME of the environment variable holding this source's key. Absent means the source needs no credential, which is the normal case for a local backend. To bind it: set it to the variable's NAME (e.g. ANTHROPIC_API_KEY), never the key itself. |

## `ladder`

The rungs work climbs, and what each is bound to.

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `tiers` | list of blocks | **yes** | — | The rungs, cheapest first. A higher rung must be measurably better than the one below or it is not a rung — binding a faster-but-weaker model above a slower-but-stronger one inverts the ladder and makes escalation actively harmful. |

### `ladder.tiers`

The rungs, cheapest first. A higher rung must be measurably better than the one below or it is not a rung — binding a faster-but-weaker model above a slower-but-stronger one inverts the ladder and makes escalation actively harmful.

An ordered list. Each entry takes these keys:

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `name` | text | **yes** | — | How this rung is referred to elsewhere — risk floors, routing policy, telemetry. Conventionally `<locality>_<model>`, e.g. `local_qwen2.5-coder-7b`, which says what the rung is rather than where it sits: a positional name silently changes meaning when a rung is inserted above it. There is no role in the name because a binding's role is already given by where it sits — this is the ladder, so it is a worker. |
| `source` | text | **yes** | — | Which declared source executes this rung. Resolution happens at the execution seam only — nothing above it knows where work ran. |
| `model` | text | **yes** | — | Model identifier as the source names it. |
| `attempts` | number (min 1) | no | `1` | How many times this rung may be tried before escalation moves on. The default of 1 is escalate-rather-than-retry: a second attempt re-runs the same model on the same input, and the figure inherited from local-ai and not re-verified here (#152) — worker-tier remediation rescued 2 of 35 failures — says that is usually spend without a result. Raising it is most defensible on the dearest rung, which has nowhere to escalate to. A contract's `limits.attempts` caps this per task; the lower of the two applies. |

## `orchestrator`

The role that turns a prompt plus a repository into contracts. Only used in delegated mode; direct mode authors contracts itself.

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `source` | text | no | unset | Which declared source serves this role. Unset until something needs the role. To bind it: name one of the sources declared under `sources`. |
| `model` | text | no | unset | Model identifier as that source names it. To bind it: name a model the bound source can serve. |

## `verifier`

The role that reads an applied diff in fresh context.

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `enabled` | boolean | no | `false` | Model verification of the applied diff, on top of the gate. Off by default because the deterministic gate is the acceptance bar and a keyless install is a supported configuration, not a degraded one. |
| `source` | text | no | unset | Which declared source serves this role. Unset until something needs the role. To bind it: name one of the sources declared under `sources`. |
| `model` | text | no | unset | Model identifier as that source names it. To bind it: name a model the bound source can serve. |

## `sandbox`

Where a task's commands run.

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `mode` | one of `docker`, `tempdir` | no | `docker` | `docker` runs each task in its own container, torn down after. `tempdir` is the explicitly weaker fallback for installs without Docker: acceptance commands are arbitrary shell from a contract, running on someone else's machine. |
| `image` | text | no | unset | Base image for task containers. Unset means detect the repository's stack and build one. To bind it: name an image tag, or leave unset to let the stack be detected. |
| `setup` | list of text | no | `[]` | Commands run once when the task image is built, before any task. |

## `delivery`

How accepted work gets back to you.

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `mode` | one of `branch`, `none` | no | `branch` | Where an accepted change is committed. `branch` puts it on a new local branch named after the contract and leaves the branch you have checked out, your index and your working tree exactly as they were — the delivery tells you the `git push` to run. `none` commits onto the branch you have checked out. Nothing here pushes or opens a pull request: mcgyvr reaches your repository through `git` and has no forge, so the last step off this machine is yours. |
| `token_env` | env var name | no | unset | NAME of the environment variable holding a forge token, recorded for tooling you drive after a delivery. Nothing in mcgyvr reads it: no mode talks to a forge, so a token here is a note to yourself, not a credential mcgyvr will spend. To bind it: set it to the variable's NAME (e.g. GITHUB_TOKEN), never the token itself. |

## `budgets`

The ceilings that bound one task's cost.

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `max_escalations` | number (min 0) | no | `1` | How many rungs a task may climb before it is handed back unfinished. A cheap rung that fails and escalates costs more than starting higher, so this is a real ceiling, not a retry count. |
| `max_attempts` | number (min 1) | no | unset | Hard ceiling on how many attempts one task may spend in total, across every rung and every family it climbs. Unset means the ladder's own budget bounds it — the sum of each reachable rung's `attempts`, which `mcgyvr pool` prints — so leaving it unset is not unbounded. Set it when you have raised a rung's `attempts` or `max_escalations` and want one number that still holds. A decline costs nothing against it: a rung that stepped aside spent no attempt. To bind it: set a whole number of attempts, or leave it unset to be bounded by the ladder's own budget (`mcgyvr pool` prints that number). |
| `task_timeout_s` | number (min 1) | no | `900` | Wall-clock ceiling for one task, including acceptance commands. |
