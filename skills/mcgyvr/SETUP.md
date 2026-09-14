<!-- Code generated from src/mcgyvr/config.py by `make docs`. DO NOT EDIT. -->

# Setting up mcgyvr

First run, once per machine. Nothing here is read to author a contract;
this is how `fleet.yaml` and `policy.yaml` come to exist and what they can say.

```
mcgyvr init
mcgyvr pool
```

`mcgyvr init` detects what is reachable and writes a config bound to it. It
refuses to overwrite an existing config without `--force`, and prints what
was decided and why, then what is *not* configured and what that costs.
Backends on another machine come in with `--host` (repeatable).

`mcgyvr pool` reads that config back: the usable rungs cheapest-first with
their family, attempt budget and model; the escalation ceiling and where it
came from; every skipped rung with the reason it was skipped; and the
orchestrator and verifier models. `--probe` also asks each source whether it
is answering — off by default, because it spends. Run it whenever a run
picks a rung you did not expect.

Three keys of that one config file are the levers, and `mcgyvr pool` is how
you read all three:

- `units` — What runs where, keyed by a name you choose. A unit carries every fact about what it is and can physically do: its address, engine, model, width, window, reply size and timeout.
- `ladder` — The ordered list of unit names work climbs, cheapest first.
- `max_escalations` — How many rungs a task may climb before it is handed back unfinished.

`mcgyvr config` prints the resolved config; `mcgyvr detect` and
`mcgyvr capabilities` say what a source is and what it can do.

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
| `profile` | one of `live`, `dev` | no | `live` | Which setup this file is: `live` or `dev`. A fleet fact: live outranks dev on the rigs. |
| `units` | block map | **yes** | — | What runs where, keyed by a name you choose. A unit carries every fact about what it is and can physically do: its address, engine, model, width, window, reply size and timeout. |
| `ladder` | list of text | **yes** | — | The ordered list of unit names work climbs, cheapest first. |
| `fanout` | one of `none`, `idle`, `full` | no | `none` | Whether a batch of contracts spreads across units or queues on one. |
| `attempts` | map of numbers (min 1) | no | — | How many times each unit may be tried before escalation moves on. To bind it: e.g. {srv2_7b: 2}. |
| `max_escalations` | number (min 0) | no | `1` | How many rungs a task may climb before it is handed back unfinished. |
| `max_attempts` | number (min 1) | no | unset | Hard ceiling on how many attempts one task may spend in total. To bind it: set a whole number of attempts, or leave it unset. |
| `task_timeout_s` | number (min 1) | no | `900` | Wall-clock ceiling for one task, including acceptance commands. |
| `max_window_fraction` | decimal number (min 0.0, max 1.0) | no | unset | The largest share of a unit's context window one contract may claim. To bind it: a share between 0 and 1. |
| `orchestrator` | block | no | — | Which unit turns a prompt plus a repository into contracts. |
| `verifier` | block | no | — | Which unit reads an applied diff in fresh context. |
| `sandbox` | block | no | — | Where a task's commands run. |
| `delivery` | block | no | — | How accepted work gets back to you. |
| `breadth` | block | no | — | How many answers one attempt asks for. |
| `cleanup` | block | no | — | What may be fixed without asking a model. |
| `serving` | block | no | — | What mcgyvr may do to the machines that serve the units. A unit's HuggingFace cache is a fact about that unit and lives on it, not here: only the policy of starting and stopping a card is a setting. |
| `journal` | block | no | — | Where mcgyvr keeps its own record of what it dispatched. |

## `units`

What runs where, keyed by a name you choose. A unit carries every fact about what it is and can physically do: its address, engine, model, width, window, reply size and timeout.

