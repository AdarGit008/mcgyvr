# mcgyvr

Offload scoped coding work from your agent to a configurable worker ladder.

mcgyvr runs scoped coding work as *contracts* — one target, one task, one way
to judge it. `mcgyvr "<prompt>"` has the proposer your setup binds plan a prompt
into contracts; `mcgyvr direct FILE... | DIR` takes contracts you or your session
model wrote. Either way each contract is vetted, run on a deterministic tool or up
a ladder of local and API models, in the order its dependency tree allows, and
only what the deterministic gate accepts is kept, as a change in your working
tree. It never commits unless told to, and it never writes anything else into
the repository. `skills/mcgyvr/SKILL.md` (`/mcgyvr <prompt>`) and
`skills/mcgyvr-direct/SKILL.md` (`/mcgyvr-direct <files|dir>`, with the contract
vocabulary) say how a session drives each; how a setup is written is in
`skills/mcgyvr/SETUP.md`.

## Install

Linux and macOS:

```sh
uv tool install mcgyvr
git clone https://github.com/AdarGit008/mcgyvr
mcgyvr/skills/mcgyvr/install.sh
```

Windows (PowerShell):

```powershell
uv tool install mcgyvr
git clone https://github.com/AdarGit008/mcgyvr
powershell -NoProfile -ExecutionPolicy RemoteSigned -File mcgyvr\skills\mcgyvr\install.ps1
```

`install.sh` (`install.ps1` on Windows) copies the `/mcgyvr`, `/mcgyvr-direct`
and `/mcgyvr-use` skills into `~/.claude/skills/<name>` and
`~/.pi/agent/skills/<name>`, and warns when the `mcgyvr` on `PATH` is older
than the skills can drive. On a Mac or a Windows machine, setup runs llama.cpp
natively, with no Docker; `skills/mcgyvr/SETUP.md`, *macOS and Windows*, says
what else differs there.

## GPUs and engines

mcgyvr pins one build of each local engine, and each build runs on NVIDIA
cards from a floor up. Read your card's compute capability (cc) first:

```sh
nvidia-smi --query-gpu=name,compute_cap,driver_version --format=csv
```

| Engine and build                                      | CUDA       | Lowest cc |
|-------------------------------------------------------|------------|-----------|
| llama.cpp `b11960` container (`server-cuda-b11960`)   | 12.8       | 5.0       |
| llama.cpp `b11960` native, CUDA 12 archives           | 12.8, 12.4 | 5.0       |
| llama.cpp `b11960` native, CUDA 13 archives           | 13.4       | 7.5       |
| vLLM `v0.26.0` container (`vllm/vllm-openai:v0.26.0`) | 13.0       | 7.5       |

- The CUDA toolkit sets the floor along with the engine: CUDA 13 dropped every
  card below cc 7.5 (Maxwell, Pascal, Volta), so a CUDA 13 build of any
  engine does not run on them. The CUDA 12 llama.cpp builds reach cc 5.0, 6.1
  and 7.0 through PTX only (no compiled kernels for those cards).
- A native llama.cpp unit takes the newest CUDA build your driver runs
  (driver 580 or newer: CUDA 13; 525 or newer: CUDA 12). It does not read the
  card's cc, so on a card below cc 7.5 with driver 580 or newer, name the
  backend yourself: `MCGYVR_NATIVE_BACKEND=vulkan` (or `cpu`).
- vLLM needs cc 7.5 or newer; on an older card, serve with llama.cpp.
- A Mac runs llama.cpp on Metal, with no CUDA floor.
- Floors belong to a build: re-read them when a pin moves.

## First run: `mcgyvr setup`

`mcgyvr setup` reads this machine's hardware (and any rig named with `--host`,
over ssh), recommends the units, ladder and fleet that fit it for the use case
you choose (`mcgyvr-code`, `code`, `chat` or `agent`), and writes `fleet.yaml` and
`policy.yaml` into a folder of the run's own under `$MCGYVR_DATA/setup/<run>`
(default `~/.local/state/mcgyvr/setup/<run>` on Linux; SETUP.md names the
macOS and Windows folders), never the working directory.
Asked, it starts the units and samples them; a fleet whose sample passes is
locked and promoted, and `~/.mcgyvr/live.json` names it as the live fleet. A
fleet that could not be sampled is locked only on `--accept-unsampled` or an
explicit yes, and one whose sample failed is never locked.

