# Handoff — sleep/wake round, 2026-09-09

Everything is on **`red/sleep-wake`** (PR #430). `records/plans/sleep-wake.md`
is the design; **§7.5 is now factually wrong** and rewriting it is the first
item below.

Read these three first, in this order:

1. `records/measurements/ram-headroom-2026-09-09/README.md` — what the two RAM
   gates are worth, measured on both rigs with the fleet's own models.
2. `records/measurements/vllm-sleep-2026-09-09/README.md` — sleep funds a wake;
   it works; here are the two conditions.
3. `records/plans/fleet-shape/formulas.md` — the runtime fleet-shape controller,
   reduced to formulas with cited parameters.

## Where the branch stands

`main` is untouched. PR #430 is open, mergeable, not a draft, and is still a RED
specification: **the alternatives GREEN has not been written**, and that remains
the branch's actual blocker.

**Test state: `uv run --no-sync pytest -q` gives exactly 22 failures**, verified
2026-09-09, all intentional RED. The suite takes over ten minutes.

| file | failures |
|---|---|
| `test_a_wake_is_asked_for_in_the_config_and_bounded_by_its_own_budget.py` | 8 |
| `test_a_sleeping_rung_is_woken_rather_than_declined.py` | 5 |
| `test_sleeping_a_card_takes_every_rung_it_serves.py` | 4 |
| `test_a_dev_round_may_operate_the_ladder_it_may_not_install.py` | 2 |
| **the four sleep/wake files** | **19** |
| `test_two_models_on_one_url_are_alternatives.py` | 3 |
| **total** | **22** |

They fail because `src/mcgyvr/wake.py` does not exist and alternatives are
unimplemented. **Anything outside these five files is new.** The 2026-09-08
handoff said "19 failures ... plus the three open ones", which reads as 19 total
and is not — 19 is the four sleep/wake files alone. Nothing regressed.

ruff, ruff format, mypy, `python -m mcgyvr.docgen --check` and
`mcgyvr emit --check` on both hosts were all re-run after the edits and are clean.

## What 2026-09-09 settled, with the evidence

### The two RAM gates are different numbers, and both are now measured

`fit` prices two gates with one constant (`RAM_HEADROOM_GB = 2.0`,
`serving/__init__.py`). They compare different things and **fail differently**:

| gate | compares | swept result | verdict |
|---|---|---|---|
| **mode** (map or `--load-mode none`) | the **blob** | flat from +2.0 to +0.5 GiB; below zero a bounded **+19%** wake, decode untouched | **2.0 → 0.5** |
| **refusal** (launch or refuse) | the **spilled experts** | flat to +0.55 GiB, then a **cliff**: 385 s wake, 2.3 M faults, **decode at 32%** | **keep 2.0** |

The refusal gate keeps 2.0 for reasons that are now measured rather than
inherited: the cliff sits in the unmeasured 1.5 GiB between +0.55 and −0.97; the
failure is **silent** (the unit serves every request off swap and nothing
errors); and the margin refuses nothing this fleet would have run.

**The one code change all of this asks for is splitting that constant in two.**
It has not been made — only the comment has been corrected.

### srv1 should go mapped

Three alternating pairs, cold cache, production `swappiness=60`: unmapped
**132.9 s**, mapped **139.6 s**. The 24 s gap an earlier single sample showed was
an artifact. The trade is 8.4 GiB of reclaimable RAM against **6.7 s** of one-off
wake on a rung that stays up. Dropping the mode gate to 0.5 makes `emit` choose
this by itself; srv1 is still serving unmapped as left.

### How much RAM a model needs — settled

Measured, ±0.05 GiB over three arms each:

* **mapped** consumes **0.80 GiB**; the blob sits in reclaimable page cache. It
  wants the whole blob as a *cache* — short by 1 GiB costs re-reads, ~20% wake.
* **unmapped** consumes **9.12–9.17 GiB** against `fit`'s predicted 9.2. It
  *allocates* the spilled experts — short by 1 GiB costs 68% of decode.

**KV never touches host RAM.** Context is paid for in RAM indirectly: the card is
saturated regardless of `-c`, so a wider window puts more KV on the card, evicts
expert blocks off it, raises `--n-cpu-moe`, and grows the spill. 2048→32768 per
slot costs **1.1 GiB of host RAM and zero VRAM**.

### Sleep funds a wake — it works

srv2's 3B and 7B both `is_sleeping: true`, a llama.cpp 80B serving on the card
they gave back, **in 100 s**. Two conditions, both configuration:

1. the vLLM units must launch `--enable-sleep-mode` (+ `VLLM_SERVER_DEV_MODE=1`);
   without it `/sleep` is 404, which is how the live ladder runs;
2. the 80B must be **one expert block lighter** than `emit` writes it. Sleepers
   leave 11,409 MiB; `emit` asks for 11,960 at `--n-cpu-moe 35` and fails at 28 s
   with `failed to create_context`, then crash-loops. `--n-cpu-moe 36` fits.

`emit` sizes placement against an idle card and **cannot express** a placement
against the card a sleeping co-resident leaves.

### vLLM sleep levels, verified twice

| | sleep | wake |
|---|---|---|
| **L2** | 0.25 / 0.30 s | 0.24 / 0.31 s |
| **L1** | **5.05 s first**, 0.74 s after | 0.41–0.82 s |

**Level 1 must be banned.** It never returns the host RAM — not on wake, not
after 60 s idle — and **a level-2 sleep does not release what level 1 took**.
Only a container restart recovers it. The cost is 10.23 GiB of RAM to free
6.5 GiB of card. It is bounded, not a leak (the second L1 sleep reuses the
buffer), but it is permanent for the process's lifetime.

### A refused wake costs production nothing

Waking a vLLM unit into a full card: **HTTP 500 in 0.29 s**, named CUDA OOM. Real
completions on the 80B succeeded before, during and after; the card never moved;
the sleeper stayed asleep and woke normally once the 80B came down. The only
loud, fast, safe failure found all day.

### The trap that has no fix yet

A **sleeping vLLM unit answers `/v1/models` with 200 and then hangs forever on a
real request** (no response in 60 s). `serve-up.py` polls `/v1/models`, so **the
door would call a sleeping rig healthy** and gate 7 would call the run green.
Anything treating a unit as serving must consult `/is_sleeping`.

## Owner rulings from this session — do not re-litigate

1. **Alternatives declare their own window.** Forced by evidence: `emit` refuses
   deepseek on srv1 at Qwen's 8192/slot — a *card* refusal (5,854 MiB of 6,127
   free with every expert already in RAM). It fits at 4096. srv1's two
   alternatives cannot share a window.
