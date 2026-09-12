<!-- Code generated from src/mcgyvr/config.py by `make docs`. DO NOT EDIT. -->

# Setting up mcgyvr

First run, once per machine. Nothing here is read to author a contract;
this is how `mcgyvr.yaml` comes to exist and what it can say.

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

- `sources` — Where model work is executed, keyed by a name you choose. A source is an endpoint with a capacity and a wire protocol — nothing above the execution seam knows which host or backend served a request.
- `ladder` — The rungs work climbs, and what each is bound to.
- `budgets` — The ceilings that bound one task's cost.

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
| `version` | number (min 1) | **yes** | — | Config schema version. Currently 1; bumped only by a breaking change to this file's shape. |
| `profile` | one of `live`, `dev` | no | `live` | Which setup this file is: `live`, the ladder that serves for real, or `dev`, a setup under development. The default is `live`, because the safe value is the one you get when you say nothing: `~/.mcgyvr/config/mcgyvr.yaml` is the unnamed fallback and is the live setup, and a dev setup is a file you name in `MCGYVR_CONFIG` (or a `mcgyvr.yaml` beside the work), so forgetting the variable lands on the live setup and never the other way round. Live outranks dev on the rigs: a run under a `dev` profile does not start or stop the live ladder, refuses a rig another run holds, and yields the rig to a live run that takes it. |
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
| `serving` | block | no | — | What mcgyvr may do to the machines that serve the ladder, and where it keeps the launch specs that say how. Nothing here names a card or a host: a rung's card is derived below the execution seam from the URL its source states, which is what keeps a rung re-pointable by a config edit. |
| `journal` | block | no | — | Where mcgyvr keeps its own record of what it dispatched. |

## `sources`

Where model work is executed, keyed by a name you choose. A source is an endpoint with a capacity and a wire protocol — nothing above the execution seam knows which host or backend served a request.

Each entry takes these keys:

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `sources.base_url` | URL | **yes** | — | Where the source answers, including scheme and port. To bind it: e.g. http://localhost:8080. |
| `sources.api` | one of `openai` | **yes** | — | Wire protocol. `openai` covers vLLM, llama-server, LM Studio and TGI, so adding a backend is a protocol question, not an integration. |
| `sources.max_parallel` | number (min 1) | no | `1` | How many requests this source may run at once. Concurrency is capacity, not a preference: measured, three models ran concurrently on one card in 23.6 s against ~44 s serial. |
| `sources.context_window` | number (min 1) | no | unset | How many tokens this source's process serves in one request. Absent means nobody declared it and nothing is enforced against it: a window invented here would be a number nobody measured, and the first live day found exactly that failure — a ladder whose bottom priced a request at twice what its top could hold. Read it back from the running unit (`max_model_len` on vLLM, `n_ctx` on llama.cpp) and write what it said. It belongs on the source rather than the rung because the window is a fact about the process, and a rung that carried one could not be re-pointed at another machine. To bind it: e.g. 4096 — what the unit reports, not what you hoped for. |
| `sources.api_key_env` | env var name | no | unset | NAME of the environment variable holding this source's key. Absent means the source needs no credential, which is the normal case for a local backend. To bind it: set it to the variable's NAME (e.g. ANTHROPIC_API_KEY), never the key itself. |
| `sources.engine` | one of `llama.cpp`, `vllm` | no | unset | Which server program runs behind this URL, for `mcgyvr emit` to write a launch spec for. `api` cannot answer this: it is a wire protocol, and vLLM and llama-server both speak `openai` while taking entirely different argv. Absent means llama.cpp, which is what emit assumed unconditionally before this field existed. It belongs on the source rather than the rung because a URL points at one process and one process runs one engine. To bind it: leave it out unless the backend is not llama-server. |
| `sources.image` | text | no | unset | Container image `mcgyvr emit` writes for this source's process, as a tag or a digest. Absent means the engine's own default, and that is a floating tag: srv1's numbers are only valid against a stated build (okf/must-read/touching-rigs.md), so a source that must run one image says which here. To bind it: e.g. vllm/vllm-openai@sha256:<hex>, or llamacpp:b10644-L3. |

