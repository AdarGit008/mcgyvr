<!-- Code generated from src/mcgyvr/config.py by `make docs`. DO NOT EDIT. -->

# Setting up mcgyvr

First run, once per machine. Nothing here is read to author a contract;
this is how `fleet.yaml` and `policy.yaml` come to exist and what they can say.

```
mcgyvr setup
mcgyvr local_pool
```

`mcgyvr setup` reads each rig once and stages a setup bound to what it
serves in a folder of the run's own, `$MCGYVR_DATA/setup/<run>/` (default
`~/.local/state/mcgyvr/setup/<run>/`), kept as the record of that run; it
writes nothing in the working directory. It prints what was decided and
why, then what is *not* configured and what that costs.

Run at a terminal with no flags, it asks which rigs serve — `local`,
`remote` or `both` (Enter is `local`) — and, for `remote` or `both`,
the ssh host(s) to read. It then asks the use case by letter (`[d]
coding`, `[c] chat`, `[a] agent`; Enter or `d` is
`coding`) and whether to dedicate a unit to Jev (Enter is no): the
questions `--use-case` and `--jev` answer. It plans a
model of that use case for each rig, says whether its candidates came
from the Hugging Face Hub, the cache of an earlier Hub read or the
shipped catalog, asks before each download, writes the staged setup
once and emits its launch specs once, and asks before it starts the
serving containers through the door. It then samples the fleet: a read
of every rig, a
probe and a load of every unit, the use case's sample task (for
`coding`, a one-function bug fix the deterministic gate must pass) and
a Jev unit's one typed choice. A green sample is stamped, and on
`Lock the fleet and name it live? [y/N]` it is locked, promoted and
named live. A red sample is never locked; its reasons are printed.

When the interactive setup finishes, it offers to append
`export PATH="$HOME/.local/bin:$PATH"` to the login shell's rc file
(`~/.bashrc`, `~/.zshrc`, `~/.profile`, or
`~/.config/fish/config.fish`, by `$SHELL`), once you say yes; a file
that already carries a `.local/bin` PATH line is left alone.

A fleet that could not be sampled — its containers not started, or
every unit hosted — is locked
approved on no evidence only once you say so: setup says why and what
that means, and asks `Lock it approved on no evidence? [y/N]`. With
flags, setup binds the servers already answering and starts none, so
nothing is sampled; `--accept-unsampled` is that acknowledgment, and
without it nothing is locked. Backends on another machine come in with
`--host` (repeatable).

A locked fleet is promoted to a folder of its own under
`$MCGYVR_HOME/fleets/` and named in `$MCGYVR_HOME/live.json`, with
`serving.enable_sleep_wake` on and its launch specs in the staged folder
(`serving.compose_dir`), so a request to a unit that is down wakes it
through the door. That live fleet is the config every command reads,
wherever it is run, unless `$MCGYVR_CONFIG` or `--config DIR` names
another; a `fleet.yaml` in the working directory is not read. Setup
stages in `PATH` or `--config DIR` when one is named, and there refuses
to overwrite a setup without `--force`.

A hosted API unit comes in with `--api` (repeatable), written as
`model=<id>,address=<url>,api_key_env=<VAR>` — so a machine with no
GPU and no local backend gets the same two files rather than a
refusal. `api_key_env` is the NAME of the environment variable
holding the key; the key itself is never written to either file.
A machine with no local backend and no `--api` still refuses, because
a config that dispatches nowhere is not a head start.

What the config is for comes in with these, all optional:

- `--use-case` — `coding` (the deterministic gate, the default), `chat`
  or `agent`.
- `--deployment` — `hybrid` (an API-tier orchestrator drives mcgyvr) or
  `local-only` (mcgyvr is the backend); the default is `local-only` for
  `chat` and `hybrid` otherwise.
- `--priority` — compose the ladder for `throughput`, `quality` or
  `cost` instead of the default ladder.
- `--profile` — deprecated, removed in the release after next: use
  `--priority`. A word naming a priority maps onto it, other text is
  ignored, and either way it warns.
