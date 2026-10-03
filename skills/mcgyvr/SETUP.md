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

A hosted API unit comes in with `--api` (repeatable), written as
`model=<id>,address=<url>,api_key_env=<VAR>` — so a machine with no
GPU and no local backend gets the same two files rather than a
refusal. `api_key_env` is the NAME of the environment variable
holding the key; the key itself is never written to either file.
A machine with no local backend and no `--api` still refuses, because
a config that dispatches nowhere is not a head start.

A setup is two files in one directory, and `mcgyvr init` writes both (by
default into the working directory):

- `fleet.yaml` — what runs where: `profile`, `units`, `rigs` and `fleets`.
- `policy.yaml` — how work moves over those units: `ladder` and every other top-level key below but `relief`.

A third file, `relief.yaml`, holds `relief`: the units other
people lend you through a hub. `mcgyvr rig rungs sync` writes it whole
and nothing else does, so it is neither locked nor edited by hand.

Each file refuses a key that belongs in the other. `rigs`, `fleets` and
each unit's `unit_id` are not in the tables below: `mcgyvr fleet lock`
keys a lock on them, and the run config drops them when it loads the
setup. A `fleets` entry takes `layout` and `next`; a `rigs` entry is
checked only as a block. `examples/fleet.yaml` shows all three.

`mcgyvr pool` reads that config back: the usable rungs cheapest-first with
their family, attempt budget and model; the escalation ceiling and where it
came from; every skipped rung with the reason it was skipped; and the
orchestrator and verifier models. `--probe` also asks each unit whether it
is answering — off by default, because resolving a ladder should not need
a network. Run it whenever a run picks a rung you did not expect.

Three keys across the two files are the levers, and `mcgyvr pool` is how
you read all three:

- `units` — What runs where, keyed by a name you choose. A unit carries every fact about what it is and can physically do: its address, engine, model, width, window, reply size and timeout.
- `ladder` — The ordered list of unit names work climbs, cheapest first.
- `max_escalations` — How many rungs a task may climb before it is handed back unfinished.

`mcgyvr config` prints the resolved config; `mcgyvr detect` shows what
can run the work; `mcgyvr capabilities` shows the shipped capability table.

## Value types

| Type | Accepted |
| --- | --- |
| number | A whole number. `true` is not a number, even though Python says it is. |
| text | A non-empty string. An empty value is rejected rather than treated as unset — remove the key instead. |
| URL | Text that carries a scheme: it must start with `http://` or `https://`. |
| boolean | `true` or `false`, unquoted. |
| decimal number | A number that may carry a fraction. |
| one of ... | Text drawn from a fixed set. Anything else is rejected, with the valid values named. |
| env var name | The **name** of an environment variable (e.g. `ANTHROPIC_API_KEY`), never the value. Credentials are never written into this file; the orchestrator resolves the name at point of use and a task sandbox never sees the result. |
| list of text | A YAML list of non-empty strings. |
| block | A nested mapping with a fixed set of keys, documented in its own section. |
| block map | A mapping whose keys you choose; every entry takes the same fixed set of keys. |
| free-form block | A nested mapping whose keys the schema does not fix. |
| map of numbers | A mapping from names you choose to whole numbers. |