Each entry takes these keys:

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `units.address` | URL | **yes** | — | Where this unit answers, including scheme and port. One address is one process: a unit is the one term for what used to be a source. To bind it: e.g. http://srv2:8002. |
| `units.model` | text | **yes** | — | Model identifier as the unit names it. |
| `units.engine` | one of `llama.cpp`, `vllm` | no | unset | Which server program runs behind this address. Absent means llama.cpp. To bind it: e.g. vllm -- leave it out for llama.cpp. |
| `units.image` | text | no | unset | Container image this unit runs, as a tag or digest. To bind it: e.g. vllm/vllm-openai@sha256:<hex>. |
| `units.api_key_env` | env var name | no | unset | NAME of the environment variable holding this unit's key. To bind it: set it to the variable's NAME (e.g. ANTHROPIC_API_KEY), never the key itself. |
| `units.rig` | text | no | unset | The rig this unit runs on, by the name fleet.yaml uses. Units that share a rig and an address are served by one process. To bind it: e.g. srv2. |
| `units.width` | number (min 1) | no | unset | How many requests this unit may run at once. Concurrency is a property of the process, so it is a unit fact. To bind it: e.g. 8 -- the slot count the backend was started with. |
| `units.window` | number (min 1) | no | unset | Tokens this unit serves in one request. Read it back off the running process, not hoped for. To bind it: e.g. 4096 -- what the unit reports, not what you hoped for. |
| `units.output_tokens` | number (min 1) | no | unset | Room a reply on this unit is given, the `max_tokens` its backend is actually sent. To bind it: e.g. 2048 -- the reply length this unit needs. |
| `units.request_timeout_s` | decimal number (min 0.0) | no | unset | How long one dispatched request to this unit may take before the transport gives up. To bind it: e.g. 180. |
| `units.room_mib` | number (min 0) | no | unset | The card room this unit needs, in MiB, measured or stated. Replaces the model block's vram/ram/disk sizes. To bind it: e.g. 7000 -- the card room this unit needs. |
| `units.kv_cache_memory_bytes` | number (min 0) | no | unset | The vLLM KV cache this unit pins, in bytes. Absent where the engine sizes its own cache; required before a vLLM unit is locked. To bind it: e.g. 34359738368. |
| `units.attention_backend` | text | no | unset | The attention backend this vLLM unit pins, because the card decides what is valid. To bind it: e.g. FLASH_ATTN, or TRITON_ATTN on cc 7.5. |
| `units.container` | text | no | unset | The container name this unit runs under. To bind it: e.g. mcgyvr-srv2-srv2_7b. |
| `units.hf_cache` | text | no | unset | The HuggingFace cache on the rig holding this unit's weights, as an absolute path there. A serving fact about this unit, not a knob. To bind it: e.g. /home/<user>/.cache/huggingface, as the rig sees it. |
| `units.launch` | free-form block | no | — | The resolved launch, whole. Free-form by design: a unit hashes its whole resolved launch with no hand-kept field list (ID-2), so a flag this reader has never heard of cannot go unhashed. To bind it: the resolved launch, e.g. serve_args, geometry_json, moe. |

## `orchestrator`

Which unit turns a prompt plus a repository into contracts.

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `orchestrator.unit` | text | no | unset | Which unit serves this role. A unit is the one term. To bind it: name one of the units declared under `units`. |
| `orchestrator.model` | text | no | unset | Model identifier as that unit names it; absent means the unit's own. To bind it: name a model the bound unit serves. |

## `verifier`

Which unit reads an applied diff in fresh context.

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `verifier.enabled` | boolean | no | `false` | Model verification of the applied diff, on top of the gate. |
| `verifier.unit` | text | no | unset | Which unit serves this role. A unit is the one term. To bind it: name one of the units declared under `units`. |
| `verifier.model` | text | no | unset | Model identifier as that unit names it; absent means the unit's own. To bind it: name a model the bound unit serves. |

## `sandbox`

Where a task's commands run.

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `sandbox.mode` | one of `docker`, `tempdir` | no | `docker` | `docker` runs each task in its own container, torn down after. `tempdir` is the explicitly weaker fallback for installs without Docker: acceptance commands are arbitrary shell from a contract, running on someone else's machine. |
| `sandbox.image` | text | no | unset | Base image for task containers. Unset means detect the repository's stack and build one. To bind it: name an image tag, or leave unset to let the stack be detected. |
| `sandbox.setup` | list of text | no | `[]` | Commands run once when the task image is built, before any task. |

## `delivery`

How accepted work gets back to you.

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `delivery.mode` | one of `branch`, `none` | no | `branch` | Where an accepted change is committed. `branch` puts it on a new local branch named after the contract and leaves the branch you have checked out, your index and your working tree exactly as they were — the delivery tells you the `git push` to run. `none` commits onto the branch you have checked out. Nothing here pushes or opens a pull request: mcgyvr reaches your repository through `git` and has no forge, so the last step off this machine is yours. |

