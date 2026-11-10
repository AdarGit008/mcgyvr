# Changelog

Format: [Keep a Changelog](https://keepachangelog.com).

Paths in older entries are where files were when the entry was written.
`docs/` moved to `archive/docs/` (#395); most of `archive/`,
`records/plans/`, `docs/` and the write-ups under `records/` are now
archived outside this repository, under the same paths.

## [Unreleased]

### Changed

- **`relief.yaml` is `hitchhike.yaml`, and nothing says relief rung any
  more.** A rung a hub lends you is a hitchhike rung (slot sharing; the owner:
  relief rung is not a concept). `mcgyvr rig rungs sync` writes
  `hitchhike.yaml` with its one key `hitchhike` and removes an old
  `relief.yaml` beside it. Migration: none needed; a setup holding only
  `relief.yaml` is read from it, under its key `relief`, for one release, and
  the rig agent's next refresh (or `mcgyvr rig rungs sync`) rewrites it. A
  `relief` block in fleet.yaml, policy.yaml or a setup written as one document
  is refused, naming `hitchhike`. The config reference's `relief.*` fields are
  `hitchhike.*`; a result file's per-attempt `relief` is `hitchhike`; `mcgyvr
  ladder show` lists *Hitchhike rungs*. On the wire, the rider no longer
  requires the hub's constant `relief: true` on each rung, and the published
  rider schema marks it deprecated: a hub keeps sending it this release, from
  one compat shim, for rigs up to 0.5.1. Deprecated: the hub stops sending it
  in the next release, and a rig up to 0.5.1 then refuses every rung listing
  until it is upgraded. For Python callers: `Config.relief`, `Unit.relief`,
  `RELIEF_FILENAME`, `load_relief`, `ReliefUnavailableError` and the rest are
  their `hitchhike` names. Also: hubwire's `ONE_PER_RIG`,
  `SESSION_KEY_CONTEXT`, `HEAD_DEVICE_RPC` and `QUANT_CLASSES`, read nowhere
  else, are private (`_ONE_PER_RIG` and so on), and `scan.BYTES_PER_GB` is
  `BYTES_PER_GIB` (1024**3 bytes).

- **`mcgyvr local_pool` is now `mcgyvr ladder show`, and SETUP.md opens its
  words with a glossary.** The verb printed the ladder but was named for a
  pool, which the hub's pool is not; `mcgyvr local_pool` is refused with the
  new name (exit 2) and is never sent to a proposer as a prompt. Migration:
  type `mcgyvr ladder show` (same flags: `PATH`, `--config`, `--probe`,
  `--probe-timeout`). Its output, the capacity errors, the cool-down reason
  and the verifier's refusal say unit where they said source (`Probed N
  unit(s)`, `unit 'x' did not answer`, `unit 'x' failed N dispatches in a
  row`). SETUP.md's new *Glossary* defines each word once: decomposition,
  scaffold, fill, draft, vet, proposer, direct, delegate, ladder, rung, top
  rung, unit, standing session, hitchhike, general and crew pool, rig, host,
  system, session, writer, family and floor. The prose follows it: the chat a
  run is filed under is the writer; host is the person who offers slots, rig
  the machine and system its OS block (the wire keeps `host`); the unit key
  file is `unit-keys/<address>-<port>.env`; the `tempdir` sandbox's notes and
  the `sandbox` and `expose` field help say this machine where they said the
  host; `mcgyvr contract` shows `floor (no model)` or `ladder (a model)` where
  it said `deterministic tier` or `model tier`; and the header of a generated
  fleet.yaml/policy.yaml and the notes and refusals `mcgyvr setup` prints say
  `setup` where they said `init`. For Python callers: `mcgyvr.local_pool` is
  `mcgyvr.ladder_map` (`PoolError` is `LadderError`; `SourceMap`,
  `source_map`, `SourceUnavailableError` and `SourceProbe` are `UnitMap`,
  `unit_map`, `UnitUnavailableError` and `UnitProbe`), the setup wizard's
  `mcgyvr.propose` is `mcgyvr.ladder_proposal` (`Rung` and `Proposal` are
  `LadderRung` and `LadderProposal`, apart from the ladder's `Rung` and a
  contract's `Proposal`), `deliver.digest_of` is `text_sha256` and
  `repo.index.digest_of` is `bytes_fingerprint` (one name meant two digests),
  and the jev choice alphabet is `decision.CHOICE_LABELS`, which the decision
  log now reads instead of a copy. `rig.pooled.PoolError` is a different error
  and keeps its name.

- **`mcgyvr recommend` asks placement whether a model fits (I-47).** Its own
  arithmetic left out the scratch allowance and the RAM rule placement applies,
  so it could recommend what placement then refused. A checkpoint is now a
  `ModelSpec` with its header as the geometry and a catalog record one stated
  by its file and cache, and both go through `serving.fit` at the context and
  user count recommend plans (`recommend._sized`). A checkpoint whose experts
  fit beside the card is no longer refused for want of RAM for all of them; a
  catalog record is held to the 2.0 GB headroom placement gives an unscanned
  model, as placement's own catalog specs are, so a chat or agent plan's most
  context is that much smaller and a coder placement would refuse is no longer
  picked (on the shipped catalog: Qwen3-8B on an 8 GiB card 24064 -> 9472
  tokens; on 16 GiB the 7B coder instead of the 14B; on 8 GiB no coder).
  `recommend._slot_bytes` and `_host_ram_bytes` are gone.

- **One per-card fit law, in `mcgyvr.hubwire`, for the sizer, a split and the
  hub's planner; the flat 768 MiB allowance is gone (I-05, I-23).** What a card
  of a llama.cpp layer split holds beside its tensors was two laws: the
  product charged a flat 768 MiB on one card (`SCRATCH_AND_CONTEXT_MIB`) and a
  measured per-arch reading only on a split, and the hub charged its own
  context-growing compute buffer. Now one law decides it, on one card and on
  each card of a split, and the hub imports it: a reading from
  `hubwire.MEASURED_SCRATCH_MIB` (per arch, by ubatch, CUDA cards only) when
  there is one, else the card's context (`CARD_CONTEXT_MIB` 161 MiB, or
  `UNIFIED_CONTEXT_MIB` 512 MiB on a unified device) plus a compute buffer of
  232 MiB and, per cell of context, the larger of the KQ mask (6 bytes an ubatch
  row) and an f16 copy of the widest layer's K and V
  (`hubwire.card_allowance`). The cells (`cache_cells`, `cache_bytes`, padded
  to 256 a sequence), the card total (`card_bytes`, `bytes_on_card`) and an MoE
  spill's host bytes (`offloaded_expert_bytes`) are there too;
  `vramfit.kv_bytes` and `vramfit.allowance` price a scan's rows for it, and
  `hubwire.FIT_CALIBRATION_RUNS` are the ten measured runs both planners are
  held to. A reading holds at the cells it was read at
  (`hubwire.MEASURED_SCRATCH_CELLS`: qwen35moe's 16384, qwen3next's 8192; none
  on record for the others) and grows past them at the law's per-cell slope
  (`compute_bytes_per_cell`), and a card is never charged less than its context
  (512 MiB on a unified device), as the hub's reserve already was. Numbers
  move: qwen35moe on one card is charged its 316.57 MiB reading at ubatch 512
  (304.57 at 256, the reading with a context on record, for 302.7) and
  qwen3next its 829 MiB (both were 768) up to their read contexts; an
  unmeasured arch is charged 161 + 232 MiB plus its per-cell term, less than
  768 MiB below about 128k cells of 3 KiB and more above, so the width search
  can choose fewer slots. `vramfit.SCRATCH_AND_CONTEXT_MIB` and
  `vramfit.allowance_mib` are removed (`vramfit.allowance` replaces the second).

- **A llama.cpp unit's cache type is one llama.cpp takes, priced at its own
  width (I-24).** `vramfit.CACHE_ELEM_BYTES` knew f32, f16, bf16 and q8_0, so a
  unit naming q4_0, q4_1, iq4_nl, q5_0 or q5_1 (all of which llama.cpp takes)
  failed with a bare `KeyError` once it was sized. The widths are now the
  scanner's type table (`ggufscan.T`) filtered to the nine types llama.cpp's
  `kv_cache_types` lists (`vramfit.LLAMACPP_CACHE_TYPES`), and a llama.cpp unit
  naming any other (`auto`, `q4_k`, an upper-case spelling) is refused when its
  launch block is read, naming the ones it takes
  (`serving.check_cache_types`). vLLM's names are not checked. Upgrading: a
  llama.cpp unit with such a type, which llama.cpp itself would refuse at
  launch, now stops `mcgyvr` at load instead.

- **One function prices a token of cache for the catalog, a rig's hello and the
  sizer (I-46).** The catalog's `kv_bytes_per_token` (f16, every caching layer),
  the hello's (q8_0, every caching layer, rounded up) and `vramfit.kv_bytes`
  (the run's cache types, sliding rows charged their window) were three sums of
  the same `kv_layers` rows. All three now call
  `vramfit.cache_bytes_per_token(rows, cache_type_k=, cache_type_v=, only=)`:
  `only=None` charges every row the full context (the catalog and the hello),
  `"full"` and `"sliding"` are the two sums `kv_bytes` multiplies by its own
  cell counts, so the sliding-window discount stays in `kv_bytes`. Every figure
  is the one it was: the shipped catalog's values and the hello's are
  unchanged. `knowledge.hub.F16_BYTES` is now `CATALOG_CACHE_TYPE = "f16"` and
  `rig.inventory._KV_TYPES` is gone (the widths are `vramfit.CACHE_ELEM_BYTES`).

- **Who may use a rig is one vocabulary, `own | crew | anyone`, and how a rig
  takes part is its mode, `lend | hitchhike` (I-04).** The pools the wire
  names by audience now carry the audience's name: `hubwire.POOL_SOLO`
  (`solo`) is `POOL_OWN` (`own`) and `POOL_GENERAL` (`general`) is
  `POOL_ANYONE` (`anyone`); `crew`, `hitchhike` and `shared_ladder` are
  unchanged. New in `mcgyvr.hubwire`, for the hub to import: `MODE_LEND`,
  `MODE_HITCHHIKE`, `MODES`, `MODE_AUDIENCES` (a hitchhike rig is `own` or
  `anyone`, never a crew's alone), `rig_pool(audience, mode)`, `POOL_NAMES`
  (each pool in words: the general pool is shown as "general pool
  (anyone)"), and `RETIRED_SHARING_MODES` (the hub's old `solo`, `crew`,
  `pool`, `hitchhike`, each as the audience and mode that replace it). A
  unit's `scope`, `ride_scope`, `relief.scope` and `mcgyvr rig rungs sync
  --ride-scope` that write `solo`, `pool` or `general` are refused with the
  word to write (`own`, `anyone`; `hubwire.RETIRED_AUDIENCES`,
  `retired_audience`), never read as
  an alias; they were refused before too, without naming it. The generated
  SETUP.md maps each audience and mode to its pool and the use cases it
  serves, and says a host serves strangers only once a hub admin approved it.

- **The docs say what already ships, tests pin it, and helpers no command
  calls say so; one prompt changes.** A new generated `COMMANDS.md` lists
  every verb and flag, rendered from the CLI's own parser by
  `mcgyvr.cli.verbdoc` (`attach`, `index`, `resolve`, `read --hint/--holds`,
  `fleet alerts`, `rig leave`, `rig peers`, the `caps` and `rig lend` aliases
  were in no document); `make docs` writes it and `make docs-check` fails when
  it drifts. SETUP.md points at it, and says that `emit` refuses a
  unit larger than the free disk, that setup's sample writes a reply ceiling
  into `fleet.yaml` for a unit that names none, what `$MCGYVR_ENDPOINTS`,
  `$HF_TOKEN` and `$HF_ENDPOINT` do (the `MCGYVR_TEST_*` hooks are test-only),
  that a head given a model digest refuses another file as `model_missing`,
  and that the journal is the one piece of state that does not move with
  `$MCGYVR_DATA` or `$XDG_STATE_HOME`.
  `task_timeout_s` names its second use, the queue wait, and says that with
  no config each command still ends at the sandbox's own 900 s; `start_rung` no longer promises a rung picked ahead of a run
  (`triage_ahead` is wired to no command); /mcgyvr-direct names the
  `unchanged` / `identical-to-base` finding. New tests pin the split-path disk
  refusal, the head digest check and its lease renewal, the `crew.yaml`
  reader, the reply ceilings and `read --hint/--holds`. `disposition`,
  `credential_env_names`, the decision-log metrics, `alerts.rejudge` and
  `delegate_log`'s reader say who calls them. The js/ts worker prompt asks
  for the target's own language — TypeScript for `.ts`/`.mts`/`.cts`/`.tsx`,
  plain JavaScript otherwise — instead of typed TypeScript for every target
  (its standing stays "measured, no effect": #144 measured the text before
  this change, and it is not re-measured).

- **`redact.scrub` drops a bare credential, not only a URL's userinfo.** It
  stored whole prompts and replies — and failure notes and run tags — cleaned
  only of the `user:token@` of a URL, so a key a model echoed back (`sk-...`,
  `ghp_...`, an AWS id, a pasted private key, a `Bearer` token) survived into a
  journal blob that can be copied elsewhere. `scrub` now also blanks every
  provider token shape of the one shared vocabulary
  (`mcgyvr.credential_shapes.VALUE_SHAPES`, folded into one pass), a pasted
  private key taken whole from its header to its footer, and a `Bearer`
  authorization token (the last two spelled in `redact`: a Bearer token has no
  prefix of its own, and the whole-block private-key pass is wider than the
  gate's line-form header shape; the gate and config loader want neither). The
  one cleaning entry point is what telemetry, notes and the sandbox already
  call, so the widening reaches them
  all: the sandbox's `safe_env` now drops an environment *value* that holds a
  token (not only a credential-named variable), and `holds_a_secret` now keeps
  a login rc file out of a workspace when its text carries a token as well as
  when it carries a `word=` login. `safe_url` stays userinfo-only; text with
  no credential still comes back unchanged, so the compare-to-detect callers
  are unaffected (I-62).
- **A failed session's log excerpt is cleaned of host paths and credentials
  before it is sent to the other members.** `rig/sessionwire.scrub` only blanked
  unprintable characters and cut the text to the excerpt cap — it removed no
  secrets — yet it shared its name with the real cleaner `redact.scrub`. The rig
  sends this excerpt to every member of a session, so a host path or a key in a
  container's log reached other users. It is renamed `printable_tail` (its call
  sites in `sessionwire` and the UPnP error text in `rig/portmap` with it), and
  `rig/session`'s `_fail` now runs `redact.scrub_paths` and `redact.scrub` on the
  excerpt before the printable-and-capped shaping, so host paths become
  `<redacted>` and a token (now that `redact.scrub` carries the token shapes,
  I-62) is dropped. The protocol schema's `log_excerpt` text now says the rig
  strips host paths and credentials before sending; the hub renders that text
  from its own docstring; a hub twin PR carries the identical text and re-pins
  in the same train (I-63).
- **A Mac's GPU is sized from the Metal working set llama.cpp logged, a
  reading, once a native server has started on it.** The native supervisor
  already filed `recommendedMaxWorkingSetSize` from llama-server's start-up
  log in `native/metal.json` in the data folder, and nothing read it: the
  machine reader sized the GPU from `iogpu.wired_limit_mb`, else 0.75 of the
  memory, an estimate. Now the reader (`rigscan.metal_working_set`, which
  finds the data folder by `fleet.roots.data_home`'s rule) sizes card
  `apple.0` and its `unified` resource from that file, held to the memory,
  with `figure: reading`, and `mcgyvr detect` and fit listings take it. The
  supervisor now files the wired limit in force beside the figure, and the
  reading is taken only while that limit is the one set: after the limit is
  changed, or after a reboot that cleared it, the GPU is sized by estimate,
  as on a first run, until a native server starts again. A file that holds
  no reading is passed over the same way. `mcgyvr scan` notes why in each
  case; `mcgyvr detect` and the hub show only `figure: estimate`. Upgrading:
  a file an older supervisor wrote names no limit and is not taken, and a
  supervisor still running the older code writes it that way again on every
  server it restarts, so restart a Mac's native units on this release to
  size it from the reading. A Mac whose native server has started sizes
  from the reading, which may be above or below the estimate, so the models
  that fit it can change. The folder name and file name are spelled once,
  in `fleet.roots` (`NATIVE_DIR`, `METAL_FILE`); `estimate.usable_unified_mb`
  (no caller) and `native.metal_working_set` (tests only) are removed, and
  with them `estimate.UNIFIED_SHARE`, which only that function used.

- **`mcgyvr PROMPT` scaffolds by default, and the top rung fixes what vetting
  refuses (I-30a, I-30b).** Unset `orchestrator.authoring` is now `classifier`
  under `mcgyvr-code` whether or not Jev is on: the scaffold lays out each
  field's candidates, Jev picks from them when it is opted in, and without Jev
  the scaffold's first candidates stand. That path no longer needs an
  `orchestrator` model: with none bound the command proposes rather than
  exiting 3, and the prose unit stands in only where one is bound.
  `authoring: prose` stays as the opt-in, and still exits 3 with no model
  bound; its message now says dropping `authoring: prose` scaffolds instead.
  A bare install (no config at all) still exits 3, now told to run `mcgyvr
  setup` rather than to bind an orchestrator model. A proposal vetting refuses is no longer handed back to the proposer
  that made it: it goes, with the refusal, to the top rung — the ladder's
  dearest usable rung within `max_escalations`, named once as
  `route.top_rung` — in a prompt that asks for the corrected proposal and
  nothing else; the answer is vetted again, the rounds are still bounded by
  `max_reproposals` (default 1), and what is still refused is reported as
  before. The re-plan of a spent contract asks the `orchestrator` model when
  one is bound and the top rung when none is. `--log` names the rung asked
  (`fixer`, `fixer_model`). The classifier, the refiner and the scaffold no
  longer re-ask their own refusals (`iterate.reproposals` is gone).
  `mcgyvr direct` is unchanged: a contract you wrote that vetting refuses
  comes back to you with the reason. No gate approves a contract before
  dispatch: passing vetting is what stamps it (I-30e).

- **Every kept file is renamed into place by `mcgyvr.atomic`, which retries
  while Windows holds the target (I-54).** The native launcher's records,
  specs and settled copy, the rig identity key's no-hard-links fallback, the
  Python lease's rewrite, the fetcher's verified download, the unpacked
  llama.cpp build and a standing swap's record each staged a file and renamed
  it by hand, and only the launcher's records were tried again when Windows
  refused the rename. They now go through
  `atomic.write` or, for a staged file or folder built some other way,
  `atomic.replace`: `os.replace` tried again on PermissionError, 20 times
  50 ms apart (the launcher's `REPLACE_TRIES`, now `atomic.REPLACE_TRIES`),
  then the refusal raised. Every `atomic.write` caller gains the retry; a
  rename that is refused on any system now fails after about a second rather
  than at once. `atomic.write` takes `mode` for an ordinary file made with a
  narrower mode (the lease keeps 0644). The shipped lease, fetcher and native
  launcher carry `mcgyvr.atomic` (standard library and `hostos`, Python 3.9).
  Modes, fsync and the lease's staging name are as they were; the launcher's
  and the swap record's staging files are now atomic's
  `.<name>.<pid>-<thread>.part`, and on Windows the launcher's records and the
  lease (a free take as well as a rewrite) are written with `\n` line ends
  instead of `\r\n`. A test holds that no module but `atomic` calls
  `os.replace` or `Path.replace`, and the macOS and Windows runners replace a
  file a reader holds open.

- **Fleet alerts no longer list `l2_wake_s` as a judged field.** Nothing wrote
  it: no read measures a vLLM unit's L2 wake, and no lock approves one with a
  seconds tolerance, so the entry in `fleet.alerts._JUDGED` could trip only in
  its own unit test. An `l2_wake_s` row, if one is ever filed, is recorded and
  not judged, like the cold wake. No rig's alerts change.

- **The run outcome words `accepted` and `error` are spelled once, in
  `escalate.Outcome`.** `tree.ACCEPTED` and `cli/commands/run.RAISED` repeated
  them; the tree's provider check and the run's raised-step word and
  correction row now read `Outcome.ACCEPTED` / `Outcome.ERROR`, imported where
  they are used so loading the tree or the command line does not load the
  climb. The tree's `blocked`/`abandoned` and the run's commit words stay
  where they are: they name other stages on purpose. The words written are
  unchanged.

- **`deployment`'s two words and its default are written once, in the schema
  field (`config.DEPLOYMENT_FIELD`).** `mcgyvr setup --deployment` took its
  choices and the default its help names, `Config.deployment` its unset value,
  and `mcgyvr init` the deployment it writes when none is asked for, each from
  its own copy of `hybrid` / `local-only`; they now read the field. Every value
  agrees with before, so nothing a user sees changes.

- **A misspelled `$MCGYVR_LOCAL_TRANSPORT` is refused, not ignored.** For
  this machine's rig names, a value that is neither `direct` nor `ssh` (after
  trimming and lowercasing, so `Direct ` still works) used to fall through to
  auto-detection, so a user forcing one transport could get the other; it now
  stops with a `ValueError` naming the variable, the word and the two it
  takes, as `$MCGYVR_NATIVE_BACKEND` already does. An unset or empty variable
  still auto-detects, and another rig is still reached over ssh whatever the
  word says.

- **`breadth.temperature`'s default is one constant,
  `config.BREADTH_TEMPERATURE_DEFAULT` (0.7).** The schema field reads it,
  and so does the worker attempt when a config does not name the key, which
  used to fall back to 0.0 and make every draw after the first a greedy copy
  of draw 0 (the case the schema refuses at load). A loaded config always
  carried 0.7, so a user's draws do not change; a hand-built config's draws
  1..n-1 now sample at 0.7. Draw 0 stays greedy.

- **git's empty-tree id is `gitcmd.EMPTY_TREE`, and a glob step lists its
  files the one way.** `deliver`, `repo.repo` and `gate.changeset` each kept
  their own copy of the id; they now import it. A step whose target is a
  pattern (`drive.exec`) expanded it with its own `git ls-files`, which on a
  workspace git cannot list ended `mcgyvr run` in a raw `CalledProcessError`
  traceback; it now uses the repo index's `enumerate_files`, and the run
  catches the named `IndexBuildError` like any other step failure: it prints
  `error: cannot enumerate <workspace>: ...`, files the attempt's `error`
  correction, writes an `error` result and exits 1, with no traceback.

- **"Absent engine means llama.cpp" is decided once, in
  `config.DEFAULT_ENGINE`.** The default was `serving.DEFAULT_ENGINE` and the
  bare string in `default_launcher`, emit's unit host, the native launcher
  check, the lock's and the sampler's unit digests, `fleet.read.engine_of`,
  `inspect`, the sampler's window read and setup's bootstrap; each now reads
  the one constant (`serving.DEFAULT_ENGINE` re-exports it) and the `engine`
  field's doc quotes it. It is not made the field's schema default, so a loaded
  unit that names no engine still has none and a stated `engine: llama.cpp`
  stays in the setup identity: no lock digest, rendered unit or SETUP.md line
  changes. A literal that names llama.cpp as a kind of engine stays.

- **The four model-on-disk listers are pinned together by one test (I-138).**
  The scan (`rigscan._models_on_disk`), the rig agent (`rig/inventory.read`),
  recommend's discovery (`recommend.discover_command`) and the local-rig
  emulator (`localrig.run`) list model files by different rules, on purpose:
  their protocols differ. One test lists an invented tree with all four and
  states each rule (formats, depth, split parts, hidden names, case), and
  checks the emulator against the real `find`. Nothing behaves differently.

- **A scan reads /proc/meminfo and the CPU model once (I-141).** The reader
  parsed /proc/meminfo three times per scan (the memory section, the bandwidth
  probe's `_spare_gb`, the snapshot) and looked the CPU model up twice (the CPU
  section, the snapshot's `cpu_model`). The short reading now reads each once
  and the probe and snapshot take those reads: `rigscan.measure_bandwidth`
  takes the memory section's available MiB (`spare_mib`, MemAvailable else
  MemFree) instead of a root to read from, and `_spare_gb` is gone. A scan's
  output is unchanged on every invented machine (15 scans compared, meminfo and
  cpuinfo variants among them), and it does fewer reads: meminfo 3 to 1,
  cpuinfo 2 to 1. Off Linux the probe still takes its small block, as it did.

- **The native supervisor asks `nvidia-smi` through the reader's runner
  (I-140).** `native.nvidia_driver` and the card-holder read behind
  `native.held` ran `nvidia-smi` with their own `subprocess.run`, bounded in
  time only; both now run through `rigscan._run`, still held to
  `native.PROBE_S` (10 s) and now also to the reader's output bound
  (`rigscan.BYTES_MAX`), with the tool's process group ended with it. The
  answers are the same: the driver or None, and holders as `pid,name,<n>MiB`,
  "none" or "unread".

- **`mcgyvr detect` finds Docker as the reader finds its tools (I-139).**
  `detect._run` and `detect_docker` looked the program up with `shutil.which`,
  which on Windows tries the working folder first and everywhere searches a
  relative PATH entry; they now use `hostos.which_absolute`, PATH's absolute
  folders only, and run the path that was found. A `docker` reachable only
  through the working folder or a relative PATH entry now reads as "not on
  PATH". The `docker info` check itself and the CPU count are unchanged.

- **A relative `$XDG_CACHE_HOME` is passed over, as a relative
  `$XDG_STATE_HOME` already was (I-146).** `hostos.user_cache_dir` took any
  value, so `XDG_CACHE_HOME=cache` put the model index under whatever folder a
  command ran from; it now honours the variable only when it is absolute (`~`
  still expanded) and otherwise uses the system's own cache folder. The
  `weights_dir` docstring no longer says the weights follow the variable (they
  never did), and SETUP.md's *Folders* says the XDG variables win "when
  absolute".

- **A hello's `ram_total_mb` is the MiB the reader counted (I-133).** The
  rig's hardware report (`rig/hardware.py`) took the hello's RAM total from the
  memory section's GB figure, which the reader rounds to 0.1 GB, so it could
  differ from the host-RAM resource in the same hello by up to ~51 MiB. It now
  takes the resource's exact `total_mb`; a reading with no host-RAM resource
  reports RAM unread (0 MiB total), as one with no memory section did. Every
  rig's hello figure moves by those few MiB. `recommend`'s own GB-to-MiB turn
  (`recommend._memory_mib`) is left as it is.

- **Two machine-reading designs are said and pinned; nothing behaves
  differently.** First contact with a rig over ssh is the scan's: `mcgyvr scan
  --rig`, `setup` and `recommend` send a rig with no rig file the POSIX reader,
  then the Windows one when its shell answers PowerShell, while a serve or a
  read through the door ships by the rig file alone (`gatelib.shipping_os`)
  and refuses a rig with no rig file before reading it; the door's `link`
  timer needs no rig file and ships the POSIX line. SETUP.md's *macOS and
  Windows* says so (*A rig over ssh*), and drops "remote rigs are Linux
  machines", which a Windows or Mac rig over ssh no longer is. And this
  machine's exact names (`gatelib.LOCAL_RIGS`: localhost, 127.0.0.1, ::1, [::1])
  alone decide a unit's bind and key: the comment there says the list must
  never grow to the looser match that finds a rig file
  (`rigfile._names_this_machine`), and tests pin that a unit addressed at
  127.0.0.2, 0.0.0.0 or `[::]` is `lan` and keyed, that a launch stating
  127.0.0.2, `LOCALHOST`, 0.0.0.0 or `::` listens beyond this machine, and
  that `http://LOCALHOST` is `local`: a URL's host is case-insensitive, so it
  names `localhost`.

- **A rig starts a CPU head: a whole model on the cores and memory it lends, no
  card.** A `head_start` whose devices are a single `cpu` device
  (`hubwire.HEAD_DEVICE_CPU`) now starts a head that runs every layer on the
  host's CPU (`llama-server -dev none -ngl 0`), held to the cores the rig lends
  (`sharing.head_limits` → llama-server's `--threads`; a pooled head's container
  also gets `--cpus` and `--memory`). The agent refuses the head unless the rig
  actually lends both memory and cores (`not_capable`, "this rig lends no memory
  and cores"), and refuses a model that does not fit the lent RAM
  (`insufficient_memory`) — on a native host (macOS/Windows), which runs no
  container, that fit check is the only thing holding the model to the lent RAM,
  as there is no `--memory` cap. Before, the agent refused every cpu head
  `not_capable` ("this agent starts no cpu head yet"). The head needs no tunnel
  and no card; a `cpu` device is refused beside any other (it serves the whole
  model alone). A rig that lends no card still heads no pipeline (`rpc` devices
  stay refused), and `mcgyvr rig status` now says memory and cores run a whole
  model on the CPU rather than that no hub places one. `pooled.CPU_DEVICE` is the `-dev` value
  (`none`, llama.cpp's "don't offload"), and a cpu head carries no tensor split.

- **The vLLM split's cache figure is documented as an upper bound.** A
  llama.cpp split charges a sliding-window layer's cache only its window; a
  vLLM split charges every layer the whole context, so the same checkpoint is
  sized larger under vLLM and a fit can be refused. The `units.<unit>.launch`
  reference (SETUP.md) and `sharding._vllm_kv` now say so; no figure changed.
  What vLLM allocates for a sliding layer is to be measured before any
  discount is taken.

- **The rule for an address a peer can be at is defined once, in
  `mcgyvr.hubwire.is_peer_address`.** `rig/tunnel.py` (`is_lan`, `may_aim_at`)
  and `rig/probe.py` (`reachable`) each spelled the same five checks (not
  loopback, link-local, multicast, reserved or unspecified). They now read the
  one predicate: `probe.reachable` is it, `tunnel.is_lan` is it and private,
  and `may_aim_at` is it outside the tunnel's network and this machine's own
  addresses. No address is classified differently. Reading interfaces is
  unchanged and still Linux only; macOS and Windows rigs still name their
  `endpoints` by hand.

- **Every yes/no question in `mcgyvr setup` is written `[y/n]` (I-122).** The
  wizard mixed `[Y/n]`, `[y/N]` and `[y/n]`; it now asks `[y/n]` everywhere,
  as the Jev and PATH questions already did. What Enter means is unchanged:
  Enter is no at every question except the one that offers to reuse a model
  already on disk, where Enter still reuses it, and that question now says so
  (`[y/n, Enter reuses]`). `SETUP.md` quotes the new spelling.

- **The agent channel's limits, shapes and codes are defined once, in
  `mcgyvr.hubwire`.** The protocol version, frame limits, the counts and
  bounds of every frame (models, sessions, endpoints, features, peers, allowed
  IPs, devices, RTT samples, probe, tunnel and port-forward bounds and their
  schema defaults), the roles, session states and relay outcomes, the text
  shapes (message id, tag, machine id, agent version, digest, short tag,
  runtime, endpoint host, WireGuard key, IPv4, content type, base64, token,
  ticket) and the close, error and session codes were written in
  `rig/protocol.py` and `rig/sessionwire.py` and again in the hub. They now
  live in `hubwire` (stdlib only, as before), with `AGENT_ERROR_CODES` (every
  code, the schema's `x-error-codes`), `UDP_VERSION` and
  `RIDER_SCHEMA_VERSION` and the relayed response's HTTP status range
  `RELAY_STATUS`; the rig modules name them as the same objects, and
  the hub can import them at its next pin. No value and no behaviour changed
  (every existing public name of `rig/protocol.py`, `rig/sessionwire.py` and
  `rig/udpwire.py` compares equal before and after); `rig/udpwire.py` runs
  without the package, so it keeps its UDP version and relay ticket shape,
  held to `hubwire`'s by test. The `hubwire` docstring now lists what is
  shared and what is not.
- **The `mcgyvr.orchestrator` package is split by job: `mcgyvr.repo`,
  `mcgyvr.decompose` and `mcgyvr.decision_log`.** The package read code, built
  and cached the repository index, ranked and read files, and turned proposals
  into contracts; it orchestrated nothing. `mcgyvr.repo` now holds the context
  layer (`symbols`, `languages/`, `index`, `cache`, `resolve`, `read`,
  `context`, `references`, and `repo` for attaching a repository);
  `mcgyvr.decompose` holds the part that takes a proposer (`decompose`,
  `iterate`, `candidates`, `fields`, `provides`, `baseline`); and the jev
  shadow log `orchestrator/telemetry.py` is `mcgyvr.decision_log`, so it no
  longer sits beside `mcgyvr.telemetry` under the same name. Every other
  module keeps its name, and nothing behaves differently: a pure move and
  import rewrite, with no compatibility shim, so code outside mcgyvr that
  imports `mcgyvr.orchestrator` must import from the new paths. The
  policy.yaml `orchestrator` block, journal keys and messages are unchanged.
- **`SETUP.md` now names `numbers.yaml`, the file that overrides mcgyvr's
  shipped estimates.** A user can drop `numbers.yaml` in the config folder
  (`$MCGYVR_HOME`, default `~/.mcgyvr`) to replace the estimates mcgyvr sizes
  and judges a machine with but cannot read off it — decode drift, link speeds,
  host memory — each keyed by an engine, a unit's tolerance class, or a class of
  link, and a refusal already invites it, but the setup document never named the
  file. `docgen.render_setup` adds a paragraph for it, so `make docs`
  regenerates `skills/mcgyvr/SETUP.md` with it. Docs only; no code path changes.

- **SETUP.md says what is and is not supervised for a unit split across
  machines.** A split that cannot be launched is refused when `mcgyvr emit`
  or `mcgyvr setup` sizes its units. Once up, each part is kept up on its own
  rig: a docker part by docker's `unless-stopped` policy and the rig's boot, a
  `launcher: native` part by mcgyvr's own supervisor, which restarts it and
  gives up after five exits running and is not started again at boot. Nothing
  orders a worker before its head or tells the head that a worker on another
  rig stopped, so the unit's requests fail or time out until the worker is
  back; the serving door's `serve down` then `serve up` on the head's rig
  starts the head afresh. Documentation only: supervision stays with compose,
  the native supervisor and the rig's boot (I-52).

- **mcgyvr keeps one default port, 8080, for every engine, and the setup wizard
  reads vLLM's stock 8000 from the detect sweep instead of spelling it again.**
  `serving.DEFAULT_PORT` is the port any engine's unit listens on when its
  address carries none, so a portless vLLM unit resolves to 8080, not vLLM's
  own 8000; vLLM's stock 8000 is recorded among the well-known servers' ports
  in the detect sweep's list (`detect.PORT_CONVENTIONS`). The wizard's synthetic
  detection now reuses vLLM's port from that list — writing it into the address
  it stages — rather than spelling a second literal `8000`. No existing unit
  changes the port it is served on — the value is identical, only the duplicate
  is removed — and `serving.port_of` is
  unchanged.

- **One shared vocabulary for what a credential looks like, by value shape and
  by name (`mcgyvr.credential_shapes`).** Four checks decided what a credential
  is, each from its own list — the gate's secret scan (`mcgyvr.gate.secrets`),
  the config loader's refusal of a pasted key (`mcgyvr.config`), the sandbox's
  environment filter and its rc-file check (`mcgyvr.sandbox.base`) — and the
  lists disagreed, so a key could pass one check and be refused by the next (a
  GitHub token had to be exactly 36 characters in the gate and 20-or-more in the
  config loader; an `sk-proj-...` key whose hyphens stopped the gate's
  `[A-Za-z0-9]{20,}` run was refused only by the config loader). The value
  shapes and the name words now live in one module; each check keeps its own
  anchoring (the scan looks anywhere in a line, the config loader matches the
  whole value) and its own name rule (an exact key, a word inside a variable
  name, a word followed by `=`). The merged shapes are the widest of the old
  lists — the smaller length floor, the wider character class — so no key any
  check refused before is let through now, and three checks grew stricter: the
  config loader also refuses Stripe-shaped values, a pasted private-key block and
  the key `session`; the gate's `sk-` scan catches `sk-proj-...`; the sandbox env
  and rc-file checks recognise the full vocabulary (`auth` is no longer fenced
  to `_auth`, and an rc login line keyed by `key`/`apikey`/`credential`/`session`
  now counts, so a `.npmrc`/`.pypirc`/`.yarnrc` holding one is kept out of a
  sandbox and a run naming it under `sources:` is refused). The gate's own
  `hardcoded-credential` assignment rule keeps its separate word list.
  `mcgyvr.redact`, which only strips URL userinfo, is unchanged.

- **A reviewer answers in three words: APPROVE, APPROVE_WITH_NOTES or
  REFUSE.** The prose review prompt offered four, and two of them, REMEDIATE
  and ESCALATE, were both read as a plain refusal and nothing acted on the
  difference. REFUSE replaces both (`verify.ReviewOutcome`), and the prompt
  every reviewer is shown now lists `APPROVE | APPROVE_WITH_NOTES | REFUSE`.
  What a refusal does is unchanged. A refusal's detail, which the next attempt
  is told, now opens `REFUSE:`. For this release a reply that still opens with
  REMEDIATE or ESCALATE (a model tuned on the old prompt) is read as REFUSE,
  with a debug note on the `mcgyvr.verify` logger; the next release drops
  them, and such a reply will then be no verdict at all.

- **The two shipped data files that spelled their format version `schema` now
  spell it `schema_version`, the spelling the other four already use.**
  `data/numbers.json` and `data/hardware-classes.json` recorded their version
  under `schema`; they now say `schema_version`, matching
  `data/model-geometry.json`, `data/model-catalog.json`,
  `data/capability-table.json` and `data/task-catalog.json`. Their readers
  (`mcgyvr.derived`, `mcgyvr.estimate`) read the new key, and the test fixtures
  that write these documents follow. A file and its reader ship in one wheel, so
  nothing reads the old key and no file carries both. The wire's `v`, the
  user-written `links.json` in the data folder (still `schema`), and every
  other document's version key are unchanged.

- **A task container's build trims that repository's image cache to its
  newest `sandbox.image_cache_keep` images (default 8; `0` keeps every one).**
  `sandbox.image.prune` kept the newest 8 images, but nothing called it, so
  every dependency set a repository moved to stayed cached. Now
  `DockerSandbox` prunes after each image it builds (a cache hit builds
  nothing and trims nothing), and `prune` takes the repository's slug and
  counts and removes only images labelled with it (`slug_of`, the spelling the
  tag and the `mcgyvr.repo` label share). A repository is known by its
  directory's name: a run of a repository with another directory name,
  started in parallel, keeps the image it is about to start, while two
  checkouts whose directories share a name (`~/work/api` and `~/oss/api`)
  count as one repository and trim each other's images. An image docker
  refuses to remove because a container still uses it stays; what was removed
  is said on stderr, and a cache docker will not list is said and the task
  goes on. The setting reaches both of a run's sandboxes (`_floor` and
  `_climb`) through `cli.sandbox._sandbox_policy` and
  `open_sandbox(image_cache_keep=)`.
  Upgrading: a repository with more than 8 cached images loses the oldest on
  its next build; `mcgyvr sandbox --cache` lists what remains, and
  `sandbox.image_cache_keep: 0` keeps them all.

- **The general pool serves `mcgyvr-code` too, and a hub refuses a use case
  its pool does not serve with a new `/v1` code, `use_case_not_served` (403).**
  `hubwire.POOL_USE_CASES` had the general pool serve models raw only; the hub
  holds a ladder for general-pool coders, so it now serves all four use cases,
  as a member's own rigs, a crew's pool and a ride do. Upgrading: a setup under
  `mcgyvr-code` whose ladder step or role binds a unit of scope `anyone` (not a
  ride) was refused when read and is now taken; the check itself is unchanged
  (`serving_pool` and `pool_serves`). `hubwire` said the hub refuses a use case
  its pool does not serve, but no code for that existed and the hub did not
  read the header. `hubwire.API_ERROR_STATUS` and the rider schema's
  `x-openai-errors` now hold `use_case_not_served: 403`, named
  `hubwire.USE_CASE_NOT_SERVED`, beside `out_of_scope`; the hub change that
  reads `x-mcgyvr-use-case` follows in the hub repo. With every pool a request
  is served from serving every use case, what it refuses today is a header
  value that is not a use case; a request without the header is not checked.
  The `hubwire` text on the header and the `units.scope` reference now say
  this. `hubwire.scopes_serving(use_case)` names the scopes whose pool serves
  a use case: the list the setup check's refusal offers, kept in one place for
  the hub's refusal too.

- **The Linux CI and the release live in `.github/workflows/`, the only
  workflows the repository carries.** `ci.yml` is the full Linux suite
  (`make check`: lint, typecheck, docs-check and every test, with the pinned
  prettier and shellcheck installed so their tests cannot skip) plus the
  import check on Python 3.13 and 3.14; its job `test` is the required check,
  `ci / test (pull_request)`. `release.yml`
  builds the distribution once from a `v*` tag, checks the wheel is the tag's
  version and the notes are the tag's CHANGELOG.md section, publishes a GitHub
  release with `gh release create`, and uploads the same files to PyPI by
  trusted publishing (environment `pypi`; no token in the repository or its
  secrets). `release.yml` and the macOS/Windows job in `platforms.yml` run
  only on GitHub: a forge that also reads `.github/workflows` skips them
  instead of half-making a release or queueing for runners it does not have.
  `tests/test_release.py` reads `.github/workflows`.

- **The WireGuard helper's spec says what the product reads of a release,
  and only that.** Section 1 of `src/mcgyvr/rig/HELPER-SPEC.md` keeps the
  repository the product downloads from (`wgpin.REPO`), the tag format, the
  asset names, the archive layout and the pin rows; how the helper's own
  releases are cut and checked is no longer in the product. `wgpin.py` points
  at that section; `serving/release.py` no longer cites a design note the
  product does not ship, and defines its install order itself.

- **A Linux rig is leased by the one Python lease, as macOS and Windows rigs
  are; the bash lease scripts are gone.** A Linux rig over ssh was sent five
  bash scripts on `bash -s -- lease` (read, take a free rig, reclaim a stale
  lease, stamp, release), and every other rig the Python lease
  (`mcgyvr.serving.leasefile`), held to the scripts by a twin test. Now every
  rig over ssh is shipped that Python lease (`shipped.lease`), on the
  reader's line (`echo <base64> | base64 -d | python3 -I -B - OP '~/.mcgyvr'
  [held=ID] ['line=LINE']`), and `gatelib._LEASE_SCRIPTS` and
  `gatelib.LEASE_SHELL` are removed. The lease file (`~/.mcgyvr/lease`, one
  line), each operation's exit status and the file it leaves are the
  scripts' own over every lease state, pinned by a table test that keeps
  every case of the twin test. A Linux rig needs nothing new: its Python 3.9
  or newer already runs the shipped reader for `mcgyvr scan --rig`, which a
  serve needs before the lease, and again at gate 2. What differs there:
  each lease call starts a Python (about a tenth of a second more than bash)
  and carries the program, `mcgyvr.atomic` with it (about 27 KB), in its
  command line; its writes go through `atomic.write`, as every other rig's do;
  `~/.mcgyvr/lease.lock` appears beside the lease and two lease calls on one
  rig no longer interleave; a lease file that is a symbolic link, or cannot
  be read, is refused (status 5, and the run is not let onto the rig) where
  bash followed the link or read it as empty; a rig whose `~/.mcgyvr` (or,
  with no such folder, whose home) cannot be written answers every lease
  call with status 4, so the run is refused with "could not be read:
  Permission denied" where bash read the lease and named its holder; and the
  read makes `~/.mcgyvr` when it is missing.

- **A docker llama.cpp or vLLM unit listens on 127.0.0.1 or, behind a key
  mcgyvr makes, on every interface (`expose: local | lan`).** `mcgyvr emit`
  rendered every container's server on every interface with no key
  (`LLAMA_ARG_HOST=0.0.0.0`; vLLM's own default). Now `expose: local` is
  `LLAMA_ARG_HOST=127.0.0.1` or `--host 127.0.0.1`, and `expose: lan` is
  `0.0.0.0` plus an API key (`mcgyvr.unitkey`): 256 bits, made the first time
  `mcgyvr emit` writes the unit, kept at 0600 in `unit-keys/<host>-<port>.env`
  in the data folder of the machine that runs `mcgyvr emit` (one shared helper,
  `atomic.write_private` / `read_private`), and named by the service's
  `env_file`, so it is in no compose file and no `fleet.yaml`. A unit that
  states no `expose` is `local` when its address names this machine
  (localhost, 127.0.0.1, ::1) or it runs native, and `lan` when its address
  names another host, a locked unit too (`mcgyvr.serving.exposure`). mcgyvr's
  own requests to the unit send the key as a bearer token: a dispatch, the
  availability probe, the status poll (`/slots`), the door's `serve` probes
  (on curl's stdin, never its command line; the direct transport reads it from
  there too), the compose healthcheck (which asks `/health` of a keyed unit),
  the rig agent's relay of a ride, and what runs on the rig for `serve read`,
  a lock's sample and `fleet probe`: rig-units.sh's reads and the lock's
  harness, both handed the key on ssh's stdin with the text they run, never on
  a command line or a file on the rig. `mcgyvr fleet key <unit>` prints the
  key. A `--host` or `LLAMA_ARG_HOST` a unit's launch states renders byte for
  byte as before; native units refuse `expose: lan`; rpc workers are
  unchanged. `mcgyvr emit` names where each keyed unit
  listens, and warns about a keyed unit its launch or lock keeps on 127.0.0.1,
  a unit stating `expose: local` whose address names another host, and a
  stated host beyond this machine with no key. Upgrading:
  - a unit addressed at another host is keyed on its next emit: a client of
    yours other than mcgyvr needs `mcgyvr fleet key <unit>`, and an existing
    lock of such a unit gains the key too (`mcgyvr emit --check` reports its
    compose file changed until it is emitted again);
  - hitchhike sharing stops for a docker unit with `rider_slots` that a
    controller emits onto another machine, until the rig agent there holds
    its key: an agent that holds no key for a unit whose server asks for one
    (its config says `lan`, or the server refuses `/v1/models` without a key,
    asked once every 30 s) does not share it, and says once on its stderr
    `unit '<name>' is not shared with riders: its server asks for a key and
    this agent holds none in <data>/unit-keys/<host>-<port>.env; ...`, the
    file named for the address the agent's own config gives the unit (e.g.
    `localhost-<port>.env`). Copy the key there at 0600 (`mcgyvr fleet key
    <unit>` on the machine that emitted it). A rig that emits and serves its
    own localhost units is unaffected.

- **Two rigs behind cone NATs reach each other directly: the hub punches a
  UDP hole.** When a session's rigs have no working port forward, the hub
  offers each rig the other's reflexive address — the address its STUN
  responder saw the tunnel port at — and the two send to each other at once,
  each opening its own NAT to the other, so a pair of cone NATs settles on a
  direct path instead of the relay. The mapped address is a candidate only
  when both rigs have one and neither NAT is known to map per destination; a
  symmetric NAT never admits a peer's packet, so such a pair still takes the
  relay. Only the address the hub observed itself is offered: a rig's word
  alone never aims a peer at a third party.

- **One symmetric NAT no longer forces the relay: the birthday-paradox hole
  punch.** When exactly one side of a pair is behind a symmetric
  (per-destination) NAT and the other has a stable endpoint (cone NAT, port
  forward, owner-declared or public), the hub offers the two a ``birthday``
  candidate instead of a reflexive one: the non-symmetric side probes a
  bounded range of candidate ports on the symmetric side's public address
  (``birthday``, ``ports``), while the symmetric side sends bursts at the
  peer's stable endpoint (``birthday_burst``) so its per-destination mapping
  lands inside the probed range. 256 bursts against 1024 probes meets ~98% of
  the time (the published curve, reproduced by the hub's ``test_birthday``);
  the probe and the burst are both bounded, so a rig is never turned into a
  port scanner or an amplifier. Two symmetric NATs still take the relay.
  The wire stays version 1: ``birthday``/``birthday_burst`` are new kinds of
  the open-set ``Endpoint.kind`` and ``ports`` is an optional hint a rig that
  does not read it ignores.

- **A setup rides only the rigs it trusts: `ride_scope`, unset `crew`, and
  `private`.** A relief rung's requests name the narrower of its own scope and
  the setup's new `ride_scope` (`own`, `crew` or `anyone`, the wire's scopes,
  narrowest first: `hubwire.narrowest_scope`), so the hub refuses a ride on a
  host outside it before the host sees it. Unset is `crew`: your own rigs and
  your crewmates'. A setup whose relief rungs were synced before (every one
  written `scope: anyone`) now rides only its own and its crewmates' hosts,
  fan-out included, until it opts in with `mcgyvr rig rungs sync --ride-scope
  anyone`, which writes the policy line and shows the hub's privacy text as it
  does; a sync now writes the setup's `ride_scope` on each rung and says whose
  rigs take its rides (the rig's refresher says the same line once). A ride
  the hub refuses as outside that scope (`403 out_of_scope`,
  `hubwire.OUT_OF_SCOPE`) is a full rung: one note names the rung, the scope
  and the opt-in, the climb and fan-out move on with no attempt spent, and the
  rung is not asked again in that process. Under `ride_scope: own` the sync
  says no relief rung serves the setup (the hub never lists your own rigs as
  rungs). `private: true` rides no relief rung: a sync and the
  rig's refresher refuse before the hub is sent anything, a rung already kept
  is not ridden, and a ladder step or a role naming one is refused.
  `deployment: local-only` is unchanged (it says mcgyvr is the backend, not
  that nothing leaves). `mcgyvr use` and the opt-in share one policy-line
  writer (`mcgyvr.policy_line`).

- **The programs shipped to a rig are assembled from the modules they import,
  and run on Python 3.9.** The reader, the fetcher, the lease and the native
  launcher each go as one program built at ship time
  (`mcgyvr.serving.shipped`): `hostos`, the wire's names from `hubwire` and the
  module itself, so the reader and the fetcher keep no copies of `hostos`
  (the weights folder, the process group, the nvidia-smi.exe lookup are
  `hostos`'s) and the reader names the system, the resource kinds and the
  figures the wire names. They run on the oldest Python a rig has, macOS's own
  `python3` (3.9), and refuse an older one with a sentence. The reader's line
  is about 52% of the one ssh argument Linux allows (it was 36%).

- **The Linux llama.cpp image is pinned to the native build: `server-cuda-b11960`**
  (was the floating `server-cuda`), so a container and a native binary of one
  split are one build. A fleet already stamped keeps the `image` its units
  state (a stamp fills only an empty one); `mcgyvr emit --check` reports a
  compose file emitted with the old tag as changed until it is emitted again.

- **mcgyvr imports, and keeps its files, on macOS and Windows too
  (`mcgyvr.hostos`, #810).** One module answers what differs between the three
  systems: file locks (`flock`, or `msvcrt.locking` of one byte past the end
  of the same lock files), the user, private modes, opening without following
  a link (or a junction), child process groups and their kill, the stop
  signals, whether a pid lives, the boot id, and the data, cache and
  per-user temporary folders. The lock, uid, mode, link and process-group
  calls go through it (`rigscan` and the fetcher, shipped to a rig alone,
  keep tested clones), so `import mcgyvr.cli` no longer needs `fcntl`, and
  Linux makes the very calls it made. On macOS the data folder defaults to
  `~/Library/Application Support/mcgyvr` and the caches (the index, the
  weights) to `~/Library/Caches/mcgyvr`; on Windows to `%LOCALAPPDATA%\mcgyvr`
  and `%LOCALAPPDATA%\mcgyvr\cache`. `$XDG_STATE_HOME` and `$XDG_CACHE_HOME`
  still win when set, the config folder stays `~/.mcgyvr` everywhere, and
  `journal.dir` still defaults to `~/.local/state/mcgyvr/journal`. With no
  `$SHELL`, setup offers the PATH line for `~/.zshrc` on macOS. Windows checks
  no file owner or mode (`chmod 600` and the token store's refusals do not
  apply there): a file is as private as its folder's ACL, the user's alone in
  the profile folders mcgyvr makes by default. A `platforms` workflow runs the
  import and these tests on macOS and Windows. Upgrading on macOS: move what
  is under `~/.local/state/mcgyvr` except `journal/`, and `~/.cache/mcgyvr`,
  to the new folders, or keep them with the XDG variables (the weights, which
  no XDG variable moves, with `$MCGYVR_WEIGHTS`).

- **A Mac's rig id changes once, and the reader ships packed.** A Mac had no
  machine-id file, so its id was hashed from its host name; it is now hashed
  from its IOPlatformUUID, with its unified GPU named in it, so a fleet lock
  that pinned a Mac's rig id names it again after one `mcgyvr scan`. The
  reader the door ships over ssh goes as one zlib-packed program (the line is
  about a third of its old length), since its source in base64 neared the
  128 KiB Linux allows one argument; the line's shape is unchanged. (#809)

- **Under `mcgyvr-code` an unset `fanout` is `idle` and an unset `triage` is
  `jev` while a Jev unit is bound and on (`none` when Jev is off).** A raw use
  case keeps both `none`, and a stated value wins. `idle` takes the first own
  rung with a slot free, or rides a relief rung when your own rungs are full.
  `mcgyvr setup` writes both keys unset so the use case decides them.
- **Fan-out never sends a contract to a priced api rung.** Under `idle` or
  `full`, a contract whose own rungs are all full waits on its own ladder
  instead of entering at an api rung (`idle` first rides a free relief rung),
  and inside the api family the rungs are taken in ladder order. Escalation
  still climbs to the api rungs.
- **Use cases are `mcgyvr-code`, `code`, `chat` and `agent`; `coding` is gone,
  with no alias.** `mcgyvr-code` is what `coding` was, every stage between the
  model and you on by default, each under a policy switch (SETUP.md, *Use cases
  and switches*); it is also what a policy that names no use case means.
  `code`, `chat` and `agent` serve the model raw: `mcgyvr PROMPT` and `mcgyvr
  direct` refuse under them (exit 3, `use_case_raw` in the delegate log)
  before any model, gate or proposer is touched, and only `mcgyvr-code`
  provisions a local proposer. A config, `setup --use-case` or `mcgyvr use`
  naming `coding` is refused, naming both. The interactive setup asks for one
  of the four with no Enter default, and asks the Jev question only for
  `mcgyvr-code`. Under `mcgyvr-code`, a batch defaults to `--jobs auto` and
  proposals are authored by the classifier when a Jev unit is bound
  and on. The model catalog's `coding` kind is `code` (`recommend --profile
  code`), and the task catalog's task types belong to `mcgyvr-code`.
  Upgrading: a setup written before this says `use_case: coding` and no longer
  loads; `mcgyvr use mcgyvr-code` rewrites that one line and nothing else.

### Added

- **The release can be rehearsed, on GitHub and locally, and publishes nothing
  when it is.** `.github/workflows/release.yml` takes a `workflow_dispatch`
  input `dry_run`, true by default: `gh workflow run release.yml --ref
  <branch>` builds once, checks the wheel's version, takes the CHANGELOG
  notes, runs `twine check`, keeps the files on the run and writes a job
  summary, and the GitHub release and the PyPI upload are skipped. From a
  branch the version is stamped from the newest CHANGELOG section
  (`scripts/release/changelog_notes.py --latest`), and when that version is
  already tagged on another commit the run stays green and its summary says so
  in `make release`'s words; `dry_run: false` is refused unless the ref is a
  tag. The workflow now names no repository: `gh release
  create --repo "$GITHUB_REPOSITORY"`, so a fork's tag makes the fork's
  release. The jobs are `build` → `github-release` → `pypi` (the release moved
  out of `build`, which now holds only `contents: read`), and a tag run also
  runs `twine check` (twine 7.0.0, pinned in the workflow and the Makefile
  alike; nothing is added to `pyproject.toml` or `uv.lock`) before anything is
  published. `make release` runs the
  same local half into `build/release/` and prints the tag command; it tags,
  pushes and uploads nothing, and refuses a tree that differs from HEAD or a
  version tagged on another commit. README gains a Releasing section: what a
  tag does, the version and notes rule, both rehearsals, the secrets (none
  stored; the PyPI trusted publisher and the `pypi` environment), and how a
  fork releases.
- **A rig's hello names each model's quantisation (`quant`), so a hub can plan
  by the wire's decode rule.** The hub's planner bounded a device's decode
  speed by its memory bandwidth alone, because the rig never said a model's
  quantisation and `hubwire.decode_ms_per_gib` needs one. `ModelInfo` now
  carries `quant`, the quantisation the file's name spells (`Q4_K_M`, `BF16`),
  read by `knowledge.hub.quant_of`, the reading the product's own decode
  estimate takes; a name that spells none (a split model's first part among
  them) sends none. The field is in the hub's published schema
  (`hubwire_schemas/protocol.schema.json`) as an optional short tag. It is
  additive: a hub from before it ignores the field (its models read with
  `extra="ignore"`), and a hub that reads it plans without it for an agent
  that does not send it.

- **`serving.start_timeout_s`: how long the serving door's `serve up` and
  `serve wake` watch a unit come up.** The door polled each unit 120 times, three seconds apart,
  and then reported it down, with no way to wait longer for a load that needs
  it, such as a large vLLM unit read off a slow disk. The key states the
  limit in seconds (unset: 360, the same six minutes; at least one poll is
  always made; a negative value is refused when the config is read). The
  serve step reads it from the config gate 1 read, so `mcgyvr serve wake` and
  a run that wakes a card through the door are bounded by it too. That config
  is the one `$MCGYVR_CONFIG` names, else the live fleet's, never a `--config`
  path given to the command that started the door. A config the step can no
  longer read, or one that is no longer the config gate 1 read (a `mcgyvr
  fleet use` in between), is refused (exit 2) before anything starts.
  `HEALTH_POLLS` is gone:
  `servelib.wait_for` takes `timeout_s`, and `health_polls` says how many
  polls it buys (I-53).

- **`mcgyvr usage` reads the journal back, and a row of a layout it does not
  know is refused.** Every run appended rows under `journal.dir`, and nothing a
  user ran read them: `telemetry.fold` was called only by tests, and the layout
  `version` stamped on each row was checked by nothing. `mcgyvr usage [JOURNAL]`
  folds each `<session>.jsonl` in the journal (or one named file) with
  `telemetry.fold` and prints, per run and per rung, the attempts, how many
  answered, the input and output tokens the rows reported (`-` when none did),
  the summed `elapsed_s`, and the verdicts the attempts folded to; corrections
  that name no attempt are counted apart. With no argument it reads the
  `journal.dir` of the setup a run here would use (`--config PATH` names
  another), and an empty or not-yet-made journal says so and exits 0. `fold` now
  raises `telemetry.JournalVersionError` for a row whose `version` is not
  `TELEMETRY_VERSION` (`1`) or is missing, naming the file, the line and the
  version; `usage` prints it and exits 1. Damaged lines are still skipped as
  before. `config.journal_dir` is the one resolution of `journal.dir` that
  `direct`, `mcgyvr PROMPT` and `usage` share.

- **The README says which NVIDIA cards each pinned engine runs on (I-124).**
  A new *GPUs and engines* section gives the lowest compute capability of the
  llama.cpp `b11960` container and native archives (5.0 on CUDA 12, 7.5 on
  CUDA 13) and of the vLLM `v0.26.0` image (7.5), says that CUDA 13 drops every
  card below 7.5, and names `MCGYVR_NATIVE_BACKEND` for an older card whose
  driver would get the CUDA 13 native build. It replaces `docs/GPU-SUPPORT.md`,
  which left main with the docs/ archive (16acf4884); its last version is
  tagged `archive/gpu-support-on-main-pin`. The engines mcgyvr does not pin are
  left out, and every floor was read again from the pinned builds.

- **A worker rig tells the hub which models its tensor cache holds
  (`hello.weight_cache`), so the hub plans a cheaper load there.** The cache
  names each file by the FNV-1a hash of one tensor, and the hub names weights
  by the sha256 of the model file, so the agent now keeps a record beside the
  cache folder (`<folder>.models.json`, mode 0600, `tensorcache.Record`): when
  a worker session that `worker_start.model.digest` named gives the cache back,
  each file it stored is recorded under that digest. A hello names a digest
  while the ledger vouches for every file recorded under it (a model one of
  whose files a trim or a check removed is forgotten), at most `MAX_MODELS`,
  the newest, and only from a rig that lends the worker role with its cache
  shared. A file stored by a session that named no digest is never reported,
  nothing is named after a reboot until the folder is checked again, and a
  hello says what the last check saw: the hub learns of a new model at the
  next hello. A rig with nothing recorded sends the same hello as before.
- **A contract with `output_schema: unified_diff` runs: the model answers with
  a diff, and it is applied, gated and delivered as a whole file is.** Such a
  contract passed `mcgyvr contract` and was then refused when the run built its
  prompt ("only 'whole_file' is implemented"). Now the user message asks for one
  fenced ```` ```diff ```` block of the target alone, and the language bundle's
  first output rule says the same (`worker.bundle.for_reply`; that text is
  marked unmeasured, the whole-file bundle is sent byte for byte as before).
  The reply is read strictly (`worker.reply.parse_diff`): the target on both
  sides, behind `a/`/`b/` or not, at least one hunk, hunk lines only, and
  `--- /dev/null` only for a target with no content yet. A diff that names another file or a
  second file, deletes, renames, copies, changes a mode or is binary is refused
  before anything is applied. `git apply --recount` (through `gitcmd.run_git`)
  then applies it, all or nothing, onto the content the prompt showed, in a
  scratch directory git is kept from climbing out of; context must match
  exactly. The whole resulting file goes to the gate and delivery unchanged, and
  a result with no code left is a refusal, as it is for a whole file; so is a
  block with no code in it (comments only, or a JSON status), before it is read
  as a diff, so the model is not told to guess one. Every
  refusal, a context mismatch included, is a named `ReplyError`
  (`malformed-diff`, `diff-outside-contract`, `diff-many-files`,
  `diff-not-a-text-edit`, `diff-does-not-apply`), so the draw fails and the next
  attempt is told why, as for a malformed `whole_file` reply. A
  `unified_diff` contract written by hand now needs `stop_conditions`, as a
  `whole_file` one always did. `worker.prompt.UnsupportedSchemaError` is gone:
  every schema the contract field accepts (`contract.OUTPUT_SCHEMAS`) has an
  output rule and a parser. `whole_file` contracts are sent and read exactly as
  before.

- **The hub says whether a member may host strangers, and the rig prints it.**
  A member's rigs serve strangers (the general pool's `anyone`, riders on their
  units) only after a hub admin approves that member once; nothing on the wire
  said so, so `mcgyvr rig status` and `mcgyvr rig share` could not tell a host
  why they served nobody. The hello's ack now carries `hosting_approved`
  (`hubwire.HOSTING_APPROVED_FIELD`, a boolean, optional so an older hub that
  omits it changes nothing): the agent keeps it in its state, and `rig status`
  and `rig share` print "approved to host" or "waiting for admin approval" when
  the hub has said — as of the agent's last connect, since only the hello ack
  carries it (a mid-session approval shows after the next reconnect), and only
  for the hub this machine is joined to now. The shipped `protocol.schema.json`
  gains the optional field on `AckBody`; the hub sends it at its next pin.

- **A ride is sealed end to end, rider to host: the hub carries ciphertext.**
  The host's agent makes an X25519 key each time it starts (`mcgyvr.seal`, in
  memory only) and names it on every unit it advertises (`unit_advert`'s
  `seal`); the hub lists it with the rung, and `mcgyvr rig rungs sync` keeps it
  in `relief.yaml` (`relief.<rung>.seal`). Every request to a keyed rung, a
  dispatch's and a Jev decision's alike, is sealed to it (X25519, HKDF-SHA256,
  ChaCha20-Poly1305; `hubwire.SEAL_SUITE`): in clear go only `model`, `stream`
  and `stream_options` (`hubwire.SEALED_CLEAR_FIELDS`). The agent opens it,
  holds it to the fields the hub passes a unit (`hubwire.FORWARDED_FIELDS`,
  the hub's `max_tokens` cap), and seals the answer back event by event, each
  event bound to its place; only its model and token counts stay in clear,
  for the hub to name and charge it by (`hubwire.SEALED_ANSWER_CLEAR_FIELDS`).
  An answer that does not open is a protocol error. A key the unit no longer
  holds (its agent started again) is answered `503 seal_key_unknown`, now one
  of `hubwire.RUNG_BUSY`: the rung is passed over, said once, and held out for
  the rest of the run until `rungs sync` writes the new key. A ride the agent
  cannot open, or one outside the bounds the hub holds a clear request to (now
  hubwire's: `CHAT_MAX_MESSAGES`, `CHAT_MAX_TOOLS`, `CHAT_MAX_STOP`,
  `CHAT_MAX_TOP_LOGPROBS`, `MESSAGE_ROLES`, `MESSAGE_FIELDS`, `CHAT_RANGES`),
  ends `bad_seal` and reaches no unit; the rider holds its own request to the
  same bounds before sealing it and refuses one outside them as the hub's `400
  invalid_request` would, unsent, so it never reads as a stale key. Each rung
  `rungs sync` keeps says
  `sealed <kid>` or `in clear`, and a rung that was sealed and comes back
  keyless is noted, by the sync and by `rig run`'s refresher; `rig run` says its
  run's key id when it first advertises a unit, and loads no cipher on a rig
  hosting nothing. A rung with no key (an older hub or agent) is asked in
  clear as before, and so is everything that is not a ride. New dependency:
  `cryptography>=44`. Upgrading: an older product cannot load a `relief.yaml`
  a sync by this one wrote with a `seal` (`unknown key 'seal'`): remove
  `relief.yaml`, which a sync rewrites whole, and sync with the older one. SECURITY.md says where plaintext still is.

- **A rig lends host memory and cores, and its hello says exactly what it
  lends (#822).** `mcgyvr rig share` (or `rig lend`) `--ram-mb N --cpu-cores
  N` lends memory and cores to the heads it runs (0, the default, lends none):
  a head's container is given the memory lent and held to the cores lent, and
  llama-server to that many threads; an amount under the hub's lending floor
  (`hubwire.LEND_FLOOR_MB`, `LEND_FLOOR_CORES`) is refused naming the floor,
  and so is RAM of a DDR generation under `hubwire.RAM_DDR_MIN` (read on
  Windows from each module's SMBIOS type; unread elsewhere, where RAM counts
  by its size alone). Memory past what is available less a headroom, cores
  past all but one, and a listed card under its kind's floor are refused too.
  The hello carries the lent resources (`resources`, hubwire's contract) and
  the host it runs on; its `cards` are now the cards those make
  (`hubwire.cards_from_resources`), not every card the machine has, so a rig
  that lends nothing names no card, and the heartbeat re-reads the lent
  resources. A card's memory bandwidth, which the reader does not read, is its
  class's estimate from `data/hardware-classes.json`, labelled so. A rig
  lending no card offers the head role alone and heads no pipeline (memory and
  cores serve whole models, never a pipeline stage); a Mac or Windows rig
  offers no session role, so lends nothing, until a native session host runs
  there. `mcgyvr rig status` names what is lent and, with your personal hub
  key in `$MCGYVR_HUB_API_KEY`, your credits. The native build's arch and
  `nvidia-smi` are now the machine reader's. Deploy a hub that reads resources
  first: a card whose free memory was not read goes out with `free_mb` unset,
  which such a hub marks unread and an older hub, reading the cards alone,
  takes as all free.


- **A plan says how fast its model decodes, and a unified GPU's memory is
  counted once (#817).** `data/hardware-classes.json` states the memory
  bandwidth of Apple silicon chips and NVIDIA consumer cards, each row with
  its source page and the words quoted (or, for a table row, a summary of its
  cells) and whether that source was read cleanly (`verified`).
  `mcgyvr.estimate` matches a device to its class by name (an NVIDIA card then
  by its memory, a chip by its GPU cores or the machine's memory, the slower
  variant, said so, when those are unread; no class, no estimate) and
  estimates decode as bandwidth over the bytes a token reads: 0.75 of it for
  16- and 8-bit weights and 0.60 for 4- to 6-bit, fitted under llama.cpp's
  Apple-silicon table (discussion 4167), with an Apple chip from 800 GB/s up
  at most 0.50 and 0.40; an NVIDIA card's estimate says the shares were
  fitted on Apple silicon. A mixture of experts reads its shared weights and
  the experts it uses. The plan of `mcgyvr recommend` states its placement's
  `decode_tok_s` as the live fleet's measured speed for that model at that
  host (a `reading`, `fleet.lock.decode_readings`), else that `estimate`,
  else why there is none, and each card's class bandwidth (an estimate for
  that card). `estimate.usable_unified_mb` states a Mac GPU's memory as the
  reader sizes it: the wired limit, else three quarters of memory (estimates),
  or the working set llama.cpp logged (a reading). Sizing on a unified GPU
  now weighs spilled experts, a mapped blob and co-resident units against the
  host memory the GPU leaves, in a unit's fit, a plan's fit and a claim; a
  card with its own memory is sized exactly as before. A split prices a
  CUDA-measured scratch reading only on CUDA cards
  (`vramfit.MEASURED_SCRATCH_BACKEND`).

- **The machine reader reads macOS and Windows.** On a Mac (Apple silicon) the
  GPU that shares the memory is read as one `unified` card: its size is the
  share the kernel lets it take (`iogpu.wired_limit_mb`, else three quarters
  of the memory), always labelled an estimate, its free memory is what the
  machine has available, and the rig id holds when that cap moves. Memory comes
  from `sysctl` and `vm_stat`, so a Mac keeps its memory section; the machine
  id is its IOPlatformUUID. On Windows one PowerShell CIM call reads memory,
  CPU, system and display adapters (never `wmic`), nvidia-smi.exe is looked
  for on PATH, in System32 and in the NVSMI folder, a card no tool sizes is
  listed unsized under Vulkan, and the machine id is the registry's
  MachineGuid. Every reading now carries `host` (`os`, `arch`, `version`),
  `cpu` (`model`, `cores`, `threads`, `performance_cores`) and `resources` in
  the hub's resource contract (a sized card, host RAM, the CPU); each card
  names its `kind` and `backend`. `mcgyvr detect` and `mcgyvr scan` print the
  system, a card's backend and the CPU model, and say when a size is an
  estimate. A Linux machine reads as before and keeps its rig id. A Mac's
  unified GPU is not lent yet: a lent card is served by a CUDA worker in a
  container, and it joins lending with native launch. (#809)

- **A Mac or Windows rig lends a pooled head natively through its pinned
  helper (#823).** `mcgyvr rig share --launcher native --endpoints HOSTS` on
  macOS or Windows needs no engine image: the rig's sessions run through
  `mcgyvr-wg`, a userspace WireGuard helper (no TUN device, no admin
  rights), one per session, whose release mcgyvr pins by tag and sha256
  (`mcgyvr.rig.wgpin`) and fetches as it fetches llama.cpp. Its first
  release, `v0.1.0`
  (https://github.com/AdarGit008/mcgyvr-wg/releases/tag/v0.1.0), is pinned
  for macOS and Windows on arm64 and x86_64 (and for Linux, whose rigs do
  not run it), so such a rig now offers the head role where it used to say
  `roles: none offered`; its head's API asks a key of the session's own
  (Security, below). The helper holds the session's key and UDP socket and
  starts the pinned llama-server as its own child on 127.0.0.1 alone, the
  head reaches each worker only through a forward that accepts the head's
  own process and dials only that worker through the tunnel, and each
  process is recorded so a head left behind is ended by the next teardown or
  sweep. Such a rig offers the head role alone (a worker is refused
  `not_capable`), names the pinned build as its runtime, and does not list
  `traversal` yet, so the hub pairs it with rigs on its own LAN. A Mac or
  Windows machine reads no network interface yet, which is why it names
  `--endpoints`. On Linux the launcher changes nothing: the session layer
  reaches its machine through one host, and the docker host asks the daemon
  exactly what it asked before. A locked native unit whose `role` is `rpc`
  renders as `ggml-rpc-server` bound to the IPv4 address its `-H` states,
  one a worker may listen on (`llamacpp.worker_may_listen`), not as a server
  on the loopback. That rule is now an allow-list, for container fleets too:
  an rpc worker binds an address of a private network (RFC 1918: 10/8,
  172.16/12, 192.168/16) or an overlay's (RFC 6598: 100.64/10) and nothing
  else, so a link-local or documentation-range bind is refused.
- **A rig names the llama.cpp RPC protocol it speaks.** A rig running the
  pinned build, natively or as the pinned image, sends
  `capabilities.rpc_proto` (`hubwire.RPC_PROTO_FIELD`; b11960 speaks 8.0) in
  its hello, so that once the hub reads it, it pairs a head only with workers
  `hubwire.rpc_compatible` allows; a rig on another image sends none.

- **A Mac or Windows machine is a remote rig over ssh (#824).** A rig's first
  contact is sent the POSIX reader line as every rig always was; a rig whose
  shell cannot run it is asked the PowerShell question, and a Windows rig
  (OpenSSH, with cmd.exe or PowerShell as its shell) is sent every program by
  one constant `powershell -NoProfile -NonInteractive -EncodedCommand` line
  that finds a Python 3.9 or newer (`py -3`, then `python`), writes the program
  with WriteAllBytes under `%LOCALAPPDATA%\mcgyvr\tmp`, runs it with `-I -B`
  and removes it; the program, its arguments and what it reads on its own
  stdin (the fetcher's job, which holds a token, never on disk) travel on
  stdin, so no path or argument is ever read as PowerShell. `mcgyvr scan --rig` files the reading, whose
  `host.os` the door reads from then on, asking nothing. On a rig whose file
  records macOS or Windows: the lease is the one Python lease this machine
  runs itself (Linux rigs keep their bash scripts, unchanged); `serve up`,
  `down` and `fetch` run the native launcher there, shipped like the reader,
  each unit on 127.0.0.1 under a supervisor that runs a copy the launcher
  leaves in `bin/shipped/` under the rig's mcgyvr home; what holds the rig
  (gates 2 and 7, `read`) is the launcher's twin of rig-units.sh; the health
  probe names `curl.exe` on Windows. `emit` and `setup` write `launcher:
  native` for a llama.cpp unit on such a rig. `read --probe`/`--load` (the
  lock's harness) and pooled sessions stay Linux's. A Linux rig is sent, byte
  for byte, the commands it was sent before. Upgrading: a Mac rig scanned
  before this release has a reading that names no system and is taken as
  Linux; `mcgyvr scan --rig NAME` once makes it a Mac rig.

- **mcgyvr runs on macOS and Windows: the Mac/Windows layer.** One entry for
  the layer as a whole; each part keeps its own entry here. The OS seam
  (#810): `mcgyvr.hostos` answers what differs between the systems, the CLI
  imports everywhere, and data and caches go to each system's own folders. The
  machine reader (#809) reads macOS and Windows, and a Mac's GPU is one
  `unified` device whose memory is always labelled an estimate. Estimates
  (#817): a plan states its decode speed as a reading, or as an estimate from
  a sourced bandwidth table, and counts unified memory once. Native launch
  (#818): `launcher: native` runs the pinned llama.cpp build (b11960) with no
  container, on 127.0.0.1 alone. Setup and docs (#821): `mcgyvr setup` names
  what it starts (native llama.cpp servers on this Mac or Windows machine,
  containers elsewhere) and says first that the pinned build is fetched and
  checked and that no firewall is expected to ask. On Windows its PATH offer
  writes `$env:Path = "$HOME\.local\bin;$env:Path"` to the profile PowerShell
  names, found by full path (PowerShell 7's when installed), and where the
  execution policy runs no profile it writes none and names `uv tool
  update-shell`. `skills/mcgyvr/install.ps1` installs the skills on Windows,
  the twin of `install.sh`, and both now skip a record line naming a file
  outside the skill folder; the README installs in three lines per system.
  SETUP.md's *macOS and Windows* (docgen) names each system's folders, the
  native launcher and its backends, the firewall and quarantine, long paths,
  and the commands that start `mcgyvr rig run` at login (a launchd agent on
  macOS; on Windows, a Startup-folder line). A failed `mcgyvr serve` names
  the door's log in this system's data folder, and the door's `--help` names
  each system's weights folder.

- **A unit runs natively, with no container: `launcher: native` (#818).** The
  llama.cpp build mcgyvr pins (b11960, `mcgyvr.serving.llamacpp`; the Linux
  image is the same build, `server-cuda-b11960`) is fetched on first use into
  `bin/llama.cpp/<tag>/` under the mcgyvr home, checked against the size and
  sha256 committed for each archive, unpacked so no member lands outside its
  folder, cleared of macOS's quarantine flag, and kept up by mcgyvr's own
  supervisor: one per unit, restarting a server that exits with a doubling
  pause and giving up after five crashes running, its log in
  `logs/<container>.log` under the data folder. The build is Metal on Apple
  silicon; CUDA where `nvidia-smi` reads a driver one of the pinned CUDA
  builds runs, else Vulkan where a Vulkan loader is installed, else the CPU
  (`$MCGYVR_NATIVE_BACKEND` names one instead). A native server listens on
  127.0.0.1 alone (the rig agent relays to it), and runs only on the
  machine mcgyvr runs on (`--host localhost`). The door's
  `serve up`/`down` start and stop native units, gate 3 asks no daemon of
  them, and `mcgyvr serve status --host localhost` lists them; `serve
  sleep`/`wake` refuse them (no sleep route: down, then up). The working set
  Metal reports at start-up (`recommendedMaxWorkingSetSize`) is filed as a
  reading. `setup` writes `launcher: native` for a llama.cpp unit on the Mac
  or Windows machine it runs on; a unit stating no launcher is a container,
  as before.
- **The rig that is this machine is reached without ssh** where it runs no
  sshd: always on macOS and Windows, on Linux when nothing listens on port 22
  (`$MCGYVR_LOCAL_TRANSPORT=direct|ssh` decides instead). The door runs the
  rig's steps here: the shipped readers and the fetcher on its own
  interpreter, health probes with urllib, the lease in `~/.mcgyvr/lease` in
  Python, and nothing else; `docker` talks to the local daemon, and Docker
  Desktop's `docker-desktop` stands for this machine. Where `/proc` cannot
  prove a gate descends from the door, a one-time secret the door hands down,
  whose digest waits in a 0600 file while the door lives, proves it. On
  Windows the door runs its `ssh`/`docker` shims by argv (with `.cmd`
  launchers beside them) and hands a gate its export pipe as a handle.

- **What a rig lends is defined once, as resources, in `mcgyvr.hubwire`
  (#812).** A `Resource` (`gpu`, `unified`, `ram` or `cpu`; `RESOURCE_KINDS`)
  names its index, name, MiB lent and free with whether they are an estimate
  or a reading (`figure`, one of `FIGURE_KINDS`), cores (`cpu` alone), memory
  bandwidth with its own `bandwidth_figure`, and its backend
  (`RESOURCE_BACKENDS`: `cpu` for host memory and cores, never for a card); a
  `unified` device's memory is the host's (`shares_ram`). `validate()`
  refuses a break by the field at fault. `resources_fit` holds an advert to
  `MAX_RESOURCES`, each kind and index once, at most `MAX_CARDS` cards with
  each card index once, and one `ram` and one `cpu`; `ResourceReading` and
  `readings_fit` are a heartbeat's. A `Host` names its `HOST_OS`, `HOST_ARCH`
  and version. `cards_from_resources` and `card_readings_from` make the legacy
  `cards[]` of a hello and a heartbeat from the `gpu` and `unified` ones, and
  `STANDBY_UNITS` names the unit standby is counted in per kind (names only);
  `LEND_FLOOR_MB`, `LEND_FLOOR_CORES` and `counts_as_lent` say the least a
  resource lends to count as lent (a 1 MiB card or one core earns nothing):
  2048 MiB for a `gpu`, 4096 for a `unified` device, 8192 of host `ram`, two
  `cpu` cores. A `ram` resource may name its DDR generation (`Resource.ddr`,
  1 to `MAX_RAM_DDR`, `ram` alone); one known to be older than `RAM_DDR_MIN`
  (DDR4) never counts, and one whose generation the reader could not tell
  counts by its size. The shipped protocol schema carries `ddr` on a resource;
  `FIGURE_ESTIMATE` and `FIGURE_READING` name the two figure kinds.
  A `cpu` resource serves whole models only, never a pipeline stage. The rig
  agent's card rules (`rig.protocol.CARD_NAME`, `CARD_NAME_MAX`, `MAX_MB`,
  `MAX_CARD_INDEX`, `MAX_CARDS`) are now these names, imported. The shipped
  `protocol.schema.json` is the hub's with `resources[]` and `host` on a hello
  and `resources[]` on a heartbeat, and the tests hold every value above to
  it. `RpcProto` names the llama.cpp RPC protocol a rig
  speaks (`RPC_PROTO_FIELD`), and `rpc_compatible` says which workers a head
  may take: llama.cpp's own rule, the same major and no newer minor. Nothing
  sends resources yet. Ruff now refuses a raw bidirectional control character in
  source (`PLE2502`).

- **The wire names each value it holds, and carries a member's lending, a cpu
  head device and the decode rule (#814).** Each backend, OS and arch has its
  own name (`BACKEND_CUDA`..`BACKEND_CPU`, `HOST_LINUX`/`HOST_DARWIN`/
  `HOST_WINDOWS`, `ARCH_X86_64`/`ARCH_ARM64`), and `RESOURCE_BACKENDS`,
  `HOST_OS` and `HOST_ARCH` are built from them, in the same order. An advert
  names at most one `unified` device (`ONE_PER_RIG`: one unified device, one
  `ram`, one `cpu`; `resources_fit` refuses a second); `readings_fit` no
  longer counts a kind, as a hub reads only what the advert named.
  `STANDBY_UNIT_SIZE`
  sizes the standby unit a hub pays by (a card, 16384 MiB of host memory, 8
  cores) and `STANDBY_UNITS`' names are made from it. `HEAD_DEVICE_KINDS`
  (`local`, `rpc`, `cpu`) names the devices a `head_start` may list; the rig
  agent reads them by these names and starts a `cpu` device as a whole model on
  the host's cores and memory (see the cpu-head entry above).
  `Lending` is what a member chooses to lend on a rig (card indexes, each
  once, null for every card, empty for none; host memory in MiB; cores; each
  0 or at least its lending floor), carried in the hello's ack as `LENDING_FIELD`. `rpc_incompatible`
  (503) joins the `/v1` error table beside `no_path`. The shipped protocol
  schema carries the ack's `lending`, `capabilities.rpc_proto` and a `cpu`
  head device; the rider schema carries `rpc_incompatible`.
  The decode rule a hub plans by is here, stdlib only: `DECODE_EFFICIENCY`,
  `HIGH_BANDWIDTH_GBPS`, `HIGH_BANDWIDTH_EFFICIENCY`, `FITTED_ON`,
  `QUANT_CLASSES`, `quant_class`, `decode_efficiency` and
  `decode_ms_per_gib` (milliseconds a token takes per GiB of weights).

  `decode_ms_per_gib` (milliseconds a token takes per GiB of weights), each
  naming the vendor; `fitted_on(kind, backend)` tells a hub, which sees no
  vendor, when a device is of the fitted one (a unified Metal device).
- **`mcgyvr rig crew sync` keeps the units your crews lend you in `crew.yaml`
  (#829):** scope `crew`, units a step or a role binds, never api rungs.
- **A unit says whose it is, and a role or a ladder step may bind a hub unit
  (#811).** Every unit has a `scope` (`own`, `crew` or `anyone`; a unit of your
  fleet is `own` unless it says otherwise, and `mcgyvr rig rungs sync` writes
  `anyone` on each relief rung), and every chat request names it in
  `x-mcgyvr-scope` beside the use case. A ladder step or `orchestrator`,
  `verifier` or `jev` may name a relief rung; one the ladder names is a step
  and no longer ridden as relief. The pool a unit is served from is the
  wire's (`hubwire.SCOPE_POOLS`, `hubwire.serving_pool`), and a step or role
  bound to a unit whose pool does not serve the use case is refused when the
  setup is read: under `mcgyvr-code`, a unit of scope `anyone` that is not a
  ride. `code`, `chat` and `agent` run on any scope. Upgrading: a unit under
  `units` that points at a hub and states no `scope` now sends `own`, where
  before it sent nothing and the hub used your own serve scope (`anyone`
  unless you changed it); state `scope: crew` or `scope: anyone` on it.
- **`mcgyvr use NAME` switches the use case, and `/mcgyvr-use` is its skill.**
  It rewrites the policy's `use_case:` line and nothing else, and says what
  that turns on or off.
- **A switch for each stage that had none.** `gate.enabled` (off: no language
  rung or acceptance command runs; scope, secrets and structured-data parse
  still refuse; the change is labelled `ungated`, delivery skips its re-gate
  and no repair runs), `jev.enabled` (off: every typed decision is asked as if
  no Jev unit were bound), `infer_dependencies` (off: a batch is ordered by
  `depends_on` alone) and `same_file: wait|parallel`.

- **A proposal the decomposer refuses goes back to the proposer once (#802).**
  After vetting, each refusal that names a proposal field is handed back with
  the refused proposal and its `what_to_change`: prose is shown them as data
  (`mcgyvr.repropose.render`, in the shape of a re-plan), the classifier asks
  the refused field again through `iterate.reask`, the one re-ask the W6 loop
  takes too. What comes back is vetted again; what is still refused is
  reported. A refusal of the request, or a catch-all, is reported at once.
  `max_reproposals` (default 1, beside `max_replans`) bounds the rounds; 0 is
  what `decompose` was. The `mcgyvr.delegate_log/1` record's `detail` counts
  `refused`, `reproposed`, `recovered` and `still_refused` (additive, no new
  kind), and under `--log PATH` the classifier's typed decisions — every field,
  `split` and `partition` answer, with its model — are recorded beside it, in
  `PATH.decisions.jsonl`, named by `detail.decisions`.
- **Classifier authoring splits each proposal until one file and jev says no
  (#799).** With `orchestrator.authoring: classifier` and a jev unit bound,
  `mcgyvr.refine.RefiningProposer` breaks the classifier's proposal down again
  and again: a scope over several files becomes one proposal per file, and a
  one-file proposal is asked the typed `split` question, then which split
  (`partition`) — by its sentences, by the target's definitions it names, or by
  the failing tests that name the target — or none. Two or more contracts on
  one file are ordered by the tree where one creates a name another spells,
  and kept apart by `Scope.meets` otherwise. A proposal stops once its file
  has been split `max_splits_per_file` rounds (3, F24), emitted as it stands;
  this replaces #799's `max_refine_depth`, which is gone. A split into more
  parts than `max_refine_fanout` (8) is a refusal with what to change, which
  `decompose` now reports beside the contracts. When jev declines, prose
  stands in for the whole request, as before.
- **`mcgyvr delegate --run --jobs N` runs up to N ready contracts at once.**
  Each is settled on the tree as its run ends, and the tree is asked again
  after every settle, so a dependent starts as soon as what it waits on has
  settled (`capacity.run_eager`, beside `run_batch`). The default, 1, is the
  loop it was, on the calling thread; `auto` or 0 is the fleet's total slots
  (`Capacity.total`), the cap on any N. Two contracts whose scopes may write
  one file never run at once (`Scope.meets`), so the second starts from what
  the first landed; deliveries still go through the per-git-dir lock. A run's
  stdout and stderr are held and written whole when it ends. A run that raises
  stops the batch once the runs beside it have ended, and `--log` records
  `internal_error` as before; no new `mcgyvr.delegate_log` kind.
- **`mcgyvr delegate --log PATH` writes how the command ended, as data.** One
  `mcgyvr.delegate_log/1` record, written atomically on every exit once the
  arguments are read, a crash included: its `kind` (one per exit path —
  `config_*`, `orchestrator_*`, `source_unavailable`, `repo_*`, `reply_*`,
  `proposal_*`, `session_unresolved`, `usage_invalid`, `emitted`,
  `emitted_with_refusals`, `none_emitted`, `batch_held`, `internal_error`),
  the exit code, the contracts and refusals, and the facts behind a failure
  (the cut-off reply's token counts, the decoder's position, the proposal
  entry and field). `batch_held` names the Board's state file, not the
  per-contract results. Defined once in `mcgyvr.delegate_log` with its JSON
  Schema (`json_schema()`, with `x-exit-codes`) and a reader (`read`) that
  tolerates kinds added later under `/1`. For a script that called
  `delegate`; it is not part of the /mcgyvr skill, and stderr is unchanged.
- **A failing pytest command is noted one failing test at a time.** When an
  acceptance or demonstrating command is pytest, the gate asks it for its JUnit
  XML report (`--junitxml` into the workspace, `junit_family=xunit1`; the
  report is removed before the tree is restored) and files one finding — one
  failure note — per failing test, with its `test_id` (the node id), `path`,
  `line` (where the test's definition starts), the exception it raised, and
  the command and its exit; `code` is `failed`, `error` or `collection-error`,
  prefixed `demonstration-` for a demonstrating command. A NameError,
  ImportError, ModuleNotFoundError or AttributeError gives `symbol`, read only
  from the interpreter's fixed wording of that exception. A rewrite or a
  timeout comes first, then the tests a report named — at most 19 across the
  run, the rest counted, so the count is within the 20 notes a worker is
  shown — then the raw tail of any other failing command. A command that is not pytest, or where a flag could change what it
  means (`--`, a JUnit option of its own), runs as written and keeps the tail
  of its output; one that took the flags but wrote no report is run again as
  written, and that run is judged. The schema's `kind`s are unchanged.
- **A rerun can start with an earlier run's failure notes.** `mcgyvr run
  --notes-from RESULT` reads an earlier run's result file for the same
  contract (`mcgyvr.notes.seeded`) and opens the climb with its records under
  `retry_notes: climb`, so the first attempt of a rerun on another ladder or
  machine is shown what the earlier run was refused for, under a banner naming
  that run (`IN AN EARLIER RUN (<stamp>), NOT THIS ONE: …`) and within the
  same 20-note, 5-record bounds. The record schema is unchanged; the run
  travels beside it. A result of another contract, a record of another schema
  version or with an absolute or escaping path, a file over 1 MiB, unreadable
  or not JSON stops the run before anything is spent; messages are scrubbed
  again. The result's new `seeded` key says what was read (`from`, `records`
  with their `run`) and how much the climb was handed (`handed`).
- **A contract whose ladder is spent is re-planned, not left to stop.** In
  `mcgyvr delegate --run`, a contract that tried every rung and came to
  `ladder_spent` goes back to the orchestrator (`mcgyvr.replan`): its own work
  is decomposed again on the checkout as it now stands, and the prose
  proposer is shown the spent contract and the failure-notes records its
  result carries (`attempts[].notes`) as data, under the worker prompt's
  bounds and never under the worker's "fix these" banner. The contract or
  contracts that come back take its place on the dependency tree, and what
  waited on it waits on the one on its target, or on all of them when none
  is, so a dependent it held is freed. Each carries `replan` (the id it
  `replaces` and its `round`), and `max_replans` (policy, default 1, 0 off)
  bounds the rounds from that. The spent result keeps outcome `ladder_spent`
  and gains `replanned` (`round`, `max_replans`, `contracts`, `detail`), and
  its `detail` names the replacement, or says why there is none: past the
  bound, a re-plan that failed, or one that proposed nothing new. A single
  `mcgyvr run` still stops at `ladder_spent`, and notes on its result how a
  batch would go on; the `ladder_spent` disposition names the re-plan when
  `max_replans` is above 0.
- **A contract whose provider did not land is held, not climbed.**
  `mcgyvr delegate --run` keeps the batch's contracts on a live dependency
  tree (`mcgyvr.tree`, `mcgyvr.board`), one per repository, and runs the next
  one the tree says is ready. A contract waits on what its `depends_on` names,
  and on the sibling that creates a symbol one of its `deps` needs. When a
  provider fails, or lands without a symbol a dependent needs, the dependent
  is never sent: no rung, no triage call, no slot is spent, and once nothing
  more can run it gets a result with the new outcome `blocked`, exit 3, and
  `blocked_by` naming the reason, the providers and what each came to, and
  the names it needed. What a contract needs of its provider is read from the
  contracts and the committed tree, never asked of a model: the names it uses
  that the provider is to create (its `interface`, a rename's new name) or to
  change (a rename's old name, a name its task spells that its target
  defines). One that uses from the failed provider's file only names already
  there, which the provider was not to change, still runs. The tree is
  written live to `trees/<tree>.json` under `journal.dir`. `dependents: run`
  (policy, default `hold`) sends every contract as before.
- **Failure notes travel with the contract across rungs.** Every failed
  attempt leaves a record (`mcgyvr.notes.FailureNotes`, schema
  `mcgyvr.failure_notes/1`) built from what the gate, the reviewer or the reply
  parser observed: per check its file, line and code, and the command and its
  exit where the check ran one; nothing is parsed out of prose. The climb keeps
  the history, so a rung above starts with what the rungs below it were refused
  for, under a banner naming the rung and attempt (`retry_notes`: `climb`, the
  default, `rung` or `none`; bounded to 20 notes and 5 records). The result
  file carries the record as `attempts[].notes`, its JSON Schema is
  `skills/mcgyvr/references/failure-notes.schema.json`.
- **A rig keeps the kernels its cards' driver compiled.** The rig's scan
  reads the rig's own mcgyvr home, and `mcgyvr emit` mounts
  `$MCGYVR_HOME/cuda-cache` (default `~/.mcgyvr/cuda-cache`) into every
  llama.cpp serve and rpc-server service at `/cuda-cache`, with
  `CUDA_CACHE_PATH` naming it and `CUDA_CACHE_MAXSIZE` at NVIDIA's documented
  4 GiB maximum, so a unit no longer compiles again the kernels an earlier
  start compiled. A rig whose scan read no home, until it is scanned again,
  and vLLM units are rendered as before (#772).
- A rig is found under any address it answers at. A unit addressed by its
  rig's LAN address (`10.0.0.7` for the rig filed as `gpu-box`), or by a name
  that resolves to one, finds the rig's file, so a swap reckons room on it.
  The scan already records the address its ssh session arrived at and those on
  the rig's interfaces, now from `hostname -I` where `ip` is missing; a rig whose
  scan recorded none is asked for one by the `mcgyvr setup` wizard, or states
  it with `mcgyvr setup --rig-address RIG=ADDRESS`, kept in the rig file under
  `addresses` and carried across later scans.
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

- **The wire the hub serves a rider is defined once, in `mcgyvr.hubwire`.** A
  stdlib-only module, importable without `mcgyvr.cli` or `mcgyvr.rig`, holds
  the rung positions, the model-name pattern and `hitchhike@<offer>`
  (`rung_model`, `rung_offer`), the ladder and unit-advert limits with the
  ride-cap rule (`rider_cap_fits`), the relay limits, the `/v1` error table
  (`API_ERROR_STATUS`) and the pairs read off it (`RUNG_BUSY`,
  `MODEL_UNPLACED`, `MODEL_NOT_FOUND`), the request fields a request through
  the hub may carry, the scope header and its values, the use-case names
  (`USE_CASES`) and the model category each is recommended
  (`USE_CASE_CATEGORY`), the use-case header, which use cases each pool serves
  (`POOL_USE_CASES`: a member's own rigs, lent to nobody, serve all four; the
  general pool `code`, `chat` and `agent`; a crew's pool and a ride all four;
  a shared ladder `mcgyvr-code` alone), and
  the hub's two JSON Schemas, shipped in the package (`hubwire_schemas/`, the
  hub's files byte for byte). `rig.rungs`, `rig.sessionwire`, `rig.protocol`,
  `runner`, `config` and `recommend` import them. Every chat request the
  runner and Jev send names the setup's `use_case` in `x-mcgyvr-use-case`;
  the hub is to import these names and refuse a use case its pool does not
  serve. The scope header is not sent yet. Moved: `rig.rungs.BUSY` is `RUNG_BUSY`,
  `MAX_LADDER_RUNGS` is `LADDER_MAX_RUNGS`, `_LADDER_MODEL`, `_MODEL` and
  `_ID` are `LADDER_MODEL`, `MODEL_NAME` and `OFFER_ID`;
  `runner.UNKNOWN_MODEL` is `MODEL_NOT_FOUND` and `runner.MODEL_UNPLACED` is
  `MODEL_UNPLACED`. The test fixtures `hub_*_v1.schema.json`, their sha256
  pins and the re-pin tool (`python -m tests.rig_schema`) are gone: a hub
  checkout named by `MCGYVR_HUB_REPO` is compared byte for byte, and
  `MCGYVR_HUB_SCHEMA_UNDER_TEST` works as before.
- **`mcgyvr "<prompt>"` and `mcgyvr direct FILE... | DIR` replace `run` and `delegate`.**
  The bare verb plans a prompt into contracts and runs them, as `delegate
  --run` did; it needs a session (`--session`, else exit 2 before any
  proposer is asked), and `--output DIR` plans without running. `direct` takes
  contracts someone wrote and vets each as a proposal is vetted (the target is
  a committed file, the ladder serves the task type, the worker's view is
  under the ceiling): a refusal prints `refused: <file>: <reason>` and
  `change: <what_to_change>` on stderr and is logged, the rest of the set
  runs, and when nothing passes the exit is 3; a contract that does not load,
  one id twice and a `depends_on` cycle are refusals too. What passes goes into one tree and runs through the
  batch path, with no re-plan. Both take one flag set; a flag with no meaning
  on one side (`--budget` on `direct`, which has no prompt) is refused, exit
  2. `mcgyvr run` and `mcgyvr delegate` are removed with no alias: `run
  CONTRACT` is `direct CONTRACT`, `delegate PROMPT --run` is `PROMPT`, and
  `delegate PROMPT` is `PROMPT --output DIR`. `--orchestrator` is removed
  too; `--session` is the name. `direct` prints no `result:` line (read it
  with `--result PATH`, or from the journal), and a setup named by `--config`
  or `$MCGYVR_CONFIG` that is missing or invalid is exit 1 before anything runs.
- **`mcgyvr delegate` exits 3 when no contract came of the request.** The
  request was read and declined, which is `REFUSED`, with or without `--run`
  (was 0).
- **The session a run is filed under is named with `--session ID`.** On
  `mcgyvr run` and `mcgyvr delegate`, `--session` replaces `--orchestrator`,
  which named the session and not the orchestrator role. The result file
  carries the name as `session`, and still writes it under `orchestrator` too,
  the same value, for one release.
- **`delegate --run` names its session before the orchestrator is asked.**
  The session is resolved through the same check `mcgyvr run` makes, before
  the config is read: nobody to file the batch under is exit 2 (was 1, after
  the role had been asked and the contracts written), with no model call and
  nothing written to `--output`. A blank `--session`, or one holding `/`, is
  refused there too.
- **`delegate --run` prints no `result:` lines.** Each contract's result is
  read in process by the batch; the paths are in the Board's state file,
  `<journal>/trees/<tree>.json`. `mcgyvr run` still ends on its `result:`
  line.
- **A climb enters every rung of the ladder by default.** `max_escalations`
  is unset by default and unset means no escalation ceiling, where it used to
  default to 1 and stop a three-rung ladder with `escalation_ceiling` before
  its top rung. A setup that states a number is capped by it as before.
- **Units start together.** Units on one card start at the same moment when
  every one of them turns llama.cpp's fitting off (`--fit off` or
  `LLAMA_ARG_FIT=off`), since each then takes only the memory its launch
  states; otherwise, and for any vLLM unit, they keep waiting on a healthy
  neighbour. The same holds for a locked fleet's layout on a host. The
  `mcgyvr setup` wizard starts every rig's units at once instead of one rig
  after another, and names every rig whose start failed (#772).
- **llama.cpp starts with fitting off.** `mcgyvr emit` launches every
  llama.cpp server with `--fit off`, and a pooled head is started with it
  too: each already states its `-c` and `-ngl`, so fitting only dry-ran the
  load and read free memory that a unit starting beside it was still taking.
  Off, a load that does not fit exits 1. Units on one card therefore start
  together by default. A unit turns fitting back on with `--fit on` in its
  `launch.serve_args`, and then keeps the card's start chain; an rpc-server
  worker and a vLLM unit take no `--fit`. A locked fleet keeps the argv it
  states (#774).
- **Wake-on-demand runs inside the run.** With `serving.enable_sleep_wake` on,
  a climb that reaches a sleeping rung puts the units sharing its card down,
  wakes it, and records the swap. The sleeper goes back down, and the units it
  displaced come back up, only when it is idle and the nearest awake rung below
  it is not full; until then a draw on a displaced unit is refused and the
  climb moves past it, so nothing starts beside the sleeper. A swap honours the
  live fleet's host lock, finds its card's memory under any name the rig
  answers to, and a failed wake prints its reason. A review never wakes a unit:
  a reviewer that is down is passed over, by the existing stand-in rules.
- **The typed proposer writes `code` contracts.** `authoring: classifier` asks
  which line is the task, the request verbatim first, and states the reply cap
  from the target's size (twice its tokens, at least 1024, at most the
  decomposer's `max_input_tokens`). Without a `jev` unit the classifier path
  asks no model, takes rank 0 per field, and states the same cap.
- A stated reply cap larger than the room a unit's window leaves the prompt is
  narrowed to that room instead of refused; it is refused only when the room is
  smaller than the target the cap was sized from.
- The interface question offers the chosen symbol's signature, or at most 8
  when no symbol is chosen, instead of every signature in the target.
- `mcgyvr emit` writes the fleet through `render_fleet`; nothing writes or reads
  `# launch:` comment lines any more.

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

- **Serving and rig paths nothing called are cut (I-75, I-81, I-82, I-103,
  I-143, I-154, I-157).** `session_status` takes no `progress_pct` (no caller
  sent one; the hub's schema keeps its optional field). The capability table
  drops its `backends` block, which was shape-checked and never loaded; a
  table that still carries it is refused by the key's name, and only the
  shipped table is ever read. `emit.render_command` (the bare shell line) and
  `emit.render_compose` go: `mcgyvr emit` writes through `emit_all`, and the
  tests that called them now read the file `emit_all` writes. `Wake.deviation`
  (always None), `Wake.predicted_s`, `predicted_wake_s` and the
  `<host>.wake.json` record that fed only them go: a wake no longer writes it,
  and one left by an earlier mcgyvr is read by nothing. The tolerance class no
  longer reads `launch.flags` or `launch.n_cpu_moe`, keys nothing writes and
  emit never applies: a fleet file that carries them by hand is classed by its
  `argv` and `speculative` alone. `derived.lookup` goes; `lookup_all` and the
  named getters remain.

- **`mcgyvr recommend --profile code` no longer asks a local model to pick.**
  It asked whatever answered on `http://127.0.0.1:8080` to choose among the
  fitting candidates, by name and description only, and fell back to the
  largest weights when nothing answered, the request failed or the answer
  named nothing offered. Now it always takes the candidate with the largest
  weights, as `chat` and `agent` already did, and probes and asks nothing.
  The plan's `decision` is always `deterministic` for a placement (`null` for
  a scaffold, as before) and its `decision_endpoint` key is gone. Upgrading: a
  `code` plan made with a model answering on port 8080 may now name a
  different candidate; one made without one is unchanged.

- **A vLLM unit is no longer split across machines.** The multi-node vLLM
  launch was planning only: tested with invented rigs, never run live, and a
  locked `emit` already refused it. A vLLM unit whose `launch.shards` name
  cards of more than one machine is now refused when it is sized, in the
  words of that locked refusal (only llama.cpp is split across machines, as a
  head plus rpc-server workers). Removed with it: the per-machine node launch
  (`--distributed-executor-backend mp`, `--nnodes`, `--node-rank`,
  `--master-addr`, `--master-port`, `--headless`), the `headless` process
  role, `launch.master_port` and its default `VLLM_MASTER_PORT` (29501), and
  the equal-cards-per-machine check. A vLLM split over one machine's cards
  (tensor x pipeline, one process) is unchanged, as is every llama.cpp split.
  Upgrading: a stated `launch.master_port` is now ignored, not checked;
  delete it.

- **The unused floor fallback is gone: `mcgyvr.deterministic.route`,
  `Degradation` and `Routed`.** `route` planned a floor contract whose program
  was missing on the cheapest dearer family and recorded a `degraded` note
  saying who pays; nothing in mcgyvr called it, only its tests. It is removed
  with its helpers (`_have`, `_why_missing`, `_cheapest_above`) and the tests
  that exercised it; the tests that ran the floor's step through `route` now
  plan it through `mcgyvr.route.plan`, which is the path runs take. Nothing
  behaves differently: a floor contract with no program bound still stops
  `mcgyvr run` with exit 1, naming the dearer family it does not climb to.
- **Sessions, the manager loop and the retired-name shims are gone.** `chat`
  and `agent` are no longer contract task types: `code` is the one shipped
  type, and chat and agent stay as plain use of an endpoint. Removed with
  them: session records and `sessions/` in the journal, `mcgyvr sessions`,
  `--session-sandbox` and `sandbox.sessions`, the `prose` output schema,
  `mcgyvr manage` with its tick, board and `manager:` block, and
  `ladder_manager.decide_on`. The retired-name shims go too: old task-type
  names, `risk`, `BUDGET_FIELDS` and the renamed-key table. A policy written by
  an earlier `mcgyvr setup` is refused once, naming every retired key it holds
  (`manager`, `sandbox.sessions`, `orchestrator.tools`) with the lines to
  delete; `mcgyvr setup <dir>` on that folder offers to delete them.
- **mcorch is gone.** `mcgyvr mcorch serve`, the `mcgyvr.mcorch` package and
  its prompt, `setup --mcorch` and `--window`, the wizard's mcorch question,
  and the lock, promote and live checks that held an mcorch policy's units
  awake are removed. `orchestrator.type` takes only `proposer`;
  `orchestrator.authoring` takes `prose` or `classifier` (`direct` was
  mcorch's); `orchestrator.tools` is retired and refused by name.
- `mcgyvr setup` no longer offers the `media-gen` use case: it has no sample,
  so setup could not sample it, and it is off until one is built. The
  use-case prompt is `d` coding (default), `c` chat, `a` agent; a
  `--use-case media-gen`, or a config naming `use_case: media-gen`, is refused
  in one line naming `coding`, `chat` and `agent`. The `media` task type is
  removed in this release too (#731); see the next bullet.
- **The `media` task type and the `media-gen` use case are gone.** `code`,
  `chat` and `agent` were left (`chat` and `agent` go below). Removed with them: the
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
  `checked` assurance is gone too.
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
- **`mcgyvr setup --profile` is gone**, as the 0.4.0 deprecation promised: it
  is now an unknown flag. Use `--priority throughput|quality|cost`.
- Paths nothing but tests reached are cut (no command, flag or default
  changes):
  - per-rung width bounds and the width probe: `mcgyvr.capacity.RungWidth`,
    `WidthProbe`, `SourceWidthProbe`, `Capacity(rungs=)` and
    `Capacity.of(probe=)`. Every rung is held on its unit's own bound, as every
    production capacity already was;
  - `mcgyvr.gate.check_clean_tree` (a run on a dirty tree already says the
    sandbox is HEAD);
  - `mcgyvr.decompose.iterate.iterate`, its `Approver` and
    `MAX_REFUSAL_RETRIES`: a refused proposal goes to the top rung
    (`mcgyvr.repropose`), bounded by `max_reproposals`;
  - `Request.quality_sensitive`, `QualityCaveatError`, `CAVEAT_NOTE` and
    `quality_safe` in `mcgyvr.runner`; the completion row in the journal no
    longer carries `quality_safe`, which was always true;
  - `RecordedProposer` leaves `mcgyvr.decompose` for `tests/recorded_proposer.py`:
    it is a test double.
- **Model records carry no leaderboard `scores`.** `BOARDS`, `Board`, `Score`
  and the `board` source are gone from `mcgyvr.knowledge.record`, and the
  knowledge document is `schema_version: 3`. A version-2 document (a cache an
  earlier mcgyvr wrote) still loads, its `scores` skipped unread; an earlier
  mcgyvr refuses a version-3 cache file and skips it.

### Fixed

- **The rig's log says why the hub stopped a session or cancelled a relay
  (I-76).** `session_stop` and `relay_cancel` carry the hub's reason; the
  agent parsed it and dropped it. `Sessions.stop` and `Relays.cancel` now log
  it (`session s1: the hub stops it: <reason>`, "no reason given" when the
  frame has none). No wire change.

- The setup reference says what an unset `attempts` entry means: a unit with
  no entry is tried once on its rung, as it always was, not the contract's
  `limits.attempts` default of 2, which only caps the number. The one value
  is `config.UNSET_RUNG_ATTEMPTS`, and `mcgyvr local_pool` now reads a rung's
  budget through `route.configured_attempts` (was `_configured_attempts`),
  the reader a plan uses, instead of its own copy of the default.

- The Python worker prompt (`prompts/python.md`) no longer tells the model
  to leave out "everything listed under OUT OF SCOPE": the message a worker
  is sent has no such section, and the gate already refuses a change outside
  the contract's scope. The bundle is 1901 bytes after provenance is
  stripped (was 1972; the ceiling is 2048), and its standing is unchanged.

- A type error on a line the change added now rejects even when the type
  checker's re-run on the base tree times out. That re-run only decides the
  diagnostics elsewhere in the touched files; its timeout used to drop the
  added-line findings with them, and a change with type errors was accepted
  with only an environment note. The added-line findings now stand, the
  off-diff diagnostics are left out, and the note
  (`python: typecheck base re-run timed out after …`) says the comparison was
  skipped. A timeout over the change itself is unchanged (I-57).

- The `type_check` contract key and the JavaScript adapter say what a
  TypeScript type check is: `tsc --noEmit`, run as the contract's acceptance
  command and read pass or fail by its exit code. Its errors are not
  attributed to the lines the change added or compared with the base, as the
  gate's own type check does for Python; no tsc output parser exists. Prose
  only, no behaviour change (I-56).

- **Setup's discovery and the fleet sampler send a keyed unit its own key.**
  Both asked a unit's `/v1/models` (and `/props`, `/api/v0/models`, `/info`)
  with no key, so a unit behind `expose: lan` answered 401: setup did not list
  it, and the sampler read no window or slots from it. Now `detect.probe`, its
  window read and `fleet.sampler.served` send the key mcgyvr keeps for that
  address (`unitkey.for_address`) as a bearer token, to that address alone:
  the key file is named for one host and port, so a sweep of another host or
  port sends none, and the header is not replayed across a redirect. Setup
  therefore lists keyed units it used to skip. A key file setup cannot trust,
  or a data folder it cannot name (a relative `$MCGYVR_DATA`), is a `Unit key:`
  note and the unit is asked without the key; the sampler raises, as a
  dispatch to the unit does.

- Prose says what the code does, with no behaviour change. The host's `rig
  run` and `rig join` print a run's seal key id (there is no `rig up`);
  SECURITY.md cites `Sharing.image`, `_image` and `rpc_proto=` instead of line
  numbers that had moved; `--orchestrator` is not described as a working
  alias, since the CLI refuses it; README's, docgen's and the Makefile's lists
  of generated documents name `/mcgyvr-use`; docstrings no longer say delivery
  gates through `gate_workspace` or that nothing wires the shadow decision
  sink (`mcgyvr PROMPT --log` does); retired `init` and `mcgyvr run` names in a
  docstring and a comment are `setup`, `mcgyvr PROMPT` and `mcgyvr direct`; the
  install script's floor comment states its rule without a version. Two
  internal helpers nothing called, `symbol_options` and `shipped.b64`, are
  deleted.

- The rig agent no longer lists `backend_select` among its features. It read a
  worker card's `backend` (`cuda_notc`, `rocm`, ...) and started the worker
  exactly as without one, so the claim was not true. A hub that sees no
  `backend_select` names only the backends every fork speaks (`cuda_notc` as
  `cuda`, `openvino` and `sycl` as `vulkan`); what a worker runs is unchanged.

- **The rig agent and `mcgyvr rig status` read your personal hub key from the
  variable `mcgyvr rig rungs sync --key-env` was told.** The agent's
  background refresh and the `rig status` credits read only
  `$MCGYVR_HUB_API_KEY`, so with a variable of your own the refresh never
  started, or, with the default set too, rewrote `relief.yaml` with the
  default name. A sync now records the NAME (never the key) as a top-level
  `api_key_env` in `relief.yaml`, with or without rungs listed, and both read
  it back (`rungs.key_env`); each refresh writes the same name back, and a
  `relief.yaml` that does not load is still rewritten by the next refresh. A
  `relief.yaml` written before is read by the `api_key_env` its rungs name;
  with none recorded there, by the one `crew.yaml`'s units name
  (`rig crew sync --key-env`); else the default. An older mcgyvr refuses a
  `relief.yaml` with the new key (`unknown key 'api_key_env'`); a
  `rig rungs sync` with it rewrites the file.

- **Two first writes into a home folder that does not exist yet both land.**
  `rig join` and a service's `rig run` (or two first unit keys) could both
  find no home folder and both `mkdir` it; the second failed with
  `FileExistsError` and lost its write, which the identity-key race test
  caught now and then. `atomic.write_private` and
  `rig.credentials.write_private` now take the folder the other write just
  made (still created at 0700) instead of failing on it.

- A relief rung whose host's unit already serves as many rides as it may
  (`503 pool_busy`) is passed over as full, as the other busy answers are,
  instead of failing the dispatch: a sync writes `pool_busy` into each rung's
  `busy_answers`.

- `mcgyvr delegate` says why an orchestrator reply is not JSON — the
  decoder's message, the line and column, an excerpt either side of that
  point and the reply's length — and prints the whole reply, delimited, on
  stderr after the error, so a failed run can be diagnosed from its output.
  A complete JSON array or object with prose only before or after it is now
  read and the prose ignored; malformed JSON inside it (a trailing comma, a
  comment) is not repaired and still fails, with that reason.
- `mcgyvr delegate` names an orchestrator reply cut off at its cap as cut
  off — its output tokens, the unit and the cap it was sent, and what to
  raise — instead of reporting the half-written array as "not JSON".
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

- **A Mac or Windows rig's pooled head answers only the key its session
  made.** A native head listens on 127.0.0.1, which every local process
  reaches, so each native session makes a key of its own (256 bits,
  `unitkey.new_key`, as a unit's key is made) and hands it to llama-server as
  `LLAMA_API_KEY` (its `--api-key`) in the head's environment, never on its
  command line, and into no record, log or hub frame. The agent's health
  check, warm-up, relayed requests and `/slots` read send it as a bearer
  token, and a native head is not started without one. HELPER-SPEC.md
  section 6 asked for this before the helper's first pin. A Linux rig's
  pooled head, in a container on its tunnel's network, is started and asked
  as before, with no key.
- **The README says, in one sentence, what the privacy + security program
  makes true** (`## Privacy`; the hub's README carries the same paragraph):
  your own and your crew's rigs by default (an account made before crew became
  the default keeps the scope it had, anyone for most), strangers' rigs only
  by opt-in and the hub admin's approval, who can read a prompt and its
  answer, that a ride your client seals is unread by the hub unless the hub
  swaps the host's key for its own, what the hub keeps (who asked and from
  what address, which rigs answered, which model, how many tokens and when;
  never the text), identity-key pinning for current rigs from first contact,
  port-forward consent on the rig, docker units on their own machine or behind
  a key, and no network while the gate tests code a host returns.
  `SECURITY.md` has the detail.
- **A rig forwards its UDP ports only when its owner allowed it on the rig
  too, and never takes a permanent lease unasked.** The lending settings gain
  `port_forward` and `port_forward_permanent` (`rig-sharing.json`, both off;
  `mcgyvr rig share --port-forward` / `--permanent-forward`, and
  `mcgyvr rig join --port-forward`). Until `port_forward` is on, the hello
  names no `port_map` feature, a `port_map` from the hub is refused as
  `port_map_report` `failed` `not_allowed` (an open-set error tag: no new wire
  state) and a `port_check` as `not_capable`; turning it off gives a forward
  back within a minute. A router that grants only permanent leases (UPnP 725,
  or a lease of 0) is refused as `failed` `permanent_only` unless
  `port_forward_permanent` is on; NAT-PMP is never asked for a lifetime of 0
  (that deletes). Every mapping is recorded in `rig-port-forward.json` under
  the data home until it is given back, and an agent that starts gives back
  what a crashed one left, only to a router whose LAN the rig is on now (a
  rig that moved sends nothing; a permanent one stays on record until its
  router takes the release, and a full record forgets leased ones first). The agent's first line about the forward says what this
  rig allows, no longer "as agreed on the hub". A rig that relied on the hub's
  consent alone refuses the forward until its owner runs
  `mcgyvr rig share --port-forward`.
- **Code from a rung that is not yours never runs with a network, and never
  lands unmarked.** Whose machines a rung's code may come from is its `scope`,
  with a relief rung never read as yours (`mcgyvr.config.whose`, `Unit.whose`,
  `Endpoint.whose`); every attempt and the run's result record it as `whose`
  (`own`, `crew`, `anyone`). In `sandbox.mode: docker` such a try runs in a
  second task container started with `--network none`, whatever
  `sandbox.network` says (`none` included), `--cap-drop ALL`, `no-new-privileges`,
  `--read-only` and a `/tmp` and `/var/tmp` in memory (`CONFINED_ARGS`), while
  your own rungs' code keeps
  the task's own container, which never runs a stranger's code
  (`Sandbox.confine`, `mcgyvr.sandbox.base.confine_for`); the second
  container costs one `docker run` (about 1 s here) the first time a task
  rides, and a `docker restart` (about 1 s) before each later lent try, so
  nothing one host's code leaves outside the workspace or running is there for
  the next;
  a switch back to your own rungs costs nothing. In the `tempdir`
  sandbox, by name or as the fallback, a try on such a rung is declined before
  anything is sent, the refusal naming `sandbox.lent_code_on_host`, the list of
  repositories where it may run on this host, and a ladder declined that way
  throughout says so in its halt. An accepted change from such a
  rung is committed with `Mcgyvr-Source:` and `Mcgyvr-Model:` trailers (never
  the machine or member that served it), and under the new `delivery.lent_code:
  branch` (the default) onto `mcgyvr/<contract id>` (`-2`, `-3`, … when a run
  of the same contract already has that branch, which is never overwritten; or
  a named branch you do not have checked out), whatever `delivery.commit`
  says, without touching your checkout or its index: it is written, judged
  again and committed in a temporary worktree. A branch named plain `mcgyvr`,
  which leaves git no `mcgyvr/<id>`, is refused naming `delivery.lent_code`.
  `checkout` delivers it as before. SECURITY.md names the hub, the rider, the
  host and a peer on your network, and what each can do.
- **A rig has an identity key, signs each session's tunnel key with it, and
  pins its peers' keys.** `mcgyvr rig join` (or the first `rig run` of a rig
  that joined before) makes a long-lived Ed25519 key, kept beside the rig
  token as `rig-identity.json` at 0600, owner-checked and opened without
  following a link, as the token is (`mcgyvr.rig.identity`; the token file's
  checks are now `credentials.write_private` and `read_private`, its messages
  unchanged). Its public half rides in every `hello`
  (`hubwire.IDENTITY_KEY_FIELD`), and `session_prepared` carries its
  signature over the session's WireGuard key (`hubwire.SESSION_KEY_SIG_FIELD`,
  over `hubwire.session_key_message`: a context, the session id and the key).
  On `tunnel_up` the rig checks each peer's signature against the identity
  key the hub forwards and pins that key by rig id in `rig-peers.json`; a
  changed key, an unsigned or wrongly signed tunnel key, or a missing key for
  a pinned peer is refused as `tunnel_failed`, naming both fingerprints; a
  peer taken with no key is logged ("sent no identity key ... taken
  unpinned"). Two first runs at once keep one key: the key is linked into
  place, and the run that finds one there takes it. The hub can still stand
  in for a peer on first contact, and names the rig ids, so only a pinned id
  is protected: compare the fingerprint
  (`hubwire.identity_fingerprint`, base32 of the key's sha256, 16 characters)
  that `mcgyvr rig status` prints with the hub's rig page; `mcgyvr rig peers`
  lists the pins and `--forget <rig-id>` drops one after a rotation. All
  fields are optional: an agent or hub from before them sends none and
  ignores them. Adds the `cryptography` dependency.
- SECURITY.md names the llama.cpp build mcgyvr pins (b11960, above b8492,
  the fix for CVE-2026-34159), says an image that serves `rpc-server` must be
  b8492 or later, and states what bounds CVE-2026-78147, which no build fixes
  yet: the RPC port is open only to the session's WireGuard peers, in locked
  down containers.
- A failure note names no path on the machine it was made on. The acceptance
  rung gives a path under the workspace its command ran in — pytest's
  `rootdir:`, a traceback's file, in either sandbox mode — repo-relative
  (`Sandbox.roots`, `mcgyvr.redact.relativize`), and every `FailureNote`,
  however it is built or read back, replaces any other absolute path in its
  `message` and `command` (site-packages, `/tmp/...`, a home directory) with
  `<redacted>` (`mcgyvr.redact.scrub_paths`) and drops a `path` that is not
  repo-relative. A record carried to another user's rig no longer carries the
  first user's paths.
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
