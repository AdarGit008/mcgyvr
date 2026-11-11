<!-- Code generated from the mcgyvr parser by `make docs` (src/mcgyvr/cli/verbdoc.py). DO NOT EDIT. -->

# mcgyvr commands

Every verb and flag the `mcgyvr` parser defines, listed from the parser itself; `mcgyvr VERB -h` prints
the same help. The bare verb, `mcgyvr PROMPT [flags]` (delegate), decomposes a prompt into contracts and
runs them with `direct`'s flags. Where a flag's help says *the usual setup*, that is $MCGYVR_CONFIG, else
the live fleet folder under $MCGYVR_HOME/fleets (default ~/.mcgyvr/fleets) that $MCGYVR_HOME/live.json
(default ~/.mcgyvr/live.json) names — a directory holding fleet.yaml and policy.yaml.

- `mcgyvr` — Offload scoped coding work to a configurable worker ladder.
  - `--version` — the product version, and the path of the config a run here would use.
- `mcgyvr capabilities` (also `caps`) — show the shipped model estimates.
  - `--vram GB` — show only models that fit this much VRAM with working headroom; for a unified-memory
    GPU, the memory it may use, as `mcgyvr detect` states it (an estimate).
- `mcgyvr config [PATH]` — validate the configuration file and show what it resolves to.
  - `--config PATH` — config to read (default: the usual setup).
- `mcgyvr ladder` — read the ladder a setup resolves to.
- `mcgyvr ladder show [PATH]` — show the ladder as it resolves against the declared units.
  - `--config PATH` — config to read (default: the usual setup).
  - `--probe` — also ask each unit whether it is answering, and drop the rungs of any that is not (off by
    default: resolving a ladder should not require a network).
  - `--probe-timeout SECONDS` — how long a unit has to answer a probe (default: 2).
- `mcgyvr catalog [NAME]` — show the task types mcgyvr can be asked for, and what each guarantees.
  - `--against CONFIG` — resolve against a configured ladder and name the types it cannot start (default
    config: the usual setup).
  - `--config PATH` — resolve against this setup's ladder, as --against PATH does (default: the usual
    setup).
- `mcgyvr contract PATH` — validate a task contract and show what it resolves to.
  - `--worker-view` — print exactly the fields a worker prompt may be built from.
- `mcgyvr usage [JOURNAL]` — show what the journal's runs added up to: tokens, time and outcomes per run
  and per rung.
  - `--config PATH` — read the journal this setup's `journal.dir` names (default: the usual setup).
- `mcgyvr detect` — show what can run the work, and how each fact was detected.
  - `--host HOST` — also sweep this machine for backends, by name or address (repeatable; default:
    localhost only). Hardware detection stays local — a remote rig is described by what it serves.
- `mcgyvr scan` — measure this machine, record it, and report what changed since.
  - `--json` — write the scan to stdout and nothing else — the wire format the remote transport parses.
  - `--rig RIG` — scan RIG instead, over your own ssh (read-only), and save it as the serving door's rig
    file RIG.json in $MCGYVR_RIGS (default $MCGYVR_HOME/rigs), which a door run from an install holds the
    rig to; says what moved since the last.
  - `--model-store DIR` — a directory holding \*.gguf and \*.safetensors checkpoints to inventory as
    models-on-disk, in addition to the weights dir (repeatable).
- `mcgyvr recommend` — print one JSON plan: which checkpoint and engine serve a profile.
  - `--profile PROFILE` — the usage profile to place for.
  - `--users N|single` — how many users the placement serves: `single` or a positive number.
  - `--host RIG` — a rig to re-read over ssh and place on (repeatable).
  - `--model-store DIR` — a directory on the rig holding \*.gguf checkpoints (repeatable); when any fits,
    a coding plan recommends only from it.
- `mcgyvr serve DIRECTION` — put a card to sleep, or wake it, through the serving door.
  - `--host HOST` — the rig, as the host in a unit's `address` names it.
  - `--config PATH` — config to read (default: the usual setup).
