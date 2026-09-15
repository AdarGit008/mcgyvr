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
| `plan.py` | freezes a use's order into `<use>/RUNS.md` and writes its wrappers |
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
  with no time limit. The verdict is the 30-s card peak ≤ room. Pace, the
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

## Stop and ask

`drive.sh` runs `assemble_evidence.py check` after every entry and stops at the
first non-zero (`STOP <reason>`, exit 3). The list is `stops()` in
`assemble_evidence.py`, and only there. An exit code is logged and never decided
on.

## The evidence, mapped

`assemble` writes `fleet-setup/evidence.json` in the shape `src/mcgyvr/fleet/lock.py`
reads:

| evidence | from |
|---|---|
| `rigs.<rig>.card_mib` | the snapshot's `gpu_vram_mib`, one value across every run |
| `rigs.<rig>.snapshot` | the last run's snapshot; one rig id across the runs, and the pin itself for a rig `use.json` keeps |
| `combinations[].overhead_mib` | max `gpu_reserve_mib`, refused beyond gate 2's tolerance of hosts.json (`02-rig.py:62-66`) |
| `combinations[].card_peak_mib` (llama.cpp) | max of the 30-s peaks |
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