## Top-level keys

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `profile` | one of `live`, `dev` | no | `live` | Which setup this file is: `live` or `dev`. A fleet fact: live outranks dev on the rigs. |
| `units` | block map | **yes** | — | What runs where, keyed by a name you choose. A unit carries every fact about what it is and can physically do: its address, engine, model, width, window, reply size and timeout. |
| `ladder` | list of text | **yes** | — | The ordered list of unit names work climbs, cheapest first. |
| `fanout` | one of `none`, `idle`, `full` | no | `none` | Whether a batch of contracts spreads across units or queues on one. |
| `attempts` | map of numbers (min 1) | no | — | How many times each unit may be tried before escalation moves on. To bind it: e.g. `{<unit>: 2}`. |
| `draws` | map of numbers (min 1) | no | — | How many candidates one attempt asks *this* unit for, overriding `breadth.draws` for the units named; a unit with no entry draws the breadth. Spelled the way `attempts` is because it is the same kind of per-unit routing decision, and it is policy rather than a unit fact, which is why it is not under `units`. `mcgyvr pool` prints the effective number where it exceeds one. To bind it: e.g. `{<unit>: 3}`. |
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
| `gate` | block | no | — | What the deterministic gate refuses, where a setup may choose otherwise. |
| `serving` | block | no | — | What mcgyvr may do to the machines that serve the units. A unit's HuggingFace cache is a fact about that unit and lives on it, not here: only the policy of starting and stopping a card is a setting. |
| `manager` | block | no | — | What the ladder manager may do on its own. It runs only under `mcgyvr manage`, and only when `serving.enable_sleep_wake` is on and the ladder has units that can sleep and wake. Within this block it sleeps and wakes those units, changes `fanout` and changes which local unit leads; everything else it notices it prints as a recommendation and leaves alone. A vLLM unit sleeps at level 2, keeping its process and dropping its weights and KV cache; any other unit's containers are stopped. A wake loads the model from disk again. |
| `journal` | block | no | — | Where mcgyvr keeps its own record of what it dispatched. |
| `relief` | block map | no | — | Units other people lend you through a hub (hitchhike), keyed by name. Written whole to `relief.yaml` by `mcgyvr rig rungs sync`, and by nothing else. A relief rung is never a step of the ladder. Its host can read your prompts. |

## `units`

What runs where, keyed by a name you choose. A unit carries every fact about what it is and can physically do: its address, engine, model, width, window, reply size and timeout.

