# Fleet identity — every verdict and observation keyed to what it was computed for

**Status.** Plan approved by the owner, 2026-09-10. This commit is the failing
specification: `records/plans/fleet-identity.md` plus 65 RED tests — 50, then
15 for the owner's 2026-09-10 rulings on live, dev and alerts — and no line
under `src/`. Stacks on #430 (`red/sleep-wake`), because the seams it pins
(`Waker`, `Capacity.drain`, `launch_specs`, `Card`) exist only there.

**Why.** The flexibility campaign (`records/measurements/flexibility-2026-09-09/README.md`)
found seven defects and seven records made false, and most share one cause: a
figure or a launch that does not say what it was computed for. srv2 runs a
compose `emit --check` rejects; a wake memory nobody can write; decode figures
quoted without "cold". The fix is a name for each thing, and a rule that live
runs only named, approved things.

---

## 1. The five identities

```
 msp-  model_spec_id  = H{ metadata, engine + image, knob_bounds }
                          │ resolved for one rig (unit_for · vramfit · bounds)
                          ▼
 unt-  unit_id        = H{ model_spec_id, n_cpu_moe, width, ctx_per_slot, ubatch,
                           load_mode, cache_type, gpu_memory_utilization, port }

 rig-  rig_id         = H{ host, hw{cpu, cpu_max_mhz, ram MT/s, PL1/PL2, gpu, vram, cc,
                           MemTotal}, system{driver, docker, kernel, swap, swappiness} }

 rsh-  rig_shape_id   = H{ rig_id, {unit_id: lifecycle}, start_order, compose sha256,
                           card MiB, RAM MiB }                      (totals in whole MiB)

 fsh-  fleet_shape_id = H{ set of rig_shape_id }  ── validated + committed ──▶ approved
```

`metadata` = arch, n_layer, quant, size_bytes, params_total, params_active, MTP
layers, KV-law inputs. A missing field is refused, never hashed.

**ID-1.** An identity hashes what defines the thing: declared inputs and the
computed card/RAM totals in whole MiB. Never a BOUND constant directly, never an
observation. Same primitive as `Config.digest()` (`src/mcgyvr/config.py:1092`,
prefix at `:49`).
**ID-2.** A bound reaches an identity only through a total. A bound change that
moves a total renames the rig shape and its fleet shape, and their approval
lapses. One that moves no total renames nothing.
**ID-3.** Tolerances are not hashed. They live in the approval record. A
tolerance change keeps the id and re-judges the recorded observations.