- `mcgyvr emit` — write a compose file per launch spec for the ladder's serving units.
  - `--config PATH` — config to read (default: the usual setup).
  - `--out DIR` — where the compose files are written (default: the current directory).
  - `--ctx-per-slot N` — the window this run serves per slot, for units that declare no `window` of their
    own; `-c` is this times the slot count, and the cache law is fed the same product. A unit that
    declares its window is emitted at that window, and a flag that contradicts a declaration is refused
    rather than preferred.
  - `--check` — compare the files already under --out with what this config emits and write nothing: exit
    4 when they disagree, naming each file and the lines that moved. A config edited without re-emitting
    is two configurations, and the rig goes on serving the older one.
- `mcgyvr sandbox` — show the sandbox mode and the stack detected for a repository.
  - `--repo PATH` — the repository to inspect (default: .).
  - `--cache` — list cached task images with their sizes instead of inspecting a repo.
  - `--clear-cache` — remove every task image mcgyvr has cached.
  - `--config PATH` — setup whose `sandbox` block a run here would read (default: the usual setup).
- `mcgyvr setup [PATH]` — read each rig, plan, stage, start and sample a fleet, and lock it live on your
  yes.
  - `--host HOST` — bind backends on this machine too, by name or address (repeatable; default: localhost
    only).
  - `--rig-address RIG=ADDRESS` — state the IPv4 address a rig's units are reached at, recorded in its
    rig file beside the scan (repeatable; for a rig whose scan recorded no address, so a unit addressed
    by it still finds the rig).
  - `--api SPEC` — bind a hosted API unit, which needs no GPU and no local backend, as
    `model=<id>,address=<url>,api_key_env=<VAR>` (repeatable), optionally `,output_tokens=<N>` for the
    room its replies are given (default 32768: a reasoning model spends it thinking before it writes).
    api_key_env is the NAME of the environment variable holding your key, never the key itself.
  - `--config PATH` — the same as PATH: the setup to write.
  - `--force` — overwrite an existing config, discarding hand edits.
  - `--priority PRIORITY` — compose the ladder for this priority (throughput, quality or cost) instead of
    writing the default ladder. The decision runs on the first detected backend; every number in the file
    stays measured or the schema's, never the model's.
  - `--use-case USE_CASE` — which use case this install serves: mcgyvr-code (mcgyvr between the model and
    you: the gate, repair, verifier, ladder and the rest, each switchable), or code, chat or agent (the
    model served raw); default: mcgyvr-code.
  - `--deployment MODEL` — how mcgyvr is run: hybrid (an API-tier session agent drives it) or local-only
    (mcgyvr is the backend and provisions a local proposer for mcgyvr-code); default: hybrid.
  - `--jev UNIT` — dedicate VRAM to a Jev unit: the written unit every typed decision asks, never slept
    or woken (an opt-in; no model is picked for you).
  - `--accept-unsampled` — lock the fleet setup binds approved on no evidence, and name it live: setup
    with flags starts no container, so no sample runs on what it binds. Without it nothing is locked, and
    the limits say why. Nothing measured stands behind such a lock.
- `mcgyvr attach` — attach a repository (local path or clone URL) and show its state.
  - `--repo PATH` — the repository to attach: a local git checkout, or a URL to clone
    (https/ssh/git/file) (default: .).
  - `--into DIR` — clone a URL into DIR and keep it, instead of an ephemeral temp dir.
- `mcgyvr index` — build the deterministic index of a repository and show what it cost.
  - `--repo PATH` — the repository to index (default: .).
  - `--search TERM` — also run a text search for TERM and show the hits.
  - `--symbol NAME` — also show where NAME is defined and referenced.
  - `--limit N` — cap the number of text-search hits shown (default: 20).
  - `--no-cache` — build from source without reading or writing the index cache.
  - `--refresh-cache` — ignore the cached index, rebuild from source, and store the result.
  - `--clear-cache` — remove this repository's cached index and exit.
- `mcgyvr resolve QUERY` — resolve a natural-language target to a ranked shortlist of paths.
  - `--repo PATH` — the repository to resolve against (default: .).
  - `--limit N` — cap the shortlist to N candidates (default: 10).
- `mcgyvr read QUERY` — resolve a target, then read the regions it justifies within a budget.
  - `--repo PATH` — the repository to read from (default: .).
  - `--budget TOKENS` — cap exploration at TOKENS estimated tokens (default: 2000).
  - `--context LINES` — lines per read window around each anchor (default: 25).
  - `--limit N` — cap the resolver shortlist to N candidates first (default: 10).
  - `--hint PATH` — a path you believe is relevant; re-ranks the shortlist but can never add to it or
    overturn a resolved leader (repeatable).
  - `--holds PATH` — a path whose current content you already hold; verified against the index, and if it
    matches its regions cost the budget nothing (repeatable).
  - `--json` — print one JSON document instead of the report: the request, the shortlist, the regions
    read, and the whole text of every shortlisted and read file — what a server with no path to this
    repository needs to index it.