## `models`

Serving specs for models the shipped capability table does not carry, or whose numbers you want to override, keyed by the model identifier a rung names. mcgyvr sizes from what it can measure; this is where an operator states what it cannot. A declaration here wins over the table and is not second-guessed — a wrong one produces a launch spec that fails on the rig, which is the operator's to make.

Each entry takes these keys:

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `models.geometry_json` | text | no | unset | Path to this model's GGUF geometry: the `geometry.json` a serving-door run leaves in its envelope, or the output of `python -m mcgyvr.serving.ggufscan <gguf>` (a list; the row scanned from `<model>.gguf` is the one read). Once set it is the source of truth for the model's bytes — `disk_gb` is read from its `size_bytes`, and the card figure, the slot count and `--n-cpu-moe` are derived from its tensor table and cache geometry by the law in `mcgyvr.serving.vramfit`. A stated `disk_gb` that disagrees with it is refused, and so is a geometry scanned from a file this model does not serve: each deviation from a scan requires a new scan. Required for an MoE; a dense model without it is sized from `vram_gb` alone, one slot wide. A relative path is read against the config file's own directory, with the route to that file resolved, so an entry reached through a symlink still names the scan filed beside it; a config with no location on disk cannot read one beside itself and is refused. To bind it: on a machine holding the file, `python -m mcgyvr.serving.ggufscan <gguf> > <model>.geometry.json`, and name that file here. |
| `models.vram_gb` | decimal number (min 0.0) | no | unset | Working set on the card with nothing offloaded, in GiB, for a dense model that has no `geometry_json`. Not the weight on disk: a working set carries buffers. Not read when `geometry_json` is set — the card figure is then derived from the header. To bind it: set it to what the server reports resident on the card with -ngl 99 and no offload, converted to GiB. |
| `models.disk_gb` | decimal number (min 0.0) | no | unset | Weight on disk, in GiB, for a model that has no `geometry_json`. Note the unit — a file listed as 13.2 GB by a tool using decimal gigabytes is 12.3 GiB here. Leave it out when `geometry_json` is set: it is then read from the scan's `size_bytes`, and a stated value that differs from that by more than rounding to two decimals is refused. To bind it: set it to `ls -l` on the weights file divided by 1024^3. |
| `models.ram_gb` | decimal number (min 0.0) | no | `0.0` | A floor on what system memory may be asked to hold, in GiB. Absent means the offload arithmetic decides it alone; state it only to claim a demand this module cannot see. |
| `models.moe` | boolean | no | `false` | Whether this model has expert weights that `--n-cpu-moe` can move off the card. Not inferable from the other numbers: it is the difference between `does not fit` and `fits differently here`. |
| `models.hf_cache` | text | no | unset | The HuggingFace cache on the rig that holds this model's weights, as an absolute path there. Required for a model served by vLLM, which loads a repository id from that cache rather than a file from the weights directory; `mcgyvr emit` mounts it read-only and starts the server offline, so nothing is downloaded on a rig at load. Not read for a llama.cpp model. To bind it: e.g. /home/<user>/.cache/huggingface, as the rig sees it. |
| `models.serve_args` | list of text | no | `[]` | Arguments appended verbatim to the server's command line after the ones mcgyvr derives, for what no scan can know: `--gpu-memory-utilization` for vLLM (measured per rig, #337, never inherited), or `--chat-template-kwargs` to turn a thinking model's reasoning off. One flag or value per entry; an entry containing whitespace is refused at emit, because the compose file and the pasted command cannot spell it the same way. |

## `ladder`