- `--jev UNIT` — dedicate VRAM to a Jev unit, the written unit every
  typed decision asks; it is never slept or woken.

`mcgyvr setup --help` has each one's full text.

Two commands measure and plan before `mcgyvr setup` writes a config.
`mcgyvr scan` measures this machine (free and total VRAM, available RAM,
cores, timed memory bandwidth, free disk), records it as this machine's
rig file (`localhost.json` in the rig-file folder, `$MCGYVR_RIGS`, by
default `~/.mcgyvr/rigs`), says what moved since the last record, and
exits 4 when a card, total RAM, the cores or the bandwidth moved.
`mcgyvr recommend --profile coding --users N --host RIG` re-reads each
rig over ssh and prints one JSON plan: which checkpoint and engine serve
that profile, from `--model-store DIR` when a checkpoint there fits,
otherwise from the use case's candidates on the Hugging Face Hub
(ranked by downloads; the cache of an earlier read, then the shipped
model catalog, when the Hub cannot be asked), says which answered,
and names the host it goes on. `chat` and `agent` plan one unit: the
biggest model that fits, at the most context that fits and at least
8192 per user. It wakes and sleeps nothing, and writes nothing but that
cache.

A setup is two files in one directory, and `mcgyvr setup` writes both
(staged under the data folder, as above):

- `fleet.yaml` — what runs where: `units`, `rigs` and `fleets`.
- `policy.yaml` — how work moves over those units: `ladder` and every other top-level key below but `relief`.

A third file, `relief.yaml`, holds `relief`: the units other
people lend you through a hub. `mcgyvr rig rungs sync` writes it whole
and nothing else does, so it is neither locked nor edited by hand.

Each file refuses a key that belongs in the other. `rigs`, `fleets` and
each unit's `unit_id` are not in the tables below: the fleet lock
keys on them, and the run config drops them when it loads the
setup. A `fleets` entry takes `layout` and `next`; a `rigs` entry is
checked only as a block. `examples/fleet.yaml` shows all three.

`mcgyvr local_pool` reads that config back: the usable rungs cheapest-first with
their family, attempt budget and model; the escalation ceiling and where it
came from; every skipped rung with the reason it was skipped; and the
orchestrator and verifier models. `--probe` also asks each unit whether it
is answering — off by default, because resolving a ladder should not need
a network. Run it whenever a run picks a rung you did not expect.

