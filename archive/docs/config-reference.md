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
| decimal number | A number that may carry a fraction. Sizes written this way are in **GiB** — powers of 1024 — which is what the rest of mcgyvr measures in; a file a tool reports as 13.2 GB is 12.3 here. |
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
| `models` | block map | no | — | Serving specs for models the shipped capability table does not carry, or whose numbers you want to override, keyed by the model identifier a rung names. mcgyvr sizes from what it can measure; this is where an operator states what it cannot. A declaration here wins over the table and is not second-guessed — a wrong one produces a launch spec that fails on the rig, which is the operator's to make. |
| `ladder` | block | **yes** | — | The rungs work climbs, and what each is bound to. |
| `orchestrator` | block | no | — | The role that turns a prompt plus a repository into contracts. Only used in delegated mode; direct mode authors contracts itself. |
| `verifier` | block | no | — | The role that reads an applied diff in fresh context. |
| `sandbox` | block | no | — | Where a task's commands run. |
| `delivery` | block | no | — | How accepted work gets back to you. |
| `budgets` | block | no | — | The ceilings that bound one task's cost. |
| `breadth` | block | no | — | How many answers one attempt asks for. Separate from `budgets` because breadth is not a ceiling: it is what a single attempt spends, and every budget in this file still counts that attempt once. |
| `cleanup` | block | no | — | What may be fixed without asking a model. |
| `journal` | block | no | — | Where mcgyvr keeps its own record of what it dispatched. |

## `sources`

Where model work is executed, keyed by a name you choose. A source is an endpoint with a capacity and a wire protocol — nothing above the execution seam knows which host or backend served a request.

Each entry takes these keys:

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `base_url` | URL | **yes** | — | Where the source answers, including scheme and port. To bind it: e.g. http://localhost:11434. |
| `api` | one of `ollama`, `openai` | **yes** | — | Wire protocol. `openai` covers vLLM, llama-server, LM Studio and TGI, so adding a backend is a protocol question, not an integration. |
| `max_parallel` | number (min 1) | no | `1` | How many requests this source may run at once. Concurrency is capacity, not a preference: measured, three models ran concurrently on one card in 23.6 s against ~44 s serial. |
| `api_key_env` | env var name | no | unset | NAME of the environment variable holding this source's key. Absent means the source needs no credential, which is the normal case for a local backend. To bind it: set it to the variable's NAME (e.g. ANTHROPIC_API_KEY), never the key itself. |
| `engine` | one of `llama.cpp`, `vllm` | no | unset | Which server program runs behind this URL, for `mcgyvr emit` to write a launch spec for. `api` cannot answer this: it is a wire protocol, and vLLM and llama-server both speak `openai` while taking entirely different argv. Absent means llama.cpp, which is what emit assumed unconditionally before this field existed. It belongs on the source rather than the rung because a URL points at one process and one process runs one engine. To bind it: leave it out unless the backend is not llama-server. |

## `models`

Serving specs for models the shipped capability table does not carry, or whose numbers you want to override, keyed by the model identifier a rung names. mcgyvr sizes from what it can measure; this is where an operator states what it cannot. A declaration here wins over the table and is not second-guessed — a wrong one produces a launch spec that fails on the rig, which is the operator's to make.

Each entry takes these keys:

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `geometry_json` | text | no | unset | Path to this model's GGUF geometry: the `geometry.json` a serving-door run leaves in its envelope, or the output of `python -m mcgyvr.serving.ggufscan <gguf>` (a list; the row scanned from `<model>.gguf` is the one read). Once set it is the source of truth for the model's bytes — `disk_gb` is read from its `size_bytes`, and the card figure, the slot count and `--n-cpu-moe` are derived from its tensor table and cache geometry by the law in `mcgyvr.serving.vramfit`. A stated `disk_gb` that disagrees with it is refused, and so is a geometry scanned from a file this model does not serve: each deviation from a scan requires a new scan. Required for an MoE; a dense model without it is sized from `vram_gb` alone, one slot wide. A relative path is read against the config file's directory. To bind it: on a machine holding the file, `python -m mcgyvr.serving.ggufscan <gguf> > <model>.geometry.json`, and name that file here. |
| `vram_gb` | decimal number (min 0.0) | no | unset | Working set on the card with nothing offloaded, in GiB, for a dense model that has no `geometry_json`. Not the weight on disk: a working set carries buffers. Not read when `geometry_json` is set — the card figure is then derived from the header. To bind it: set it to what the server reports resident on the card with -ngl 99 and no offload, converted to GiB. |
| `disk_gb` | decimal number (min 0.0) | no | unset | Weight on disk, in GiB, for a model that has no `geometry_json`. Note the unit — a file listed as 13.2 GB by a tool using decimal gigabytes is 12.3 GiB here. Leave it out when `geometry_json` is set: it is then read from the scan's `size_bytes`, and a stated value that differs from that by more than rounding to two decimals is refused. To bind it: set it to `ls -l` on the weights file divided by 1024^3. |
| `ram_gb` | decimal number (min 0.0) | no | `0.0` | A floor on what system memory may be asked to hold, in GiB. Absent means the offload arithmetic decides it alone; state it only to claim a demand this module cannot see. |
| `moe` | boolean | no | `false` | Whether this model has expert weights that `--n-cpu-moe` can move off the card. Not inferable from the other numbers: it is the difference between `does not fit` and `fits differently here`. |

## `ladder`

