# Fleet identity — every launch and every figure keyed to what it was computed for

**Status.** RED, rewritten 2026-09-11 to the design the owner ruled after the
board review of 2026-09-10. The design is one fleet lock instead of five hashed
shapes, fleets as named layouts of room slots that move only along listed
switches, and a fixed room per unit. The failing specification is this plan and
90 RED tests (B1–B90, P0 included), with no line under `src/`.
- **Commits.** The RED specification lands as one commit on `red/fleet-identity`.
  P0's GREEN fixes land inside #430 (`red/sleep-wake`), before P1.
- **Parked.** The five-id design's plan and tests stay on the local branch
  `park/fleet-identity-five-ids`.
- **Measurements.** The measurements this design waits on are owned by
  `red/fleet-identity-measurements`.
- **Gaps.** B83–B90 close what a comparison of the serving terms against this
  plan found untracked (owner's rulings, 2026-09-11), on `red/fleet-identity-gaps`:
  per-combination headroom, a llama.cpp unit's card peak, the vLLM attention
  backend, prefill, and CUDA_Host.

**Why.** The flexibility campaign
(`records/measurements/flexibility-2026-09-09/README.md`) found seven defects and
seven records made false. Most share one cause: a figure or a launch that does
not say what it was computed for.
- srv2 serves a compose `emit --check` rejects.
- The Waker's memory lives in a `/tmp` this machine cannot write.
- Decode figures were quoted without "cold".

The fix has three parts. Each thing that runs gets a name. A lock says which of
those things production may run. Every observation is stamped with the names it
was computed for.

---

## 1. Identities

```
unt-  unit         = H{ engine, image id (sha256:…), weights sha256, argv, env, GPU compute capability }
rig-  rig          = H{ host, hardware, system }                   any hardware or system change renames it
cmb-  combination  = H{ rig-, [ slot 0, slot 1, … ] }              each slot: (unt-, awake | asleep) or free
      fleet        = a name (flt-05) pinned to sha256{ rig- → cmb- }
```

**ID-1.** One primitive, the shape of `Config.digest()`
(`src/mcgyvr/config.py:1092`, prefix at `:49`): a prefix plus the sha256 of a
canonical tree. A missing field is refused, never hashed. The retired prefixes
`msp-`, `rsh-`, `fsh-` and `cfg-` are refused as identity kinds.

**ID-2.** A unit hashes its whole resolved launch, with no hand-kept field list.
The vLLM research in §8 found KV capacity moved by flags whose effect differs by
model family, and a list misses the next such flag silently. A tag is not an
image: srv1's `llamacpp:b10644-L3` is a local build a rebuild replaces under the
same string, so the id is the image's `sha256:` Id.

**ID-3.** Tolerances are not hashed. They live in the lock.

**ID-4.** A rig's units are an **ordered list of room slots** (owner: "list
position is a room slot").
- Slot k is identity; the order units start in is not.
- A slot holds a unit, `awake` or `asleep`, or is free. An asleep unit keeps
  its room; a unit whose room is freed leaves its slot free.
- Keeping the room and freeing it are two combinations, and so two fleets
  (owner: "save room vs don't save = 2 different rig setups = 2 different
  fleets").
- Level-1 vLLM sleep stays refused (`src/mcgyvr/serving/servelib.py:234`).

**A rig is renamed by any hardware or system change** (owner's ruling). That
inverts `src/mcgyvr/scan.py:642` on purpose. RAM moved between the rigs twice in
six days, and a BIOS reset took PL1 from 95 W to 4095 W
(`tools/runs/hosts.json` `_rig_doc`). Whether `gpu_reserve_mib` belongs in the
name is open (§12).

## 2. Two files, one vocabulary

| file | holds | locked |
|---|---|---|
| `fleet.yaml` | units (address, engine, launch, model, room, width, window, output_tokens, request_timeout_s), rigs, fleets (layout as room slots, next) | yes |
| `policy.yaml` | ladder (an ordered list of unit names), fanout, attempts, max_escalations, max_attempts, task_timeout_s, max_window_fraction, breadth, cleanup, orchestrator, verifier, sandbox, delivery, journal | no |

**The rule.** A fact about what a unit is or can physically do is locked. A
decision about how work moves between units is policy.

**What is not a setting.**
- Deterministic-first and cheap-first are code (`src/mcgyvr/route.py:3-16`).
- `budgets.wake_timeout_s` goes (§5).
- A rig's card total and headroom are measured in dev and live in the lock (§4),
  never in `fleet.yaml`.

**Retired words.** "config", "source", "rung" and "tier" are gone; a unit is the
one term.

**Outside units.** A unit outside every rig (a cloud API, another team's server)
is a unit with no rig. It is not locked, except for the address check in §4.

| name | means | not |
|---|---|---|
| `host` | the name a rig is reached by (`srv1`) | "tag", which is a docker image tag here |
| `rig` / `rig_id` | the physical box: host, hardware, system | "machine" |
| `os_machine_id` | the OS install (`/etc/machine-id`) | the two functions now both called `machine_id` (`src/mcgyvr/scan.py:894`, `src/mcgyvr/serving/gatelib.py:388`) |
| `unit` / `unit_id` | one process at one address, its launch resolved | `UnitKey` (`src/mcgyvr/serving/__init__.py:399`), which addresses a process and names no knob; "source", "rung", "tier" |
| `slot` | one room on a rig's card, by position | "start order" |
| `combination` | one rig's slots, each holding an awake or asleep unit, or free | "rig shape", "state" |
| `fleet` | a named layout: one combination per rig | "fleet shape", "config" |
| `switch` | an approved move from one fleet to another | "transition" |
| `observation` / `alert` | measured / past its locked tolerance | "deviation" |
| ours | a container of the `mcgyvr` compose project (the door runs every serve as `-p mcgyvr`; `mcgyvr emit` names its units `mcgyvr-<host>-<service>`, `src/mcgyvr/emit.py:505`) | anything else holding the card, which is foreign |

## 3. Switches

```
flt-05 ──▶ flt-02 | flt-11 | flt-14        listed in fleet.yaml; no other switch from flt-05 is approved

"switch to flt-02"   (the operator, or the Waker)
   pair slot k of flt-05 with slot k of flt-02, per rig:
     srv2  slot 0  7b awake  → 7b awake        (none)
           slot 1  3b asleep → 4b awake        drain 3b · stop 3b · start 4b
     srv1  unchanged                           (none)
```

- A switch is commanded at fleet level and carried out at rig and slot level.
  Only slots that differ act.
- Within a slot, the leaving unit drains, then sleeps or stops, **before** the
  arriving unit wakes or starts. How several changing slots interleave is not
  identity.
- The downtime is approved by design, because the switch is (owner).
- With fixed room (§8), a slot the switch does not change never blinks.
- A switch's dev run is keyed by its **rig move**: the rig, the combination it
  starts from, and the actions. One run proves every fleet switch that derives
  the same move, so dev time grows with distinct rig moves, not with pairs of
  fleets.
- The run records the switch's downtime and start/wake times.

## 4. The fleet lock

```
records/fleet/<fleet>.json                   layout sha256, next, and for each switch the rig moves it uses with their times
records/fleet/rigs/<rig->/<cmb->.json        a combination's validation: the rig's measured card, the combination's own
                                             headroom, rooms, pinned KV, each vLLM unit's reported attention backend,
                                             each llama.cpp unit's card steady and peak, restarts, warm decode and
                                             prefill (the locked values are the as-run figures), the no-NVMe baseline,
                                             wake, validated_at, envelope
```

**Who writes it.** `mcgyvr fleet lock` writes these files from passing dev runs
only.
- It locks only the combinations a fleet lists.
- An edit leaves every combination it does not touch byte for byte.
- A switch is locked on a rig move another switch already ran.

Committing the files is the approval. Live reads them offline and never writes
them.

**Locking refuses**, naming what failed:
- a combination no dev run passed;
- a listed switch whose rig move never ran in dev, or ran without recording its
  times;
- a combination whose headroom (Σ CUDA contexts of its units + driver reserve)
  its dev run never measured;
- a combination where Σ unit room + its headroom > card, asleep units included;
- a vLLM unit whose KV size is not pinned (`--kv-cache-memory-bytes`);
- a vLLM unit whose attention backend is not pinned (`--attention-backend`), or
  whose dev run reported a different one;
- a llama.cpp unit with no measured card peak, or whose peak exceeds its room;
- an awake unit whose dev run recorded no prefill;
- a unit whose `output_tokens ÷ validated warm decode tok/s > request_timeout_s`;
- NVMe use that costs warm decode more than its tolerance against the no-NVMe
  baseline. A model too big for any no-NVMe run is locked against its own value
  and marked "no baseline: NVMe required";
- any restart in a dev validation;
- an outside unit answering at a rig unit's address;
- a policy ladder naming a unit the fleet does not have.

Every check is arithmetic on the lock, never a rig read.

## 5. What is judged

| parameter | rule |
|---|---|
| restarts | exactly 0; no tolerance reaches it |
| warm decode | at lock, as-run vs the no-NVMe baseline; live, alerts only below its locked as-run value less tolerance |
| card memory (llama.cpp), steady and peak | each alerts only above its locked value plus tolerance; the peak is the highest reading across the load and the requests |
| prefill | alerts only below its locked as-run value less tolerance |
| L2 wake | judged against its locked value (± tolerance) |
| a switch | downtime, start and wake times, against its rig move's dev run |
| swap-out, swap-in, major faults | recorded beside every observation, never alerted: NVMe is allowed wherever warm decode holds |
| cold wake, vLLM RAM, Shmem | recorded, not alerted, until measured |
| CUDA_Host, attention backend | recorded beside every observation, never alerted |

**The Waker's wait limit** is a unit's validated wake plus the lock's wake
tolerance. That replaces `DEVIATION_RATIO = 1.5` (`src/mcgyvr/wake.py:98`) and
`budgets.wake_timeout_s`.
- An L2 wake past the limit alerts.
- Before cold wake is measured, a cold wake's limit is its validated cold wake
  plus the lock's provisional wake tolerance. Crossing it ends the wait and
  files the observation, and raises no alert.

**Tolerances are the lock's, and provisional.** Until
`red/fleet-identity-measurements` sets them, they are the survey's proposals
(`records/evidence/2026-09-10-tolerance-survey/`):
- warm decode −3% vLLM, −5% llama.cpp, −15% with CPU experts;
- card +32 MiB (+74 on an arch with no C-step bound);
- L2 wake ±0.1 s.

Prefill has no proposal: the survey holds no prefill observation. Cold wake has
no tolerance yet: it is recorded until measured, and the survey's
cold max(10%, 5 s) is not applied. The tests pin the rules and never these
numbers.

## 6. Live and dev

**Live is production:** mcgyvr delegating real code tasks. It runs a fleet the
user picked from the locked set. The orchestrator never names a fleet, a rig or
a unit.

**Dev runs everything**, `serve up` and `down` included, with any launch spec.
Gate 1's composition guard (`refuse_unless_the_live_ladders_own`,
`src/mcgyvr/serving/gate-scripts/01-round.py:112`) goes.

**Gate 1.**
- A live `serve up` is admitted if and only if its units are in the fleet lock
  for that rig. Gate 1 reaches no rig, so the refusal costs no rig time.
- A live `serve down` is always admitted, because stopping starts nothing
  unapproved and it is the way out.

**Admission** (`mcgyvr run`, `mcgyvr serve`, the Waker):
- no fleet named, or a fleet with no lock → refused;
- a fleet whose layout was edited after it was locked → refused, and the refusal
  says to re-lock;
- a rig that is not the rig it was locked on → refused, naming the rig and its
  id;
- units of ours the fleet does not name → cleaned, and the fleet restored;
- an empty rig → restored;
- a process that is not ours (§2) → that rig refused, naming the process.

**The Waker** wakes a unit only along a listed switch: one door run toward a
fleet the current one lists, and nothing toward one it does not.

**A dev run holding the rig's lease** is displaced by gate 2's existing rule
(live outranks dev, R1), and its serve units are torn down (P0).

## 7. Observations and alerts

- **Stamping.** Every observation is filed under the journal, stamped with the
  fleet, `rig-`, `cmb-` and `unt-` it was computed for. Nothing goes under
  `/tmp`, so the Waker's `/tmp` memory (`src/mcgyvr/wake.py:217`, `:341`) goes.
- **Dev** fails on an alert.
- **Live** does three things:
  - warns once, as one `warning:` line on stderr;
  - counts repeats;
  - **pulls the combination at once:** its units stop taking work, requests
    already running finish, and its containers stay up for inspection. A pull
    asks for no stop.
- **Clearing.** A pull clears only when the combination's validation is
  re-committed (a `validated_at` newer than the alert). A clean reading later does
  not clear it. `rejudge` reports what a tighter tolerance finds and pulls
  nothing.
- **Nothing left.** With every combination pulled, live refuses all work loudly,
  naming each.
- **Reading alerts.** `mcgyvr fleet alerts` lists the pulled combinations. The
  run's own stdout carries no alert: that channel is the caller's.
- **Readers.** `/proc/meminfo`, `/proc/vmstat`, and card use per container, where
  a process in no container of ours is foreign.

## 8. Memory: fixed room per unit

**Rule, per combination:** Σ unit room + headroom ≤ card, asleep units included.

- **A vLLM unit's room** is its share (`--gpu-memory-utilization`), with its KV
  size pinned (`--kv-cache-memory-bytes`, in `unt-`).
- **A llama.cpp unit's room** is its computed card need (`vramfit`; qwen3next
  needs 829 MiB, not `SCRATCH_AND_CONTEXT_MIB = 768`,
  `src/mcgyvr/serving/vramfit.py:66`, measuring-gaps Q3).
- **Card total** is measured per rig in dev and recorded in the lock.
- **Headroom** is measured by each combination's own dev run and recorded in its
  record, never pooled across a rig. The CUDA context it holds differs per card
  and per engine: llama.cpp read 115.69 MiB on srv1's GTX 1660 SUPER and 146.69 on
  srv2's RTX 3060 for one model and `-ub`, on two images
  (`records/evidence/2026-09-04-srv1-ncmoe-floor/srv1-buffer-probe.tsv:6`,
  `srv2-buffer-probe.tsv:5`); vLLM's driver and context read 470 MiB on srv1 and
  491 on srv2 on one image (ADR-0039,
  `archive/docs/archive/decisions/0039-a-serving-memory-declaration-is-bytes-not-a-fraction-of-the-card.md:229-231`).
- **A llama.cpp unit's peak must fit its room.** The lock takes the peak from the
  dev run, never from `DEFAULT_HEADROOM_GB = 2.0`, the guess held back for a model
  with no geometry (`src/mcgyvr/serving/__init__.py:553`). A peak sampled only
  while loading reads 2–26 MiB below steady
  (`records/measurements/fleet-gaps-2026-09-09/README.md:78-81`), so the peak
  spans the requests too.
- **A vLLM unit's attention backend** is pinned in its launch, because the card
  decides what is valid: srv1 (cc 7.5) reports `TRITON_ATTN`
  (`records/evidence/2026-08-31-inventory/board3-srv1-off1v1.log:25`), srv2
  `FLASH_ATTN` (`records/evidence/2026-08-24-resolved-config/srv2-startup.log:22`)
  and `FLASHINFER` under an fp8 KV cache
  (`records/evidence/2026-08-24-config-sweep/srv2-1.5B.jsonl:12`). v0.26.0
  resolves `--attention-backend` (`srv2-1.5B.jsonl:38`).

**Why start order stops mattering.** These are facts from the vLLM v0.26.0
code, the version srv2's pinned image digest `ffb2d59b…` runs:
- A share is a fraction of the card's **total** memory
  (`vllm/v1/worker/utils.py:430-432`).
- A unit whose share is not free at start refuses rather than shrinks
  (`utils.py:434-443`).
- A pinned KV size returns before any profiling (`vllm/v1/worker/gpu_worker.py:462-480`).

So when Σ share × card + headroom ≤ card, every start passes in any order, and a
neighbour cannot move anyone's KV cache.

**srv2 today.** Its shares 0.26 + 0.72 of 11.63 GiB leave 0.23 GiB for two CUDA
contexts and the reserve. That is too thin, so the shares shrink, sized by the
measurement branch.

**Corrections.**
- **Refuted.** The previous version of this plan
  (`park/fleet-identity-five-ids`, `records/plans/fleet-identity.md:126-129`)
  said the first-started unit decides a vLLM KV split. The 3B's 42,608 tokens
  against 12,352 came from two things, and start order was neither:
  - a restart after a crash, whose peak activation read 0.15 GiB instead of
    0.60;
  - the 7B releasing about 0.59 GiB inside the 3B's profiling window.

  The 7B started first in every arm (`results-q14-pair-healthy.json`,
  `results-q15-sleepmode.json` in `records/measurements/flexibility-2026-09-09/`;
  `records/measurements/fleet-gaps-2026-09-09/results-vllm.json`).
- **Contradicts the code.** The `src/mcgyvr/emit.py:411-414` docstring says a
  vLLM unit "sizes its cache from `--gpu-memory-utilization` of what is free *at
  load*". The code takes a fraction of the total. Order decides whether a unit
  starts, not its cache.

## 9. Given up (owner accepted)

All of it is kept on `park/fleet-identity-five-ids`:
- the pre-load fit check that read the rig live (previous B27–B29);
- the transition engine: lease, read, verdict, one unit at a time after healthy
  (previous B30–B33);
- BOUND/EXPECTED as a runtime class, and the 1% rule as a test (previous B21,
  B22, B24–B26);
- the model spec, rig shape and fleet shape ids, and the config digest as an
  approval key (previous B5–B8, B15–B20, B35–B40, B51);
- alert buckets and paging judged as an alert (previous B54, B55, B57, B59, B60);
- the per-process status reader (previous B47);
- the GGUF quant/expert scan and the HuggingFace scan that fed the model spec
  (previous B49, B50).

## 10. Existing tests changed, and why

**Unchanged from the previous RED commit.**
- The ten wake and sleep tests that declare `profile: dev`:
  - in `tests/test_a_sleeping_rung_is_woken_rather_than_declined.py`:
    `test_with_the_switch_off_a_refused_port_ends_the_run_exactly_as_it_does_today`,
    `test_a_refused_vllm_card_this_config_holds_a_spec_for_is_woken_not_written_off`,
    `test_the_dispatch_that_follows_a_wake_spends_no_attempt`,
    `test_a_llama_cpp_card_is_woken_exactly_as_a_vllm_one_is`,
    `test_a_card_with_no_launch_spec_is_down_rather_than_asleep`;
  - in `tests/test_sleeping_a_card_takes_every_rung_it_serves.py`:
    `test_sleeping_the_card_takes_both_rungs_down_in_one_door_run`,
    `test_an_operators_own_sleep_is_not_gated_by_the_automatic_switch`,
    `test_a_dispatch_in_flight_is_never_cut_by_a_sleep`;
  - in `tests/test_a_launch_spec_this_config_does_not_plan_is_never_woken.py`:
    `test_a_wake_that_cannot_say_which_spec_starts_nothing_and_says_so`,
    `test_a_host_of_alternatives_is_not_no_launch_spec`.
- The two dev-refusal tests removed from `tests/red_port/test_dod_profile.py`.

**Docstring updated.** Only prose changed in these two files; their assertions
are the same.
- `tests/test_a_dev_round_may_serve_any_launch_spec.py`, which replaced
  `test_a_dev_round_may_operate_the_ladder_it_may_not_install.py`. It now points
  at gate 1 and admission.
- `tests/test_draining_a_source_whose_rung_declares_a_width_does_not_raise.py`,
  now B78 in P0.

**Stub changed.** The docker stub in `tests/onedoor.py` now removes on
`compose down` what Docker's does: the containers the file names, and with
`--remove-orphans` every other `mcgyvr-` container. It used to clear every
listed name, which would have let B81 pass under the defect it pins.

**Changed by the gaps commit (B83–B90).**
- `tests/test_the_fleet_lock_is_written_only_from_passing_dev_runs.py`: headroom
  moves from the rig to each combination, and B31 is renamed
  `test_a_combination_whose_headroom_dev_never_measured_is_not_locked`. The
  fixture's vLLM units pin `attention_backend`, and each combination carries its
  reported backend and as-run prefill, so B27–B42 still describe a lockable fleet.
- `tests/test_an_alert_pulls_its_combination_until_it_is_revalidated.py`:
  `card_mib` becomes `card_steady_mib` and `card_peak_mib`, and B64 judges both.
  The approved fixture carries a prefill value for B89.

**Deleted, parked.**
- `test_a_model_spec_and_its_units_are_named_by_what_they_resolve.py`
- `test_a_rig_shape_and_fleet_shape_name_what_was_planned.py`
- `test_a_fit_is_read_from_the_rig_not_summed_from_the_shape.py`
- `test_a_transition_locks_reads_and_starts_one_unit_at_a_time.py`
- `test_a_deviation_fails_a_dev_run_and_warns_a_live_one.py`
- `test_a_parameter_past_its_tolerance_alerts_the_operator_once.py`
- `test_a_model_scan_reports_its_quant_and_expert_params.py`
- `test_a_live_run_is_an_approved_fleet_shape_or_nothing.py`

**Renamed.**
- `test_a_rig_is_its_hardware_and_system_and_not_its_reserve.py` →
  `test_a_rig_is_its_host_hardware_and_system.py`. The reserve test goes; the
  reserve is open (§12).
- `test_a_bound_is_small_verified_and_scoped.py` →
  `test_the_scratch_allowance_for_qwen3next_is_what_it_measured.py`, which keeps
  only the 829 MiB test (B77).
  - **Why it may pin a number.** Measured values belong to the measurement
    branch, but this one is exempt: its measurement already landed in
    `b08b4c31` (`records/measurements/measuring-gaps-2026-09-10/README.md` Q3).

**Rewritten.**
- `test_a_fleet_id_is_a_prefixed_content_digest.py` now covers three kinds and
  the retired prefixes.
- `test_rig_readers_parse_what_the_kernel_and_the_driver_print.py` loses the
  per-process status reader.
- The Waker test moves into
  `test_live_runs_only_a_locked_fleet_and_cleans_what_is_not_in_it.py` (B55).

**Changes when gate 1 enforces the lock (P2).** These door tests `serve up`
under the default profile with no lock, and in the same change they declare
`profile: dev`:
- `tests/test_the_door_serves_a_ladder_and_leaves_it_up.py:107-173` (four
  tests) and `:208-218` (one);
- the P0 tests B79 and B80.

The ruling spoke of six door tests; that six included the two `serve down` tests
(`:179-206`). They stay live, because gate 1 always admits a live down, and so
do B81 and B82.

## 11. Phases

| | work |
|---|---|
| P0 | **Inside #430, before P1.** GREEN fixes: the `Capacity.drain` sort (`src/mcgyvr/capacity.py:1288`, B78); a second wake of a card on one day (B79); a restart count per unit in `serve-up.json` (B80); `serve down` removes every container of ours (B81); gate 2 tears down a displaced dev run's serve units (B82). #430 goes green by fixing its base failures on `red/sleep-wake` (listed below). |
| P1 | two files and one vocabulary: `fleet.yaml` / `policy.yaml`, and "unit" for source, rung and tier (B22–B26) |
| P2 | identities and slots (B1–B21, `os_machine_id` included), the lock and its checks (B27–B43, B83–B88), gate 1's lock check shipped with the guard's removal and the door tests' `profile: dev` (B46–B47, B58–B59), qwen3next 829 (B77) |
| P3 | live admission, auto-clean, the Waker only along listed switches (B48–B57), and card use per container, which B54's foreign-process refusal reads (B76) |
| P4 | observations, alerts, pulls, `mcgyvr fleet alerts`, the other readers (B60–B75, B89–B90); the wake limit from the lock, and the `/tmp` memory and `DEVIATION_RATIO` go (B44–B45) |
| measurements | `red/fleet-identity-measurements`, in parallel with P1–P4: warm decode baselines and tolerances, cold wake, vLLM RAM, Shmem, fp8 KV on the RTX 3060, `--kv-cache-memory-bytes` on a rig, headroom per rig, `gpu_reserve_mib` across boots; not yet planned there: headroom per combination, a llama.cpp card peak spanning requests, prefill |

**#430's base failures.** The base `938a5158` fails five tests, and docs-check
fails on the `SETUP.md` drift:
- `test_one_door.py::test_nothing_under_records_is_executable`
- `test_the_mcgyvr_skill_is_rendered_from_the_schema.py::test_docs_check_refuses_a_skill_that_drifted`
- two in `test_the_seam_holds.py`: `mcgyvr.wake` and `mcgyvr.weights` are in
  neither half, and `mcgyvr.config` imports `mcgyvr.serving.servelib`
- `test_the_setup_document_is_rendered_and_drift_checked.py::test_setup_markdown_on_disk_is_byte_identical_to_render_setup`

Every phase ends on `make check` and `make docs-check`. `src/` moving opens a
round.

## 12. Open

- **`gpu_reserve_mib` in the rig's name — answered by the measurement branch.**
  Gate 2 compares it literally with `tools/runs/hosts.json`
  (`src/mcgyvr/serving/gate-scripts/02-rig.py:238-242`). Two boots per rig are
  now read idle and btime-stamped (`results-reserve.json`): srv1 401 MiB on
  2026-09-01T08:11:08Z and 399 MiB on 2026-09-11T06:34:36Z — a 2 MiB move across
  a reboot with every other declared key identical — and srv2 377 MiB on both
  boots. The reserve therefore does not name the rig; the fix on
  `red/card-reserve-bound` (#439) drops it from the identity and from gate 2's
  literal comparison.
- **Snapshot gaps.** The rig snapshot reads no kernel, swap, swappiness or
  MemTotal (`src/mcgyvr/serving/gate-scripts/rig-snapshot.sh:185-197`), and
  `rig-` needs them (P2).
- **Tolerance values** are now measured in `tolerances.json` (warm decode:
  vLLM 1%, llama.cpp 1%, CPU experts 48% — the 48% rests on one unit and one
  outlier baseline sample, and needs an owner ruling) and `wake.json` (cold-wake
  clocks). The prefill tolerance stays open (below).
- **Offline matching at gate 1.** Gate 1 reaches no daemon. Which launch fields
  it matches against the lock offline is open; the image Id is the daemon's, and
  gate 3 reads the daemon.
- **Placeholder seams.** The seam paths the tests resolve (`mcgyvr.fleet.*`,
  `mcgyvr fleet alerts --journal`) are placeholders
  (`tests/red_port/conftest.py`): rename them freely, and keep what is asserted.
- **Prefill tolerance.** The survey holds no prefill observation, and the
  measurement branch's M1 reads decode only. B89 pins the rule; the value is owed.
- **Pooled CUDA context.** "85–147 MiB" (`src/mcgyvr/serving/vramfit.py:6`,
  `records/plans/fleet-shape/evidence_and_params.md:60`,
  `okf/must-read/touching-rigs.md:173`) is not a per-card figure. Its 147 is
  srv2's Qwen3.6 reading, not net of idle
  (`records/evidence/2026-09-04-srv1-ncmoe-floor/srv2-buffer-probe.tsv:6`), where
  srv1 read 116.69 for the same model (`srv1-buffer-probe.tsv:7`), so the range
  spans cards, images and instruments.
- **measuring-gaps Q3's `-ub 1024` rows ran at `-ub 512`.** Each
  `compose.srv*-q3-*-ub1024.yml` passes `-b 512 -ub 1024`, and llama.cpp clamps
  the micro-batch to the batch. So the README's "the `-ub` law … saturates"
  (`records/measurements/measuring-gaps-2026-09-10/README.md:83-86`) is that
  clamp, not a law. B77's 829 MiB stands, because units run at `-ub 512`
  (`DEFAULT_UBATCH`, `src/mcgyvr/serving/__init__.py:89`).
- **Two "headrooms".** `DEFAULT_HEADROOM_GB` and `Fit.headroom_gb` hold back
  room for one unit; the lock's headroom is a combination's CUDA contexts plus
  the driver reserve. One word should mean one thing.
- **Proposed, not ruled.** The rewrite made these choices, which the owner has
  not ruled on:
  - the `cmb-` content-digest prefix for a combination (B1, B14);
  - `engine` as a field of `unt-` (B5–B8);
  - refusing a retired word, or a key in the wrong file, naming its replacement
    (B24–B26);
  - `rejudge` reporting only, pulling nothing (B72).

  The gaps commit made these:
  - headroom per combination rather than per rig (B31, B83);
  - refusing a llama.cpp peak above its room (B85);
  - refusing a reported backend other than the pinned one (B87);
  - refusing a lock whose dev run recorded no prefill (B88). The owner ruled
    that prefill is judged; the refusal is what gives a live run a value to
    judge against.
  - dropped: writing `GGML_OP_OFFLOAD_MIN_BATCH` into a unit's environment. No
    record names it, and op offload is `--no-op-offload` in the argv, which
    `unt-` hashes.

---

## Behaviors

`tests/test_a_fleet_id_is_a_prefixed_content_digest.py`
- B1 Every identity kind (`unt-`, `rig-`, `cmb-`) carries its own prefix — `test_every_identity_kind_carries_its_own_prefix`.
- B2 Key order does not change an identity — `test_key_order_does_not_change_an_identity`.
- B3 Any changed or added field is a new identity — `test_any_changed_or_added_field_is_a_new_identity`.
- B4 A retired or unknown prefix is refused — `test_a_retired_or_unknown_prefix_is_refused`.

`tests/test_a_unit_is_named_by_its_whole_resolved_launch.py`
- B5 A unit id is `unt-` plus a digest of its launch; env order is not identity — `test_a_unit_id_is_unt_plus_a_digest_of_its_launch`.
- B6 Any flag, image, weights, environment, card generation or engine is a new unit — `test_any_flag_image_weights_environment_or_card_is_a_new_unit`.
- B7 A tag is not an image id — `test_a_tag_is_not_an_image_id`.
- B8 A launch missing a field is refused, not hashed — `test_a_launch_missing_a_field_is_refused_not_hashed`.

`tests/test_a_rig_is_its_host_hardware_and_system.py`
- B9 A driver bump mints a new rig — `test_a_driver_bump_mints_a_new_rig`.
- B10 A BIOS reset mints a new rig — `test_a_bios_reset_mints_a_new_rig`.
- B11 The host is part of the rig — `test_the_host_is_part_of_the_rig`.
- B12 The scan names the OS install `os_machine_id` — `test_the_scan_names_the_os_install_os_machine_id`.
- B13 The door names the OS install `os_machine_id` — `test_the_door_names_the_os_install_os_machine_id`.

`tests/test_a_fleet_is_a_named_layout_that_moves_only_along_its_switches.py`
- B14 A combination names its rig and what each room slot holds; slot k is identity — `test_a_combination_names_its_rig_and_what_each_room_slot_holds`.
- B15 A unit is awake or asleep and nothing else — `test_a_unit_is_awake_or_asleep_and_nothing_else`.
- B16 A fleet name is pinned to the sha256 of its layout; an edited layout says re-lock — `test_a_fleet_name_is_pinned_to_the_sha256_of_its_layout`.
- B17 Only a listed switch is approved — `test_only_a_listed_switch_is_approved`.
- B18 A switch acts only on the slots that differ — `test_a_switch_acts_only_on_the_slots_that_differ`.
- B19 A switch pairs slot k with slot k and stops before it starts — `test_a_switch_pairs_slot_k_with_slot_k_and_stops_it_before_it_starts`.
- B20 Sleep and wake are switches like any other — `test_sleep_and_wake_are_switches_like_any_other`.
- B21 A rig move proven once serves every fleet switch that derives it — `test_a_rig_move_proven_once_serves_every_fleet_switch_that_derives_it`.

`tests/test_the_fleet_and_its_policy_are_two_files.py`
- B22 A unit carries its model, width, window, reply size and timeout — `test_a_unit_carries_its_model_width_window_reply_size_and_timeout`.
- B23 The policy ladder is an ordered list of unit names — `test_the_policy_ladder_is_an_ordered_list_of_unit_names`.
- B24 A unit fact in the policy file is refused, naming it — `test_a_unit_fact_in_the_policy_file_is_refused_naming_it`.
- B25 A policy setting in the fleet file is refused, naming `policy.yaml` — `test_a_policy_setting_in_the_fleet_file_is_refused_naming_policy_yaml`.
- B26 The retired words are refused, naming what replaced them — `test_the_retired_words_are_refused_naming_what_replaced_them`.

`tests/test_the_fleet_lock_is_written_only_from_passing_dev_runs.py`
- B27 The lock files each fleet and each rig combination once, with switch evidence and the as-run decode; an outside unit is never locked — `test_the_lock_files_each_fleet_and_each_rig_combination_once`.
- B28 A combination no dev run passed is not locked — `test_a_combination_no_dev_run_passed_is_not_locked`.
- B29 A listed switch whose rig move never ran is not locked — `test_a_listed_switch_whose_rig_move_never_ran_is_not_locked`.
- B30 A switch run that recorded no times is not locked — `test_a_switch_run_that_recorded_no_times_is_not_locked`.
- B31 A combination whose headroom dev never measured is not locked — `test_a_combination_whose_headroom_dev_never_measured_is_not_locked`.
- B32 Every unit's room plus headroom must fit its card, asleep or awake — `test_every_units_room_plus_headroom_must_fit_its_card_asleep_or_awake`.
- B33 A vLLM unit whose KV size is not pinned is not locked — `test_a_vllm_unit_whose_kv_size_is_not_pinned_is_not_locked`.
- B34 A reply its unit cannot finish inside its timeout is not locked — `test_a_reply_its_unit_cannot_finish_inside_its_timeout_is_not_locked`.
- B35 NVMe use is locked only where warm decode holds against its baseline — `test_nvme_use_is_locked_only_where_warm_decode_holds_against_its_baseline`.
- B36 A model with no no-NVMe run is locked on its own value and marked — `test_a_model_with_no_no_nvme_run_is_locked_on_its_own_value_and_marked`.
- B37 A restart in a dev validation is not locked — `test_a_restart_in_a_dev_validation_is_not_locked`.
- B38 An outside unit may not answer at a rig unit's address — `test_an_outside_unit_may_not_answer_at_a_rig_units_address`.
- B39 A policy ladder naming a unit the fleet lacks is not locked — `test_a_policy_ladder_naming_a_unit_the_fleet_lacks_is_not_locked`.
- B40 Evidence for a combination no fleet lists is not locked — `test_evidence_for_a_combination_no_fleet_lists_is_not_locked`.
- B41 Editing one fleet leaves every other combination record untouched — `test_editing_one_fleet_leaves_every_other_combination_record_untouched`.
- B42 A fleet switch is locked on a rig move another switch ran — `test_a_fleet_switch_is_locked_on_a_rig_move_another_switch_ran`.
- B43 `mcgyvr fleet lock` is a command — `test_mcgyvr_fleet_lock_is_a_command`.
- B44 The wake limit is the validated wake plus its tolerance — `test_the_wake_limit_is_the_validated_wake_plus_its_tolerance`.
- B45 The wake ratio in code and the hand-set wake timeout are gone — `test_the_wake_ratio_in_code_and_the_hand_set_wake_timeout_are_gone`.

`tests/test_gate_1_admits_a_live_serve_up_only_from_the_fleet_lock.py`
- B46 A live serve up no fleet lock names is refused at gate 1, before any rig — `test_a_live_serve_up_no_fleet_lock_names_is_refused_before_any_rig`.
- B47 A live serve up of units the fleet lock names is admitted — `test_a_live_serve_up_of_units_the_fleet_lock_names_is_admitted`.

`tests/test_live_runs_only_a_locked_fleet_and_cleans_what_is_not_in_it.py`
- B48 Live names a locked fleet or refuses — `test_live_names_a_locked_fleet_or_refuses`.
- B49 A fleet whose layout was edited after locking is refused — `test_a_fleet_whose_layout_was_edited_after_locking_is_refused`.
- B50 A rig that is not the rig it was locked on is refused, naming its id — `test_a_rig_that_is_not_the_rig_it_was_locked_on_is_refused`.
- B51 The locked fleet on its own rigs is admitted with nothing to do — `test_the_locked_fleet_on_its_own_rigs_is_admitted_with_nothing_to_do`.
- B52 An empty rig is admitted and its fleet restored — `test_an_empty_rig_is_admitted_and_its_fleet_restored`.
- B53 Units of ours the fleet does not name are cleaned and it is restored — `test_units_of_ours_the_fleet_does_not_name_are_cleaned_and_it_is_restored`.
- B54 A process that is not ours refuses that rig and names it — `test_a_process_that_is_not_ours_refuses_that_rig_and_names_it`.
- B55 The Waker does not wake toward a fleet nobody locked — `test_the_waker_does_not_wake_toward_a_fleet_nobody_locked`.
- B56 The Waker wakes a unit along a listed switch — `test_the_waker_wakes_a_unit_along_a_listed_switch`.
- B57 The Waker does not wake along a switch nobody listed — `test_the_waker_does_not_wake_along_a_switch_nobody_listed`.

`tests/test_a_dev_round_may_serve_any_launch_spec.py`
- B58 A dev round may bring up a launch spec of its own — `test_a_dev_round_may_bring_up_a_launch_spec_of_its_own`.
- B59 A dev round may serve when no live ladder is configured — `test_a_dev_round_may_serve_when_no_live_ladder_is_configured`.

`tests/test_an_alert_pulls_its_combination_until_it_is_revalidated.py`
- B60 Every observation is filed under the journal by what it was computed for, nothing under `/tmp` — `test_every_observation_is_filed_under_the_journal_by_what_it_was_computed_for`.
- B61 A dev run with an alert fails — `test_a_dev_run_with_an_alert_fails`.
- B62 A single restart alerts however loose everything else, a restart tolerance included — `test_a_single_restart_alerts_however_loose_everything_else`.
- B63 Warm decode alerts only below its approved value less tolerance — `test_warm_decode_alerts_only_below_its_approved_value_less_tolerance`.
- B64 Card memory, steady and peak, each alerts only above its approved value plus tolerance — `test_card_memory_alerts_only_above_its_approved_value_plus_tolerance`.
- B65 Swap and major faults are recorded and never alerted — `test_swap_and_major_faults_are_recorded_and_never_alerted`.
- B66 Cold wake, vLLM RAM and Shmem are recorded until measured, and L2 wake is judged — `test_cold_wake_vllm_ram_and_shmem_are_recorded_until_measured_and_l2_wake_is_judged`.
- B67 A live switch slower than its dev run alerts, naming the switch — `test_a_live_switch_slower_than_its_dev_run_alerts_naming_the_switch`.
- B68 A live alert pulls its combination at once, asks for no stop, and its units stop routing — `test_a_live_alert_pulls_its_combination_at_once_and_its_units_stop_routing`.
- B69 A pull clears only when its validation is re-committed — `test_a_pull_clears_only_when_its_validation_is_recommitted`.
- B70 With every combination pulled, live refuses all work naming each — `test_with_every_combination_pulled_live_refuses_all_work_naming_each`.
- B71 A repeated alert warns once and is counted — `test_a_repeated_alert_warns_once_and_is_counted`.
- B72 Rejudging reports what a tighter tolerance finds and pulls nothing — `test_rejudging_reports_what_a_tighter_tolerance_finds_and_pulls_nothing`.
- B73 The operator reads a live alert on stderr and from `mcgyvr fleet alerts` — `test_the_operator_reads_a_live_alert_on_stderr_and_from_mcgyvr_fleet_alerts`.

`tests/test_rig_readers_parse_what_the_kernel_and_the_driver_print.py`
- B74 `/proc/meminfo` gives available, Shmem and swap in MiB — `test_meminfo_gives_available_shmem_and_swap_in_mib`.
- B75 `/proc/vmstat` gives swap-out and major faults — `test_vmstat_gives_swap_out_and_major_faults`.
- B76 Card use is attributed per container and the rest is foreign — `test_card_use_is_attributed_per_container_and_the_rest_is_foreign`.

`tests/test_the_lock_pins_each_combinations_headroom_card_peak_backend_and_prefill.py`
- B83 A combination is fitted with its own headroom — `test_a_combination_is_fitted_with_its_own_headroom`.
- B84 A llama.cpp unit is locked on its measured card peak and never without one — `test_a_llama_cpp_unit_is_locked_on_its_measured_card_peak_and_never_without_one`.
- B85 A llama.cpp unit whose card peak exceeds its room is not locked — `test_a_llama_cpp_unit_whose_card_peak_exceeds_its_room_is_not_locked`.
- B86 A vLLM unit whose attention backend is not pinned is not locked — `test_a_vllm_unit_whose_attention_backend_is_not_pinned_is_not_locked`.
- B87 The lock files the reported backend and refuses one the unit did not pin — `test_the_lock_files_the_reported_backend_and_refuses_one_the_unit_did_not_pin`.
- B88 Prefill is locked as run, and a run that recorded none is not locked — `test_prefill_is_locked_as_run_and_a_run_that_recorded_none_is_not_locked`.

`tests/test_prefill_is_judged_and_cuda_host_and_the_backend_are_recorded.py`
- B89 Prefill alerts only below its approved value less tolerance — `test_prefill_alerts_only_below_its_approved_value_less_tolerance`.
- B90 CUDA_Host and the attention backend are recorded and never alerted — `test_cuda_host_and_the_attention_backend_are_recorded_and_never_alerted`.

`tests/test_the_scratch_allowance_for_qwen3next_is_what_it_measured.py`
- B77 qwen3next's scratch allowance is its measured 829 MiB — `test_the_scratch_allowance_for_qwen3next_is_what_it_measured`.

P0, inside #430:

`tests/test_draining_a_source_whose_rung_declares_a_width_does_not_raise.py`
- B78 Draining srv1's width-declaring unit does not raise — `test_draining_a_source_with_a_width_declaring_rung_does_not_raise`.

`tests/test_a_card_can_be_woken_twice_in_one_day.py`
- B79 A second serve up on one day is not refused for the first one's record — `test_a_second_serve_up_on_one_day_is_not_refused_for_the_first_ones_record`.

`tests/test_serve_up_records_each_units_restart_count.py`
- B80 serve up files a restart count for every unit — `test_serve_up_files_a_restart_count_for_every_unit`.

`tests/test_a_serve_down_removes_every_container_of_ours.py`
- B81 serve down removes a container of ours its file does not name — `test_serve_down_removes_a_container_of_ours_its_file_does_not_name`.

`tests/test_a_live_run_tears_down_the_serve_units_of_the_dev_run_it_displaced.py`
- B82 A live run removes the serve units of the dev run it displaced — `test_a_live_run_removes_the_serve_units_of_the_dev_run_it_displaced`.