Three keys across the two files are the levers, and `mcgyvr local_pool` is how
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
| `use_case` | one of `coding`, `chat`, `agent` | no | `coding` | Which of the three use cases this install serves: `coding` (scoped edits judged by the deterministic gate), `chat` (a raw un-gated endpoint) or `agent` (a raw un-gated endpoint with tool-calling). |
| `deployment` | one of `hybrid`, `local-only` | no | `hybrid` | How mcgyvr is run. `hybrid` drives it from an API-tier orchestrator in the user's session; scoped work is offloaded to the local cheap-to-dear ladder, whose dearest rung is an API model so a task always completes. `local-only` makes mcgyvr the backend: a non-chat use case provisions a local orchestrator unit, and chat is just the ladder serving text. |
| `units` | block map | **yes** | — | What runs where, keyed by a name you choose. A unit carries every fact about what it is and can physically do: its address, engine, model, width, window, reply size and timeout. |
| `ladder` | list of text | **yes** | — | The ordered list of unit names work climbs, cheapest first. |
| `fanout` | one of `none`, `idle`, `full` | no | `none` | Whether a batch of contracts spreads across units or queues on one. |
| `attempts` | map of numbers (min 1) | no | — | How many times each unit may be tried before escalation moves on. To bind it: e.g. `{<unit>: 2}`. |
| `draws` | map of numbers (min 1) | no | — | How many candidates one attempt asks *this* unit for, overriding `breadth.draws` for the units named; a unit with no entry draws the breadth. Spelled the way `attempts` is because it is the same kind of per-unit routing decision, and it is policy rather than a unit fact, which is why it is not under `units`. `mcgyvr local_pool` prints the effective number where it exceeds one. To bind it: e.g. `{<unit>: 3}`. |
| `rider_slots` | map of numbers (min 0) | no | — | How many of each named unit's slots riders may use at once (hitchhike): people the hub matches to you, whose requests for the unit's model the agent of `mcgyvr rig` passes to it and whose prompts you can read. A unit the map does not name shares none. It is policy, not a fact of the unit, so changing it never changes the setup's identity or its lock, and a running agent sends the hub the change within a second, with no reconnect. Below the unit's `width`, so you always keep a slot, and your own requests go first: a ride is taken only while the unit has a slot free, your requests and the rides in flight together fewer than its `width`, so riders use only slots you are not using, and a unit whose server does not report what it has in flight shares nothing. A ride that has started runs to its end; a request of yours that arrives meanwhile waits for a slot as any of yours does. A unit is shared only when it is on the `ladder`, needs no key (`api_key_env`), is not a relief rung, states its `window`, the context of each slot, and has a `width` of at most 16, the most the hub takes; one unit per model. To bind it: e.g. `{<unit>: 1}` -- at most one below the unit's `width`. |
| `max_escalations` | number (min 0) | no | `1` | How many rungs a task may climb before it is handed back unfinished. |
| `max_attempts` | number (min 1) | no | unset | Hard ceiling on how many attempts one task may spend in total. To bind it: set a whole number of attempts, or leave it unset. |
| `task_timeout_s` | number (min 1) | no | `900` | Wall-clock ceiling for one task, including acceptance commands. |
| `max_window_fraction` | decimal number (min 0.0, max 1.0) | no | unset | The largest share of a unit's context window one contract may claim -- its prompt and its declared reply together -- checked before the contract is sent, so a contract claiming more fails unsent on the unit it was sent to. It is a ceiling no contract can raise: a contract's own `limits.max_window_fraction` may hold it to less, never to more, and the stricter of the two applies. Unset enforces no run-wide share. To bind it: a share between 0 and 1. |
| `users` | number (min 1) | no | `1` | Users this install serves at once, and therefore the slot count the local orchestrator unit is served at: one session per user. A written `width` on the orchestrator's unit wins. `1` is a single-user install, which for a local-only non-chat use case is flagged, not refused — the resident orchestrator consumes the card the ladder would otherwise use. |
| `orchestrator` | block | no | — | Which unit turns a prompt plus a repository into contracts, and what that unit is. |
| `verifier` | block | no | — | Which unit reads an applied diff in fresh context. |
| `jev` | block | no | — | Which one unit answers every typed decision: a question answered with a single-token label rather than prose. Those are the gate's Jev rung, the reviewer's verdict, the fleet's choice of whether to wake a smarter rung and the typed proposer. Left unbound, each of those keeps asking the unit it asks today: the verifier, the reviewing rung, the fast rung or the orchestrator. |
| `sandbox` | block | no | — | Where a task's commands run. |
| `delivery` | block | no | — | How accepted work gets back to you. |
| `breadth` | block | no | — | How many answers one attempt asks for. |
| `cleanup` | block | no | — | What may be fixed without asking a model. |
| `gate` | block | no | — | What the deterministic gate refuses, where a setup may choose otherwise. |
| `serving` | block | no | — | What mcgyvr may do to the machines that serve the units. A unit's HuggingFace cache is a fact about that unit and lives on it, not here: only the policy of starting and stopping a card is a setting. |
| `journal` | block | no | — | Where mcgyvr keeps its own record of what it dispatched. To say what a run belongs to — an experiment, a build — set `MCGYVR_RUN_TAGS` to a JSON object of text, number or true/false values, e.g. `{"round": "r7"}`, at most 4096 bytes: every row the run writes carries it under `run_tags`. Set to anything else, the run is refused before it starts. |
| `relief` | block map | no | — | Units other people lend you through a hub (hitchhike), keyed by name. Written whole to `relief.yaml` by `mcgyvr rig rungs sync`, and by nothing else. A relief rung is never a step of the ladder: under `fanout: idle` it takes work only when your own rung is full, ahead of a priced api rung, and no escalation climbs to it. Its host can read your prompts. |

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
| `units.window` | number (min 1) | no | unset | Tokens this unit serves in one request. Read it back off the running process, not hoped for: `setup` reads it off a local backend and writes it, and lists a unit it could not read as not configured. Less the prompt, it is the ceiling a `code` contract's `limits.max_output_tokens` is held to on this unit; a unit with neither `window` nor `output_tokens` refuses code dispatch. To bind it: e.g. 4096 -- what the unit reports, not what you hoped for. |
| `units.output_tokens` | number (min 1) | no | unset | Room a reply on this unit is given, hidden reasoning included: a ceiling a `code` contract's `limits.max_output_tokens` is held to, beside the room `window` leaves for the prompt (the smaller of the two where both are set). It never raises the contract's cap, which is sent exactly; a cap above the ceiling is narrowed to it, and refused by name where the ceiling is below half the cap. A hosted reasoning model needs tens of thousands; `setup --api` writes 32768. To bind it: e.g. 2048 -- the reply length this unit needs. |
| `units.request_timeout_s` | decimal number (min 0.0) | no | unset | How long one dispatched request to this unit may take before the transport gives up, in seconds. Unset, a hosted unit (one with `api_key_env`) waits for its reply however long it takes, and a local unit gives up after 120 s. To bind it: seconds; leave it unset on a hosted unit. |
| `units.room_mib` | number (min 0) | no | unset | The card room this unit needs, in MiB, measured or stated. To bind it: e.g. 7000 -- the card room this unit needs. |
| `units.kv_cache_memory_bytes` | number (min 0) | no | unset | The vLLM KV cache this unit pins, in bytes. Absent where the engine sizes its own cache; required before a vLLM unit is locked. To bind it: e.g. 34359738368. |
| `units.attention_backend` | text | no | unset | The attention backend this vLLM unit pins, because the card decides what is valid. To bind it: e.g. FLASH_ATTN: the backend the unit's own log names. |
| `units.container` | text | no | unset | The container name this unit runs under. To bind it: e.g. `mcgyvr-<host>-<unit>`. |
| `units.hf_cache` | text | no | unset | The HuggingFace cache on the rig holding this unit's weights, as an absolute path there. A serving fact about this unit, not a knob. To bind it: e.g. /home/<user>/.cache/huggingface, as the rig sees it. |
| `units.sampling` | one of `request`, `server` | no | `request` | Who sets the sampling parameters of a request to this unit. `request`: the request states `temperature` -- 0.0 for the greedy first draw, `breadth.temperature` for the draws after it -- which is what a deterministic gate needs from a local unit. `server`: the unit's model fixes its own sampling and refuses the parameters, so none is sent; the hosted Claude models from Opus 4.7 on answer a request naming `temperature` with HTTP 400 (Anthropic's model migration guide). A `server` unit cannot be asked for more than one draw: without a temperature every draw is the first draw again. A fact about the unit's server, so it is here and not in the policy. |
| `units.role` | one of `always-on`, `sleeps-until-needed` | no | `always-on` | Whether this unit is up whenever its launch spec is (`always-on`) or is a swap partner that starts asleep (`sleeps-until-needed`). A sleeper shares its card's one launch spec with the always-on units under a compose profile, so a whole `serve up` leaves it down and the awake set still fits the card. A run whose climb reaches it, or a fleet sample, swaps it in, stopping the units whose room it needs first; a sample starts those again when it sleeps. llama.cpp units only: a vLLM unit swaps at level 2 with its process kept. |
| `units.launch` | free-form block | no | — | The resolved launch, whole. Free-form by design: a unit hashes its whole resolved launch with no hand-kept field list, so a flag this reader has never heard of cannot go unhashed. Two keys sizing reads, llama.cpp only: `speculative` (`none` \| `mtp`, default `none`) runs the GGUF's own grafted multi-token-prediction head as the draft (`--spec-type draft-mtp`), and `spec_draft_n_max` (a count, at least 1, default 2) is its `--spec-draft-n-max`. The head is read off the scan's tensor table and charged to the card, so the `--n-cpu-moe` floor rises, and a scan with no nextn block refuses the declaration. Whether it pays depends on the card and the width. A vLLM unit declaring `mtp` is refused: its speculative decoding is `--speculative-config`, a different mechanism. Keys that split a unit across cards, of one machine or several: `shards`, a list of `{rig, gpu}` (with `bind`, the IPv4 address a worker on another machine listens on, and `room_mib`, that card's room for the lock), the first on the machine the address names; `split` (`layer` \| `tensor`, llama.cpp; `tensor` spans one machine's cards, and `row` has no split buffers on CUDA and is refused); `tensor_parallel` and `pipeline_parallel` (vLLM); `rpc_port` and `master_port`, the first port of llama.cpp's workers and vLLM's rendezvous port, each the engine's own default when absent; and `tensor_table_json`, a vLLM unit's `python -m mcgyvr.serving.safetensorscan` row. Each card is sized from the tensor table. A split left to mcgyvr is tensor across one machine's cards and pipeline across machines; what crossing between cards costs is reported, as an estimate by link class until your own reading replaces it (`mcgyvr fleet probe` times the links an awake split unit crosses) or your setting outranks both. To bind it: the resolved launch, e.g. serve_args, geometry_json, moe, speculative. |