## `breadth`

How many answers one attempt asks for.

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `breadth.draws` | number (min 1) | no | `1` | How many candidates one attempt asks its rung for before the gate picks between them. Draws are not attempts: they share one prompt and one attempt's budget, and the gate ranks the answers rather than the next attempt being told what the last one got wrong. The default of 1 is  unchanged — one draw, one verdict, and the draw is the answer. Raising it is most defensible on a cheap rung that is often almost right, where three draws are still cheaper than escalating; a lever whose whole benefit is fewer crossings into the api family cannot be evaluated before the telemetry that counts crossings, which is why this is something to ask for rather than something you are given. |

## `cleanup`

What may be fixed without asking a model.

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `cleanup.enabled` | boolean | no | `true` | Repair a change the gate rejected with the deterministic tools — the declared imports, the linter's own autofixes, the formatter — and judge it again on the same rung, instead of spending an attempt or a climb on what a tool clears for nothing. The tools are the ones the gate already checks with, so a repair produces the shape the rungs ask for rather than a second opinion about it, and it costs no tokens by construction. On by default (owner, 2026-09-05): the first live ladder rejected all nine replies on a reflowed line, whitespace on a blank line or an unsorted import block and paid a climb for each, and running the fixers after a rung is done is the point — it lifts every task the deterministic floor could not take outright. It rewrites a file after the gate has spoken about it, so the bytes that come back are not the bytes the worker sent: the journal keeps the reply, the tree keeps the repaired file, and the verdict says a repair ran. Set false to have the rejection stand as the gate reached it. What no tool fixes — a failed acceptance command, a name, a line too long to wrap — is rejected exactly as before. |

## `serving`

What mcgyvr may do to the machines that serve the units. A unit's HuggingFace cache is a fact about that unit and lives on it, not here: only the policy of starting and stopping a card is a setting.

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `serving.enable_sleep_wake` | boolean | no | `false` | Whether mcgyvr may take a card down and bring it back on its own. Off by default, because the feature is a trade and not an improvement: turning it on lets `mcgyvr run` stop containers on a rig other people share. It is a key here and not a `--flag` for the reason `mcgyvr run --config` already gives about which rung runs — the config a run is made under is what a run is reproducible from, and a flag would let two runs share one config where only one of them started and stopped containers on a shared rig, putting the rig side effect outside the only record that explains the run. It governs the *decisions*: `mcgyvr serve sleep\|wake`, typed by a person who has therefore asked, is not gated by it. It sits here rather than under `ladder` because `ladder.fanout` decides where work goes among rungs that exist and this decides whether rungs come into existence — two authorities, and only one of them touches a rig. |
| `serving.compose_dir` | text | no | unset | Where this checkout keeps the launch specs `mcgyvr emit` wrote. The one thing that has to be stated rather than derived, because `mcgyvr emit --out` defaults to the current directory and a wake has to find the file again. It is deliberately not a device and not a host: a `device: cuda:0` beside a `base_url` would be two statements of one fact and would go stale the first time a source was re-pointed, whereas this cannot go stale against anything — it says where files are, not where work runs. A config that omits it has no sleeping cards at all, only down ones: `asleep` is `down` plus a launch spec mcgyvr holds for that card, and with no directory there is no spec. To bind it: the directory `mcgyvr emit --out` writes to -- e.g. ~/.mcgyvr/fleets/<fleet>/compose -- or leave it unset and this ladder has no sleeping cards, only down ones. |

## `journal`

Where mcgyvr keeps its own record of what it dispatched.

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `journal.dir` | text | no | `~/.local/state/mcgyvr/journal` | Where every run journals what it asked, what came back and how it landed: one `<orchestrator>.jsonl` per writer, the prompts and replies content-addressed under `blobs/`, and each run's result file under `results/`. Deterministic runs are here too, with a row naming the program instead of a model. This is mcgyvr's own record, it never lands in the repository a run works on, and nothing on the command line moves it: it is the one place every run is, which is what makes it worth asking questions of. `mcgyvr run --record DIR` adds a second copy for your own use. Read either back with `tools/live/review.py DIR`. |