The rungs work climbs, and what each is bound to.

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `tiers` | list of blocks | **yes** | — | The rungs, cheapest first. A higher rung must be measurably better than the one below or it is not a rung — binding a faster-but-weaker model above a slower-but-stronger one inverts the ladder and makes escalation actively harmful. |
| `fanout` | one of `none`, `idle`, `full` | no | `none` | Whether a batch of contracts spreads across rungs or queues on one. `none` is today's behaviour: the cheapest rung at or above the contract's floor, queued behind whoever is already there. `full` starts each climb on the cheapest rung that has a free slot, so a batch fills every rig that can serve it instead of stacking on one — and it never leaves the contract's floor family, so it cannot spend. `idle` uses that same rule and then lifts the one limit: the floor is the only bound and nothing bounds it above, so when every rung of every cheaper family is full it enters a priced api family rather than wait. That is the difference between the two, and it is a spend decision the knob makes deliberately. Neither mode reorders the ladder: load decides which rung a climb starts on and never what it may spend, so a rung passed over for being full is still walked, and a rung that can run now is never passed over for a dearer one with more room. It is a knob rather than a behaviour because the right answer is a property of the machines: two interchangeable rigs should share a batch, but a throughput rig feeding an intelligence rig must not — the second is sized to drain the first's failure tail, and fanning volume onto it eats exactly the capacity that drain needs. |

### `ladder.tiers`

The rungs, cheapest first. A higher rung must be measurably better than the one below or it is not a rung — binding a faster-but-weaker model above a slower-but-stronger one inverts the ladder and makes escalation actively harmful.

An ordered list. Each entry takes these keys:

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `name` | text | **yes** | — | How this rung is referred to elsewhere — risk floors, routing policy, telemetry. Conventionally `<locality>_<model>`, e.g. `local_qwen2.5-coder-7b`, which says what the rung is rather than where it sits: a positional name silently changes meaning when a rung is inserted above it. There is no role in the name because a binding's role is already given by where it sits — this is the ladder, so it is a worker. |
| `source` | text | **yes** | — | Which declared source executes this rung. Resolution happens at the execution seam only — nothing above it knows where work ran. |
| `model` | text | **yes** | — | Model identifier as the source names it. |
| `max_parallel` | number (min 1) | no | unset | How many requests this rung may run at once, overriding its source's `max_parallel`. Concurrency is a property of the serving process rather than of the machine: the same weights on two rigs are two processes started with two different slot counts, so one number on the source cannot describe both. Unset means the source's number stands, which is what it has always meant. To bind it: set it to the slot count the rung's backend was started with (e.g. 8), and leave it out to inherit the source's. |
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

## `budgets`

The ceilings that bound one task's cost.

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `max_escalations` | number (min 0) | no | `1` | How many rungs a task may climb before it is handed back unfinished. A cheap rung that fails and escalates costs more than starting higher, so this is a real ceiling, not a retry count. |
| `max_attempts` | number (min 1) | no | unset | Hard ceiling on how many attempts one task may spend in total, across every rung and every family it climbs. Unset means the ladder's own budget bounds it — the sum of each reachable rung's `attempts`, which `mcgyvr pool` prints — so leaving it unset is not unbounded. Set it when you have raised a rung's `attempts` or `max_escalations` and want one number that still holds. A decline costs nothing against it: a rung that stepped aside spent no attempt. To bind it: set a whole number of attempts, or leave it unset to be bounded by the ladder's own budget (`mcgyvr pool` prints that number). |
| `task_timeout_s` | number (min 1) | no | `900` | Wall-clock ceiling for one task, including acceptance commands. |

## `breadth`

How many answers one attempt asks for. Separate from `budgets` because breadth is not a ceiling: it is what a single attempt spends, and every budget in this file still counts that attempt once.

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `draws` | number (min 1) | no | `1` | How many candidates one attempt asks its rung for before the gate picks between them. Draws are not attempts: they share one prompt and one attempt's budget, and the gate ranks the answers rather than the next attempt being told what the last one got wrong. The default of 1 is ADR-0008 unchanged — one draw, one verdict, and the draw is the answer. Raising it is most defensible on a cheap rung that is often almost right, where three draws are still cheaper than escalating; a lever whose whole benefit is fewer crossings into the api family cannot be evaluated before the telemetry that counts crossings, which is why this is something to ask for rather than something you are given. |

## `cleanup`

What may be fixed without asking a model.

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `enabled` | boolean | no | `false` | Reformat a change the gate rejected only on formatting, and judge it again, instead of spending an attempt asking a model to insert a space. The formatter is the one the gate already checks with, so a cleanup produces the shape the format rung asks for rather than a second opinion about it, and it costs no tokens by construction. Off by default because it rewrites a file after the gate has spoken about it: the bytes that come back are not the bytes the worker sent, and an operator reading a diff should have said yes to that. Nothing else is ever tidied — a lint code, a failed acceptance command or a rung that could not say what bar it applied leaves the change exactly as the worker wrote it. |

## `journal`

Where mcgyvr keeps its own record of what it dispatched.

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `dir` | text | no | `~/.local/state/mcgyvr/journal` | Where every run journals what it asked, what came back and how it landed: one `<orchestrator>.jsonl` per writer, the prompts and replies content-addressed under `blobs/`, and each run's result file under `results/`. Deterministic runs are here too, with a row naming the program instead of a model. This is mcgyvr's own record, it never lands in the repository a run works on, and nothing on the command line moves it: it is the one place every run is, which is what makes it worth asking questions of. `mcgyvr run --record DIR` adds a second copy for your own use. Read either back with `tools/live/review.py DIR`. |