Each entry takes these keys:

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `units.address` | URL | **yes** | — | Where this unit answers, including scheme and port. One address is one process. To bind it: e.g. http://box.example:8080. |
| `units.model` | text | **yes** | — | Model identifier as the unit names it. |
| `units.engine` | one of `llama.cpp`, `vllm` | no | unset | Which server program runs behind this address. Absent means llama.cpp. To bind it: e.g. vllm -- leave it out for llama.cpp. |
| `units.image` | text | no | unset | Container image this unit runs, as a tag or digest. To bind it: e.g. vllm/vllm-openai@sha256:<hex>. |
| `units.api_key_env` | env var name | no | unset | NAME of the environment variable holding this unit's key. To bind it: set it to the variable's NAME (e.g. ANTHROPIC_API_KEY), never the key itself. |
| `units.rig` | text | no | unset | The rig this unit runs on, by the name fleet.yaml uses. Units that share a rig and an address are served by one process. To bind it: e.g. box.example. |
| `units.width` | number (min 1) | no | unset | How many requests this unit may run at once. Concurrency is a property of the process, so it is a unit fact. To bind it: e.g. 8 -- the slot count the backend was started with. |
| `units.window` | number (min 1) | no | unset | Tokens this unit serves in one request. Read it back off the running process, not hoped for. To bind it: e.g. 4096 -- what the unit reports, not what you hoped for. |
| `units.output_tokens` | number (min 1) | no | unset | Room a reply on this unit is given, the `max_tokens` its backend is actually sent. To bind it: e.g. 2048 -- the reply length this unit needs. |
| `units.request_timeout_s` | decimal number (min 0.0) | no | unset | How long one dispatched request to this unit may take before the transport gives up. To bind it: e.g. 180. |
| `units.room_mib` | number (min 0) | no | unset | The card room this unit needs, in MiB, measured or stated. To bind it: e.g. 7000 -- the card room this unit needs. |
| `units.kv_cache_memory_bytes` | number (min 0) | no | unset | The vLLM KV cache this unit pins, in bytes. Absent where the engine sizes its own cache; required before a vLLM unit is locked. To bind it: e.g. 34359738368. |
| `units.attention_backend` | text | no | unset | The attention backend this vLLM unit pins, because the card decides what is valid. To bind it: e.g. FLASH_ATTN: the backend the unit's own log names. |
| `units.container` | text | no | unset | The container name this unit runs under. To bind it: e.g. `mcgyvr-<host>-<unit>`. |
| `units.hf_cache` | text | no | unset | The HuggingFace cache on the rig holding this unit's weights, as an absolute path there. A serving fact about this unit, not a knob. To bind it: e.g. /home/<user>/.cache/huggingface, as the rig sees it. |
| `units.launch` | free-form block | no | — | The resolved launch, whole. Free-form by design: a unit hashes its whole resolved launch with no hand-kept field list, so a flag this reader has never heard of cannot go unhashed. Two keys sizing reads, llama.cpp only: `speculative` (`none` \| `mtp`, default `none`) runs the GGUF's own grafted multi-token-prediction head as the draft (`--spec-type draft-mtp`), and `spec_draft_n_max` (a count, at least 1, default 2) is its `--spec-draft-n-max`. The head is read off the scan's tensor table and charged to the card, so the `--n-cpu-moe` floor rises, and a scan with no nextn block refuses the declaration. Whether it pays depends on the card and the width. A vLLM unit declaring `mtp` is refused: its speculative decoding is `--speculative-config`, a different mechanism. Keys that split a unit across cards, of one machine or several: `shards`, a list of `{rig, gpu}` (with `bind`, the IPv4 address a worker on another machine listens on, and `room_mib`, that card's room for the lock), the first on the machine the address names; `split` (`layer` \| `tensor`, llama.cpp; `tensor` spans one machine's cards, and `row` has no split buffers on CUDA and is refused); `tensor_parallel` and `pipeline_parallel` (vLLM); `rpc_port` and `master_port`, the first port of llama.cpp's workers and vLLM's rendezvous port, each the engine's own default when absent; and `tensor_table_json`, a vLLM unit's `python -m mcgyvr.serving.safetensorscan` row. Each card is sized from the tensor table. A split left to mcgyvr is tensor across one machine's cards and pipeline across machines; what crossing between cards costs is reported, as an estimate by link class until your own reading replaces it (`mcgyvr fleet probe` times the links an awake split unit crosses) or your setting outranks both. To bind it: the resolved launch, e.g. serve_args, geometry_json, moe, speculative. |

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
| `verifier.enabled` | boolean | no | `true` | Model verification of the applied diff, on top of the gate. On unless set to `false`. With no `unit`, the reviewer is the next dearer local rung whose model is not the builder's; where there is none, the work is accepted and labelled unverified. A hosted unit reviews only when `unit` names it. |
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
| `breadth.draws` | number (min 1) | no | `1` | How many candidates one attempt asks its rung for before the gate picks between them. Draws are not attempts: they share one prompt and one attempt's budget, and the gate ranks the answers rather than the next attempt being told what the last one got wrong. The default of 1 is one draw, one verdict, and the draw is the answer. |
| `breadth.temperature` | decimal number (min 0.0, max 2.0) | no | `0.7` | What every draw after the first samples at. Draw 0 of every attempt is greedy (temperature 0.0), so a single-draw install sends what it always sent, byte for byte; draws 1..n-1 sample at this temperature, because a second draw exists to be a different candidate and a greedy one is the first draw again. 0.0 is refused at load wherever any unit's effective draws exceed 1: identical draws buy N gate runs and nothing else. The wire field is the OpenAI-compatible `temperature`. The journal records the temperature per row. |

## `cleanup`

What may be fixed without asking a model.

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `cleanup.enabled` | boolean | no | `true` | Repair a change the gate rejected with the deterministic tools — the declared imports, the linter's own autofixes, the formatter — and judge it again on the same rung, instead of spending an attempt or a climb on what a tool clears for nothing. The tools are the ones the gate already checks with, so a repair produces the shape the rungs ask for rather than a second opinion about it, and it costs no tokens by construction. It rewrites a file after the gate has spoken about it, so the bytes that come back are not the bytes the worker sent: the journal keeps the reply, the tree keeps the repaired file, and the verdict says a repair ran. Set false to have the rejection stand as the gate reached it. What no tool fixes — a failed acceptance command, a name, a line too long to wrap — is rejected exactly as before. |

## `gate`