## `orchestrator`

Which unit turns a prompt plus a repository into contracts, and what that unit is.

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `orchestrator.type` | one of `proposer` | no | `proposer` | What the bound unit is. `proposer`, the only type: the bound unit drafts contracts for `mcgyvr delegate`. |
| `orchestrator.authoring` | one of `prose`, `classifier` | no | unset | How `mcgyvr delegate` gets its proposals. `prose`: the bound unit is asked for JSON proposals (`delegate.build_prompt`), and the deterministic decomposer turns them into contracts. `classifier`: the `jev` unit answers typed questions (task type, target, symbol, task, interface, dependency, scope) first, and `prose` stands in when it declines. With no `jev` unit bound no model is asked: each field takes its first candidate — the first servable type and target, the target's first symbol, and the request as the task — and `prose` stands in only when there is no target or servable type to pick. Unset is `prose`. To bind it: name one of `prose`, `classifier`. |
| `orchestrator.unit` | text | no | unset | Which unit serves this role. A unit is the one term. To bind it: name one of the units declared under `units`. |
| `orchestrator.model` | text | no | unset | Model identifier as that unit names it; absent means the unit's own. To bind it: name a model the bound unit serves. |

## `verifier`

Which unit reads an applied diff in fresh context.

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `verifier.enabled` | boolean | no | `true` | Model verification of the applied diff, on top of the gate. On unless set to `false`. With no `unit`, the reviewer is the next dearer local rung whose model is not the builder's; where there is none, the work is accepted and labelled unverified. A hosted unit reviews only when `unit` names it, or stands in for a hosted `unit` as `unit` says. |
| `verifier.unit` | text | no | unset | Which unit reviews. A unit is the one term. It reviews every rung's work except work its own model wrote, because a model does not review its own output. That work is reviewed by a fallback: the usable rung nearest this unit on the ladder whose model is not the builder's — the rungs below it first, dearest first, then the rungs above it, cheapest first. A local rung may always be the fallback; a hosted one only when this unit is hosted and the rung is below it on the ladder. The result and the journal name the fallback and say it stood in; with none, the work is accepted and labelled unverified, saying why. To bind it: name one of the units declared under `units`. |
| `verifier.model` | text | no | unset | Model identifier as that unit names it; absent means the unit's own. To bind it: name a model the bound unit serves. |

