# Handoff — sleep/wake round, end of 2026-09-09

Everything is on **`red/sleep-wake`** (PR #430). `records/plans/sleep-wake.md` is
the design. **Read this file before that one** — the design was corrected four
times on 2026-09-09, the fourth being §3, §10 and §11.2, which had come to
describe implementations that do not exist (O5 and O4 below, both since
corrected).

Read these first, in this order:

1. `records/measurements/fleet-gaps-2026-09-09/README.md` — **the day's biggest
   result.** Seven carried gaps measured; four beliefs overturned.
2. `records/plans/wake-timeout.md` — why a wake budget belongs to the unit and
   not to the fleet's shape. New today.
3. `records/measurements/ram-headroom-2026-09-09/README.md` — the two RAM gates.
4. Artifact, plain-language summary of the campaign, no jargon:
   <https://claude.ai/code/artifact/3dfb4766-8ae4-4d52-acd4-be2aa76ee8c5>

## Where the branch stands

`main` untouched. **Six commits today**, the sixth carrying everything below the
first five:

| | |
|---|---|
| `d8c5cf0a` | GREEN: two models on one URL are alternatives, each its own launch spec |
| `6a2e80d4` | GREEN: the two RAM gates hold back different margins, host RAM summed |
| `b4e9ea8e` | GREEN: a sleeping unit does not read as serving |
| `49a98c57` | Say what is true: the records this branch made false |
| `0f95fb9b` | A wake budget is a property of the unit, not of the fleet's shape |
| `cabc5a26` | the sleep/wake GREEN, the card-contention discriminator, three review fixes, the campaign |

**Four more in a later session the same day**, closing O1, O3, O5 and half of
O4 as they were written below:

| | |
|---|---|
| `ae35449e` | The three tests that asserted a refusal the owner retired |
| `531a9f47` | ruff format what the last commit left unformatted |
| `6848e321` | A test may name a rig and may not reach one |
| `877a421a` | Say what is true: cards() lists a directory, gate 1 checks one |

**Test state: `uv run --no-sync pytest -q` is green** — 2,832 outcomes, no
failures, exit 0. It was 3 failures when the section above was written, and
those three are `ae35449e`. The suite takes twelve to fifteen minutes. **The
nineteen sleep/wake RED tests all pass and none was edited.**

`ruff`, `ruff format`, `mypy src` (94 files) and `docgen --check` are clean.
They were not quite when this was first written: `cabc5a26` left
`tests/test_one_door.py` failing both ruff checks, which is `531a9f47`.

## What today settled

### The alternatives shape, and then the discriminator behind it

`serving.launch_specs` cuts a ladder's units into what a door can be pointed at.
A host whose units come up together stays `compose.<host>.yml` — **nothing on
disk moved for either live rig**, verified byte-identical. A host whose units
cannot all be resident becomes one file per feasible set.

**Owner ruling: port-per-model, and card contention is the discriminator.** The
port was never the fact — it caught srv1 by accident and missed srv2 entirely.
`serving.alternate(one, other)` now asks whether two units' card figures sum onto
the free VRAM the scan read; `Fit` carries `card_free_gb` so the cut needs no
scan. Port collision survives as a second, non-discriminating clause: it never
fires under port-per-model, but it is still physically true.

`launch_specs` returns a **covering by anchor-maximal feasible sets**, not a
partition. Bounded by N rather than exponential, at the cost that some maximal
set may have no spec (A,B,C at 5 GiB on 12 gives `{A,B}` and `{A,C}`, never
`{B,C}`). Every unit is reachable from some spec; *which* feasible set to run is
the fleet-shape controller's question. Determinism was checked over 1,230
orderings with zero disagreements.

### The measurement campaign overturned four things

**Read the campaign README rather than trusting the summary below.**

* **M1 — the 80B does not crash unmapped.** At `--n-cpu-moe 36` it loads in
  117.3 s and serves at 13.46 tok/s. The loading mode's card cost is 16 MiB on
  srv1 and 52–58 MiB on srv2. G1 was never a mode with a hidden appetite; it is
  **a placement with no margin**, and `vramfit` over-predicts by 63 MiB. What the
  layout needs is a card headroom on the geometry path, not a mode term.
* **M3 — `k` is not one coefficient and not two.** The blob axis **saturates**
  (+19.2% at −0.98, +20.9% at −2.03, +20.5% at −3.03); the experts axis is a
  **step** (+2.0% at −0.34, +190% at −0.97). KAT's unexplained `k = 0.66` is
  exactly what a plateau predicts. **G4's cliff narrows from 1.5 GiB to 0.63.**
  Arm budget falls from 18 to 10.
* **M5 — the 168 s pair figure was an artifact.** The production vLLM pair
  crash-restarts the 3B 1–2× per cold start (`No available memory for the cache
  blocks`), hidden by `restart: unless-stopped`, because `depends_on:
  service_started` releases the 3B before the 7B has taken its card. **This
  invalidates the 86 s subtraction built on it.** `--enable-sleep-mode` costs
  decode and TTFT nothing and starts 36 s *faster*.
* **M4 — `r(srv1)`'s intercept is positive, ~22.5 s**, reversing the sign that
  forced the proportional form. `r(srv2)` has **negative R²** on three points and
  was named and refused rather than adopted.

M2 measured the first two-MoE co-residency ever run here: `Shmem` 7.47 + 10.76 =
**18.23 GiB exactly**, card 5,711 of 5,712 MiB. The law is right — and a no-op on
this fleet, because both live vLLM units carry `Fit.ram_gb = 0.0` while actually
costing ~2.9 GiB each.

### Live state, as left

srv1 serving Qwen3.6-35B at `--n-cpu-moe 30`, **mapped** — the one deliberate
change from how the day began, owner-approved. srv2 serving the 3B + 7B pair.
`vm.swappiness` 60 on both, no balloons, all endpoints 200,
`mcgyvr emit --check --out ~/.mcgyvr/config` clean on both hosts.
`/is_sleeping` is still **404** on srv2 — sleep mode is off, as found.

## Owner rulings from today — do not re-litigate

1. **Port-per-model; card contention is the discriminator, not the port.**
2. **A derived wake budget may never shorten or abort a wake.** It warns and it
   informs scheduling. `budgets.wake_timeout_s` (default **480 s**) stays the
   sole authority that gives up.
3. **Record predicted vs actual on every wake, warn in both directions.** Faster
   than predicted usually means it did not load what you think.
4. **Say it about case `n`, not case `n=5`. A behaviour belongs to a named
   config, never to a rig's reputation.** Now in `okf/must-read/always.md`.
5. srv1 re-emit + restart: approved and **done**.
6. The earlier handoff's rulings still stand, notably: hold #430 until the GREEN
   lands, and the fleet shape is fluid and runtime-changeable.

## Open — ranked, one recommendation each

*(O1, O3 and O5 are closed and kept below with what doing them taught. **Start
at O2**, which needs a ruling before it can be built.)*

### O1. ~~Three failing tests, and it is one decision~~ — **closed, `ae35449e`**

The three tests all asserted that two units which do not sum onto a card are a
refusal. Under ruling 1 they are alternatives, and the refusal was unreachable
dead code, so they now assert what replaced it: the cut, and the sentence
`hold_together` returns for it — both spec files named, plus the stale
`compose.<host>.yml` an earlier emit left behind.

Three things worth carrying forward from doing it:

* **The mixed-host case could not be tested with srv1's fixtures at all.** A
  llama.cpp unit grows to fill whatever card it is given, so no two of them ever
  co-reside and the "mix" was three alternatives. It needed declared figures —
  8 + 8 + 3 GiB on a 12 GiB card — which emit as `{big_a, small}` and
  `{big_b, small}`. That is the covering, exercised for the first time.
* **The card sum's one live tooth had no test.** A ladder sized against one
  reading of a card and checked against a tighter one is caught there and
  nowhere else, because `alternate` cuts on `Fit.card_free_gb` and
  `hold_together` reads the scan. It has one now.
* The earlier handoff's ruling 5 killed the mixed-host refusal, and the test
  asking for it was rewritten rather than deleted: the covering is a claim worth
  holding.

### O2. The wrong-weights hole is still open on the path that matters

`mcgyvr run` builds its pool with **no probe** (`cli._climb`), so a dispatch
aimed at a rung whose model is not resident still reaches llama.cpp and is still
answered from the wrong weights. `Availability.not_serving` exists and is
correct, but only `mcgyvr pool --probe` consults it.

A probe was written, tested, and **backed out the same day** — see O3.

**Rec, and it is better than probing:** `runner.generate` already receives
`document["model"]`, which llama.cpp fills with the loaded path, and throws it
away. Capture it into `Completion.model` and compare with
`availability._is_model`. Zero latency, no network, no schema key, and a
wrong-weights answer becomes impossible to *record*. Needs a ruling because it
turns a dispatch into a failed attempt. Fallback: an off-by-default `serving.`
key gating a `Residency` probe, which costs a schema key and re-identifies every
existing config. Both are written into the comment at `_climb`'s `source_map`
call. **Cannot fire on either live rig today** — both are single-spec hosts.

### O3. ~~The test suite can reach the production rigs~~ — **closed, `6848e321`**

`conftest._no_test_resolves_a_machine` refuses `socket.getaddrinfo` for every
name that is not this machine, which is under `urllib`, `http.client` and
anything else that opens a socket. It denies the whole world rather than the two
rigs: a guard listing srv1 and srv2 is a guard the third rig is not in.

Two ways through, both narrow and both stated in the fixture. Addresses that are
dead by standard (RFC 5737, RFC 3849) stay reachable, because `test_runner`
dials `192.0.2.1:9` to drive a real transport failure — the suite already used
them by convention and this makes the convention the only door. And a test's own
`monkeypatch` still wins, which is the escape `_offline_probes` leaves.

**What it does not cover:** a subprocess resolves in its own interpreter, where
the fixture is not. `test_one_door.py` is the guard on that side, and it guards
what may spawn rather than what a spawned thing may reach. Closing that would
mean a resolver stub the gate scripts inherit, and nobody has needed one.

The first draft of the guard was wrong twice and the suite caught both — it
broke the two 192.0.2.1 tests, and it wrote a credential into its own refusal,
because urllib hands the resolver `user:sk-...@127.0.0.1` with the userinfo
still attached. Both are pinned in
`tests/test_a_test_may_name_a_rig_and_may_not_reach_one.py`.

### O4. Gate 1's provenance check has two holes — **docstring corrected
(`877a421a`), the holes are still open and still yours**

`refuse_unless_the_live_ladders_own` replaced the profile check. Traversal and
symlinks are genuinely closed. Two holes remain, and both are now written into
the gate's own docstring and into `sleep-wake.md` §11.2, where the shipped check
was being described by a proposal it does not implement:

1. **It is a directory check, not a provenance check.** Any file named
   `compose.*.yml` inside the live `compose_dir` is started, whatever is in it. A
   dev round reaches this with `mcgyvr emit --out ~/.mcgyvr/config`. Asking the
   planner instead needs units, and units need a scan — the cost this check was
   chosen to avoid.
2. **A dev config can declare itself live.** `configlib.user_config_path()`
   expands `~` against `$HOME`, and the door builds gate env as
   `dict(os.environ)` with `HOME` untouched. Repointing `HOME` makes a dev tree
   the "live" config.

Neither is a regression — the old `profile: live` check was defeated as easily.
What was fixed is the overclaim on a gate that guards a live rig. **Closing hole
2 means the door stops trusting `$HOME`, which is a real behavioural change and
yours.**

### O5. ~~`sleep-wake.md` §3 and §10 describe a `cards()` that does not
exist~~ — **closed, `877a421a`**

§3 now says what was built: the naming convention moved *into* `serving`
(`spec_name`, `safe_host`, `safe_model`, which `emit` imports, so it is spelled
once), and `cards()` calls `spec_files` — a directory listing — because
`planned_paths` needs units, units need a scan, and not needing a scan is the
whole of D1. Why a listing beats a name is there too, and so is the IPv6 bug
that spelling the convention twice produced.

§10 no longer says a ladder whose units cannot co-reside "was never emittable".
It is emitted as N alternatives, and `hold_together`'s refusal survives for the
tighter-scan case only.

### O6. `emit` should pass `--alias` for llama.cpp

So both engines report the declared model name rather than a weights path.
`availability._is_model` currently compensates by stripping suffixes and shard
tails. **Not done because it moves every compose file on the fleet** — a re-emit
and a restart of both rigs. Yours.

### O7. Two internal contradictions in the campaign README

Both inside `records/measurements/fleet-gaps-2026-09-09/README.md`:

* the same four srv1 arms are quoted **140.9 s** in M3 and **140.7 s** in M4
  (true mean 140.75);
* M7's table says the 7B keeps **10.32 GiB**, the exchange-rate sentence says
  **10.23** (3.14 + 10.32 = 13.46 is the self-consistent one).

Correcting a measurement record is deliberate, not cleanup — hence yours.

### O8. Gaps the campaign left, and one it created

* **G1 is redefined, not closed.** The layout needs a **card headroom on the
  geometry path**; `vramfit` over-predicts by 63 MiB and `--n-cpu-moe 35` mapped
  really clears srv1's card by ~16 MiB. Nothing implements that headroom.
* **`Fit.ram_gb = 0.0` for declared-figure units** (both live vLLM units) while
  they cost ~2.9 GiB each. The host-RAM sum is a no-op exactly where it matters.
* `r(srv1, vLLM)` unmeasured — reachable, three arms, one carrying real lock risk.
* M3's −3.03 decode arm read 5.09 tok/s on a **single cold sample**; steady state
  unmeasured.
* The vLLM pair needs `condition: service_healthy` to stop the cold-start crashes
  M5 found. A `src/` change nobody made.
* `serve-up.py` polls per service, so the door's clock reports "how much longer
  after the first" for a pair — **2.1 s for a unit that took 100**.

### O9. Level-1 vLLM sleep must be banned in code

Measured twice; reproduces identically. 3.14 + 10.32 = 13.46 GiB kept
permanently, a level-2 sleep does not release it, and L1 frees the same card as
L2 while being 4–12× slower. **Refuse `POST /sleep?level=1` at the runtime, not
in `emit`.** A decision that was never written down as code.

## Rig gotchas — still true, still paid for

* **A RUN_ID cannot contain `+`.** Gate 5 requires `[A-Za-z0-9_.-]+`.
* **The door refuses to overwrite an envelope** (gate 5, write-once). Move
  `serve-{up,down}.json` aside deliberately; `--suffix` distinguishes the RUN_ID,
  not the artifact.
* **Two models alternating on one port cannot share a teardown.** Tear down with
  the compose of whatever is *actually* up, or gate 7 refuses.
* **`restart: unless-stopped` turns a crash into a crash-loop**, and the door
  reports `NOT ANSWERING after …s` rather than a failure to start. **Read the
  container log before believing a timeout** — this is what hid M5's crashes for
  weeks.
* **`docker inspect`'s `StartedAt` is UTC.** Use `calendar.timegm`, not
  `time.mktime`.
* **`--load-mode none` allocates `Shmem`, and `Shmem` swaps.** Both rigs run
  8 GiB of swap.
* **Editing `src/` opens a new round** — it moves the product hash and the door
  writes into `tools/bench/rounds.json` by itself. Expected.

## Two process lessons from today

**A line-number citation is a liability.** `prose-comb` reported
`records/plans/**` CLEAN — 147 references, 0 broken — while **every one of them
resolved by line count and pointed at the wrong code**. 36 were fixed only by
reading each target line, and several had been wrong since before this branch.
One described a refusal that no longer exists, so renumbering would have left the
prose false. **Cite by name where you can.** A handoff outlives its line numbers;
this file deliberately carries almost none.

**A guard that passes because the text changed has not passed.** A test bound
`SEAM = "ssh"` to slip past the door scanner's spawn check. Teaching the scanner
to tell `monkeypatch.setattr(…, "ssh", …)` from a real spawn then exposed **two
dead entries in its `ALLOWED` list**, each a hole waiting for a real spawn in
that file. Both removed. Net stricter.