The rungs work climbs, and what each is bound to.

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `ladder.tiers` | list of blocks | **yes** | — | The rungs, cheapest first. A higher rung must be measurably better than the one below or it is not a rung — binding a faster-but-weaker model above a slower-but-stronger one inverts the ladder and makes escalation actively harmful. |
| `ladder.fanout` | one of `none`, `idle`, `full` | no | `none` | Whether a batch of contracts spreads across rungs or queues on one. `none` is today's behaviour: the cheapest rung at or above the contract's floor, queued behind whoever is already there. `full` starts each climb on the cheapest rung that has a free slot, so a batch fills every rig that can serve it instead of stacking on one — and it never leaves the contract's floor family, so it cannot spend. `idle` uses that same rule and then lifts the one limit: the floor is the only bound and nothing bounds it above, so when every rung of every cheaper family is full it enters a priced api family rather than wait. That is the difference between the two, and it is a spend decision the knob makes deliberately. Neither mode reorders the ladder: load decides which rung a climb starts on and never what it may spend, so a rung passed over for being full is still walked, and a rung that can run now is never passed over for a dearer one with more room. It is a knob rather than a behaviour because the right answer is a property of the machines: two interchangeable rigs should share a batch, but a throughput rig feeding an intelligence rig must not — the second is sized to drain the first's failure tail, and fanning volume onto it eats exactly the capacity that drain needs. |

### `ladder.tiers`

The rungs, cheapest first. A higher rung must be measurably better than the one below or it is not a rung — binding a faster-but-weaker model above a slower-but-stronger one inverts the ladder and makes escalation actively harmful.