## `jev`

Which one unit answers every typed decision: a question answered with a single-token label rather than prose. Those are the gate's Jev rung, the reviewer's verdict, the fleet's choice of whether to wake a smarter rung and the typed proposer. Left unbound, each of those keeps asking the unit it asks today: the verifier, the reviewing rung, the fast rung or the orchestrator.

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `jev.unit` | text | no | unset | Which unit serves this role. A unit is the one term. To bind it: name one of the units declared under `units`. |
| `jev.model` | text | no | unset | Model identifier as that unit names it; absent means the unit's own. To bind it: name a model the bound unit serves. |

## `sandbox`

Where a task's commands run.

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `sandbox.mode` | one of `docker`, `tempdir` | no | `docker` | `docker` runs each task in its own container, torn down after; with no Docker daemon answering, the task is refused unless `allow_fallback` is on. `tempdir` is the explicitly weaker mode for installs without Docker: a contract's acceptance commands run without a shell, but each runs whatever program it names, on the host, with only the host's process, network and resource isolation. |
| `sandbox.allow_fallback` | boolean | no | `false` | What `mode: docker` does when no Docker daemon answers. Off, the task is refused and the refusal says how to go on. On, the task runs in the `tempdir` sandbox instead and says so once — the weaker mode, chosen ahead of time rather than read about after the run started. |
| `sandbox.network` | one of `bridge`, `none` | no | `bridge` | The network a task container is attached to. `bridge` is Docker's default: acceptance commands can fetch dependencies and reach the configured worker endpoints — and anything else this machine can reach. `none` gives the container no network at all, so a contract whose commands download anything fails. `none` needs `mode: docker`: the `tempdir` sandbox runs on this host, where the network cannot be taken away, and is refused under it. |
| `sandbox.image` | text | no | unset | Base image for task containers. Unset means detect the repository's stack and build one. To bind it: name an image tag, or leave unset to let the stack be detected. |
| `sandbox.setup` | list of text | no | `[]` | Commands run once when the task image is built, before any task. In docker mode the gate's type checker, eslint and prettier run in the task container, because their configuration can load code from the task's workspace, so they are found on the image's PATH. The image mcgyvr builds installs the one the repository configures (mypy, eslint, prettier) when its dependency install does not, at the lockfile's version where it pins one; pyright, or a checker the repository does not configure, is yours to put on the image, here or with `sandbox.image`. A checker the image lacks is skipped and said so, as an absent checker is on the host. |

