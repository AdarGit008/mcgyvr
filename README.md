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
  `references/failure-notes.schema.json` from the CLI's flags and the schemas in
  `src/mcgyvr/config.py`, `src/mcgyvr/contract.py` and `src/mcgyvr/notes.py`.
- `make check` — everything CI runs: lint, typecheck, docs check, and test.

The CLI is `mcgyvr` (`mcgyvr.cli:main`, defined under `src/mcgyvr/cli/`).
