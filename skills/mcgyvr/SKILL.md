---
name: mcgyvr
description: "Offload a coding request to mcgyvr, a CLI that plans a prompt into task contracts and runs them on deterministic tools, local models or API models, keeping only what its deterministic gate accepts. Pass the user's words as the prompt: mcgyvr surveys the repository, a proposer proposes contracts, every proposal is vetted, and the contracts that pass run in dependency order. It never loads itself; invoke it with /mcgyvr <prompt>. Contracts you write yourself, or ones it refused or could not finish, go to /mcgyvr-direct."
disable-model-invocation: true
---

<!-- Code generated from src/mcgyvr/flagset.py and src/mcgyvr/docgen.py by `make docs`. DO NOT EDIT. -->

# /mcgyvr

Offload a coding request to mcgyvr in the user's own words. mcgyvr plans it
into contracts (one target, one task, one way to judge it each), runs them,
gates every answer deterministically, and leaves accepted `code` changes in
the working tree. It never commits unless told to, and it never writes
anything else into the repository.

## Run it

```
mcgyvr "<prompt>" [--repo PATH] [flags]
```

The prompt is everything the user wrote after `/mcgyvr`, passed as one
argument; one whose first word is a command name goes after `--`
(`mcgyvr -- "<prompt>"`). The contracts planned are printed on stdout, and
what happens to them on stderr.

Every run works on the repository as committed at HEAD: uncommitted edits
and untracked files, including a test you just wrote, are not in the
sandbox. A batch refuses unless it can say who typed it: Claude Code and Pi
sessions are detected from the environment, otherwise pass `--session ID`.

## What it does

```
prompt -survey-> evidence -propose-> proposals -vet-> contracts | refusals
       -schedule-> tree -run-> settle -(spent)-> replan
```

Planning is survey, propose and vet. mcgyvr reads the repository for the
evidence the prompt points at, and the proposer bound in the config proposes
contracts from it. Every proposal is vetted: its target is a file the index
holds, each dependency's signature is in the index or in a contract that
creates it, what the worker is shown fits its ceiling, and its id is unused.
One that fails is a refusal, printed as `refused:` with a `change:` line
saying what to change.

Dispatch is schedule, run, settle and replan. The contracts that passed go on
one dependency tree and run in the order it allows, each settled as it ends.
One whose provider did not land is held, never sent (`blocked`). One whose
ladder is spent goes back to the proposer with its failure notes, and what
comes back runs in its place, up to `max_replans` times.

## Flags that matter

- `--jobs N` — run up to N ready contracts at once, each settled as it ends and the next started as soon
  as it is ready (default: 1, one at a time). N is capped at the fleet's total slots, the most dispatches
  its units take at once; `auto` or 0 is that cap. Two contracts whose scopes can write one file never
  run at once, and a run's output is written whole when it ends. Runs beside each other share the fleet's
  slots, so one may wait for a rung, or pass a busy one by, as two runs typed in two terminals would.
- `--commit`, `--no-commit` — commit each accepted change, or not (--no-commit), whatever
  `delivery.commit` says.
- `--branch NAME` — commit each accepted change onto branch NAME; implies --commit.
- `--session ID` — the session the runs are filed under, resolved before any work (default: the session
  that typed this command, and a refusal, exit 2, when there is none); not needed with --output, which
  runs nothing.
- `--record DIR` — also journal each run under DIR, as a complete second copy.
- `--output DIR` — stop once the contracts are planned: write each one that passed vetting to
  DIR/<id>.json and run none of them, so `mcgyvr direct DIR` can run them later. Without it a prompt's
  contracts are printed on stdout and run from a temporary directory, and `direct` runs its files where
  they are.

`mcgyvr direct -h` lists every flag; both verbs take the same set.

## How it ended

- 0 — the contracts were planned (and, unless `--output`, every one that ran
  ended well).
- 1 — a failure: the config, the proposer or its reply, the repository, a
  run that did not land its change, or a crash; stderr says which.
- 2 — usage: a flag that cannot be honoured or has no meaning on this side, a
  contract path that is not there, or no session to file the runs under.
- 3 — refused: no proposer is configured, no contract came of the prompt or
  passed vetting, or a contract was held and never sent (`blocked`).

`--help` prints the same table.

## Where the results are

Nothing on stdout points at a result. Each contract that ran has a result
file under the config's `journal.dir`, as `results/<id>-<stamp>.json`;
`--record DIR` puts a complete copy of each under `DIR/results/`. Read
`outcome` first: the /mcgyvr-direct skill lists every key of the file. An
`accepted` change is in its target, uncommitted unless `--commit` or
`--branch NAME` was given: review it there and commit it yourself.

## Refused or spent: hand it to /mcgyvr-direct

A refusal, a contract held `blocked` behind one, and a contract whose ladder
is spent past `max_replans` are work this batch will not finish. Finish it
with /mcgyvr-direct: write the contracts yourself, or plan again with
`--output DIR`, which writes each contract that passed vetting to
`DIR/<id>.json` and runs none, fix those files from the refusals and the
findings, and run them with `/mcgyvr-direct DIR`.