## `delivery`

How accepted work gets back to you.

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `delivery.commit` | boolean | no | `false` | Whether `mcgyvr run` commits an accepted change. Off, the change is left in your working tree, uncommitted, for you to review and commit. On, it is committed onto the branch you have checked out, or onto `branch` when that is set. `run --commit` and `run --no-commit` decide for one run instead. Nothing here pushes or opens a pull request: the last step off this machine is yours. |
| `delivery.branch` | text | no | unset | The branch an accepted change is committed onto, instead of the one you have checked out. It says where, not whether: nothing is committed while `commit` is off. A branch that does not exist is created from the commit you have checked out; one that does gets the commit on its tip, refused when its copy of the target differs from the one the change was judged against. Either way the branch you have checked out, your index and your working tree are left exactly as they were, and the run prints the `git push` to run. A branch checked out in another worktree is refused. `run --branch NAME` names one for one run and implies `--commit`. To bind it: name a branch, or leave unset to commit onto the branch you have checked out. |

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
| `serving.enable_sleep_wake` | boolean | no | `false` | Whether mcgyvr may take a card down and bring it back on its own. Off by default, because the feature is a trade and not an improvement: turning it on lets `mcgyvr run` stop containers on a rig other people share. It is a key here and not a `--flag` for the reason `mcgyvr run --config` already gives about which rung runs — the config a run is made under is what a run is reproducible from, and a flag would let two runs share one config where only one of them started and stopped containers on a shared rig, putting the rig side effect outside the only record that explains the run. A card sleeps when a person runs `mcgyvr serve sleep`, or when a run swaps a sleeper in to make room and puts it back once it is idle; a sleep rests a vLLM card at level 2, which keeps its process and drops its weights and KV cache, and stops the containers of any other card, of a vLLM card with no sleep route, or of one holding a unit split across machines, whose level 2 is not measured; either way the next wake loads the model from disk. For that sleep it also makes `mcgyvr emit` start every vLLM unit with `--enable-sleep-mode` and `VLLM_SERVER_DEV_MODE=1`, which registers vLLM's development routes -- /sleep, /wake_up, /reset_prefix_cache and others -- on the unit's serving port, unauthenticated: anyone who can reach that port can sleep, wake or reset the unit. The emitted file says so in a comment. With the switch off, emit writes neither. It governs the *decisions*: `mcgyvr serve sleep\|wake`, typed by a person who has therefore asked, is not gated by it. It is a key of its own rather than part of `fanout` because `fanout` decides where work goes among rungs that exist and this decides whether rungs come into existence — two authorities, and only one of them touches a rig. |
| `serving.compose_dir` | text | no | unset | Where this checkout keeps the launch specs `mcgyvr emit` wrote. The one thing that has to be stated rather than derived, because `mcgyvr emit --out` defaults to the current directory and a wake has to find the file again. It is deliberately not a device and not a host: a `device: cuda:0` beside a unit's `address` would be two statements of one fact and would go stale the first time a unit was re-pointed, whereas this cannot go stale against anything — it says where files are, not where work runs. A config that omits it has no sleeping cards at all, only down ones: `asleep` is `down` plus a launch spec mcgyvr holds for that card, and with no directory there is no spec. To bind it: the directory `mcgyvr emit --out` writes to -- e.g. ~/.mcgyvr/fleets/<fleet>/compose -- or leave it unset and this ladder has no sleeping cards, only down ones. |