What the deterministic gate refuses, where a setup may choose otherwise.

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `gate.param_mutation` | one of `refuse`, `report`, `skip` | no | `refuse` | A Python function that changes an object its caller passed in, on a line the change adds: it assigns or deletes into a parameter, an element of one or a loop variable over one (`rows[0] = x`, `item.count += 1`, `del table[key]`), or calls append, extend, insert, remove, pop, clear, sort, reverse, update, setdefault, add, discard or popitem on it. `self`, `cls`, `*args` and `**kwargs` are not checked, nor is a parameter rebound to a new object on every path before the change. `refuse` rejects the change. `report` does not reject it: the finding is listed among the gate's observations, which an enabled verifier is shown and the gate's retry note does not carry, and `mcgyvr run` prints it once, before delivering the accepted change, as reported by this setting. `skip` does not look. Delivery judges the change again by the same setting. A contract whose `task` or `interface` asks for in-place work stands the check down under every setting. |

## `serving`

What mcgyvr may do to the machines that serve the units. A unit's HuggingFace cache is a fact about that unit and lives on it, not here: only the policy of starting and stopping a card is a setting.

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `serving.enable_sleep_wake` | boolean | no | `false` | Whether mcgyvr may take a card down and bring it back on its own. Off by default, because the feature is a trade and not an improvement: turning it on lets `mcgyvr run` stop containers on a rig other people share. It is a key here and not a `--flag` for the reason `mcgyvr run --config` already gives about which rung runs — the config a run is made under is what a run is reproducible from, and a flag would let two runs share one config where only one of them started and stopped containers on a shared rig, putting the rig side effect outside the only record that explains the run. It also lets `mcgyvr manage`, the ladder manager, put an idle unit to sleep and wake it again on its own, but only while that command is running: with it on and no manager running, nothing sleeps a card except a person. A sleep, the manager's or a person's `mcgyvr serve sleep`, rests a vLLM card at level 2, which keeps its process and drops its weights and KV cache, and stops the containers of any other card, of a vLLM card with no sleep route, or of one holding a unit split across machines, whose level 2 is not measured; either way the next wake loads the model from disk. For that sleep it also makes `mcgyvr emit` start every vLLM unit with `--enable-sleep-mode` and `VLLM_SERVER_DEV_MODE=1`, which registers vLLM's development routes -- /sleep, /wake_up, /reset_prefix_cache and others -- on the unit's serving port, unauthenticated: anyone who can reach that port can sleep, wake or reset the unit. The emitted file says so in a comment. With the switch off, emit writes neither. It governs the *decisions*: `mcgyvr serve sleep\|wake`, typed by a person who has therefore asked, is not gated by it. It is a key of its own rather than part of `fanout` because `fanout` decides where work goes among rungs that exist and this decides whether rungs come into existence — two authorities, and only one of them touches a rig. |
| `serving.compose_dir` | text | no | unset | Where this checkout keeps the launch specs `mcgyvr emit` wrote. The one thing that has to be stated rather than derived, because `mcgyvr emit --out` defaults to the current directory and a wake has to find the file again. It is deliberately not a device and not a host: a `device: cuda:0` beside a unit's `address` would be two statements of one fact and would go stale the first time a unit was re-pointed, whereas this cannot go stale against anything — it says where files are, not where work runs. A config that omits it has no sleeping cards at all, only down ones: `asleep` is `down` plus a launch spec mcgyvr holds for that card, and with no directory there is no spec. To bind it: the directory `mcgyvr emit --out` writes to -- e.g. ~/.mcgyvr/fleets/<fleet>/compose -- or leave it unset and this ladder has no sleeping cards, only down ones. |

## `manager`