2. **Hold #430 until the alternatives GREEN lands.** Do not merge a RED-only
   spec onto `main`.
3. **A wake must read the target's live GPU and RAM state.** Evict first, then
   read, then launch — measured safe: release is a step, ~1 s after container
   exit, landing on the recorded idle figures.
4. **§17's symmetry is worth keeping.** Sleep-funds-a-wake is the case it was
   written for and it is now measured to work.
5. **The "refuse a host mixing alternatives and co-residents" recommendation is
   withdrawn.** Under the fluid ladder the owner wants, that mix is the normal
   case, not an edge to refuse.
6. **The fleet shape is fluid and runtime-changeable.** Fleet can start empty,
   either rig can serve anything, and the resident set adapts to queue and rung
   pressure. `records/plans/fleet-shape/` is the first pass at the controller.

## Open, ranked, with a recommendation each

### 1. Split `RAM_HEADROOM_GB` into two constants — the one change the evidence asks for

Mode gate 0.5, refusal gate 2.0. `serving/__init__.py:420-424`. Needs a RED test
then GREEN. ~20 minutes. Everything above is the evidence.

### 2. Fix the health probe — a sleeping unit must not read as serving

`serve-up.py` polls `/v1/models`. Consult `/is_sleeping` where the engine
offers it. This is a precondition for any runtime sleep/wake, because otherwise
the door cannot tell a slept rig from a live one.

### 3. Rephrase §7.5 of `records/plans/sleep-wake.md`

It says "sleep never funds a wake on this fleet". That is false. Proposed:

> **Sleep funds a wake on this fleet only under a configuration it does not
> currently run.** Measured 2026-09-09: srv2's 3B and 7B, launched
> `--enable-sleep-mode`, sleep at level 2 in 0.25–0.30 s and hand back all but
> 503 MiB of the card — enough for a llama.cpp 80B to serve on it in 100 s with
> both showing `is_sleeping: true`. Two things stand between that and the live
> ladder, and both are configuration rather than physics: the vLLM units launch
> without the flag, so `/sleep` is 404; and `emit` sizes the 80B against an idle
> card (`--n-cpu-moe 35`, 11,960 MiB) where the sleepers leave 11,409 — it fails
> to create a context and crash-loops. One expert block lighter fits and serves.
> `records/measurements/vllm-sleep-2026-09-09/`.

§17's "worth its numbers" bullet references the same claim and must move with it.

### 4. `wake_timeout_s` — derive per unit, not per fleet shape

**Owner asked for pushback and here it is.** Keying the budget on "fleet setup"
needs a measurement per (model × shape) pair, and with a fluid fleet the number
of shapes is unbounded. The evidence says wake is a property of the *unit*:

| unit | blob | wake | s/GiB |
|---|---|---|---|
| srv1 deepseek mapped | 8.29 | 85.7 s | 10.3 |
| srv1 Qwen mapped | 12.30 | 139.6 s | 11.4 |
| srv1 Qwen unmapped | 12.30 | 132.9 s | 10.8 |
| srv2 80B mapped | 35.67 | 102.9 s | **2.9** |

Roughly linear in blob at a per-host rate; srv2 is 3.8× srv1, which is the disk.
Engine does not appear. The shape contributes only two terms: **RAM clearance**
(squeezed, srv1's Qwen went 132.9 → 385.3 s) and **sequencing** (`depends_on`
makes a file's budget the sum of its units — the vLLM pair is 168 s because the
3B waits on the 7B, which then takes 1.0 s).

