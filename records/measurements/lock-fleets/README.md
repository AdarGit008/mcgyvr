# lock-fleets — the campaign that measures what a fleet lock needs

Owner, 2026-09-15: "lock-fleets, general campign to lock new fleets in. we are
using it on our private case (16b -> 35b srv1, 3b + 7b ->80b srv2)".

`lock-fleets` is reusable. Nothing about any one use is written in its files:
units, rigs, cards, layouts, combinations, moves, argv, images, ports, engines,
rooms and pins come from `fleet-setup/fleet.yaml`, `fleet-setup/policy.yaml`,
`fleet-setup/digests-<rig>.json` and `tools/runs/hosts.json`. A use is a folder
here with a `use.json` (why it exists, the checks it adds, the rig pins that must
not change, the compose files that must equal live) and the `RUNS.md` the planner
freezes from it. The first use is [`rig-id-relock/`](rig-id-relock/RUNS.md).

## The files

| file | what it does |
|---|---|
| `tools/runs/campaigns/lock-fleets/_unit.sh` | one cold start of one llama.cpp unit, through the door |
| `tools/runs/campaigns/lock-fleets/_move.sh` | one timed switch move on one rig, through the door |
| `tools/runs/campaigns/lock-fleets/lockfleets.py` | the facts and refusals both steps act on; renders the move's rig shell; writes their artifacts |
| `tools/runs/campaigns/lock-fleets/<use>/NN-*.sh` | one generated wrapper per campaign run of a use |
| `plan.py` | freezes a use's order into `<use>/RUNS.md` and writes its wrappers; `retry` gives a failed entry its one retry, and `diagnose` a failed retry its one diagnostic start |
| `<use>/retries.json` | a use's retries, one per failed entry, and its diagnostic starts, one per failed retry, each placed right after its entry in its rig's order |
| `drive.sh RIG USE` | runs one rig's frozen order through the door, and stops to ask |
| `assemble_evidence.py` | `check` (the stop-and-ask list), `assemble` (the lock's evidence), `tolerance` |

A use runs as:

1. `uv run --no-sync python records/measurements/lock-fleets/plan.py freeze --use USE`,
   committed before the window. It refuses once the log holds a row: a run is
   expandable until its first measurement, and frozen from then on.
2. `bash records/measurements/lock-fleets/drive.sh srv1 USE` and the same for
   srv2, at once. Each rig logs into the one `RUNS.md`, under a flock.
3. `uv run --no-sync python records/measurements/lock-fleets/assemble_evidence.py assemble --use USE`,
   which writes `fleet-setup/evidence.json` and `<use>/runs.json` and prints
   the fleet.yaml edits, then the owner edits fleet.yaml and runs `mcgyvr fleet lock`.
4. `assemble_evidence.py tolerance --use USE --class C --unit U` for each prefill
   class tolerance to be derived.

## What is measured

Every combination of every fleet layout, K = 3 cold starts each, and every switch
move (`mcgyvr.fleet.lock._switch_moves` over each fleet's `next`), K = 3 runs
each. A combination seen in two fleets is measured once, named by the first.

- **A llama.cpp combination** (one llama.cpp unit) is a campaign unit run,
  `_unit.sh`: the unit is started as fleet.yaml states its launch, as
  `<RUN_ID>-<unit>` with `--gpus all --network host`, its wake to `/health` ok
  is timed (data), the lock's own harness (`src/mcgyvr/fleet/harness.py`) runs
  on the rig — the measure, with every sample, then the load — and the
  container's restarts and `/proc/vmstat` `pswpout`/`pgmajfault` are read.
- **A vLLM combination** (a group of vLLM units) cannot be a campaign run: the
  door's campaign sequence needs a GGUF `--model` for data-20 and data-30. It is
  measured by the door's own serve and read, per cold start: `serve up` of the
  dev fleet's compose file (`mcgyvr emit`), `read --probe` its units, `read
  --probe U --load WxN` per unit, `serve down`.
- **A move** is `_move.sh`: each side is one llama.cpp unit (`docker run`) or a
  vLLM group (`docker compose -p mcgyvr -f -`, the emitted file on stdin).
- Any other combination (two llama.cpp units on one card, or a mix) is refused
  by the planner by name.

### The order

Per rig: interleaved by cold start — c1 of every combination, then c2, then c3 —
then the moves, r1 of every move, then r2, then r3. Moves are last on every rig,
so on the rig that finishes sooner they go last. `RUNS.md` states a recorded lower
bound per rig when every wake and rate it needs is in a committed lock, and says
there is none otherwise. `drive.sh` logs each rig's `finished_at` and the other
rig's idle tail; no fill work is added.

## Definitions (owner rulings, 2026-09-15)

- **K** = 3 cold starts per combination and 3 runs per move. Every run is kept as
  a data point.
- **Decode and prefill** pin the median of the 3 run medians. Every sample is kept
  beside its median (`decode_samples`, `prefill_samples`), and a run's median
  must equal the median of its own samples.
- **Room** is the unit's own container's card peak under load, context included:
  per-process MiB from `rig-units.sh --card-holders`, read with
  `mcgyvr.fleet.read.parse` and filtered by the container id. `room_mib` pins the
  max of the 3 load peaks.
- **`overhead_mib`** is the max, over the combination's runs, of the snapshot's
  `gpu_reserve_mib`: the driver reserve only, on every rig. No CUDA context probe.
- **Restarts** must be 0 everywhere.
- **A load** asks W concurrent requests (W = `--parallel`/`-np` or
  `--max-num-seqs`) each to fill the per-slot window N (`-c`/`-np` or
  `--max-model-len`), and runs at most 30 s: card samples every 0.5 s, pace as
  prompt tok/s from the unit's own counter or null with a reason. At 30 s the
  unfinished requests are closed and the load waits for the unit to read idle,
  with no time limit, sampling the card all the while (2026-09-15, below). The
  verdict is the card peak over every sample up to idle ≤ room. Pace, the
  completion counts, `idle_after_close` and `idle_after_s` are filed, not judged.
  A load is refused for errors other than the 30-s close, for a status-page error
  during the idle wait (`idle_error`), for no sample showing the container, or
  for `limit_s` ≠ 30 — never for unfinished requests, nor for
  `idle_after_close` false alone. A llama.cpp pace is null: no fleet.yaml unit
  runs `--metrics`.
- **A move is timed the same way on every rig**, srv1's 2026-09-13 way
  (`records/measurements/fleet-setup-2026-09-13/srv1/measure_move.py:72-102`):
  the source up and healthy (untimed); `t0` as its stop is issued; the page cache
  dropped with `sudo -n sh -c 'echo 3 > /proc/sys/vm/drop_caches'`, its return
  code filed; the target started — `t1` after `docker run -d` returns, or, for a
  compose target, `t1` just before `docker compose up -d` and `t_compose` after
  it, with each unit's poller started at `t1`; health polled every 1 s (5 s curl
  timeout) up to 900 s — llama.cpp healthy when `/health` says ok, OK or
  `"status":"ok"`, vLLM when `curl -sf /v1/models` returns 200. `downtime_s` =
  max(t2_u) − t0 and `wake_s{u}` = t2_u − t1, and the lock pins the max of the 3
  runs for both. A move passed when every run has every t2 and every `rc_*` is 0.
- **The stopwatch runs on the rig**: each timed move is one ssh argv, stamped by
  the rig's `date +%s.%N`, polling at the rig's 127.0.0.1, with the docker verbs
  in the argv so the shim's spend check and the lease see them. Stamps, and the
  START/END markers (`pl1_uw`, `pl2_uw`, `uptime_since`, `ram_mt_s`) of every
  unit run and move, are teed to `~/mcgyvr-relock/<RUN_ID>.move` (or `.unit`) and
  read back by a second ssh, because a lock takes the ssh pipe with it
  (`okf/must-read/touching-rigs.md`).
- **`validated_at`**: a combination measured through serve and read takes the
  last cycle's serve-down header `started_at`, which must be later than the last
  alert `at` in that combination's journal directory (`alerts.py:312-318`); a
  combination measured by campaign runs takes the last run's `ended_at`.
- **The prefill class tolerance**, for a named class and unit, over that unit's
  K × PREFILL_SAMPLES samples: L = the locked prefill (the median of the run
  medians), tol = max(1, ceil(max_i (L − s_i) / L × 100)), a sample above L
  counting as 0. The 2026-09-12 M1 wording took the shortfall from the unit
  median over 15 samples; this takes it from the locked value.
- **A failed start keeps the container's full log** (2026-09-15). When a
  container a step started exits or never says healthy — `_unit.sh`'s unit, or
  the source or the targets of `_move.sh` — its whole `docker logs` (stdout and
  stderr, every line, through the door's docker shim) is filed in the envelope
  as `<artifact stem>.<unit>.docker.log` before anything removes it, and the
  artifact's `failure` names the file after its short text. The wrapper does not
  declare it: gate 8 holds a declared name to exist (`08-parse.py:182-188`) and
  this file exists only when a start failed, while gate 5 guards and gate 7
  stamps only declared names (`05-envelope.py:298-306`,
  `07-teardown.py:231-272`). So `lockfleets.keep_log` writes it once and never
  through a link.
- **A failed entry gets one retry** (2026-09-15, "Fix PR, then retry srv2").
  `plan.py retry --use U --entry E --reason "..."` refuses unless E is logged and
  fails its check, has no retry yet and is not itself a retry. A campaign unit or
  move run is retried through a wrapper and an artifact of its own; a read or a
  load has neither — `drive.sh` mints its run id just before it runs — so its
  retry is the same door command under a new id (the read by the owner's
  2026-09-16 ruling below; the load by Claude's extension of it, recorded
  there). A serve-up
  or serve-down gets none: a second run of one moves its kept `serve-<mode>.json`
  aside as `serve-<mode>.superseded-<run id>.json` (`05-envelope.py:645-682`),
  naming a data point superseded. It lists the retry in
  `<use>/retries.json` and, for a campaign run, writes its wrapper,
  `NN-<step>-retry1.sh`, declaring
  `<artifact stem>-retry1.json`; `read_runs` places `E-retry1` right after E in
  that rig's order, and RUNS.md is not edited. The failed run is kept as a data
  point: `check` says it failed, retried by `E-retry1`, and the driver goes on
  to the retry; `assemble` keeps it in `runs.json` with its reasons and counts
  the retry among the K valid runs in its place. A failed retry stops and gets
  no second one. `--log-from TREE` runs the check on the log, envelopes and
  outputs of another tree with the same frozen order, for a checkout whose own
  RUNS.md log was never written.
- **Swap is recorded on a listed rig, not stopped on** (2026-09-15, "Record swap
  on srv1, don't stop"). `use.json`'s `swap_recorded_not_stopped_on` names the
  rigs; the planner refuses one no fleet places a unit on. On a listed rig a
  campaign run's pswpout start, end and delta are filed in `runs.json`
  (`pswpout`) and its growth is no reason to stop. Every other stop still
  applies there — uptime_since, pl1_uw, pl2_uw or ram_mt_s moving between START
  and END, restarts, a failure — and every other rig keeps the swap stop.
  `rig-id-relock` lists srv1: srv1-01's 47,425 pages sit inside the
  35,000–48,000 pages per wake that
  `records/measurements/ram-headroom-2026-09-09/README.md` measured for that
  blob mapped on srv1 at swappiness 60, with decode unaffected.
- **srv2 is listed too** (2026-09-16, "Record swap on srv2 too").
  `srv2-01-relaunch1` (`srv2_35b_256k`, a-solo, 35B at 256k) ran clean — exit 0,
  `failure` null, restarts 0, identical START and END markers, wake 8.202 s,
  decode median 49.22 tok/s, prefill 632.02 tok/s, card peak 10564 MiB against
  its 10597 MiB `room_mib`, its load sampled until idle — and the driver stopped
  it only on `pswpout` rising 91686 -> 91786: 100 pages, ~0.4 MB, on a rig
  carrying 8 GB of swap with ~46 GB MemAvailable at start. The 2026-09-13
  measurement that unit's pin came from,
  `records/measurements/fleet-setup-2026-09-13/srv2/a-solo-running.json`,
  records `vmstat_delta.pswpout` 295 — more swap than this run moved — and it is
  the measurement
  `records/fleet/rigs/rig-cbe770b5…/cmb-90c09b09….json` was locked from. srv2 is
  listed through the mechanism above and not a second one: `use.json` now names
  both rigs, every other stop still applies on both, and swap stays filed as
  data — never judged, and never a reason to call a run invalid.
- **The card is sampled until idle** (2026-09-15, "Sample the card until idle").
  Closing the load's request at 30 s does not cancel the work in llama.cpp
  b10644: srv1-01's artifact
  (`records/evidence/2026-09-15-lock-fleets/rig-id-relock-srv1-c1-srv1_35b_maxctx.json`)
  files `idle_after_close` false, `idle_after_s` 104.3, `prompt_tokens` 32690,
  `completed` 0, `closed_unfinished` 1, and 58 card samples, every one taken
  before the close. So after the close the harness samples `rig-units.sh
  --card-holders` beside every status reading, the first idle one included,
  with still no time limit. `samples_before_close` marks where the close fell,
  and `sampled_until_idle` whether the samples reach an idle reading; an
  `idle_error` still ends the wait short of idle. The load's verdict, `room_mib`
  and `card_peak_mib` are the max over every sample, and `peak_before_close_mib`
  is filed as data. A load not sampled until idle is kept, its peak a lower
  bound (`peak_is_lower_bound`), and `check` does not stop on it; `assemble`
  refuses a unit's room, naming the runs, while fewer than K of its valid runs
  were sampled until idle. The stop on `idle_after_close` false on a rig's
  first long-context run is gone, and the flag stays filed.
- **One extra cold start for room** (2026-09-15, "One extra cold start for
  room"). `plan.py rerun --use U --entry E --reason "..." [--log-from TREE]`
  gives a logged unit entry that passed its check, but whose load was not
  sampled until idle, ONE extra entry `E-rerun1` right after it: the same unit,
  cold start and door command, with its own wrapper and artifact, listed under
  `reruns` in `<use>/retries.json`. It refuses an entry that is unlogged, fails
  its check, is not a unit entry, was sampled until idle, already has a re-run
  or a retry, or is itself a retry or a re-run. E stays a valid run: decode and
  prefill take E, while room and `card_peak_mib` take `E-rerun1`, and E's 30-s
  peak is kept as a lower bound. `check` passes E and its re-run runs next.
  `rig-id-relock` re-runs srv1-01.
- **A failed start files its exit cause** (2026-09-15, "Fix PR, then one
  diagnostic start"). srv2-01's retry exited before `/health` said ok, 42 s in,
  as srv2-01 had. Its artifact
  (`records/evidence/2026-09-15-lock-fleets/rig-id-relock-srv2-c1-srv2_35b_256k-retry1.json`)
  files that and no cause, and its whole docker log
  (`rig-id-relock-srv2-c1-srv2_35b_256k-retry1.srv2_35b_256k.docker.log`, beside
  it) ends at "warming up the model" and `[expert cache] io_uring_queue_init
  failed: Operation not permitted`. **That line is fatal for this source**, and
  the 2026-09-15 wording above it — that it was known to be non-fatal and had
  fallen back to the RAM tier — was wrong. The image is the Lidenburg fork at
  `e85e4d9`, whose expert cache prints exactly that and then calls `abort()`
  (`ggml/src/ggml-backend.cpp` L565-578): there is no fallback, and no env var
  disables the tier (`GGML_EXPERT_CACHE` / `GGML_EXPERT_RAM_CACHE` are
  compile-time defines; the `_MAX` pair only sets sizes). The diagnostic start
  proved it — its artifact's `exit` files State `ExitCode` **139**, `OOMKilled`
  false, and the kernel's `traps: llama-server[602541] general protection fault
  ... in libc.so.6[289a2,...]`, which is glibc's `abort()` reaching its
  last-resort `hlt` because llama-server is PID 1 and drops the `SIGABRT` it
  sends itself. The 2026-09-13 hand start served because its unrecorded flags
  allowed io_uring, not because anything degraded gracefully.
  `_unit.sh` then removed the container, so its exit
  code, OOMKilled flag and State.Error, and the rig's kernel log, were never
  filed. Now, whenever a unit step fails after `docker run` — the container
  exited before `/health` said ok, said no ok in 900 s, or anything later failed
  while it exists — it files, before anything removes the container, the
  artifact's `exit`: `state`, the container's whole `docker inspect` State
  through the door's docker shim (ExitCode, OOMKilled, Error, StartedAt,
  FinishedAt and Status among it), and `kernel_log`, the rig's `journalctl -k`
  from the START marker (`kernel_log_since`) to now through the door's ssh shim,
  with `kernel_log_command` as run. A read that fails is filed as `state_error`
  or `kernel_log_error`, its exit code and what it said, and what journalctl says
  on stderr beside a log it printed as `kernel_log_stderr`; neither is a stop.
  `failure` names the exit code and OOMKilled. The cause is data: `check` still
  fails the entry for exiting and does not judge why. `_move.sh` is unchanged: a
  move's failed start keeps its whole docker logs, as above.
- **A failed retry gets one diagnostic start** (2026-09-15, "Fix PR, then one
  diagnostic start"). `plan.py diagnose --use U --entry E --reason "..."
  [--log-from TREE]` refuses unless E is a retry of a unit entry, has no
  diagnostic start yet, is logged and fails its check. It lists the diagnostic
  start under `diagnostics` in `<use>/retries.json`, beside its own ruling, and
  writes its wrapper, `NN-<step>-diag1.sh`, declaring `<artifact stem>-diag1.json`,
  both named from the retried entry's; `read_runs` places `<entry>-diag1` right
  after the failed retry in that rig's order, with the same unit, cold start and
  door command, and only the step path and artifact name differ. `check` says the
  retry failed, diagnosed by `<entry>-diag1`, and the driver goes on to the
  diagnostic start. **If the diagnostic start passes its check, it stands in for
  the failed entry exactly as a passing retry would**: `assemble` keeps the entry
  and its retry in `runs.json` with their reasons (`retried_by`, `diagnosed_by`)
  and counts the diagnostic start among the K valid runs in their place. If it
  fails, the driver stops as for any entry, with its exit cause filed. A
  diagnostic start gets no retry, re-run or second diagnostic start.
  `rig-id-relock` gives srv2-01-retry1 its diagnostic start, `srv2-01-diag1`;
  running it waits on the owner's ruling.
- **A unit states the seccomp its engine needs, and a changed launch gets one
  fresh start** (2026-09-16, "Fix PR: allow io_uring"). A unit's `launch` may
  state `seccomp:`, a profile file named relative to `fleet-setup/`. Both
  launch paths apply it: `_unit.sh` passes `--security-opt seccomp=<file>`
  (absolute — the docker CLI reads the profile itself and, under the door, runs
  here against the rig's daemon over `-H ssh://<rig>`), and `mcgyvr emit`
  renders `security_opt` into the compose file and writes the profile beside
  it, which is where compose resolves it. A unit that states none launches
  exactly as before; a stated profile that is not a file is refused by name
  before the rig is touched; and `_move.sh` refuses a unit that states one,
  because its stopwatch runs docker on the rig, where a path on the operator's
  disk is not readable. `srv2_35b_256k` states
  `seccomp/io-uring.json` — docker's default profile plus `io_uring_setup`,
  `io_uring_enter` and `io_uring_register`, and nothing else
  (`fleet-setup/seccomp/README.md` records its base and commit). It is not part
  of what `digests-<rig>.json` hashed, so no `unit_id`, combination id or lock
  record moves.
  `plan.py relaunch --use U --entry E --reason "..." [--log-from TREE]` then
  gives a logged failed diagnostic start of a unit entry ONE fresh cold start,
  `E-relaunch1`, listed under `relaunches` in `<use>/retries.json` beside its
  own ruling and placed right after it: the same unit, cold start and door
  command, under the launch as it now stands. It refuses an entry that is not a
  diagnostic start, is unlogged, passes its check, already has a fresh start, or
  is itself one. `check` says the diagnostic start failed, relaunched by
  `E-relaunch1`, and the driver goes on to it; a passing fresh start stands in
  for the entry exactly as a passing retry would, and a failing one stops the
  driver. The three runs that failed under the old launch stay exactly as they
  are. `rig-id-relock` gives srv2-01-diag1 its fresh start,
  `srv2-01-relaunch1`; running it waits on the owner's ruling.
- **A vLLM backend is read from the whole log, and the line is recorded**
  (2026-09-16, "fix the reader and record the line"). `rig-id-relock`'s srv2-03,
  a `read` of the b-small pair on srv2, failed with `STOP srv2-03: srv2_3b
  reported no attention_backend` while BOTH vLLM units filed
  `attention_backend: null` — the check names only the first. Everything else in
  that read was fine: srv2_3b card 3446 MiB, decode 126.54, prefill 12393.58;
  srv2_7b card 7522 MiB, decode 68.32, prefill 6773.06; restarts 0.
  `rig-units.sh`'s `backend_of` took the first line matching
  `attention[ _]backend` and looked for a token in that line alone, so a log
  naming the backend on any other line read `none`; the live journal holds
  exactly two `attention_backend` rows ever, both null, both from this read. The
  09-13 method that worked
  (`records/measurements/fleet-setup-2026-09-13/srv2/measure_vllm.py:89-99`)
  searched the WHOLE log for the same tokens and recorded `FLASH_ATTN` for these
  same units. So `backend_rows` searches the whole log over the same token list,
  and the 2026-09-15 B4 rule still holds: a log naming no token anywhere stays
  `none`, never a guess. Beside it the reader prints `backend_line=PORT,BASE64`,
  the first line it matched, truncated to 400 characters on the rig and again in
  `mcgyvr.fleet.read`, so a huge log cannot bloat a row or a journal entry, and
  empty when the log has no such line. A read files it as
  `attention_backend_line`, data that is never judged, so a `none` names the
  wording the rig printed instead of nothing. **The stop does not move**:
  `assemble_evidence.py` still refuses a backend that is missing or not
  unanimous, and `<unit> reported no attention_backend` still stops the driver.
  srv2-03 is logged as failed, so it gets its one retry, `srv2-03-retry1`, under
  the rule above: a read has no wrapper and no artifact of its own, so the retry
  is the same door command under the run id `drive.sh` mints for it.
  **This ruling covers the `read`.** `plan.py`'s `RETRIED` also admits a `load`,
  which the owner has not ruled on: Claude extended the ruling because a load is
  the same shape as a read — it starts nothing, and `drive.sh` mints its run id
  the same way — and no load has failed in this window. The first one that does
  is worth putting to the owner before it is retried. A serve-up or serve-down
  is refused either way, for the reason in the retry rule above.

## Stop and ask

`drive.sh` runs `assemble_evidence.py check` after every entry and stops at the
first non-zero (`STOP <reason>`, exit 3). The list is `stops()` in
`assemble_evidence.py`, and only there. An exit code is logged and never decided
on. A logged failed entry with its one retry is the exception: its re-check is
logged as failed, retried by its retry, and the retry runs next. So is a logged
failed retry with its one diagnostic start: logged as failed, diagnosed by it,
and the diagnostic start runs next.

## The evidence, mapped

`assemble` writes `fleet-setup/evidence.json` in the shape `src/mcgyvr/fleet/lock.py`
reads:

| evidence | from |
|---|---|
| `rigs.<rig>.card_mib` | the snapshot's `gpu_vram_mib`, one value across every run |
| `rigs.<rig>.snapshot` | the last run's snapshot; one rig id across the runs, and the pin itself for a rig `use.json` keeps |
| `combinations[].overhead_mib` | max `gpu_reserve_mib`, refused beyond gate 2's tolerance of hosts.json (`02-rig.py:62-66`) |
| `combinations[].card_peak_mib` (llama.cpp) | max of the until-idle peaks, K runs sampled until idle |
| `combinations[].restarts` | max of every count, which must be 0 |
| `combinations[].warm_decode_tok_s`, `prefill_tok_s` | median of the run medians |
| `combinations[].attention_backend` (vLLM) | unanimous across the runs, and the pin |
| `combinations[].validated_at` | as defined above |
| `combinations[].envelope` | the evidence folder(s) |
| `combinations[].baseline_tok_s` | `{}` |
| `moves[].downtime_s`, `wake_s` | max of the runs |

It refuses, by name: a frozen entry missing its log row, artifact or rows; any
check failure; fewer than K valid runs; a median that is not the median of its
samples; Σ room + overhead > card for any layout (`lock.py:138`); a reply that
cannot finish inside `request_timeout_s` (`lock.py:240-245`); a `validated_at`
not after the journal's last alert; and a move with t1 < t0, t2 < t1, or a
compose target without `t_compose`. `<use>/runs.json` holds every run whole, and
the fleet.yaml edits (rig ids, `room_mib` per unit) are printed, never written.

## Unique artifact names

The door declares a step's artifacts statically — gate 5 reads `# RUN_ARTIFACTS:`
from the step file's text (`05-envelope.py:423-437`) and refuses a declared name
that already exists (`05-envelope.py:635-643`) — and a step's arguments cannot
send its output elsewhere (`run.py:697-736`). `--suffix` gives a re-run its own
run id but not its own file name; a `RUN_REWRITES` declaration would move each
earlier run aside as `<name>.superseded-<run id>.json` (`05-envelope.py:645-682`)
and name a kept data point superseded. So each campaign run of a use has a
generated three-line wrapper of its own, which declares one artifact and execs
`_unit.sh` or `_move.sh`. Its step name — the use, the rig, the run and the unit
or move — is also the run id's tail, so no two runs share a run id either.