**A rig is renamed by any hardware or system change** (owner's ruling). That
inverts `src/mcgyvr/scan.py:642` on purpose: RAM moved between the rigs twice
in six days, and a BIOS reset took PL1 from 95 W to 4095 W
(`tools/runs/hosts.json` `_rig_doc`).

## 2. Names

| name | means | not |
|---|---|---|
| `host` | the name a rig is reached by (`srv1`) | "tag" — a docker image tag here |
| `rig` / `rig_id` | the physical box: host, HW, system | "machine" |
| `os_machine_id` | the OS install (`/etc/machine-id`) | the two functions now both called `machine_id` (`src/mcgyvr/scan.py:894`, `src/mcgyvr/serving/gatelib.py:388`), which return different values |
| `model_spec_id` | a model as served by an engine, before a rig | `model_id`, already a catalog name (`src/mcgyvr/capability.py:218`) |
| `unit_id` | one process, knobs resolved | `UnitKey` (`src/mcgyvr/serving/__init__.py:399`), which addresses a process and names no knob |
| `rig_shape` / `fleet_shape` | what is planned on a rig / the fleet | "state"; `formulas.md` already calls `S(h)` a shape |
| `lifecycle` | `awake` \| `asleep-L2` | "state" |
| `knob_bounds` | declared knob ranges | "envelope" — the door's evidence directory |
| `expectation` / `observation` / `deviation` | predicted / measured / the difference | `emit.Drift`, which is compose drift |

Rules: a prefixed `_id` is content-addressed and a bare `_id` (`run_id`,
`lease_id`) is minted; the scope word comes first (`rig_shape`, `fleet_shape`);
"shape" is always planned and "observation" always measured.

## 3. BOUND or EXPECTED (cut-off approved)

```
spread ≤ 1% of that rig's VRAM or RAM total  AND  verified (n ≥ 2, cited, inside arch × rig)
    → BOUND     declare the worst; not observed; not hashed directly
else
    → EXPECTED  an expectation on the rig shape; dev fails loud, live warns
an observation past a BOUND → deviation: dev fails loud and demotes it;
                                live warns, records and flags it for demotion
```

"Small" is the spread, not the value: `gpu_reserve_mib` is 401 MiB but moves
±3. Scope matters because `SCRATCH_AND_CONTEXT_MIB = 768`
(`src/mcgyvr/serving/vramfit.py:66`) was verified on four archs and qwen3next
measured 817–829. The rule covers memory only; decode and time are EXPECTED.

| parameter | spread | evidence | class |
|---|---|---|---|
| `gpu_reserve_mib` | ±3 MiB across boots | `fleet-shape/evidence_and_params.md` §1 | BOUND, max + 3; out of `rig_id` |
| card-law residual | ±4 MiB | flexibility Q7, Q10 | BOUND +4 |
| `C` step, qwen35moe | +38 MiB | flexibility §4 (Q11), srv2 | BOUND +38 in scope |
| `C` step, deepseek2 | +74 MiB | measuring-gaps Q4, srv2 | BOUND +74 in scope |
| `C` step, other archs | — | — | EXPECTED |
| scratch per arch | ≤34 MiB | measuring-gaps Q3 | BOUND at max (qwen3next 829); unmeasured arch EXPECTED |
| vLLM unit host RAM | 0.03 GiB | flexibility Q9 (srv1), M2 (srv2); srv2's worst 2.9533, `fleet-gaps-2026-09-09/results-vllm.json` `v-7b-alone-3` | BOUND 2.60 / 2.96 GiB |
| vLLM cold-start overhead | 20 MiB | flexibility Q15 | BOUND |
| vLLM L2 residual | 228–234 MiB | flexibility Q15 | BOUND 234 |
| `RUNTIME_RESIDENT_GB` | 0.01 GiB | `src/mcgyvr/serving/__init__.py:119` | BOUND 1.53 |
| unmapped Shmem over geometry | 0.2–0.6 GiB (4%) | flexibility Q7 | EXPECTED |
| early-start vLLM card spread | 728 MiB (5.9%) | flexibility Q15-cycles table, 6,816–7,544 (`README.md:272`; its prose says 616) | EXPECTED |
| swap-out, swap-in, major faults | decode and idle: swap-out 0; a load: nonzero and benign | `ram-headroom-2026-09-09/sweep-results-arms-repeat.json`; `flexibility-2026-09-09/results-q1-srv1.json`; 565,534 at a real deviation, `results-q7-coresidency.json` | EXPECTED, judged per window: swap-out = 0 in decode and idle; a load window per unit × rig × swappiness |
| restarts | 0, except vLLM pairs started `service_started` on srv2: one unit restarts in every arm | `fleet-gaps-2026-09-09/results-vllm.json`; `flexibility-2026-09-09/results-q15-sleepmode.json` | EXPECTED = 0; such a pair fails validation and is never approved |
| warm decode, wake seconds | not memory | flexibility §3, Q8 | EXPECTED |

## 4. Live and dev

**Live changes nothing except a transition between approved fleet shapes,
sleep and wake included.** Fits is a verdict from a live reading of the rig
against what each `unit_id` needs, not a sum over the shape.

```
 A (approved) ──▶ B (approved)
 1 LOCK     rig lease (gate 2, src/mcgyvr/serving/gatelib.py:581) + Capacity.drain on units leaving or sleeping
 2 READ     card total, used per process (pid → container via /proc/<pid>/cgroup)
            MemAvailable, RssFile per unit, Shmem, SwapFree, pswpout; /is_sleeping
 3 VERDICT  card = total − reserve bound − foreign − Σ staying − Σ residuals of sleepers
            ram  = MemAvailable − Σ max(read, need) of running mapped units − floor
            swap-out Δ must be 0;   Σ need(units B starts or wakes) ≤ room
            fails → REFUSE, nothing touched, A keeps serving
 4 APPLY    drain → sleep/down; then start units one at a time in B's order, each after healthy
 5 OBSERVE  per unit vs need; swap, faults, restarts, warm decode
 6 RELEASE  lease
```

One at a time because vLLM sizes its KV cache from what is on the card while
it profiles (flexibility Q15). `service_started` leaves the design; the order
stays in `rig_shape_id`, because which unit starts first still decides the KV
split (3B: 12,352 tokens second, 42,608 early).

**Serving quality — decode, contention, paging — is observed scope: dev fails
loud, live warns.**

**On deviation.** Dev fails (raises / non-zero). Live warns, records under the
journal keyed `(rig_shape_id, unit_id)`, keeps serving, and flags the shape
for re-validation. Nothing is written under `/tmp` (today:
`src/mcgyvr/wake.py:341`).

**Live admission — where the rule is enforced.** `profile` defaults to `live`
(`src/mcgyvr/config.py:794-795`; ruling R4, `src/mcgyvr/serving/gate-scripts/01-round.py:20`), so a load-time refusal would refuse
every config that says nothing, `init` and `config` included. `fleet_shape` is
therefore an **optional** config key and nothing refuses at load.

**Live is production (owner's ruling, 2026-09-10).** A run is live when mcgyvr
is delegating real code tasks. Only a committed, approved, working fleet shape
runs live, and what is approved is a config together with its fleet shape: the
record pins the config's `cfg-` digest beside the `fsh-` (§5). The user picks
the live default from that closed set. The orchestrator never names a config, a
fleet shape or a backend, and does not know one exists. Anything the user did
not pick — a hand-written file, a `$MCGYVR_CONFIG` — is dev.

What refuses is acting, never loading: `mcgyvr run` dispatch
(`src/mcgyvr/drive.py:641`), `mcgyvr serve`, sleep and wake, and the Waker
(`src/mcgyvr/wake.py:441`). Under live, the loaded config's digest and its
`fleet_shape` must be an approved pair, each rig's live `rig_id` the approved
one, and each compose must hash to the approved sha; any mismatch refuses,
naming what differs. The Waker wakes only toward an approved fleet shape in
which that unit is awake.

*Not pinned here — the door's gate 1.* `tests/test_the_door_serves_a_ladder_and_leaves_it_up.py`
(`:107`–`:197`) drives live `serve up|down` through the real gates with no
fleet shape. Restating them under an approved fleet shape needs the `rig_id` of
the door's fake rig, which P4 defines, so gate-1 enforcement is left open rather
than specified against a guess.

**Dev runs everything (owner's ruling, 2026-09-10)** — `serve up` and `down`
included, with any launch spec. Gate 1's composition guard
(`refuse_unless_the_live_ladders_own`,
`src/mcgyvr/serving/gate-scripts/01-round.py:112`) goes. What it protected —
production serving a ladder nobody declared — is held by live admission's
compose and `rig_id` checks above. Gate 2's arbitration (live outranks dev on a
held rig) is untouched. This settles sleep-wake N11, and lets approval validate
a rig shape by a dev run.

## 5. Approval

Validate each **rig shape** by a dev run (rigs share no memory), then approve a
fleet shape by committing `records/fleet/<fsh>.json`: the `cfg-` digest of the
config it is approved with, its rig shapes, each with `rig_id`, compose sha and
a passing validation envelope, and the tolerances. Approval without a passing
validation of every rig shape is refused. The committed records are the closed
set the user picks the live default from (§4); a config edited after approval
is not in it.

## 6. Surface the tests pin

Placeholders, per `tests/red_port/conftest.py`: rename freely, keep what is
asserted.

| module | pinned |
|---|---|
| `mcgyvr.fleet.ids` | `digest(prefix, fields)` |
| `mcgyvr.fleet.model_spec` / `.unit` / `.rig` | `model_spec_id(...)`, `unit_id(...)`, `rig_id(host, hw, system)` |
| `mcgyvr.fleet.rig_shape` | `rig_shape_id(rig_id, units, start_order, compose_sha256, card_mib, ram_mib)` |
| `mcgyvr.fleet.fleet_shape` | `fleet_shape_id`, `approve`, `admit_live`, `ApprovalRefusedError`, `LiveRefusedError` |
| `mcgyvr.fleet.bounds` | `BOUNDS`, `bound`, `classify`, `judge` |
| `mcgyvr.fleet.transition` | `fits(reading, starting)`, `apply(a, b, rig)` over a rig port |
| `mcgyvr.fleet.observe` | `parse_meminfo`, `parse_vmstat`, `parse_status`, `card_by_container`, `record`, `act`, `DeviationError` |
| `mcgyvr.fleet.alerts` | `PARAMETERS`, `check`, `rejudge`, `flagged`; `mcgyvr fleet alerts` |
| `mcgyvr.serving.hfscan` | `scan(snapshot_dir)` |
| existing | `ggufscan.scan` gains `quant`, `params_experts`, `params_active`; `vramfit.allowance_mib` for qwen3next; `scan`/`gatelib` `os_machine_id`; config key `fleet_shape`; `Capacity.drain` |

## 7. Phases

| | work |
|---|---|
| P0 | fix `mcgyvr serve sleep` crashing on srv1 (`Capacity.drain` sort, `src/mcgyvr/capacity.py:1288`); `ids.py`; rename to `os_machine_id` |
| P1 | `bounds.py` + rule test; `vramfit` and `serving` import from it; qwen3next 829; per-arch `C` steps |
| P2 | `model_spec_id`: ggufscan quant and params; `hfscan.py` |
| P3 | `unit_id` in `unit_for` (`src/mcgyvr/serving/__init__.py:606`) |
| P4 | `rig_id`: snapshot reads kernel, swap, swappiness; `hosts.json` declares `rig_id`; gate 2 compares |
| P5 | `rig_shape_id`; `mcgyvr fleet plan` (read-only) |
| P6 | readers, observations, deviations; replaces the `/tmp` wake memory |
| P7 | `fleet_shape_id`, `mcgyvr fleet validate`, approval records |
| P8 | live admission and transitions: config `fleet_shape`, the approved `cfg-` + `fsh-` pairs the user picks the live default from, `src/mcgyvr/drive.py:641`, `src/mcgyvr/cli.py` serve/wake, Waker; gate 1 drops its dev composition guard, and the `profile` field text (`src/mcgyvr/config.py:782`) and gate 1's refusal summary (`src/mcgyvr/serving/run.py:175`) stop saying a dev run does not touch the live ladder |

Every phase ends on `make check` and `make docs-check`. `src/` moving opens a
round.

## 8. What it eliminates

Items are named by their text in `records/measurements/flexibility-2026-09-09/README.md`
("Defects the campaign found", "What the campaign leaves open").

| campaign item | result |
|---|---|
| "`mcgyvr serve sleep` crashes on srv1" | eliminated as the P0 prerequisite |
| "The live config cannot `serve wake` at all"; "The Waker has no memory on this machine"; "srv2's live compose is not what the tree emits" | eliminated |
| "`Fit.ram_gb = 0.0` for declared-figure vLLM units" | eliminated by the per-rig bound |
| "G1's headroom on the geometry path" (`C` drift) | eliminated for qwen35moe and deepseek2; caught elsewhere |
| measuring-gaps Q3, 768 under qwen3next | eliminated as a class: bounds apply inside their scope |
| "Re-emit srv2 onto `service_healthy`" | the start race is eliminated; which unit starts first remains a choice between two rig shapes |
| "`emit` sums a declared-figure unit as mapped whatever the rig will do" | eliminated if the resolved mode is right; caught either way |
| "A per-architecture wake law" | mostly: wake history per unit × rig |
| "`REFUSAL_RAM_HEADROOM_GB = 2.0`"; "The geometry under-predicts an unmapped unit's `Shmem`" | caught, not eliminated |
| "The Waker cannot wake one card twice in a day"; "The CLI's own error sends an operator to the wrong place"; the `vramfit` docstring | not touched |
| "Records this campaign makes false" | stops new ones |

## 9. Already true on this branch — not re-specified

Live outranks dev on the rig lease (gate 2); gate 2 compares the rig with
`hosts.json`; `emit` already sequences co-residents on one card behind a
healthcheck (`src/mcgyvr/emit.py:395`, `:471`); level-1 vLLM sleep is refused
(`src/mcgyvr/serving/servelib.py:189`); config identity is `cfg-` + sha256.

## 10. Existing tests changed, and why

These acted under a default-live config stating `serving.compose_dir` with no
fleet shape, which the plan makes a refusal. Each now declares `profile: dev`
(a dev run may act freely) and still passes on this branch; `config_file()` and
`_config()` gained a `profile` argument that writes nothing when unset.

* `tests/test_a_sleeping_rung_is_woken_rather_than_declined.py` —
  `test_with_the_switch_off_a_refused_port_ends_the_run_exactly_as_it_does_today`,
  `test_a_refused_vllm_card_this_config_holds_a_spec_for_is_woken_not_written_off`,
  `test_the_dispatch_that_follows_a_wake_spends_no_attempt`,
  `test_a_llama_cpp_card_is_woken_exactly_as_a_vllm_one_is`,
  `test_a_card_with_no_launch_spec_is_down_rather_than_asleep`.
* `tests/test_sleeping_a_card_takes_every_rung_it_serves.py` —
  `test_sleeping_the_card_takes_both_rungs_down_in_one_door_run`,
  `test_an_operators_own_sleep_is_not_gated_by_the_automatic_switch`,
  `test_a_dispatch_in_flight_is_never_cut_by_a_sleep`.
* `tests/test_a_launch_spec_this_config_does_not_plan_is_never_woken.py` —
  `test_a_wake_that_cannot_say_which_spec_starts_nothing_and_says_so`,
  `test_a_host_of_alternatives_is_not_no_launch_spec`.

Tests that only load, emit or derive cards were left live.

The 2026-09-10 ruling that dev runs everything overturns three tests that were
green on this branch, because they pinned gate 1's dev refusal:

* `tests/test_a_dev_round_may_operate_the_ladder_it_may_not_install.py` — replaced
  by `tests/test_a_dev_round_may_serve_any_launch_spec.py`. Its first test is
  kept; its second, `test_a_dev_round_may_not_run_a_launch_spec_of_its_own`, is
  inverted.
* `tests/red_port/test_dod_profile.py` —
  `test_a_dev_profile_does_not_touch_the_live_ladder` and
  `test_a_dev_serve_refused_at_gate_1_leaves_even_the_rounds_file_alone` are
  removed. What a dev serve may do is pinned in the new file.

## 11. Open

* Tolerance values for the EXPECTED rows (Shmem, card on unbounded archs,
  paging, warm decode, wake seconds). Restarts are exactly 0. A survey of past
  tests, benches, sweeps, runs and campaigns (2026-09-10) proposes values, with
  its observations in `records/evidence/2026-09-10-tolerance-survey/`; the
  values are the owner's.
* Alerts (B54–B65) judge paging with no window, and §3 now judges it per window:
  a load swaps, decode must not. Which window an observation belongs to is
  unpinned.
* Alerts: which tolerances a dev validation run uses before approval; when a
  flag clears and warn-once resets; whether `rejudge` finding a deviation flags
  the shape; whether the Waker's `DEVIATION_RATIO` (`src/mcgyvr/wake.py:98`)
  goes, leaving one tolerance source for wake seconds.
* Gate-1 enforcement of live admission for `serve up|down` (§4). Dev validation
  is ruled: dev runs everything.
* A dev run may leave a ladder no approved fleet shape names on a free rig, and
  the next live run is then refused (B38). Does live restore its approved fleet
  shape from that state, or stay refused until an operator does?
* A config that manages no fleet (no `serving.compose_dir`) has no rig shapes. Is
  it approved with an empty fleet shape, or can it not run live?
* The base, `938a5158`, already fails 5 tests unrelated to this PR:
  `test_one_door.py::test_nothing_under_records_is_executable`,
  `test_the_mcgyvr_skill_is_rendered_from_the_schema.py::test_docs_check_refuses_a_skill_that_drifted`,
  two in `test_the_seam_holds.py` (`mcgyvr.wake`/`weights` in neither half; config
  imports servelib), and
  `test_the_setup_document_is_rendered_and_drift_checked.py::test_setup_markdown_on_disk_is_byte_identical_to_render_setup`.

---

## Behaviors

`tests/test_a_fleet_id_is_a_prefixed_content_digest.py`
- B1 Every identity kind carries its own prefix — `test_every_identity_kind_carries_its_own_prefix`.
- B2 Key order does not change an identity — `test_key_order_does_not_change_an_identity`.
- B3 Any changed or added field is a new identity — `test_any_changed_or_added_field_is_a_new_identity`.
- B4 A prefix outside the five kinds is refused — `test_a_prefix_outside_the_five_kinds_is_refused`.

`tests/test_a_model_spec_and_its_units_are_named_by_what_they_resolve.py`
- B5 One set of weights under two engines is two model specs — `test_the_same_weights_under_two_engines_are_two_model_specs`.
- B6 An image or knob-bound change is a new model spec — `test_an_image_or_a_knob_bound_change_is_a_new_model_spec`.
- B7 A model spec missing a metadata field is refused, not hashed — `test_a_model_spec_missing_a_metadata_field_is_refused_not_hashed`.
- B8 Every resolved knob, port included, is part of the unit — `test_every_resolved_knob_including_the_port_is_part_of_the_unit`.

`tests/test_a_rig_is_its_hardware_and_system_and_not_its_reserve.py`
- B9 A driver bump mints a new rig — `test_a_driver_bump_mints_a_new_rig`.
- B10 A BIOS reset mints a new rig — `test_a_bios_reset_mints_a_new_rig`.
- B11 The host is part of the rig — `test_the_host_is_part_of_the_rig`.
- B12 The card reserve is never part of the rig — `test_the_card_reserve_is_a_bound_and_never_part_of_the_rig`.
- B13 The scan names the OS install `os_machine_id` — `test_the_scan_names_the_os_install_os_machine_id`.
- B14 The door names the OS install `os_machine_id` — `test_the_door_names_the_os_install_os_machine_id`.

`tests/test_a_rig_shape_and_fleet_shape_name_what_was_planned.py`
- B15 Lifecycle, start order and compose each rename the rig shape — `test_lifecycle_start_order_and_compose_each_name_a_different_rig_shape`.
- B16 Totals are hashed in whole MiB — `test_totals_are_hashed_in_whole_mib`.
- B17 A bound that moves a total renames the rig and fleet shape — `test_a_bound_that_moves_a_total_moves_the_rig_shape_and_its_fleet_shape`.
- B18 A bound that moves no total renames nothing — `test_a_bound_that_moves_no_total_keeps_both_names`.
- B19 A fleet shape is its rig shapes in any order — `test_a_fleet_shape_is_its_rig_shapes_in_any_order`.
- B20 A tolerance change keeps the fleet shape id and changes its record — `test_a_tolerance_change_keeps_the_fleet_shape_and_changes_its_record`.

`tests/test_a_bound_is_small_verified_and_scoped.py`
- B21 Every declared bound obeys the 1% rule, n ≥ 2 and a citation — `test_every_declared_bound_obeys_the_one_percent_rule`.
- B22 The campaign's verified parameters are declared at their worst — `test_the_campaign_s_verified_parameters_are_declared_at_their_worst`.
- B23 qwen3next's scratch allowance is its measured 829 MiB — `test_the_scratch_allowance_for_qwen3next_is_what_it_measured`.
- B24 A bound outside its verified scope is EXPECTED — `test_a_bound_outside_its_verified_scope_is_expected`.
- B25 A parameter spreading over 1% is EXPECTED — `test_a_parameter_whose_spread_is_over_one_percent_is_expected`.
- B26 An observation past a bound is a deviation that demotes it — `test_an_observation_past_a_bound_is_a_deviation_that_demotes_it`.

`tests/test_a_fit_is_read_from_the_rig_not_summed_from_the_shape.py`
- B27 Card room is total less reserve, foreign, staying and residuals — `test_card_room_is_total_less_reserve_foreign_staying_and_residuals`.
- B28 A running mapped unit claims its need when the cache reads less — `test_a_running_mapped_unit_claims_its_need_when_the_cache_reads_less`.
- B29 Any swap-out while reading refuses — `test_any_swap_out_while_reading_refuses`.

`tests/test_a_transition_locks_reads_and_starts_one_unit_at_a_time.py`
- B30 A failed pre-check refuses and keeps fleet A — `test_a_failed_pre_check_refuses_and_keeps_fleet_a`.
- B31 The lease is taken before the rig is read — `test_the_lease_is_taken_before_the_rig_is_read`.
- B32 A unit is drained before it sleeps — `test_a_unit_is_drained_before_it_sleeps`.
- B33 Units start one at a time in order, each after healthy — `test_units_start_one_at_a_time_in_order_each_after_healthy`.

`tests/test_draining_a_source_whose_rung_declares_a_width_does_not_raise.py`
- B34 Draining a source with a width-declaring rung does not raise — `test_draining_a_source_with_a_width_declaring_rung_does_not_raise`.

`tests/test_a_live_run_is_an_approved_fleet_shape_or_nothing.py`
- B35 A live config without a fleet shape loads, `fleet_shape` is an optional key, and acting under it refuses naming `fleet_shape` — `test_a_live_config_without_a_fleet_shape_loads_and_cannot_act`.
- B36 An unapproved fleet shape is refused — `test_an_unapproved_fleet_shape_is_refused`.
- B37 A rig that is not its approved rig is refused — `test_a_rig_that_is_not_the_rig_it_was_approved_on_is_refused`.
- B38 A compose that is not the approved one is refused — `test_a_compose_that_is_not_the_approved_one_is_refused`.
- B39 The approved fleet shape on its own rigs is admitted — `test_the_approved_fleet_shape_on_its_own_rigs_is_admitted`.
- B40 Approval needs a passing validation of every rig shape — `test_approval_is_refused_without_a_passing_validation_of_every_rig_shape`.
- B41 The Waker does not wake toward an unapproved shape — `test_the_waker_does_not_wake_toward_a_shape_nobody_approved`.
- B51 A config that is not the one approved with its fleet shape is refused, naming it — `test_a_config_that_is_not_the_one_approved_with_its_fleet_shape_is_refused`.

`tests/test_a_dev_round_may_serve_any_launch_spec.py`
- B52 A dev round may bring up a launch spec of its own — `test_a_dev_round_may_bring_up_a_launch_spec_of_its_own`.
- B53 A dev round may serve when no live ladder is configured — `test_a_dev_round_may_serve_when_no_live_ladder_is_configured`.

`tests/test_a_deviation_fails_a_dev_run_and_warns_a_live_one.py`
- B42 A dev run with a deviation fails — `test_a_dev_run_with_a_deviation_fails`.
- B43 A live run with a deviation warns, records and keeps serving — `test_a_live_run_with_a_deviation_warns_records_and_keeps_serving`.
- B44 Observations append under the journal keyed by rig shape and unit, nothing under `/tmp` — `test_observations_append_under_the_journal_and_nothing_goes_under_tmp`.

`tests/test_rig_readers_parse_what_the_kernel_and_the_driver_print.py`
- B45 `/proc/meminfo` gives available, Shmem and swap in MiB — `test_meminfo_gives_available_shmem_and_swap_in_mib`.
- B46 `/proc/vmstat` gives swap-out and major faults — `test_vmstat_gives_swap_out_and_major_faults`.
- B47 A process status gives its mapped file, Shmem and swap — `test_a_process_status_gives_its_mapped_file_shmem_and_swap`.
- B48 Card use is attributed per container and the rest is foreign — `test_card_use_is_attributed_per_container_and_the_rest_is_foreign`.

`tests/test_a_model_scan_reports_its_quant_and_expert_params.py`
- B49 ggufscan reports quant, expert and active params — `test_ggufscan_reports_quant_expert_and_active_params`.
- B50 hfscan reads a vLLM model's config — `test_hfscan_reads_a_vllm_model_s_config`.

`tests/test_a_parameter_past_its_tolerance_alerts_the_operator_once.py` (alerts, owner's request 2026-09-10; the buckets and the alert record are in its docstring)
- B54 Every observed parameter sits in one bucket — `test_every_observed_parameter_sits_in_one_bucket`.
- B55 Memory and paging alert upward, decode downward, a wake either way — `test_each_parameter_alerts_only_on_the_side_that_harms`.
- B56 A single restart alerts live and fails dev however loose every tolerance is — `test_a_single_restart_alerts_live_and_fails_dev_however_loose_the_rest`.
- B57 A parameter's own tolerance overrides its bucket's — `test_a_parameters_own_tolerance_overrides_its_buckets`.
- B58 A tolerance is absolute in the parameter's unit or a percent of what was expected — `test_a_tolerance_is_absolute_in_its_unit_or_a_percent_of_what_was_expected`.
- B59 Approval refuses a parameter no tolerance covers, naming it — `test_approval_refuses_a_parameter_no_tolerance_covers`.
- B60 Approval refuses a tolerance keyed by nothing it can loosen, restarts included — `test_approval_refuses_a_tolerance_on_nothing_it_can_loosen`.
- B61 A live alert is filed under the journal keyed by rig shape and unit, naming parameter, bucket, direction, tolerance, profile, fleet shape, run and lease — `test_a_live_alert_names_its_parameter_bucket_and_what_it_was_computed_for`.
- B62 A repeated deviation warns once across runs and is counted — `test_a_repeated_deviation_warns_once_and_is_counted`.
- B63 A live deviation flags its rig shape for re-validation; a shape within tolerance is not flagged — `test_a_live_deviation_flags_its_rig_shape_for_re_validation`.
- B64 A tolerance change re-judges recorded observations under the same ids — `test_a_tolerance_change_re_judges_what_was_recorded_and_renames_nothing`.
- B65 The operator sees a live alert as one `warning:` line and in `mcgyvr fleet alerts`; the run's stdout carries none — `test_the_operator_reads_a_live_alert_on_stderr_and_from_mcgyvr_fleet_alerts`.

B20 now approves with a complete tolerance set, because B59 refuses an incomplete one.