**Rec: `blob × host_rate × clearance_penalty`, summed over sequenced units.**
Three coefficients per host, measured once — not a matrix per shape. A single
constant cannot survive a fluid fleet anyway: today's wakes span **0.24 s**
(vLLM L2 wake) to **385 s** (squeezed llama.cpp), a factor of 1,600. The fit is
weak and honest about it: `r(srv1)` is n=2, `r(srv2)` is n=1, and the shortfall
penalty `k ≈ 2.52` over-predicts KAT by 27%, so it is an upper bound.

### 5. GREEN the alternatives spec — still the branch's blocker

`tests/test_two_models_on_one_url_are_alternatives.py`, three failing. Three
changes, named by the tests: `emit._planned` groups by host and needs one file
per alternative (`compose.<host>.<model>.yml`); `serving.hold_together` must sum
co-residents only; `emit.check_all` and `cli._report_drift` must cover every file
a host now has (`_report_drift` hardcodes `compose.{host}.yml`).

**One gap found today:** the test defines alternatives as *same host and same
port*. That is srv1 (both on :8080). **srv2 does not fit it** — the vLLM pair is
on :8001/:8002 and the 80B on :8003; they alternate because they contend for the
**card**, not the port. The discriminator should be card contention; port
collision is one symptom of it.

### 6. Two things `fit` does not model, both able to break the layout

* **The loading mode has a VRAM cost.** srv2's 80B crash-loops under
  `--load-mode none` on a CUDA allocation with 18 GiB of host RAM to spare;
  mapped it loads in 103 s. `fit` decides the mode from host RAM alone. With
  tighter RAM it would emit that crash-looping config today.
* **Nothing sums host RAM across co-resident units.** `hold_together` sums VRAM
  per card and nothing sums RAM, so two spilling units each pass against the same
  `MemAvailable`. Owner's ruling stands: RAM summed per host, VRAM per card; the
  sum runs *after* the modes are picked, with one host headroom applied once,
  against the recorded scan and not a live read.

## Live state, as left

* **srv1**: Qwen3.6-35B-A3B, 2 slots × 8192, `--load-mode none`, serving. 5 GiB
  available. Untouched from how the day began, though the evidence says it should
  be mapped.
* **srv2**: the 3B + 7B vLLM pair, `--max-model-len 4096`, serving. Sleep mode is
  **off** again (`/is_sleeping` is 404), as it was found.
* `vm.swappiness` restored to **60** on both. No balloons left. All three
  endpoints return 200.
* `mcgyvr emit --check --out ~/.mcgyvr/config` is clean on both hosts.
* **srv2's recorded scan was retaken** idle and installed
  (`~/.local/state/mcgyvr/scans/srv2.json`; the 2026-09-05 one is kept as
  `srv2.json.bak-2026-09-05`). It fixes `disk.path`, which pointed one directory
  above where the blobs live, and a second field nobody had noticed: the old scan
  claimed **12,287 MiB of free VRAM with no card reserve**, where the idle retake
  reads 11,911 free and 376 reserved.

## Rig gotchas this session paid for

* **`docker inspect`'s `StartedAt` is UTC.** `time.mktime` reads it as local and
  adds the offset — 10,800 s here, printing a three-hour wake. Use
  `calendar.timegm`. Raw JSON in the first two sweeps carries the offset; the
  tables in the README are corrected.
* **A RUN_ID cannot contain `+`.** Gate 5 requires `[A-Za-z0-9_.-]+` because the
  id prefixes container names. Two arms were lost to labels like `B-refusal-+20`.
* **Two models alternating on one port cannot share a teardown.** `serve down`
  names one container; the other is left up and gate 7 refuses — correctly.
  Tear down with the compose of whatever is *actually* up.
* **The door refuses to overwrite an envelope** (gate 5, write-once). Move
  `records/evidence/<date>-live-<host>/serve-{up,down}.json` aside deliberately
  before a re-run; `--suffix` distinguishes the RUN_ID, not the artifact.
* **`restart: unless-stopped` turns a crash into a crash-loop**, and the door
  then reports `NOT ANSWERING after 539.9s` rather than a failure to start. Read
  the container log before believing a timeout.
* **Editing `src/` opens a new round.** The comment correction moved the product
  hash, so the door opened `r11-09-09-2026` and wrote 250 lines into
  `tools/bench/rounds.json` by itself. Expected, not a mistake.
* **`--load-mode none` allocates `Shmem`, and `Shmem` swaps.** Both rigs run 8 GiB
  of swap. The squeezed arm swapped 2.2 M pages *out* during its wake — the
  experts were evicted. The flag does not buy unpageability;
  `okf/must-read/touching-rigs.md` has been corrected.

## What is not in this branch

The fleet-shape controller (`records/plans/fleet-shape/`) is **documentation
only** — parameters, formulas and a deliberately half-baked algorithm sketch with
a diagram. No code implements it. Twelve gaps are carried as G1–G12 in
`evidence_and_params.md`; the wake fit in particular rests on n=1 and n=2 points
and says so.