An ordered list; each entry takes these keys:

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `ladder.tiers.name` | text | **yes** | — | How this rung is referred to elsewhere — risk floors, routing policy, telemetry. Conventionally `<locality>_<model>`, e.g. `local_qwen2.5-coder-7b`, which says what the rung is rather than where it sits: a positional name silently changes meaning when a rung is inserted above it. There is no role in the name because a binding's role is already given by where it sits — this is the ladder, so it is a worker. |
| `ladder.tiers.source` | text | **yes** | — | Which declared source executes this rung. Resolution happens at the execution seam only — nothing above it knows where work ran. |
| `ladder.tiers.model` | text | **yes** | — | Model identifier as the source names it. |
| `ladder.tiers.max_parallel` | number (min 1) | no | unset | How many requests this rung may run at once, overriding its source's `max_parallel`. Concurrency is a property of the serving process rather than of the machine: the same weights on two rigs are two processes started with two different slot counts, so one number on the source cannot describe both. Unset means the source's number stands, which is what it has always meant. To bind it: set it to the slot count the rung's backend was started with (e.g. 8), and leave it out to inherit the source's. |
| `ladder.tiers.output_tokens` | number (min 1) | no | unset | How much room a reply on this rung is given — the `max_tokens` its backend is actually sent. Not a second `limits.max_output_tokens`, and deliberately not spelled like one: a contract's cap says what this unit of work is worth, and this says what this backend needs to finish a reply of that worth. The two are different questions about different things, so where a rung states one it is sent and the contract's is not — the fallback where a rung states none, which is what `dispatch_prompt` has always sent. Measured over 358 journalled attempts under one contract cap of 1024: the 3B rung's replies had a p95 of 716 and the 7B rung's 465, neither within 300 tokens of the cap, while the 35B rung's p50 was 850 and 32 of its 82 replies were cut at 1024 — `reply[incomplete-reply]`, refused rather than applied (`src/mcgyvr/worker/reply.py`), so the dearest rung in the ladder was spent and produced nothing. Taking the *lower* of the two numbers, which is what `attempts` above does, re-creates exactly that: the contract's cap is the smaller one on every rung that needed more. Taking the *higher* would forbid the other direction, and a rung needs it — a rung that answers at 17 tok/s reaches 2048 tokens only just inside the default `budgets.request_timeout_s` of 120, so this number, the rung's `max_parallel` (which lowers per-stream rate) and that timeout decide each other, and raising one alone buys a socket timeout instead of a reply. What bounds a rung's number is the rung itself: a room that does not fit its source's `context_window` alongside the prompt is refused by name in `mcgyvr.gate.preflight.check_contract_against_rung`, never truncated silently. It does not excuse a contract from declaring `limits.max_output_tokens`: `mcgyvr contract` and `mcgyvr run` still refuse a model contract that leaves it out, because a ladder can be re-pointed at rungs that declare nothing and the work still has to say what it is willing to spend. To bind it: set it to the reply length this rung's own journalled attempts show it needs (e.g. 2048), and leave it out to send the contract's cap. |
| `ladder.tiers.attempts` | number (min 1) | no | `1` | How many times this rung may be tried before escalation moves on. The default of 1 is escalate-rather-than-retry: a second attempt re-runs the same model on the same input, and the figure inherited from local-ai and not re-verified here (#152) — worker-tier remediation rescued 2 of 35 failures — says that is usually spend without a result. Raising it is most defensible on the dearest rung, which has nowhere to escalate to. A contract's `limits.attempts` caps this per task; the lower of the two applies. |

## `orchestrator`

The role that turns a prompt plus a repository into contracts. Only used in delegated mode; direct mode authors contracts itself.

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `orchestrator.source` | text | no | unset | Which declared source serves this role. Unset until something needs the role. To bind it: name one of the sources declared under `sources`. |
| `orchestrator.model` | text | no | unset | Model identifier as that source names it. To bind it: name a model the bound source can serve. |

## `verifier`

The role that reads an applied diff in fresh context.

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `verifier.enabled` | boolean | no | `false` | Model verification of the applied diff, on top of the gate. Off by default because the deterministic gate is the acceptance bar and a keyless install is a supported configuration, not a degraded one. |
| `verifier.source` | text | no | unset | Which declared source serves this role. Unset until something needs the role. To bind it: name one of the sources declared under `sources`. |
| `verifier.model` | text | no | unset | Model identifier as that source names it. To bind it: name a model the bound source can serve. |

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

## `budgets`

The ceilings that bound one task's cost.

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `budgets.max_escalations` | number (min 0) | no | `1` | How many rungs a task may climb before it is handed back unfinished. A cheap rung that fails and escalates costs more than starting higher, so this is a real ceiling, not a retry count. |
| `budgets.max_attempts` | number (min 1) | no | unset | Hard ceiling on how many attempts one task may spend in total, across every rung and every family it climbs. Unset means the ladder's own budget bounds it — the sum of each reachable rung's `attempts`, which `mcgyvr pool` prints — so leaving it unset is not unbounded. Set it when you have raised a rung's `attempts` or `max_escalations` and want one number that still holds. A decline costs nothing against it: a rung that stepped aside spent no attempt. To bind it: set a whole number of attempts, or leave it unset to be bounded by the ladder's own budget (`mcgyvr pool` prints that number). |
| `budgets.request_timeout_s` | decimal number (min 0.0) | no | `120.0` | How long one dispatched request may take before the transport gives up, in seconds. A reply of `limits.max_output_tokens` tokens takes the time its rung's per-stream rate says it takes, and that rate falls as the rung serves more streams at once, so this bound, the cap and the rung's width are three numbers that decide each other. Left as a constant in the runner it decided the other two silently: a cap an operator was free to declare was unreachable at a width they were also free to declare, and the failure arrived as a socket timeout naming neither. Raise it for a slow rung serving a large cap; lower it to fail faster. |
| `budgets.task_timeout_s` | number (min 1) | no | `900` | Wall-clock ceiling for one task, including acceptance commands. |
| `budgets.max_window_fraction` | decimal number (min 0.0, max 1.0) | no | unset | The largest share of a rung's context window one contract may claim -- its prompt and its own declared reply together, over the whole window. Distinct from whether the two *fit*, which the fit check already asks: a contract that fits with nothing to spare leaves the rung nothing to absorb a long estimate with. Unset enforces no share, which is not the same as 1.0: a run that declared none is recorded as having declared none. To bind it: a share between 0 and 1 -- e.g. 0.75 to keep a quarter of every rung's window clear -- or leave it unset to enforce no share. |

## `breadth`

How many answers one attempt asks for. Separate from `budgets` because breadth is not a ceiling: it is what a single attempt spends, and every budget in this file still counts that attempt once.

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `breadth.draws` | number (min 1) | no | `1` | How many candidates one attempt asks its rung for before the gate picks between them. Draws are not attempts: they share one prompt and one attempt's budget, and the gate ranks the answers rather than the next attempt being told what the last one got wrong. The default of 1 is ADR-0008 unchanged — one draw, one verdict, and the draw is the answer. Raising it is most defensible on a cheap rung that is often almost right, where three draws are still cheaper than escalating; a lever whose whole benefit is fewer crossings into the api family cannot be evaluated before the telemetry that counts crossings, which is why this is something to ask for rather than something you are given. |

## `cleanup`

What may be fixed without asking a model.

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `cleanup.enabled` | boolean | no | `true` | Repair a change the gate rejected with the deterministic tools — the declared imports, the linter's own autofixes, the formatter — and judge it again on the same rung, instead of spending an attempt or a climb on what a tool clears for nothing. The tools are the ones the gate already checks with, so a repair produces the shape the rungs ask for rather than a second opinion about it, and it costs no tokens by construction. On by default (owner, 2026-09-05): the first live ladder rejected all nine replies on a reflowed line, whitespace on a blank line or an unsorted import block and paid a climb for each, and running the fixers after a rung is done is the point — it lifts every task the deterministic floor could not take outright. It rewrites a file after the gate has spoken about it, so the bytes that come back are not the bytes the worker sent: the journal keeps the reply, the tree keeps the repaired file, and the verdict says a repair ran. Set false to have the rejection stand as the gate reached it. What no tool fixes — a failed acceptance command, a name, a line too long to wrap — is rejected exactly as before. |

## `serving`

What mcgyvr may do to the machines that serve the ladder, and where it keeps the launch specs that say how. Nothing here names a card or a host: a rung's card is derived below the execution seam from the URL its source states, which is what keeps a rung re-pointable by a config edit.

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `serving.enable_sleep_wake` | boolean | no | `false` | Whether mcgyvr may take a card down and bring it back on its own. Off by default, because the feature is a trade and not an improvement: turning it on lets `mcgyvr run` stop containers on a rig other people share. It is a key here and not a `--flag` for the reason `mcgyvr run --config` already gives about which rung runs — `Config.digest` is what a run is reproducible from, and a flag would let two runs share one digest where only one of them started and stopped containers on a shared rig, putting the rig side effect outside the only record that explains the run. It governs the *decisions*: `mcgyvr serve sleep\|wake`, typed by a person who has therefore asked, is not gated by it. It sits here rather than under `ladder` because `ladder.fanout` decides where work goes among rungs that exist and this decides whether rungs come into existence — two authorities, and only one of them touches a rig. |
| `serving.compose_dir` | text | no | unset | Where this checkout keeps the launch specs `mcgyvr emit` wrote. The one thing that has to be stated rather than derived, because `mcgyvr emit --out` defaults to the current directory and a wake has to find the file again. It is deliberately not a device and not a host: a `device: cuda:0` beside a `base_url` would be two statements of one fact and would go stale the first time a source was re-pointed, whereas this cannot go stale against anything — it says where files are, not where work runs. A config that omits it has no sleeping cards at all, only down ones: `asleep` is `down` plus a launch spec mcgyvr holds for that card, and with no directory there is no spec. To bind it: the directory `mcgyvr emit --out` writes to -- e.g. ~/.mcgyvr/config -- or leave it unset and this ladder has no sleeping cards, only down ones. |

## `journal`

Where mcgyvr keeps its own record of what it dispatched.

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `journal.dir` | text | no | `~/.local/state/mcgyvr/journal` | Where every run journals what it asked, what came back and how it landed: one `<orchestrator>.jsonl` per writer, the prompts and replies content-addressed under `blobs/`, and each run's result file under `results/`. Deterministic runs are here too, with a row naming the program instead of a model. This is mcgyvr's own record, it never lands in the repository a run works on, and nothing on the command line moves it: it is the one place every run is, which is what makes it worth asking questions of. `mcgyvr run --record DIR` adds a second copy for your own use. Read either back with `tools/live/review.py DIR`. The config each run was made under is kept here too, as `configs/<digest>.yaml`, and every row and result names that digest: `MCGYVR_CONFIG=<dir>/configs/<digest>.yaml` re-selects the exact setup a result was produced under. |
