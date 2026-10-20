# Changelog

Format: [Keep a Changelog](https://keepachangelog.com).

Paths in older entries are where files were when the entry was written.
`docs/` moved to `archive/docs/` (#395); most of `archive/`,
`records/plans/`, `docs/` and the write-ups under `records/` are now
archived outside this repository, under the same paths.

## [Unreleased]

### Added

- `mcgyvr emit` on a locked fleet emits a llama.cpp unit split across rigs:
  its stated head on the head's rig, and on each other rig an rpc-server
  worker per card, the same services the unlocked emit writes for that unit.
  A worker listens at its shard's `bind`, else at the private IPv4 its rig
  file records. A worker rig with no recorded address, an overlay
  (100.64.0.0/10) address when the head's rig file records none on that
  overlay, and a head whose `--rpc` names other workers are refused by name
  (#731).
- **A fleet with a sleeper samples, stamps and locks as one fleet** (#731).
  `mcgyvr setup` lays a unit with `role: sleeps-until-needed` out asleep, and
  its sample wakes it through the ladder manager's own switches (the units
  `room_for` names are put down first), probes it like an awake unit, then
  puts it down and wakes those units back. Each way is a move with its rig,
  whether it passed, its downtime and each unit's wake time. The sample is
  green only when the sleeper answered its probe and the swap passed both
  ways; otherwise the reason names the unit and the way (`swap: U on R, in:`
  / `back:`). The evidence carries the moves, the fleet lock keeps them under
  `swaps` (refusing a sleeper whose swap did not run, pass or record its
  times), and `mcgyvr fleet use` prints them. A unit laid out asleep that is
  no sleeper is still red, and a fleet with no sleeper locks as before.
- `mcgyvr.knowledge.hub` lists a use case's candidates from the Hugging Face
  Hub alone: GGUF repositories by 30-day downloads, then likes, classified as
  coding, chat or agent from their tags, pipeline, name and chat template,
  one single-file GGUF each that the Hub states a sha256 for, sized from its
  header read over HTTP Range. Every number names its source and day. The
  records are cached; when the Hub cannot be asked the cache and then the
  shipped catalog answer (#731 item 2).
- Model records carry `use_cases`, and the Hub's `downloads` and `likes`.
- The shipped catalog holds Qwen3.5-4B, Qwen3-8B, Qwen3-14B and
  Qwen3-30B-A3B (chat, agent); the three coder models are tagged coding.
- The index extracts symbols from Go (`.go`), Rust (`.rs`) and Java
  (`.java`), so `resolve`, read anchors, `decompose` and `delegate` see
  their definitions and exports instead of paths alone. Each language has
  its own export rule: Go a capitalised name, Rust exactly `pub` inside
  modules and types that are exactly `pub` too (and each name a `pub use` or
  `pub extern crate` re-exports, and every `#[macro_export]` macro), Java
  `public`, `protected` and the implicitly public members of interfaces,
  annotation types and enums, inside exported types only. Go and Rust struct
  fields and Java fields are `FIELD` symbols, never exports, as Python and
  JS/TS class fields are. Rust `#[cfg(test)]` modules and `#[test]`
  functions are skipped. A file with syntax errors yields what parsed. New
  dependencies: `tree-sitter-go`, `tree-sitter-rust`, `tree-sitter-java` (no
  musllinux aarch64 wheel for `tree-sitter-java`; there it builds from
  source) (#747).

### Changed

- `mcgyvr setup` plans the use case it asked instead of coding for every
  use case, and says whether the candidates came from the Hub, the cache or
  the shipped catalog (#731 item 2).
- `recommend.plan` places `chat` and `agent` as one unit: the biggest model
  that fits, at the most context that fits and at least 8192 per user.
  `coding` plans as before. `mcgyvr recommend --profile chatting` is now
  `chat`, and `agent` is new.
- Sizing reads the knowledge cache over the shipped catalog, so a model a
  Hub read cached can be emitted.
- The wheel carries `SETUP.md` (as `mcgyvr/data/SETUP.md`), and `mcgyvr run`
  with no setup to load names that copy, a file an installed mcgyvr has,
  instead of the checkout path `skills/mcgyvr/SETUP.md`. A checkout still
  names its own path.
- `rename_symbol` stays Python and JS/TS only: a symbol defined only in
  Go, Rust or Java is refused by language, and nothing is written (#747).
- The `tree-sitter` floor is `>=0.24`. The Go and Rust grammars, and the
  already locked `tree-sitter-javascript` 0.25, are ABI 15, which 0.23
  refuses to load (#747).
- The index cache is version 4, so a cache from an older build is rebuilt
  once instead of serving `.go`, `.rs` and `.java` files without symbols (#747).

### Removed

- `mcgyvr setup` no longer offers the `media-gen` use case: it has no sample,
  so setup could not sample it, and it is off until one is built. The
  use-case prompt is `d` coding (default), `c` chat, `a` agent; a
  `--use-case media-gen`, or a config naming `use_case: media-gen`, is refused
  in one line naming `coding`, `chat` and `agent`. The `media` task type is
  removed in this release too (#731); see the next bullet.
- **The `media` task type and the `media-gen` use case are gone.** There are
  three task types: `code`, `chat` and `agent`. Removed with them: the
  `media_valid` and `asr_wer` evidence kinds and the gate's format readers and
  whisper call behind them, the contract keys `media_kind`, `transcript` and
  `wer_threshold`, the `media_artifact` output schema, and the `media-gen`
  worker bundle. A config naming `use_case: media-gen` is refused as an
  invalid value, naming `coding`, `chat` and `agent`; a contract naming
  `task_type: media` is refused as an unknown task type. The code is archived
  outside this repository.
- **The media serving engines are gone.** `units.<unit>.engine` takes
  `llama.cpp` or `vllm`; a config naming `diffusers`, `tts` or `comfyui` is
  refused as an invalid value. Removed with them: their sizing from declared
  figures and compose services, the `vae_decode_gb` and `cpu_only` launch
  figures, the capability table's media row keys (`resolution`, `steps`,
  `vae_decode_gb`, `frames`, `temporal_compress`, `sample_rate_hz`, `rtf`,
  `cpu_only`), the `lmarena-text-to-image` and `open-asr` boards, and
  `recommend --profile media_gen`. The code is archived outside this
  repository.
- `launch:` keys `cpu_only` and `vae_decode_gb` are no longer read. Launch is
  free-form, so a stale key is ignored rather than refused.
- The root `package.json` and lockfile now pin only `prettier` (`eslint`,
  `@eslint/js`, `typescript` and `typescript-eslint` are dropped); the eslint
  and prettier configs stay for the lab bench.
- **The `safety_pass` check is gone.** It shelled out to a `safety-classifier`
  binary that no implementation of existed anywhere, so the `agent` setup
  sample, which ran it on its reply, could never pass. Removed: the
  `safety_pass` evidence kind, the sample's `safety` step (the `agent` sample
  is now green on its grounded check alone: every sentence cites the source
  and the reply states each fact), and the gate's output-check rung that only
  media and safety used (`mcgyvr.gate.output`, `Gate.run(output=...)`,
  `mcgyvr.drive.output_checks_for`). With nothing left to check a reply, the
  `checked` assurance is gone too: a `chat` or `agent` reply is always
  `unchecked`.
- `mcgyvr.cleanup` is gone: its `tidy` lives in `mcgyvr.repair` beside
  `repair` (and `mcgyvr.drive` still re-exports it under the same name).
- `mcgyvr.fleet_manager` is now `mcgyvr.wake_judge`, and its
  `FleetManagerError` is `WakeJudgeError`.
- `mcgyvr.cli.commands.lab` is now `mcgyvr.cli.commands.machine`. No
  command, flag or help text changes.
- The `mcgyvr.worker` package no longer re-exports the names of its
  modules: import them from `mcgyvr.worker.bundle`, `mcgyvr.worker.prompt`
  and `mcgyvr.worker.reply` directly.
- `mcgyvr.fleet.layout.actions` is gone; nothing but its tests called it.

### Fixed

- `mcgyvr recommend` can choose any candidate on any host. A local
  checkpoint was named only by its speculative head
  (`llama.cpp:no speculative head`) and a catalog pick only by engine and
  model, so a checkpoint on two rigs, or two checkpoints in one store,
  shared a name and only the last could be chosen. Each name now carries
  the rig, engine, weights (and quant) and head, and the placement carries
  the `host` it goes on (#731).
- A rig's docker and virtual bridge addresses (interfaces `docker*`, `br-*`,
  `virbr*`, `veth*`; with no interface name, docker's default 172.17.0.0/16)
  are set aside before its `private_ipv4` is chosen, so a rig with a LAN card
  and docker records its LAN address, and `private_ipv4_how` names the bridge
  addresses set aside. Two LAN addresses still ask for a scan over the one
  its other machines use (#731).
- The skill installer's floor (`MIN_VERSION` in `skills/mcgyvr/install.sh`)
  is 0.5.1, the latest release tag; its tests plant that floor instead of a
  hard-coded 0.5.0 (#732).
- A refusal of a key in `fleet.yaml`, `policy.yaml` or `relief.yaml` is
  about the size of the file, however deeply the key nests YAML aliases: the
  setup files are read with the same bounded strict loader as the config and
  contract, where they once quoted the whole key. The pinned rig id and the
  unsampled-fleet check read `fleet.yaml` with that loader too, so a
  duplicate key there reads as no fleet instead of last-one-wins.
- Attaching a repository whose working tree holds a path that is not valid
  UTF-8 reports that path as uncommitted instead of crashing with a
  `UnicodeDecodeError`: git's output is kept as bytes and decoded with
  surrogate escapes, as delivery already did. Every git a module runs goes
  through one runner, so a changeset's git failure now also names the
  repository it failed in.
- A hosted unit (one with an `api_key_env`) is no longer asked its `/slots`
  or `/metrics` without its key. The capacity's server count and the fleet
  probe read a unit's in-flight count through one call that dropped the
  unit's credential, so every hosted rung got an unauthenticated request to
  its provider, waiting up to the status timeout; only a keyless unit is
  polled now, as a dispatch's own reads already were.
- `mcgyvr local_pool` prints the attempt ceiling a task actually runs under:
  each rung's `attempts` capped at a contract's default `limits.attempts`
  (2), as the climb caps it. It printed the uncapped sum, so a rung with
  `attempts: 3` was counted as 3 while a contract stating no limit spends 2.

### Security

- A capacity's slot directory (`mcgyvr-capacity-<uid>` under the temporary
  directory) is used only when this user owns it outright: a directory, not a
  symlink, owned by this uid and not writable by group or other. A missing one
  is made 0700, and one of this user's own that others may write into (as an
  older mcgyvr made it under a umask of 002) is narrowed to 0700; another
  user's directory, or a symlink, is refused by name, saying to remove it.
  Each slot file is made 0600, opened with `O_NOFOLLOW`, and refused when
  another user owns it, so another local user can no longer pre-create the
  directory, hold this user's slots, or have a planted symlink followed.

## [0.5.1] - 2026-10-17

### Fixed

- `mcgyvr setup` asks which rigs serve the setup as `local`, `remote` or
  `both` (Enter is `local`), with a follow-up for `remote`/`both` naming the
  ssh host(s); a stray answer is refused as a rig choice instead of being
  swallowed as a hostname (#726).
- The Jev and mcorch opt-in prompts read `[y/n]` instead of `[y/N]` (#726).
- The use-case prompt is letter keys — `d` coding (default), `c` chat, `a`
  agent, `m` media-gen — with no `What is this setup for:` text (#726).
- `mcgyvr setup` offers to append `~/.local/bin` to the login shell PATH
  after an explicit yes (#726).

## [0.5.0] - 2026-10-16

### Changed (breaking)

- **There are exactly four task types: `code`, `chat`, `agent` and `media`**
  (#686, #690).
  - The former coding types (`function_implementation`, `bug_fix`,
    `docstring`, `type_annotation`, `test_scaffold`) are now `code`. Its
    evidence is derived from the contract's own fields (`demonstration`,
    `acceptance`, `no_semantic_change`, `type_check`).
  - The deterministic operations are now
    `task_type: code` + `operation: format|import_sort|lint_fix|rename_symbol`.
    They run with no model.
  - A former name is refused with a pointer to its new spelling.
  - The `excluded` block and `mcgyvr catalog --excluded` are gone.
- **Every verb names the repository with `--repo PATH` only** (#694, F14):
  `sandbox`, `index`, `resolve`, `read`, `delegate`, `attach` and `run`. A
  repository given by position is refused with a message that says to use
  `--repo`.
- **`chat` and `agent` runs are sessions** (#693, F7).
  - They need no `target` or `scope`, and their reply defaults to `prose`.
  - Each run is recorded under `<journal.dir>/sessions/`: question, answer,
    unit, timings and outcome.
  - The result file gains `session_record`.
  - New verb: `mcgyvr sessions [ID]` lists sessions, or shows one.
- **`acceptance` and `demonstration` commands run without a shell, and
  `mcgyvr contract` now enforces it** (#692, F12).
  - A `VAR=x` prefix, `&&`, `||`, pipes, redirects, `;`, `&` and unclosed
    quotes are refused when the contract is loaded. The message suggests
    `env VAR=x cmd` or a committed script.
  - The documentation says "no shell".

- **No run takes a rig another live run holds.** Owner's ruling, 2026-10-15:
  "no one can take from no one".
  - A `serve up`, `down`, `sleep`, `wake` or `fetch` that finds the rig's
    lease (`~/.mcgyvr/lease` on the rig) held by a run that is still live is
    refused at gate 2 (exit 2), whichever door wrote the lease, before
    anything else reaches the rig: nothing is read, listed, stopped or
    written. The refusal is one line naming the holder's run, its
    `user@host`, pid and start, and says to wait for that run or end it.
  - A live run no longer displaces another: no run tears down another run's containers,
    `RUN_DISPLACED` is no longer exported, and the shims no longer re-read
    the lease before a `docker run` or an ssh that launches one.
  - A stale lease is still reclaimed, named on stderr, with nothing of its
    run torn down. Stale means: the lease carries an id, names THIS machine,
    and its pid is gone — no process has it, or the process that has it now
    started at another time than the lease records. A lease records that
    start as `pid_start` (the kernel's `/proc/<pid>/stat` start time); a
    lease without one is judged by its pid alone. A lease from another
    machine, or one with no id, is never stale: wait for it, or remove it by
    hand.
  - An empty lease file still holds nothing.

- **A rig that moved under a run is filed in the run's end record, not beside
  its artifacts.** Gate 7 still holds the rig after the step to gate 2's
  reading before it. Each key that moved is filed in `<RUN_ID>.end.json` as
  `rig_moved`, `{"<key>": {"before": ..., "after": ...}}`, absent when nothing
  moved, and the run's output says it in one line
  (`gate 7: rig changed during the run: pl1_uw 95000000 -> 4095000000`). No
  `<name>.RIGMOVED` sidecar is written, and the end record's `moved` list is
  gone. A moved rig still makes the run not green: gate 7 exits 1, and the
  door with it.

- **`mcgyvr fleet lock`, `fleet promote` and `fleet tag` are gone.**
  `mcgyvr setup` locks and promotes the fleet it sampled through the library
  (`mcgyvr.fleet.lock.write_from_stamp`, `write_unsampled`, `write`, and
  `mcgyvr.fleet.promote.promote`), which stays; `mcgyvr fleet use` still
  names a promoted folder live. `fleet tag`, the one-off rename of folders
  promoted before 2026-09-16, goes with `promote.tag`; such a folder still
  reads and is still named by `fleet use`. `$MCGYVR_RUN_ROOT` is gone with
  the verbs' default root. A setup that stamped a fleet the user did not lock
  keeps the stamp and says a later `mcgyvr setup` locks again.

- **The door runs its own gates and nothing else: `step`, campaigns and gate
  lists are the lab's.**
  - `python -m mcgyvr.serving.run` has three verbs, `serve`, `read` and
    `link`. The `step` verb is gone, with `--campaign`, `--out-root`,
    `--model`/`--parallel`/`--ctx-per-slot`/`--ubatch`, and the sibling
    declaration `$MCGYVR_DOOR_SIBLINGS`.
  - `--gates FILE` and `$MCGYVR_DOOR_GATES` are gone: no verb takes a
    caller's gate list, and no door product code opens carries one.
  - A run's RUN_ID is `<date>-<host>-<step>[-<suffix>]` (a serve run's was
    `<date>-live-<host>-<step>`), filed in the door's log as before; its
    header names no campaign, round or product digest; the rig lease names no
    campaign; gate 1 exports no `RUN_ROUND` or `RUN_PRODUCT_SHA256`; gate 5
    reads no `RUN_APPENDS`.
  - `$MCGYVR_RUN_ROOT` no longer moves where the door's gates run.
  - The door has no hook for code outside it: nothing names a driver, a
    check or a step of a caller's, and no library function runs the serve
    sequence for one. The door runs its own gates and its own serve steps.
  - A serve step declares its records as `# RUN_REWRITES:` JSON files, each
    carrying its `run_id`; the write-once `# RUN_ARTIFACTS:` directive, the
    TSV `### START run_id=` stamp and gate 7's TSV `### RIGMOVED` line are
    gone (a moved rig is filed in the run's end record), and gates 7 and 8
    read no `RUN_APPENDS`; `RUN_APPEND_STATE` is no longer exported.

- **There is one kind of run: `profile: live|dev` is gone.**
  - `fleet.yaml` no longer holds `profile`, and a file that still says it is
    refused as any unknown key is; nothing is migrated. `mcgyvr setup` and a
    promotion no longer write it, and the rig lease names no profile.
  - A run is held to the live fleet's lock whenever a fleet is live
    (`mcgyvr.fleet.roots.runs_live`): `mcgyvr run`, `serve wake`, `manage`,
    `mcorch serve` are admitted by a read of its rigs, the waker wakes only
    along the lock, and gate 1 admits a `serve up` only for units the lock
    names, whatever setup the command was given. The exception is a setup in
    the data folder: the staging folder `mcgyvr setup` starts and samples
    before anything of it is locked, which runs everything. With no fleet
    live, a setup named outside the config folder is held to no lock; a run
    under no config at all, or one in the config folder, still is.
  - An alert from a read or a probe warns and stops nothing: no run raises on
    one. `mcgyvr fleet alerts` reads the live fleet's lock and takes no
    `--config`.
  - The door's read gate is `read-01-config.py`, and `RUN_PROFILE` is no
    longer exported; `RUN_CONFIG` is.

- **`mcgyvr setup` stages in the data folder and writes nothing where it
  runs.**
  - Each run stages its `fleet.yaml` and `policy.yaml` in a folder of its own,
    `$MCGYVR_DATA/setup/<run>/` (default `~/.local/state/mcgyvr/setup/<run>/`),
    and emits, starts and samples from there. The folder is kept as the record
    of that run, as a stamp is. A `PATH` argument (or `--config PATH`) or
    `$MCGYVR_CONFIG` stages there instead; the working directory is never
    written.
  - The interactive setup writes the staged setup once, from the plan, and
    emits its launch specs once. The second write over the running servers and
    the re-emit are gone.

- **`mcgyvr setup` samples the fleet it started, stamps it, and locks it on a
  yes.**
  - Once the containers are up, the staged setup is laid out as the user's own
    fleet `own`: each rig pinned to the rig id its read named, each unit given
    the id the lock pins, the card room it was sized at, its request timeout,
    and the longest reply its measured warm decode finishes in that time.
  - It is sampled through the door (`read --fleet own` of every rig,
    `read --fleet own --probe U --load WxN` of every awake unit, and a last
    read), with the use case's sample task between them
    (`mcgyvr.fleet.sampler`): `coding` runs a bundled one-function bug fix
    through `mcgyvr run` and passes when the deterministic gate does on any
    rung; `agent` runs a bundled grounded contract, its reply checked grounded
    and by the safety check; `chat` asks one completion of each unit and reads
    back the window and slots it serves; an opted-in Jev unit gives one typed
    choice.
  - A green sample is stamped under the setup run's name, and behind "Lock the
    fleet and name it live? [y/N]" it is locked from the stamp, promoted and
    named live. A red sample is never locked: the stamp's reasons are printed.
  - A live `own` folder locked from a stamp is the user's own, which a later
    setup may name live in its place; a second setup of the same day is
    promoted to the next folder of that day (`own@<date>-2`).

- **A fleet setup could not sample is locked on no evidence only once you
  say so.**
  - A fleet with every unit hosted, one whose containers were not started, or
    one whose use case has no sample (`media-gen`), is not sampled. Setup says
    why, says what a lock on no evidence means, and asks "Lock it approved on
    no evidence? [y/N]".
  - `mcgyvr setup` with flags starts no container, so nothing it binds is
    sampled: the new `--accept-unsampled` is the acknowledgment. Without it
    nothing is locked or made live, and the limits say how to lock it. Setup
    no longer approves its own fleet unasked.

- **The interactive `mcgyvr setup` asks the use case, Jev and mcorch before
  it plans.** It planned `coding` only.
  - After the rigs it asks "What is this setup for: coding, chat, agent or
    media-gen? [coding]", then "Dedicate a unit to Jev, which answers typed
    decisions? [y/N]", and, for `coding` with Jev on, "Run mcorch, the local
    orchestrator, on a unit? [y/N]". These are the interactive `--use-case`,
    `--jev` and `--mcorch`. Enter is coding, no Jev and no mcorch.
  - With several units it asks which one is Jev and which runs mcorch;
    Enter is the first. mcorch runs at the window each slot is launched at.
  - The answer is planned, staged and sampled. Jev's and mcorch's units are
    laid out awake and probed, and the sample asks the Jev unit its typed
    choice. `media-gen` has no sample yet: setup says so, starts nothing,
    and asks before it locks the fleet on no evidence.

- **The working directory is no longer a config.** A command that reads a
  setup reads `$MCGYVR_CONFIG` (or its `--config`), else the live fleet that
  `$MCGYVR_HOME/live.json` names. A `fleet.yaml` where the command runs is not
  read, and with nothing named and no fleet live there is no config: the
  refusal says to run `mcgyvr setup` or set `$MCGYVR_CONFIG`.

- **Auto-wake is on for the fleet setup makes live.** Setup writes
  `serving.enable_sleep_wake: true` and `serving.compose_dir` naming the staged
  folder, where its launch specs are emitted and kept, so a request refused by
  a unit that is down is a door `serve up` of that unit's launch spec and the
  request again. Live wakes a rig only when the live fleet's lock names it,
  whether the lock was written from a stamp or on no evidence.
  - The door's gate 1 now admits that `serve up` for a fleet locked on no
    evidence too. It admits the containers the lock's layout places on that
    rig, while the live `fleet.yaml` still matches the lock's pin, and
    nothing else (`mcgyvr.fleet.admit.unsampled_containers`, the rule
    `host_is_locked` reads). Before, the waker passed and the door refused.
    A lock written from a stamp is still read from its combination records
    alone.
  - Such a lock now pins each laid-out unit's container,
    `"containers": {"<rig>": {"<unit>": "<container>"}}`, as a stamp's
    combination records name them. A container edited into the live
    `fleet.yaml` afterwards is refused by gate 1 and unlocks its rig for the
    waker. A lock on no evidence written before this has no `containers`, so
    its rigs' containers are refused: lock it again with `mcgyvr setup`.

- **A fleet's lock sits in `lock/`.** The lock tree inside a live fleet
  folder, a stamp folder and the dev root is `lock/` (`lock/<fleet>.json`,
  `lock/rigs/<rig->/<combination>.json`), no longer `records/fleet/`. A
  folder locked before this release is not read: lock and promote it again.

- **One reader reads a machine, and one id names it.**
  - `src/mcgyvr/serving/rigscan.py` is the only code that runs a hardware
    tool. The door ships it to a rig as one read-only line
    (`echo <base64> | base64 -d | python3 -I -B -`), and the product imports
    it locally.
  - Its one JSON document carries the short reading (machine id, host, every
    card on any vendor, RAM), the capacity scan, and the snapshot the door's
    gates hold a run to. A field that cannot be read is named in `unread`
    with the reason. It is never filled in.
  - The door's own `rig-snapshot.sh` and `machine-read.sh` are gone, and so is
    the text parser `mcgyvr.fleet.machine`. What holds a rig at run time (its
    containers and card holders) is still read by `rig-units.sh`.
  - A machine has one id, `rig-` over its machine id and its cards' names and
    sizes (`mcgyvr.fleet.ids.rig_id`). The lock pins it, live admission
    compares it, and a rig's hub hears it as the hello's `machine_id`. The
    `mch-` prefix is retired.
  - The kernel, the driver, docker and the CPU's clock are no longer in the
    id: a driver upgrade no longer mints a new rig. Ids and locks written
    before this release do not match: read each rig again and lock again.
  - `ssh_read_only` admits the shipped reader's exact bytes and no snapshot
    line.

- **One record per machine: its rig file.**
  - The scans folder (`~/.local/state/mcgyvr/scans`, `$MCGYVR_SCANS`) is gone.
    `mcgyvr scan` records this machine as its rig file,
    `$MCGYVR_RIGS/localhost.json`. `emit` and `mcgyvr manage` size from the
    rig files.
  - A rig file now holds the one reader's reading whole. Rig files written
    before this release are not read: run `mcgyvr scan --rig RIG` again.
  - `mcgyvr scan` says what moved since the last record. A gate says the same
    thing, and it now also covers the kernel, the driver, the CPU's clock,
    power limits and the card's slot.
  - Exit 4 is kept for the hardware changing: a card, RAM, cores or bandwidth.
  - `mcgyvr scan`, `mcgyvr detect` and the card figures a serve step files
    are read by the one reader. Nothing else runs `nvidia-smi` or reads
    `/proc/meminfo`.

### Fixed

- The shipped `code` example passes preflight against the stub it describes:
  its fail-first test is a `demonstration`. A command refused as
  `acceptance-baseline-failing` is now told it belongs in `demonstration`
  (#690, F5).
- Each task type's result says how it was judged, using the label for its own
  path (#690, #693, F9):
  - `code` written by a model: `verified` or `unverified`;
  - `code` with an `operation`: `deterministic`;
  - `chat`: `unchecked`;
  - `agent` and `media`: `checked`.

  `mcgyvr contract` prints the same `judged:` line. The false "this install
  has none" is gone.
- `stop_conditions` are required only where a BLOCKED reply can be heard, a
  `whole_file` reply (#692, F10).
- The Python gate no longer charges a change with lint the base file already
  had on a line the change only rewrote, as `ruff format` does (#695, F2).
- The docker sandbox image of a pyproject with no lockfile installs its
  `[dependency-groups].dev` (`pip install . --group dev`) (#695, F3).
- Whatever an acceptance or demonstration command leaves behind, such as
  `__pycache__`, `.pytest_cache` or a tool cache's nested `.git`, is cleaned up
  and named in a note. It is not refused at preflight or charged to the change
  at the gate. A command that rewrites a file of the change itself is still
  rejected (#695, F4).
- The docker sandbox points `XDG_CACHE_HOME`, `XDG_CONFIG_HOME` and
  `XDG_DATA_HOME` at `/tmp`, so `uv run` no longer writes its cache into the
  workspace (#686, F13).
- A run on a tree with uncommitted or untracked files says that the sandbox is
  built from HEAD, and names what it leaves out. The note goes to stderr and
  to the result file's new `notes`. `run`, `sandbox` and `delegate` all print
  it (#694, F11).
- The README clones the skill at the tag of the installed CLI.
  `skills/mcgyvr/install.sh` passes the skill's example contracts to the CLI
  on `PATH` and warns when it refuses them. `MIN_VERSION` is 0.5.0 (#691, F1).

- **Interactive `mcgyvr setup` writes every rig's file**, a remote rig's too.
  Before, `serve up` on a remote rig was refused unless `mcgyvr scan --rig`
  had run first. Each rig is now read once per setup: the fleet is approved
  from the same reading.

### Changed

- **The door's gate 1 is `01-config.py`** (was `01-round.py`), named for
  what it does: it names the config the run is under and admits a live
  `serve up` only for units the lock names. A refusal there now reads
  `run.py: REFUSED at 01-config.py — ...`; the gate itself is unchanged.
- **The user's own fleet is locked like any other, then promoted and named
  live.** `mcgyvr.fleet.lock.write_unsampled` locks a fleet no sample could
  run on, approved by `mcgyvr setup` on no evidence. It refuses unless the
  caller says the user acknowledged that (`acknowledged=True`; `mcgyvr setup`
  passes it for now, and will ask). `mcgyvr setup` then runs
  `promote.promote` and `promote.use`, as for every live fleet.
  `promote.approve_own` and `promote.approve_own_rigs` are gone, and
  `is_own` moved to `mcgyvr.fleet.lock`.
  - Same guarantees as before: no unit on a rig that was not read, no hosted
    unit at a machine of yours, an mcorch policy's units awake, a layout that
    reads back as pinned. New: a setup that names a unit on a rig that was not
    read is refused even when other rigs were read.
  - `promote` dates such a lock by its approval and puts a later approval of
    the same day at `<date>-2`, `-3`. It carries the hosted units with it.
  - Fixed: a live wake on a rig of your own fleet was refused, as its lock has
    no combination record. `admit.host_is_locked` now answers for a lock
    approved on no evidence from its layout, while that layout matches the
    pin.

### Removed

- **The capability table carries a model's facts and no measurement**
  (schema version 4). Its card classes, speed readings (`throughput_tok_s`,
  `seconds_per_image`, `seconds_per_clip`), harness caveats and concurrency
  findings are gone, and a table that carries one is refused by its name.
  `mcgyvr capabilities` lists each model's memory figure, without the card
  classes and caveats it printed before. A version 3 table is refused.
- **The `measure` dependency group.** Only the lab's token-estimator
  measurement used it, and the lab carries the group itself.
- **The model knowledge's online half**, `mcgyvr.knowledge.online` and
  `mcgyvr.knowledge.boards`: no command ran it. The cache, the shipped catalog
  and the geometry rows are read as before. The Hub's address `serve fetch`
  downloads from is `mcgyvr.serving.fetchlist.HUB`.

### Added

- `mcgyvr.orchestrator.baseline` detects the project's test runner from what
  the project declares, observes the baseline once, and fills an empty
  `demonstration` or `acceptance` on a `code` proposal from that observation
  (#686).

## [0.4.16] - 2026-10-11

### Fixed

- `mcgyvr setup` no longer offers to re-download a model that is already on the
  rig: the on-disk reuse match accepts an untagged canonical GGUF (its name
  carries no quant) on the strength of name + size, and enforces the quant only
  when the file name tags one.

## [0.4.15] - 2026-10-11

### Fixed

- `mcgyvr setup` now locks a fleet that can actually run: `mcgyvr emit` stamps
  the resolved launch (`image`, `container`, `engine`, `launch.argv`/`env`/
  `volumes`, `hf_cache` for vLLM) back into `fleet.yaml`, byte-identical to the
  compose file it writes, and the wizard re-emits after its final re-init so
  the launch survives into the lock. A locked fleet is emittable and live
  admission admits its rigs.

## [0.4.14] - 2026-10-10

### Added

- `mcgyvr setup` can now make a fleet whose units sit on **remote rigs** live.
  It reads each rig (the local machine locally, a remote one over a new
  read-only ssh line that ships the door's `rig-snapshot.sh`), then approves
  the fleet with all rigs laid out and pinned by their rig ids.

### Fixed

- `is_own` now recognises a fleet approved by the pre-rename `mcgyvr init`
  approver, so an own fleet approved before the rename is still re-approvable.

## [0.4.13] - 2026-10-10

### Fixed

- Two rigs asked to serve the same model collapse to one unit (one unit per
  model); the rig left out gets no launch spec. The setup wizard's
  `serve up` treated that as an emit failure and aborted; it now skips the
  redundant rig with a note, so a multi-rig setup with one model completes.

## [0.4.12] - 2026-10-10

### Fixed

- The fetch saved each downloaded GGUF under its Hub base name
  (`qwen2.5-coder-7b-instruct-q4_k_m.gguf`), but `emit` serves it from
  the model id flattened (`Qwen_Qwen2.5-Coder-7B-Instruct.gguf`). The
  container then crashed with `failed to open GGUF file`. The fetch list
  now carries an explicit local `name`, and `from_records` names it
  canonically; the setup wizard's on-disk reuse match finds it too.

## [0.4.11] - 2026-10-10

### Fixed

- The setup wizard's `serve up` now names the bootstrap config *directory*
  in `MCGYVR_CONFIG`, not its `fleet.yaml`. The loader reads `fleet.yaml`
  and `policy.yaml` (the ladder) from the directory; naming the file made it
  read `fleet.yaml` alone, which has no ladder, and gate 1 refused.

## [0.4.10] - 2026-10-10

### Fixed

- The interactive `mcgyvr setup` bootstrap phase now runs under
  `profile: dev` instead of `live`, and starts the containers with the door
  pointed at the bootstrap config. A live `serve up` is admitted only for
  units the fleet lock names, which cannot exist before the servers run; the
  bootstrap is a dev setup, and the final lock promotes it to live.

## [0.4.9] - 2026-10-10

### Fixed

- The interactive `mcgyvr setup` wizard now declares the serving context
  window it priced each placement at, passing `--ctx-per-slot` to `emit`.
  The recommendation carried the context on the placement; the wizard sizes
  at the smallest placed window, so `emit` no longer refuses a windowless
  run.

## [0.4.8] - 2026-10-10

### Fixed

- A catalog pick is again priced at the base model's ``config.json``
  context (its native window), not the GGUF header's ``n_ctx_train``.
  0.4.7 priced the shipped Qwen GGUFs at their repacked 128K window, which
  made the 7B (weights plus a 128K KV cache) no longer fit a 12 GB card, so
  ``mcgyvr recommend`` refused it. The native 32K window is the window the
  model fits and is priced at; the serve pins its own window.

## [0.4.7] - 2026-10-10

### Fixed

- A catalog pick is now priced at the GGUF header's declared context
  (`n_ctx_train`), not the base model's `config.json`. The shipped
  Qwen 7B/14B GGUFs are repacked to 128K, so the old figure under-counted
  the KV cache fourfold in `mcgyvr recommend`'s fit check.

### Added

- The capability table's rows may name the catalog model whose weights they
  match (a `model_id`), linking the two tables.
- `mcgyvr emit` sizes any catalog model from the file's bytes and its own
  context and KV figures, so a `recommend` pick is servable even when the
  capability table has no row for it; a mapped measured row and an operator's
  `launch` declaration still win in that order.

## [0.4.6] - 2026-10-10

### Fixed

- The door's own serve steps (`serve fetch`, `serve up`, `serve down`, `serve
  sleep`, `serve wake`) now run on the door's interpreter, not on whatever
  ``python3`` a cleared PATH finds. Under `uv tool` / `pipx` the package lives
  in an isolated venv the system interpreter cannot see, so `serve fetch` and
  `serve up` failed with `ModuleNotFoundError: No module named 'mcgyvr'`.

## [0.4.5] - 2026-10-10

### Fixed

- The interactive `mcgyvr setup` wizard's download and start steps now run the
  door (`python -m mcgyvr.serving.run serve fetch|up`) as a subprocess through
  ``mcgyvr.wake.spawn_door`` instead of calling the door's ``main`` in-process,
  which the door's gate 1 refused because the process was not started by the
  door.

## [0.4.4] - 2026-10-10

### Fixed

- The interactive `mcgyvr setup` wizard's download step no longer reads a
  remote rig's weights path as if it were local (a `PermissionError` on the
  machine running setup), and matches the recommended repo id by its model
  basename against the rig's own on-disk inventory, so a model already on the
  rig is offered for reuse instead of fetched again.

## [0.4.3] - 2026-10-10

### Changed

- `mcgyvr pool` is renamed `mcgyvr local_pool` (module `mcgyvr.pool` →
  `mcgyvr.local_pool`); the hub's pooled-inference rig side
  (`mcgyvr.rig.pooled`) is a different "pool" and stays.
- `mcgyvr setup` is the single setup entry point and absorbs the old
  `mcgyvr init` options — `--host`, `--api`, `--use-case`, `--deployment`,
  `--priority` (plus repeatable `--api` for two hosted tiers) — and defaults
  to `hybrid` with a hosted orchestrator. mcorch is never auto-selected.
- `mcgyvr setup` writes hosted API tiers in declaration order, below any
  detected local units. Declare cheapest first — `deepseek-flash` then
  `deepseek-v4-pro` — and the coding ladder climbs local rig(s) →
  `deepseek-flash` → `deepseek-v4-pro`.
- `mcgyvr setup` is interactive when run on a terminal with no flags: it
  prompts for the rigs, scans them, shows a `mcgyvr recommend` placement,
  asks before reusing or downloading weights, downloads chosen models, emits
  the launch specs, asks before starting the containers and before locking
  the fleet, binds the now-running servers into the config, and locks the
  fleet. Any flag (or non-terminal stdin) keeps the flag-driven
  config-writing path with no prompts.
- `mcgyvr scan` (local and `--rig`) now reports disk total and device where
  available, CPU cores/threads, memory bandwidth on the rig, and a
  models-on-disk inventory of `*.gguf` and `*.safetensors` under the weights
  dir and any `--model-store` dirs.
- Before downloading a model, the download path checks for an existing model
  with the same id + quant + size and asks whether to reuse it, defaulting to
  reuse.

### Removed

- `mcgyvr init` (use `mcgyvr setup`).

## [0.4.2] - 2026-10-10

### Changed

- The `relief.busy_answers` doc no longer claims a one-release fallback (docs
  only): an unset rung names no busy answers, and a sync writes them.

## [0.4.1] - 2026-10-10

### Removed

- The one-release relief fallback. Until now a `relief.yaml` rung that named
  no `busy_answers` was read as full on a fixed set the runner carried for one
  release (`RELIEF_UNAVAILABLE`). Past 0.4.0 that fallback is deleted: a rung
  that names no `busy_answers` names no busy answers, and a sync writes every
  rung's `busy_answers`, so a current file never relies on the old set.

## [0.4.0] - 2026-10-10

### Added

- `mcgyvr init` approves a model served on the machine it runs on, not just
  hosted units (borders plan 2c-2). When it binds a backend detected on this
  machine, it reads that machine with the door's own readers, run locally and
  not over ssh, writes its rig file (`$MCGYVR_RIGS/localhost.json`), and
  approves the fleet with the rig `localhost` laid out and pinned by the rig
  id the read named. A unit on any other machine is still refused: a remote
  machine is read over ssh, which `init` does not take.
- `MCGYVR_RIGS` names the folder that holds the door's rig files (borders plan
  2b-P1b). Unset or empty, a rig file stays at `$MCGYVR_HOME/rigs/<rig>.json`
  exactly as before. `~` is expanded; a relative path is refused, naming the
  variable. Every reader and writer of a rig file (`mcgyvr scan --rig`, the
  door's gate 2 and read-02, `fleet sample`) goes through
  `mcgyvr.serving.rigfile.path`, so a value that names no usable folder is the
  same refusal a bad rig name is.
- `MCGYVR_RUN_TAGS` tags a run's journal rows (borders plan 2a). Set it to a
  JSON object of text, number or true/false values (at most 4096 bytes) and
  every row the run writes carries it under `run_tags`, text scrubbed. Set to
  anything else, `mcgyvr run` refuses before it starts. It replaces the
  `round`/`product_sha256` stamp telemetry read from a development checkout
  (see Removed).
- The door has a `step` verb, an advanced command (owner, 2026-10-08, design
  2b): `python -m mcgyvr.serving.run step --host RIG --campaign NAME --step
  PATH [-- ARGS]` runs one script of your own on a rig under the door's fixed
  gates: the profile, the rig's lease and reading, its docker daemon, the
  envelope, then your step, then teardown and parse whatever it did, and the
  lease released. It is filed in the door's log, or under `--out-root DIR` as
  `DIR/<date>-<campaign>/`. A caller's gate list (`--gates`) runs inside that
  order as on `serve`. `link` takes `--gates` too, `before` gates only.
  `MCGYVR_DOOR_GATES=<folder>` gives a `serve`, `read`, `link` or `step` run
  the list `<folder>/<verb>.json`, so the doors mcgyvr opens itself (waking a
  ladder, the fleet's read and probe) carry those gates too; with `--gates`
  as well, both lists run, the folder's first in each phase, with a warning.
  `step` has no defaults for `--model`, `--parallel`, `--ctx-per-slot` or
  `--ubatch`: each is exported to the step only when given.
  A caller's gate can add a refusal and never take a door gate's away. The
  lab's campaign run and `--mode` are unchanged.
- `mcgyvr init` approves your own fleet when every unit it bound is hosted,
  so a fresh install runs a contract with nothing from a development
  repository. It writes `$MCGYVR_HOME/fleets/own@<today>/` (the setup it
  wrote, a fleet `own` that lays out no rig, and that fleet's lock, which
  says `mcgyvr init` approved it) and names it live as `mcgyvr fleet use`
  does; live admission holds it to its lock and reads no rig, as it has none.
  A re-run of `init` approves a new folder (`own@<today>-2` on the same day,
  a tag live names now accept) and names it live; the old one is kept. Not
  approved, and `init` says why: a unit on a rig; a "hosted" unit at a
  machine of yours (an address that is not public: loopback, private,
  link-local, shared, in any spelling a resolver reads, octal, hexadecimal,
  short, IPv4-mapped or NAT64 included; or `localhost`, a name with no dot,
  `.local`, `.home.arpa`, `.internal`; read as written, nothing is looked
  up); an mcorch setup, whose units a fleet with no rig cannot hold awake. A
  fleet live that is not `init`'s own is never replaced, and an `init` that
  wrote nothing approves nothing.
- `mcgyvr scan --rig RIG` records the rig's private IPv4 address in its rig
  file (`private_ipv4`, with `private_ipv4_how`), as the rig reports it (owner,
  Round 9): the address its ssh session arrived at (`SSH_CONNECTION`) when an
  RPC worker may listen there, else the one private address on its interfaces
  (`ip -4 -o addr show`); with several, none is guessed and the scan says
  which there are. Nothing is resolved.
- A sample stamps a fleet (`mcgyvr.fleet.sample`, `mcgyvr.fleet.stamp`;
  owner, 2026-10-07: confirm = run the sample, sample green = fleet
  stamped). A staged fleet's sample is judged from the door's own reads of it
  (`read --fleet F --probe U --load WxN`): every awake unit probed (warm
  decode and prefill read, no restart, its card inside its `room_mib`), and
  the use case's task passed (coding: the gate on any rung; chat: each unit
  answers at its planned window and slots; agent: grounded and safety; an
  opted-in Jev: one typed choice). Those reads, with your rig file, become
  the dev-run evidence `fleet lock` reads. A green sample is locked under
  `~/.local/state/mcgyvr/stamps/<fleet>/<run>/` (setup, `evidence.json`
  and the lock; no lab checkout needed), promoted to
  `$MCGYVR_HOME/fleets/<fleet>@<date>/` and named live. A red sample, or a
  lock or promote refusal, stamps nothing and lists why. Not yet sampled: a
  fleet with a unit that sleeps until needed ("the swap isn't built yet"),
  and media-gen. `mcgyvr setup` will run the sample; nothing calls it yet.
- The ladder manager's swap works for llama.cpp. A unit can say
  `units.<u>.role: sleeps-until-needed` (default `always-on`, which changes
  nothing): `emit` writes it into its card's one launch spec beside the
  always-on units, under the compose profile `asleep`, so a whole
  `serve up` leaves it down and the awake set still fits the card. When the
  dearest awake rung is full the manager stops the units whose room it needs
  (`serve down --unit`), starts it (`serve up --unit`), and starts them again
  when it sleeps. A card of co-resident llama.cpp units now switches one unit
  at a time, as a vLLM card does. A task that climbs to a sleeping swap
  partner does not start it; the manager does, after making room. The door
  reads the profile: a whole `serve up` waits for and judges the awake units
  only, and a whole `serve down` also removes a swap partner left running.
  llama.cpp units only; vLLM keeps its level-2 sleep.
- Model geometry (`mcgyvr.knowledge.geometry`, `data/model-geometry.json`):
  each model file's header row, the one thing the serving sizer reads, kept
  per file at a revision with one source and one date for the whole row. The
  shipped catalog's three files ship with theirs (read over HTTP `Range` on
  2026-10-07); an online refresh (`mcgyvr.knowledge.online.refresh`) files
  the row of any other file it reads under `$MCGYVR_HOME/knowledge/geometry/`,
  so an MoE can be sized offline next time. A cache file that does not read is skipped and named.
- Model knowledge, offline half (`mcgyvr.knowledge`): a record per model and
  quantisation in which every number says its kind (fact, estimate or
  reading), its source and the day it was read, and the closed lists of
  sources and boards those are said from. It is read from the user's cache,
  `$MCGYVR_HOME/knowledge/`, first, then from the shipped catalog.
- Model knowledge, online half (`mcgyvr.knowledge.online`,
  `mcgyvr.knowledge.boards`). The Hub lookup reads a repository's files,
  sizes and sha256 from the Hugging Face Hub API and each GGUF file's header
  over HTTP `Range` (never a weight), and answers a record per single-file
  quantisation, with the header row that says its experts per block (MoE)
  and its MTP head. The boards of each use case are read into scores: LMArena
  text (chat), BFCL (agent), SWE-bench Verified bash-only rows and EvalPlus
  below them (coding), LMArena text-to-image and Open ASR (media-gen); TTS
  has none. The refresh (`mcgyvr.knowledge.online.refresh`) re-reads the
  known models online and files what it read in the cache; asked offline (or
  under `HF_HUB_OFFLINE=1`) it asks nothing. No command runs it yet. Requests
  time out after 20 seconds, and a network that does not answer stops every
  lookup at once.
- The serving door has a user mode (`python -m mcgyvr.serving.run ...
  --mode user|lab`), approved by the owner 2026-10-07. A run from an install
  is no longer refused for want of the lab's files: the round, the lab's
  `hosts.json` and its declared docker version are not asked for, and the rig
  is held to your rig file `$MCGYVR_HOME/rigs/<rig>.json` instead. Each run
  scans the rig again, says what moved, and refuses only when the fleet no
  longer fits (a card its compose file reserves is gone or holds less than
  the file records). The lease, the daemon check (docker answers and is the
  machine read), the envelope, the step, the stray-container check and the
  live fleet's lock all stay. A user's serve run is filed under
  `~/.local/state/mcgyvr/door/<date>/<run_id>/`: the command, the rig read
  before and after, the compose text, the units up and the step's exit. A
  container or a card holder mcgyvr did not start is reported and left as
  it is. With no `--mode`, a run root that is a lab checkout (it holds the
  round's folder) is refused and asked which mode; any other runs as the
  user's. A campaign run is a lab run only. Lab mode is unchanged.
- `mcgyvr scan --rig RIG` scans RIG over your own ssh (read-only, BatchMode)
  and saves it as the door's rig file: hostname, cards and their memory, RAM,
  free disk and docker version. A second scan says what moved. The shipped
  rig scanner now reads the rig's docker version (`Scan.docker`).
- The serving door fetches weights: `python -m mcgyvr.serving.run serve
  fetch --host RIG --weights FILE` downloads the files a fetch list names
  (`{"files": [{repo, revision, file, sha256, bytes}]}`, each pinned to a
  commit and its sha256 as the model knowledge records it;
  `mcgyvr.serving.fetchlist.from_records` writes it) on the rig itself, into
  its weights folder (`$MCGYVR_WEIGHTS`, else `~/.cache/mcgyvr/weights`). It
  says the total first and has no size cap. A download resumes from its
  `.part`; a file is renamed into place only when its sha256 matches, and one
  that does not match is deleted. A file already there that matches is
  skipped; a different file of that name is left as it is. A gated model's
  token is read from the variable `--hf-token-env` names (default
  `HF_TOKEN`), goes to the Hub inside the ssh connection only (not to the
  address a download is redirected to), and is never written down. The Hub
  is `HF_ENDPOINT` when set (https, or http on loopback). The run takes the
  same gates as every serve run and is filed the same way.
- `serve up --unit C` and `serve down --unit C` start or stop one container
  of a compose file alone (`up` with `--no-deps`, `down` as `rm --stop`),
  leaving the file's other units as they are; gate 7 judges the named units
  only. They were refused before; this is the start and stop a llama.cpp
  swap partner needs.
- Three guards hold what is already true of the product's borders, so no
  change can go backwards. The offline core (`src/mcgyvr/` but `cli.py` and
  `rig/`, its scripts included) imports nothing of the hub client
  (`mcgyvr.rig`) or of `mcgyvr.cli`, by an import or by a module name handed
  to `importlib`. The core holds no more hub words (hub,
  relief, rider, hitchhike, pooled, crew, pool session, in any of their
  spellings) than it does today, file by file; that list only shrinks, and a
  count that fell must be lowered with it. On a pull request CI compares both
  lists, the words read and the places left out of the core with the base
  branch's (`python3 tests/hub_borders.py --compare`), as it already does for
  the list of uninvented machines. And a wheel built from the product alone,
  installed into a fresh environment and run from outside any checkout,
  answers `--help`, `--version`, `capabilities`, `catalog`, `contract`,
  `init --api`, `config`, `pool` and `index`, imports every module and writes
  nothing inside the install. A run right after a fresh `init` reaches the
  unit `init` bound. No product code changed.
- The rig agent's tests pin the hub's published contract more widely
  (borders plan P5). They now pin a second hub schema, the rider's REST API
  (`tests/fixtures/hub_rider_v1.schema.json`). The ladder a `rig rungs sync`
  posts is checked as a request the hub takes, and the listing the tests
  serve as an answer the hub may send. The hub's `/v1` refusals the runner
  reads (`RELIEF_UNAVAILABLE`, `MODEL_UNPLACED`, `UNKNOWN_MODEL`) are checked
  to be pairs the hub publishes, with the same status. The protocol copy is
  re-pinned to pick up the hub's `x-features` and the new `x-udp` keys. The
  agent's `FEATURES` must be a subset of `x-features`. `udpwire` writes and
  reads each of the hub's UDP test vectors as exactly its bytes, and names
  the relay's refusal reasons (`BAD_TICKET`, `EXPIRED`, `FULL`,
  `RATE_LIMITED`). `tests/rig_schema.py` pins any number of hub files.
  `python -m tests.rig_schema HUB_CHECKOUT` re-pins all of them and rewrites
  their digests. Its validator now reads `additionalProperties: false`.
  The drift check reads `MCGYVR_HUB_REPO` (a hub checkout) or each file's own
  variable (`MCGYVR_HUB_SCHEMA`, `MCGYVR_HUB_RIDER_SCHEMA`). No behaviour of
  the product changed.

### Changed

- Re-pinned both hub schema copies (`tests/fixtures/hub_protocol_v1.schema.json`,
  `tests/fixtures/hub_rider_v1.schema.json`). The hub reworded their descriptions
  so they no longer name its internal modules. The structure is unchanged. No
  behaviour of the product changed.
- The containers of a pooled session (`sandbox/pooled.py` and its seccomp
  profile `pooled-seccomp.json`) moved into the hub client, as
  `mcgyvr.rig.pooled` (`src/mcgyvr/rig/pooled.py`, `rig/pooled-seccomp.json`).
  Only `rig/` used them. What they do is unchanged, and the profile still
  ships in the wheel. Now only `mcgyvr.cli` imports the hub client, with no
  exception: the core's list of imports not yet moved is empty, and its hub
  words no longer count the file.
- Live admission refuses a live `run`, `serve wake`, `manage` or `mcorch
  serve` whose loaded config (the working directory's comes before the live
  folder's) holds a unit on a rig that the live fleet does not lay out there
  (by unit, rig and address), or a unit on no rig at a machine of yours (as
  `init` reads an address, a full stop of another script read as a dot):
  that machine is not approved for live work yet. This holds for every live
  fleet, promoted or `init`'s own.
- `data/model-catalog.json` is version 2: every number carries its source and
  the day it was read, and each entry names the file a pick downloads (with
  its revision and sha256). Each number was re-read from the Hugging Face Hub
  on 2026-10-07; the old sizes matched no file there. The three Q4_K_M sizes
  changed (DeepSeek-Coder-V2-Lite: 9558623232 -> 10364416768 bytes, so it
  fits on fewer cards). `mcgyvr recommend` reads the catalog through the
  knowledge layer, so a cached record is priced before the shipped one.
- mcgyvr's own door calls (`mcgyvr serve`, the ladder manager's sleep and
  wake, `fleet probe`'s read and link timings, and the door commands live
  admission prints) name the mode by the door's own test: `--mode lab` where
  the run root is a lab checkout, so the lab's ladder needs no rig file, and
  `--mode user` anywhere else. A lab tool that opens the door names
  `--mode lab`.
- `install.sh` warns about an `mcgyvr` older than 0.3.0, the latest release
  tag (it was 0.1.0); v0.1.0 has no `mcgyvr delegate`, which the skill names.
- mcgyvr 0.3.0 is on PyPI, so `uv tool install mcgyvr` (or `pipx install
  mcgyvr`) is the install: the README drops its "until the PyPI package is
  published" fallback to the GitHub release wheel and tag, and `install.sh`'s
  `cli:` line names the package instead of the git URL. A test holds the
  README's install line and its `cli:` line to `install.sh`.
- `mcgyvr init --priority throughput|quality|cost` replaces the free-text
  `--profile` for a composed ladder. The config's `profile: live|dev` is a
  different setting and is unchanged.
- The run-wide `max_window_fraction` is a hard ceiling (owner ruling). A
  contract is held to the stricter of its own `limits.max_window_fraction`
  and the run's: it may hold itself to less of a window than the run allows,
  never to more. Before, a contract's own share won wherever it stated one,
  so a contract declaring 0.9 was sent under a run that allowed 0.25. The
  refusal names the limit that was hit, and both when the two are equal.
- `mcgyvr rig rungs sync` writes each relief rung's busy answers into
  `relief.yaml` (`busy_answers`, an HTTP status and an error code each:
  `503 hitchhike_not_served_yet`, `503 hitchhike_host_away` and
  `404 model_not_found`), and the runner reads them off the rung instead of
  naming them itself: the hub's vocabulary is the hub client's. Nothing
  changes for a rung: a sync writes the three answers the runner held, and an
  older `relief.yaml` is read with them (borders plan, step 2d). An older
  mcgyvr refuses a `relief.yaml` that names `busy_answers` (an unknown key):
  after a downgrade, run `mcgyvr rig rungs sync` to rewrite it.

### Deprecated

- `mcgyvr init --profile`, removed in the release after next. A word naming a
  priority (`throughput`, `quality`, `cost`) maps onto `--priority`; other
  text is ignored. Either way it warns on stderr, and `--priority` wins when
  both are given.
- A relief rung with no `busy_answers` (a `relief.yaml` synced before this
  release) is read with the runner's own three answers for this release
  only. After it, such a rung has no busy answers until `mcgyvr rig rungs
  sync` rewrites the file; the rig agent re-syncs on its own where it holds
  the personal key (`$MCGYVR_HUB_API_KEY`).

### Removed

- Telemetry no longer stamps `round` and `product_sha256` on a journal row
  by executing the bench's product module from the development checkout
  around the package, nor writes `revision_error` when that read failed
  (borders plan 2a). The lab now sets `MCGYVR_RUN_TAGS` itself, and its
  readers take the round and the product digest from `run_tags`. A row
  nobody tagged carries neither, inside a checkout or out of one, and
  telemetry runs no code that is not the package's.
- The coding ladder and the hardware-recommendation planner are withdrawn, on
  the owner's decision; they will be redesigned in an issue. `mcgyvr recommend`
  is back to its 0.3.0 behaviour: `--profile coding|chatting|media_gen|other`,
  `--users`, `--host` and `--model-store`, and one JSON plan naming the
  checkpoint and engine for `coding` (it still reads the catalog through the
  model knowledge, cache first). Gone with them: the planner
  (`mcgyvr.planner`, plan version 2 and its `decision: {by, why}`), the
  recommend flags `--use-case`, `--offline`, `--config`, `--priority`,
  `--ctx-per-slot`, `--first-port`, `--jev`, `--jev-ctx`, `--climb-budget`
  and `--clear-step`, the plan's `knowledge`, `decision_unit` and
  `decision_why`, the unique candidate names and the placement's `host`,
  `serving.split_unit` and `serving.split_units`, the catalog's `serves` field
  and the four models added for the planner (`Qwen/Qwen3.5-4B`,
  `Qwen/Qwen3-8B`, `Qwen/Qwen3-14B`, `Qwen/Qwen3-30B-A3B`) with their header
  rows. The model-knowledge library (`mcgyvr.knowledge`: records, cache,
  online lookup, boards, geometry) and the Jev picker (`jev.unit`,
  `decision.classify_for`) stay as library code; `recommend` uses only the
  offline catalog read. `mcgyvr scan --rig` still records the rig's private
  address, and `init --priority` stays.

### Fixed

- The deterministic floor's program (`ruff format` for a `format` contract)
  is timed by the run's own `--config` `task_timeout_s`, as its acceptance
  commands are. It was given the ceiling of the config at the default
  location instead, so a run that named another config could have its
  formatter cut early or left running past the run's ceiling.
- A contract too big for the rung it was sent to is refused before it is
  sent, and the run fails on that rung (owner ruling: it is not moved to a
  bigger rung). It went out anyway: a llama.cpp unit answered `400` and the
  run ended as `error` naming an HTTP status. Each attempt now checks the
  contract against the window the rung declares (`units.*.window`) with
  `check_contract_against_rung`, which existed and nothing called: its
  declared ceiling, its reply cap, its prompt beside that cap, and the share
  of the window it allowed itself (`limits.max_window_fraction`). It ends as
  `error` on that rung, `ContractTooLargeForRungError` naming the contract,
  the rung, the tokens and the window. Nothing is dispatched, no journal row
  is written and no sleeping card is woken for it; a prompt over its own
  contract's ceiling (`PromptTooLargeError`) is now refused at the same
  point, and no longer leaves a journal row for a request it never sent. A
  reply cap that fills the window (`OutputCapTooLargeError`) now names whose
  number it is: the rung's `output_tokens` or the contract's
  `limits.max_output_tokens`. A rung that declares no window is not measured
  against one.
- The run-wide `max_window_fraction` in the config is now enforced; nothing
  read it before. A contract that declares no share of its own is held to
  the run's share before it is sent, by the same check and with the same
  outcome as an oversize contract: `error` on the rung it was sent to,
  `ContractTooLargeForRungError`, nothing dispatched, no journal row, no
  sleeping card woken, no climb. It is a ceiling over a contract's own
  `limits.max_window_fraction` (see Changed). The refusal
  now says which limit was hit: the run's `max_window_fraction` (config) or
  the contract's own `limits.max_window_fraction`.
- The rig agent's at-once frame test no longer fails on a busy machine: it
  wanted a queued frame at the hub within 0.1 s (it took 0.24 s at load 90).
  The agent's read of its channel now lasts far past the fake hub's patience
  in that test, and the frame is put while the agent is in that read, so a
  frame that arrives at all was sent by the put's wake, not by the read's end.
  No product code changed.
- Five more tests no longer fail on a busy machine: they bounded how long
  something took, not what it did. The slow-page tests of a cancelled relay
  and of a cancelled ride wanted the hub's handler back in 0.1 s and the end
  in 2 s; the head's page is now held until the test lets it go, so the end
  arriving while it is held shows the page was not waited for, and, with the
  page held and no giving up, the handler back with no `relay_end` sent yet
  shows it never waits. The acceptance-ceiling test wanted the whole
  `mcgyvr run` done in 5 s (it took 5.4-6.5 s under load); it now checks that
  the sandbox was given the `--config` ceiling (1 s) for the acceptance
  command and that the command was killed by it. Two lease tests slept a
  fixed time and counted any renewal; they now wait for that session's own
  tunnel lease to be renewed. No product code changed.
- Three tests no longer fail on a busy machine (they failed under several
  parallel `make check` runs, at load ~60 on 8 cores). The tensor-cache
  session tests gave the agent's cache check 5 s, but the check hashes in
  processes at the lowest priority, which by design run only on CPU nothing
  else wants: one took 4-13 s to name a 4 KiB file. They now name each file
  in the check's own thread with the same `file_name`, so a wait bounds the
  agent alone; `hash_files` keeps its own test, with no deadline. The
  machine reader's write trace ran `strace -f`, which stops every process
  at each of its system calls: 75-91 s at that load, past the run's 60 s.
  It now runs with `--seccomp-bpf` where strace has it, stopping only at the
  traced calls (9-12 s, the same calls seen). No product code changed: no
  worker can mount a torn cache file while the check runs late.
- README: the `mcgyvr --help` usage now lists `recommend`, `manage` and
  `mcorch`; a command map gives every command's own help line, and a test
  holds both to the parser.
- SETUP.md names every `mcgyvr init` option (`--use-case`, `--deployment`,
  `--profile`, `--jev`, `--mcorch`, `--window`) and the `mcgyvr scan` and
  `mcgyvr recommend` steps before it; a test holds it to the `init` parser.
- `data/README.md` no longer describes media rows: every row of
  `capability-table.json` is a text-generation model.
- `mcgyvr init`'s refusal with nothing to bind states the real cause. It
  said "With 12 GB of VRAM, no unit can be proposed" -- one card's size, on
  a machine of two such cards with no server up -- though init binds only a
  model a running server lists and card memory plays no part. It now says no
  model server answered on the endpoints tried (each named), so there is
  nothing to bind, and lists every card with its size as the cards of the
  machine running mcgyvr, saying a rig swept with `--host` is not read from
  there. `Detection.swept` records the endpoints a sweep asked.
- `mcgyvr init --profile` writes the use case and deployment it states. The
  composed candidates were built without them, so `--use-case chat --profile
  X` wrote `use_case: coding` and `deployment: hybrid` while the printed
  decisions said `chat` and `local-only`.
- The serving door's `--host` help (`python -m mcgyvr.serving.run`, and its
  `serve` and `read`) no longer names the developer's own two machines as
  if they were the choices; it says "the rig, by its name in hosts.json".
  The door's module text and a few `serving/gatelib.py` and `capacity.py`
  examples use placeholders too. A test builds every command's help and
  fails on those machine names, or on any machine the shared scan sees.
- The 0.3.0 notes left out four things that shipped in it (each on main before
  the v0.3.0 tag):
  - `mcgyvr recommend` prints one JSON plan: the checkpoint and engine for a
    usage profile on the rigs named with `--host`.
  - `mcgyvr manage` lets Jev sleep and wake the ladder's units by their queue.
  - `mcgyvr init --use-case` (coding, chat, agent, media-gen) and
    `--deployment` (hybrid, local-only) say what the install serves and how.
  - `mcgyvr init --profile` composes the ladder for a usage profile; Jev only
    names one of the candidates, so every number stays measured.

## Older releases

The entries for 0.3.0, 0.2.0 and the ones written before 0.2.0 are archived
outside this repository.