## `journal`

Where mcgyvr keeps its own record of what it dispatched. To say what a run belongs to — an experiment, a build — set `MCGYVR_RUN_TAGS` to a JSON object of text, number or true/false values, e.g. `{"round": "r7"}`, at most 4096 bytes: every row the run writes carries it under `run_tags`. Set to anything else, the run is refused before it starts.

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `journal.dir` | text | no | `~/.local/state/mcgyvr/journal` | Where every run journals what it asked, what came back and how it landed: one `<orchestrator>.jsonl` per writer, the prompts and replies content-addressed under `blobs/`, and each run's result file under `results/`. Deterministic runs are here too, with a row naming the program instead of a model. This is mcgyvr's own record, it never lands in the repository a run works on, and nothing on the command line moves it: it is the one place every run is, which is what makes it worth asking questions of. `mcgyvr run --record DIR` adds a second copy for your own use. Read either copy back from DIR directly: one JSONL per writer, prompts and replies under `blobs/`, results under `results/`. |

## `relief`

Units other people lend you through a hub (hitchhike), keyed by name. Written whole to `relief.yaml` by `mcgyvr rig rungs sync`, and by nothing else. A relief rung is never a step of the ladder: under `fanout: idle` it takes work only when your own rung is full, ahead of a priced api rung, and no escalation climbs to it. Its host can read your prompts.

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
| `relief.busy_answers` | list of blocks | no | — | The answers, each an HTTP status and an error code, that say this rung cannot take a request now: one of them is a full rung, passed over at no cost, and any other answer is read as on any rung. Unset, the rung names no busy answers; a sync writes them. To bind it: leave it to `mcgyvr rig rungs sync`, which writes them. |

### `relief.busy_answers`

The answers, each an HTTP status and an error code, that say this rung cannot take a request now: one of them is a full rung, passed over at no cost, and any other answer is read as on any rung. Unset, the rung names no busy answers; a sync writes them.

An ordered list; each entry takes these keys:

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `relief.busy_answers.status` | number (min 100, max 599) | **yes** | — | The HTTP status of the answer. |
| `relief.busy_answers.code` | text | **yes** | — | The error code the answer's body carries (`error.code`). |