- `mcgyvr fleet` — name a promoted fleet live, and read what its lock approves.
- `mcgyvr fleet use FLEET@DATE` — name a promoted fleet live, in $MCGYVR_HOME/live.json (default
  ~/.mcgyvr/live.json), and say whether the move from the fleet that was live is one its lock measured.
- `mcgyvr fleet probe [UNIT ...]` — judge the live fleet's idle units by their lock's own measurement,
  filed under <journal.dir>/fleet.
- `mcgyvr fleet alerts` — list the combinations the journal holds pulled.
  - `--journal DIR` — where the fleet journal was filed (default: <journal.dir>/fleet of the live fleet,
    where `mcgyvr fleet probe` files).
  - `--root DIR` — where the lock tree is read (default: the folder of the fleet $MCGYVR_HOME/live.json
    (default ~/.mcgyvr/live.json) names).
- `mcgyvr fleet key UNIT` — print the key a unit of `expose: lan` asks every request for, for a client of
  yours (mcgyvr's own requests send it already).
  - `--config PATH` — config to read (default: the usual setup).
- `mcgyvr rig` — publish this machine as a rig of a hub.
- `mcgyvr rig join HUB_URL` — keep a hub's rig token and run the agent in the foreground.
  - `--token TOKEN` — the rig token the hub showed when the rig was created; - reads it from stdin.
  - `--port-forward` — allow the hub's UDP port forward of this rig's tunnel ports on your router (UPnP
    or NAT-PMP), once agreed on the hub too.
  - `--no-port-forward` — refuse it (the default).
  - `--config PATH` — setup whose units the agent shares (default: the usual setup).
- `mcgyvr rig run` — run the agent again from the kept token.
  - `--config PATH` — setup whose units the agent shares (default: the usual setup).
- `mcgyvr rig status` — what is kept, what the agent last heard, what this reads as.
- `mcgyvr rig leave` — forget the rig token here.
- `mcgyvr rig peers` — the peers whose identity keys this rig pinned, with their fingerprints.
  - `--forget RIG_ID` — forget one peer's pinned key, after its owner rotated it and you compared the new
    fingerprint with them.
- `mcgyvr rig rungs` — the hitchhike rungs the hub matched you to.
- `mcgyvr rig rungs sync` — keep the hub's hitchhike rungs in the setup's hitchhike.yaml, replacing the
  ones kept.
  - `--hub HUB_URL` — the hub to ask (default: the one this machine joined).
  - `--key-env NAME` — the NAME of the variable holding your personal hub key (default:
    MCGYVR_HUB_API_KEY).
  - `--config PATH` — setup whose hitchhike.yaml is written (default: the usual setup).
  - `--ride-scope SCOPE` — set the setup's ride_scope first: whose rigs may read its rides, own, crew
    (the default) or anyone, an opt-in that shows the hub's privacy text.
- `mcgyvr rig crew` — the units your crews lend you through the hub.
- `mcgyvr rig crew sync` — keep the units your crews lend you in the setup's crew.yaml, replacing the
  ones kept.
  - `--hub HUB_URL` — the hub to ask (default: the one this machine joined).
  - `--key-env NAME` — the NAME of the variable holding your personal hub key (default:
    MCGYVR_HUB_API_KEY).
  - `--config PATH` — setup whose crew.yaml is written (default: the usual setup).
- `mcgyvr rig share` (also `lend`) — what this rig lends to the hub's sessions; change it.
  - `--on`
  - `--off`
  - `--image IMAGE` — the engine image sessions run in (none).
  - `--roles ROLES` — worker, head, or worker,head.
  - `--cards CARDS` — card indexes lent, each whole, comma separated, or all.
  - `--max-ram-mb MAX_RAM_MB` — the memory each container may take, or none.
  - `--models MODELS` — the folder models are served from, or none.
  - `--endpoints ENDPOINTS` — LAN addresses to be reached at, or none.
  - `--listen-port LISTEN_PORT` — the first tunnel UDP port; each further session at once takes the next.
  - `--cache`
  - `--no-cache`
  - `--cache-max-mb CACHE_MAX_MB` — the worker cache's size.
  - `--ram-mb RAM_MB` — host memory lent to whole models this rig heads, in MiB, or 0.
  - `--cpu-cores CPU_CORES` — cores lent to whole models this rig heads, or 0.
  - `--launcher LAUNCHER` — docker: sessions run in containers; native (macOS, Windows): through the
    mcgyvr-wg helper on the pinned llama.cpp build, head only.
  - `--port-forward` — allow the hub's UDP port forward of this rig's tunnel ports on your router (UPnP
    or NAT-PMP), once agreed on the hub too.
  - `--no-port-forward` — refuse it (the default).
  - `--permanent-forward` — let the port forward take a permanent lease on a router that grants no other
    (given back when the agent stops).
  - `--no-permanent-forward`
- `mcgyvr direct FILE|DIR ...` — vet and run contracts you wrote: files, or a directory of them.
  - `--repo PATH` — the repository to work against: a local git checkout, or a URL to clone
    (https/git/file) (default: .).
  - `--config PATH` — config that binds the ladder the contracts climb and, for a prompt, the proposer
    that decomposes it (default: the usual setup).
  - `--into DIR` — clone a URL repo into DIR and keep it, instead of a temp dir.
  - `--budget TOKENS` — cap the deterministic read of the prompt at TOKENS estimated tokens before the
    proposer is asked (default: the decompose default). No meaning under `direct`, which reads no prompt:
    refused there.
  - `--output DIR` — stop once the contracts are decomposed: write each one that passed vetting to
    DIR/<id>.json and run none of them, so `mcgyvr direct DIR` can run them later. Without it a prompt's
    contracts are printed on stdout and run from a temporary directory, and `direct` runs its files where
    they are.
  - `--jobs N` — run up to N ready contracts at once, each settled as it ends and the next started as
    soon as it is ready (default: `auto` under use case mcgyvr-code, else 1, one at a time). N is capped
    at the fleet's total slots, the most dispatches its units take at once; `auto` or 0 is that cap. Two
    contracts whose scopes can write one file never run at once unless the policy says `same_file:
    parallel`, and a run's output is written whole when it ends. Runs beside each other share the fleet's
    slots, so one may wait for a rung, or pass a busy one by, as two runs typed in two terminals would.
  - `--sandbox SANDBOX` — sandbox mode of each run; default is `sandbox.mode`, then `docker`.
  - `--commit`, `--no-commit` — commit each accepted change, or not (--no-commit), whatever
    `delivery.commit` says.
  - `--branch NAME` — commit each accepted change onto branch NAME; implies --commit.
  - `--record DIR` — also journal each run under DIR, as a complete second copy.
  - `--log PATH` — write how this command ended to PATH as one JSON record (mcgyvr.delegate_log/2, schema
    in mcgyvr.delegate_log), on every exit once the arguments are read, a crash included: its `kind`, the
    exit code, the contracts and refusals, and the facts behind a failure. For a script that called
    mcgyvr; stderr is unchanged.
  - `--session ID` — the session the runs are filed under, resolved before any work (default: the session
    that typed this command, and a refusal, exit 2, when there is none); not needed with --output, which
    runs nothing.
  - `--result PATH` — where \*you\* read the result file, when the set is one contract (`direct` with one
    file); mcgyvr keeps its own copy under the journal directory either way. Refused for more than one
    contract, and for a prompt, whose contracts are not known before it is decomposed.
  - `--notes-from RESULT` — start a contract's climb with the failure notes of an earlier run of it:
    RESULT is that run's result file, and seeds the contract in the set whose id it names; give it once
    per contract. Its records are checked (same contract, the notes schema, repo-relative paths) and
    shown to the first attempt under a banner naming the earlier run, under `retry_notes: climb`; the
    result's `seeded` says what was read and handed. For a rerun on another ladder or machine. Refused
    for a prompt, whose contracts are proposed new and whose re-decompositions carry their own notes.
- `mcgyvr use NAME` — switch the use case a setup serves: mcgyvr-code, code, chat, agent.
  - `--config PATH` — setup whose use case to switch (default: the usual setup).