Without the questions: `--host` binds backends on another machine, `--api
model=<id>,address=<url>,api_key_env=<VAR>` binds a hosted unit (the key stays
in your environment), `--use-case` and `--priority` choose what the ladder is
composed for. `mcgyvr-code` puts mcgyvr between the model and you, every stage
(gate, repair, reviewer, ladder, re-plan and the rest) under its own switch in
`policy.yaml`; `code`, `chat` and `agent` serve the model raw. `mcgyvr use NAME`
switches it later. `mcgyvr fleet use|probe|alerts` names another promoted fleet
live, probes the live one against its lock, and lists pulled combinations.

## Using it

- **The `/mcgyvr` skill.** An agent writes a contract, checks it with
  `mcgyvr contract CONTRACT.yaml`, runs it with
  `mcgyvr direct CONTRACT.yaml --repo DIR` on the live fleet, and replans on what
  the run reports. A request in words goes to `mcgyvr "<prompt>" --session ID`,
  which plans the contracts and runs them.

Read-only introspection: `mcgyvr config`, `mcgyvr local_pool`,
`mcgyvr catalog`, `mcgyvr sandbox` and `mcgyvr capabilities`.

## What decides acceptance

The **gate** (`src/mcgyvr/gate/`) is deterministic: scope and secret scans,
per-language syntax and structural checks, lint and format rungs, typecheck,
semantic resolution, and the contract's own acceptance commands, each
attributed to the lines the worker added. A run climbs the ladder
cheapest-first until a rung passes the gate or a ceiling stops it.

## Concepts

- **Config schema** (`src/mcgyvr/config.py`) — a setup declares `units`
  (address, model, engine, key variable name, limits), the ordered `ladder`
  work climbs cheapest-first, `sandbox` (mode, fallback, network), `delivery`,
  `verifier`, `orchestrator`, and the journal. Unknown, missing, or mis-typed
  keys are refused, and credentials are recorded as environment-variable
  names, never values.
- **Task catalog** (`data/task-catalog.json`) — the vocabulary of what mcgyvr
  can be asked to do: the task type (`code`), the families work
  may start on (`deterministic`, `local`, `api`), and the evidence each type
  must carry.
- **Fleet** (`src/mcgyvr/fleet/`) — reads `fleet.yaml` (units, rigs, fleets)
  and `policy.yaml` (the ladder and policy settings), locks a sampled fleet
  and promotes it to `~/.mcgyvr/fleets/`, with `~/.mcgyvr/live.json` naming
  the live one.
- **Ladder** — `src/mcgyvr/local_pool.py` resolves a setup into the dispatch
  endpoints work may actually use. `src/mcgyvr/rig/` is the optional
  hub-agent protocol, not part of setup.

## Development

The documented way in is `make`:

- `make setup` — install dependencies, frozen against `uv.lock`.
- `make test` — run the test suite (`pytest`).
- `make lint` — `ruff check .` and `ruff format --check .`.
- `make typecheck` — `mypy`, in strict mode.
- `make docs` — render and check the config reference (then delete it), and
  regenerate `skills/mcgyvr/SKILL.md` and `SETUP.md`,
  `skills/mcgyvr-direct/SKILL.md`, `references/examples.md` and
  `references/failure-notes.schema.json`, and `skills/mcgyvr-use/SKILL.md` from
  the CLI's flags and the schemas in `src/mcgyvr/config.py`,
  `src/mcgyvr/contract.py` and `src/mcgyvr/notes.py`.
- `make check` — everything CI runs: lint, typecheck, docs check, and test.

The CLI is `mcgyvr` (`mcgyvr.cli:main`, defined under `src/mcgyvr/cli/`).