What the ladder manager may do on its own. It runs only under `mcgyvr manage`, and only when `serving.enable_sleep_wake` is on and the ladder has units that can sleep and wake. Within this block it sleeps and wakes those units, changes `fanout` and changes which local unit leads; everything else it notices it prints as a recommendation and leaves alone. A vLLM unit sleeps at level 2, keeping its process and dropping its weights and KV cache; any other unit's containers are stopped. A wake loads the model from disk again.

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `manager.interval_s` | number (min 1) | no | `30` | How often the ladder manager asks its small model for a decision, in seconds. The default of 30 is an estimate, not a measurement: nothing here has timed how fast a queue builds or drains on your units. Lower it to react sooner, at the price of more questions asked of a model that is itself running on the ladder's hardware; raise it to ask less. The manager runs only under `mcgyvr manage`, and only when `serving.enable_sleep_wake` is on and the ladder has units that can sleep and wake. Everything it sees that falls outside what this block lets it change, it prints as a recommendation and does not do. |
| `manager.confirm` | number (min 1) | no | `3` | How many consecutive identical answers the manager must get before it acts on one, so a single odd answer from a small model moves nothing. The default of 3 is an estimate, not a measurement: it lets one stray answer fail to act alone, and it has not been tuned against any real queue. With the default interval it means about a minute and a half of the same answer before anything happens. Set 1 to act on every answer. |
| `manager.dwell_s` | number (min 0) | no | `600` | The least time between two switches, in seconds, so the manager cannot sleep a unit and wake it again in a loop. A unit that changed state without the manager -- a task woke it, or a person ran `mcgyvr serve` -- counts as a switch too, and a unit is put to sleep only once it has been idle for this long. A vLLM unit sleeps at level 2 and keeps its process; any other unit's containers are stopped. Either way a wake loads the model from disk again, so every switch costs a full load. The default of 600 is an estimate, not a measurement. Set it above the time your sleeping units take to wake -- `mcgyvr serve wake` prints that time -- or the manager can be asking for a unit back before the last wake has finished. 0 allows a switch on every decision. |
| `manager.fanouts` | list of text | no | `[]` | The fan-out modes the manager may choose between, each one of `none`, `idle` or `full` as `fanout` spells them, each listed once. The manager changes `fanout` only among these, and fewer than two means there is nothing to choose between, so it is never asked. Empty by default: a manager that was not told which modes it may use leaves `fanout` as the file says. |
| `manager.leads` | list of text | no | `[]` | The local units the manager may move to the front of the local family, each listed once. Each must be on the `ladder` and must need no credential: a unit that is not on the ladder is not one work climbs, and a unit with an `api_key_env` is hosted, not local. Empty by default, which means the manager is never asked which unit should lead and the ladder's own order stands. |

## `journal`

Where mcgyvr keeps its own record of what it dispatched.

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `journal.dir` | text | no | `~/.local/state/mcgyvr/journal` | Where every run journals what it asked, what came back and how it landed: one `<orchestrator>.jsonl` per writer, the prompts and replies content-addressed under `blobs/`, and each run's result file under `results/`. Deterministic runs are here too, with a row naming the program instead of a model. This is mcgyvr's own record, it never lands in the repository a run works on, and nothing on the command line moves it: it is the one place every run is, which is what makes it worth asking questions of. `mcgyvr run --record DIR` adds a second copy for your own use. Read either back with `tools/live/review.py DIR`. |

## `relief`

Units other people lend you through a hub (hitchhike), keyed by name. Written whole to `relief.yaml` by `mcgyvr rig rungs sync`, and by nothing else. A relief rung is never a step of the ladder. Its host can read your prompts.

Each entry takes these keys:

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `relief.address` | URL | **yes** | — | The hub's OpenAI-compatible address the rung is asked at, ending in `/v1`. To bind it: e.g. https://hub.example.org/v1, as the hub gave it. |
| `relief.model` | text | **yes** | — | The model string sent with each request, as the hub gave it. |
| `relief.api_key_env` | env var name | **yes** | — | NAME of the environment variable holding your personal hub key, which each request carries. To bind it: the variable's NAME (e.g. MCGYVR_HUB_API_KEY), never the key. |
| `relief.width` | number (min 1) | **yes** | — | How many of your requests the rung takes at once. |
| `relief.position` | one of `above_ceiling`, `below_floor`, `within` | **yes** | — | Where the host's model sits against the models on your own rigs, as the hub judges it. Shown, never a place on the ladder. |
| `relief.hosted_by` | text | no | unset | The handle of the person whose unit this is. They can read your prompts and the answers. To bind it: leave it to `mcgyvr rig rungs sync`, which writes the hub's word. |
| `relief.served_model` | text | no | unset | What the host's unit runs, for display. Never sent. To bind it: leave it to `mcgyvr rig rungs sync`, which writes the hub's word. |
