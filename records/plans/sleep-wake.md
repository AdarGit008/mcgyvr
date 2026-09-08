# Sleep and wake for the local ladder

Design only. Nothing here is implemented, and no line of `src/` changes on the
branch that carries this file.

**The owner's rulings this design starts from and does not revisit:**

1. **On sleep, mcgyvr evicts the ENTIRE GPU.** Not one model, not a share of
   VRAM — the whole card comes down.
2. **Sleep and wake are BOTH queue decisions, made by the queue algorithm**,
   both behind one opt-in switch that is off by default. This overturns the
   first draft's invariant that mcgyvr may add serving capacity and never
   remove it; §7 is the rewritten section and the substance of this revision.
3. **`dev` gets sleep and wake too.** The first draft read gate 1's refusal of
   `serve up|down` under `dev` and concluded a sleeping card is a decline for a
   dev run. Overturned; §11 designs the exception.
4. **There is no engine scope. Every card may sleep and wake, whatever
   serves it.** The first draft scoped the feature to vLLM and §6 reported
   that the measurement usually offered for that did not support it. The
   2026-09-08 wake measurement then closed the question outright — the engines
   wake at the same speed, and the scope excluded the only rung this fleet can
   add — and the owner dropped it (N10, ruled). §6 is the evidence and what
   remains of D4.

---

## 1. The tension, stated before it is resolved

Whole-card eviction is a claim about shared hardware. Shared hardware is
exactly what the architecture refuses to name above the execution seam.

A rung is `(source, model)`, and a source is a `base_url` — one server process,
not a machine (`src/mcgyvr/config.py:162`, `src/mcgyvr/config.py:327`,
`src/mcgyvr/pool.py:118`). `mcgyvr.escalate._widths`
(`src/mcgyvr/escalate.py:850`) keys widths by rung and says why in its own
docstring: "nothing above the execution seam learns where work runs".
`mcgyvr.route.Machine` (`src/mcgyvr/route.py:265`) is the load reader for that
rule and is a misnomer — it is per rung, it renders as `<machine>`, and the
only thing anyone above can do with one is ask how busy it is.
`mcgyvr.capacity._slot_stem` (`src/mcgyvr/capacity.py:264`) keys the host-wide
flock files by `base_url` and joins the rung only where the rung declared its
own width, because "the physical thing being protected is one server process,
not the host it happens to sit on".

So nothing in the ladder models a host, and nothing models a card. The live
config proves the gap rather than describes it: srv2 is one RTX 3060 (12 GiB,
`tools/runs/hosts.json`) behind two sources — `http://srv2:8001` at
`--gpu-memory-utilization 0.26` and `http://srv2:8002` at `0.72`, eight slots
each. The ladder bounds each of them and nothing bounds the pair. srv1 is a
GTX 1660 SUPER (6 GiB) serving one llama.cpp unit at two slots.

The failure this document exists to prevent is the obvious repair: a
`devices:` block in the config, a `device:` key on a source, a `Card` object
threaded up through `Plan` and `Ascent`. That repair puts hardware in the
vocabulary of the layer whose entire discipline is not knowing about hardware,
and it does it to serve a feature nothing above the seam ever asks for.

---

## 2. The finding that reshapes the design

**A card is already modelled. It is modelled below the seam, in
`mcgyvr.serving`, and it is called a host with a GPU index.**

* `serving.host_of(base_url)` (`src/mcgyvr/serving/__init__.py:837`) derives
  the machine from the URL. It is already how a scan is keyed.
* `serving.Unit` carries `host` and `gpu: int`
  (`src/mcgyvr/serving/__init__.py:311`), the index chosen by
  `_roomiest_gpu(scan)` (`:866`) off a `scan.Gpu` (`src/mcgyvr/scan.py:201`).
* `serving.hold_together` (`src/mcgyvr/serving/__init__.py:671`) already sums
  the units on one host against the free VRAM the scan read, and already
  refuses a ladder whose units fit one at a time and not together. It cites
  the measurement: 7.12 + 3.49 GiB on 11.63 free on srv2, 2026-09-05.
* `emit._sequence_on_one_card` (`src/mcgyvr/emit.py:223`) already groups
  services by `unit.gpu` and chains `depends_on` largest-first, because two
  units racing for one card is a measured failure — the 7B got 0.89 GiB of KV
  cache started together and 2.77 GiB started second.
* `emit.emit_all` (`src/mcgyvr/emit.py:153`) already writes **one compose file
  per host**, "because a host is what an operator brings up". The emitted file
  names the card outright: `~/.mcgyvr/config/compose.srv2.yml` carries
  `device_ids: ['0']` on both services.
* `serving/run.py` already has one step per direction for a whole file:
  `SERVE_STEPS = {"up": ..., "down": ...}` (`src/mcgyvr/serving/run.py:117`),
  run against the whole compose file under one pinned project
  (`servelib.PROJECT`, `src/mcgyvr/serving/servelib.py:26`;
  `servelib.compose`, `:86`).
* The rig already has a lock on itself: the lease at `~/.mcgyvr/lease` on the
  rig (`src/mcgyvr/serving/gatelib.py:360`), one run per rig, live outranks
  dev (R1, 2026-09-06).

Whole-card eviction is therefore not a behaviour to build. It is the behaviour
`serve down` already has, because the compose file is per host and the down
step tears down every service in it
(`src/mcgyvr/serving/gate-scripts/serve-down.py`).

**So the design is: sleep is `serve down`, wake is `serve up`, and the card is
the compose file.** Everything below is about what is genuinely missing —
knowing which rungs a card holds, telling "asleep" from "broken", electing one
waker, deciding when the queue asks for a card and when it gives one back, and
deciding who may ask.

---

## 3. D1 — The device is derived, never declared

**Decision. No `devices:` block, no `device:` field on a source, no card in
`Tier` or `Source`. The card of a rung is `(host_of(source.base_url),
unit.gpu)`, computed in `mcgyvr.serving` from the config and a scan, exactly
where it is computed today.**

Does a device named above the execution seam violate #20? **Yes, and that is
why this design does not name one.** The rule is not a style preference; it is
what makes a rung re-pointable by a config edit. `Source.context_window`'s own
schema doc turns the same argument the other way round: the window belongs on
the source "because the window is a fact about the process, and a rung that
carried one could not be re-pointed at another machine"
(`src/mcgyvr/config.py:162`ff). A card on a rung is worse — it would be a fact
about a *machine* on an object whose whole purpose is to name no machine —
and a card on a source is merely redundant, because the source's `base_url`
already names the host and `host_of` already reads it.

Two statements of one fact is the defect `Capacity.of` refuses by name: "two
answers to one question, and the machine gave one of them, so the config is
the one that is wrong" (`src/mcgyvr/capacity.py`, the width disagreement). A
hand-written `device: cuda:0` beside a `base_url: http://srv2:8002` is that
situation created deliberately, and it goes stale the first time a source is
re-pointed.

`route.Machine`'s docstring leaves this open on purpose: "A fleet holds rigs,
a rig holds containers, and a rung may come to bind at any of those levels…
What is decided is that a machine stays an opaque handle that answers 'how
busy' and names nothing" (`src/mcgyvr/route.py:288-294`). A card derived below
the seam disturbs none of that. `Ascent`, `Plan`, `Machine` and `_widths` are
untouched by this design.

**The one schema addition is not a device.** The wake path must find the
compose file emit wrote, and today `mcgyvr emit --out` defaults to the current
directory (`src/mcgyvr/cli.py:2451`ff) — the live files happen to sit in
`~/.mcgyvr/config/`. So: `serving.compose_dir`, one key, a directory path. It
states where this checkout keeps launch specs. It says nothing about where any
rung runs, it cannot go stale against a re-pointed source, and a config that
omits it has no sleeping cards — only down ones (D2).

**What is derived, and where.** A new function in `mcgyvr.serving`:

```
cards(config) -> Mapping[str, Card]     # keyed by rung name
Card: host, compose_file, rungs, sources
```

It groups the ladder's tiers by `host_of(source.base_url)` — the same grouping
`units_for` (`src/mcgyvr/serving/__init__.py:544`) already performs — and
names the file `emit_all`'s convention would have written. It needs **no
scan**, because it needs no fit: the card's identity is the host and the file,
and the GPU index only matters to `emit`, which already has it. That is what
keeps the wake path usable on a machine that never scanned the rig.

---

## 4. D2 — The lifecycle state is not stored; it is read from two facts

*(Approved by the owner as designed. Unchanged.)*

Neither neighbour fits, and the reason each fails is instructive.

`mcgyvr.cooldown` is failure-driven and its outcome is a **decline**: three
consecutive dispatch failures take a source out for sixty seconds
(`src/mcgyvr/cooldown.py:84`, `:90`), and `drive` turns the resulting
`SlotUnavailableError` into `Verdict.DECLINED` — "Nothing was asked and
nothing answered" (`src/mcgyvr/drive.py:617`). A sleeping card must queue and
wake, not step aside, so cooldown's verdict is the wrong one. Note also that a
cooldown's own docstring already names waking as a thing it must not mistake
for a fault: it ends the removal after sixty seconds because "a backend
restarting, a model being swapped in, or a machine waking turns a transient
fault into a permanent one for the rest of the run".

`mcgyvr.availability` is liveness-driven, binary, and cached for the life of a
run with no expiry on purpose. A sleeping rig reads as **down** through it —
correctly, on its own terms: nothing is listening. Its verdict is right and
its consequence is wrong.

**Decision. `asleep` is not a fourth state to store. It is `down` plus one
more fact mcgyvr already holds: a launch spec it wrote for that card.**

```
up      the unit answers                      -> dispatch, unchanged
asleep  it does not answer, and this config's
        compose_dir holds a file for its host -> queue and wake (D6)
down    it does not answer, and there is no
        such file                             -> availability's DOWN, unchanged
```

This is the fewest-new-concepts answer available. There is no state machine,
no field to keep in sync with a rig, and no third liveness module. The
distinction that actually matters to a caller — *can mcgyvr bring this back?*
— is answered by *does mcgyvr have the file?*, which is exactly the question,
and it is answerable without touching the network.

It also degrades honestly. An api source has no compose file and is never
asleep. A rig somebody else runs has no compose file and is never asleep. A
config with no `serving.compose_dir` has no sleeping cards at all.

**Where the reading lives.** In the same family and at the same seam as its
two neighbours: a view that satisfies the one-method `pool.SourceProbe`
question, wrapping an `Availability` or a `Cooldown` the way `Cooldown` wraps
an `Availability` — "an availability view that also *learns*"
(`src/mcgyvr/cooldown.py`). This one is an availability view that also
**acts**. One new module, `src/mcgyvr/wake.py`; nothing above the seam learns
anything.

**One state this reading cannot name, and must not guess at.** A card is a
compose file with more than one service on it (srv2's has two), so there is a
fourth reading — *some* units answer and some do not. It is not `asleep`: a
whole-card wake would hand the door a `serve up` on a rig that is not idle, and
gate 2 refuses exactly that (`src/mcgyvr/serving/gate-scripts/02-rig.py:269`;
the `busy` set is cleared only for `serve down`, `:255`). So a half-up card is
reported and left alone. Repairing it — `down` then `up` — is a machine repair
mcgyvr found rather than caused, which run contract §4 forbids a cell from
doing, and whether the sleep/wake algorithm is exempt from that is N9 in §16.

---

## 5. D3 — Waking goes through the door, and nothing else

**Decision. A wake is `python -m mcgyvr.serving.run serve up --host H
--compose FILE --suffix S`, spawned as a subprocess. A sleep is the same with
`down`. Nothing in `mcgyvr.wake` runs `docker` or `ssh`.**

Going around the door is not merely discouraged, it does not work. Under the
door, `ssh` and `docker` resolve to shims that "admit exactly the host the
door was opened for and refuse any process the door did not start"
(`src/mcgyvr/serving/run.py:14-18`), and `gatelib.under_door` reads the parent
chain from `/proc`. Outside it, a `docker compose up` from `mcgyvr.wake`
against a rig would be the second way in — and the seal is stated as being
"against every code path in this repository", with `tests/test_one_door.py`
banning an absolute-path `ssh` and an `env -i` in repo code
(`src/mcgyvr/serving/run.py:22-32`). A wake path that reached a rig directly
would have to defeat that test to exist.

The door also already does the work. `serve-up.py` brings the file up through
the rig's daemon and then polls each unit's `/v1/models` until it answers or
the budget is spent — `HEALTH_POLLS = 120` at `HEALTH_INTERVAL_S = 3.0`
(`src/mcgyvr/serving/servelib.py:30-31`), six minutes. That is the measured
wake this design must survive, already bounded, already recorded; §6 revisits
what the recorded figures do and do not establish.

**What the envelope costs, and why it is a benefit and not a tax.** The door
has a heavy contract: it mints its own `RUN_*` vocabulary and refuses to start
under an inherited one; it runs `SERVE_SEQUENCE` — gates 1, 2, 3, 5 and the
step (`src/mcgyvr/serving/run.py:303`) — with no way to skip an entry; and it
writes write-once evidence under `records/evidence/live-<host>/`
(`RUN_CAMPAIGN = f"live-{opts.host}"`, `src/mcgyvr/serving/run.py:770`). Four
consequences, all accepted:

1. **Every wake leaves `serve-up.json`** with the compose text, per-unit
   `healthy` and `seconds`, and `card_after` from `nvidia-smi`
   (`servelib.card`, `:166`). That is the operator signal D10 needs, in a place
   that already has readers.
2. **Same-day wakes must not collide.** Gate 5 claims the `RUN_ID` with
   `O_CREAT | O_EXCL` and refuses a second run that mints the same one
   (`src/mcgyvr/serving/gatelib.py:322`). So a wake passes `--suffix`
   (`src/mcgyvr/serving/run.py:713`) derived from the waker's pid and clock:
   every wake is its own envelope, and no wake collides with another or with
   an operator's hand-run `serve up`.
3. **A wake needs a run root.** The door files evidence under
   `records/evidence/` of `$MCGYVR_RUN_ROOT` or the checkout
   (`src/mcgyvr/serving/run.py:52-59`). From an installed wheel with no root
   set, the door refuses before gate 1. That refusal is correct and must be
   surfaced verbatim rather than swallowed: an install that cannot wake a card
   should say so, not silently decline the rung.
4. **`serve up` requires an idle rig, and `serve down` does not.** Gate 2
   refuses a rig whose `gpu_procs` or `containers` read anything but `none`
   (`02-rig.py:269`) and clears that check for `down` alone, "the one run that
   opens on a busy rig by design" (`:255`). This is not a limitation the design
   works around — it is the door independently enforcing the owner's whole-card
   ruling from the rig's side. A card is woken whole or not at all, because a
   half-up card cannot be woken (D2's fourth reading).

The `dev` refusal that gate 1 also carries has been overturned by the owner and
is designed in §11.

---

## 6. D4 — There is no engine scope, and the premise once offered for one is measured and absent

**The owner's first ruling was: sleep/wake supports vLLM first.** The reason
offered was speed — "I believe its faster over there". This design took the
ruling and declined to repeat the reason, because the timings taken did not
show it. **On 2026-09-08 the owner dropped the scope entirely** — no rig is
banned for the engine that serves it — and this section is now the record of
why a scope was never load-bearing.

**What was measured, 2026-09-08.** Units recreated with
`docker compose up -d --force-recreate` through `DOCKER_HOST=ssh://<rig>`,
`/v1/models` polled every 10 s:

* **srv1, llama.cpp**, Qwen3.6-35B-A3B MoE with CPU expert offload
  (`--n-cpu-moe 29`), 12.3 GB of weights off local disk: first 200 between
  **50 s and 80 s**, across two separate restarts.
* **srv2, vLLM**, both units — the 3B-AWQ and the 7B-AWQ — recreated in one
  `compose up`: neither answered before **110 s**, both by **120 s**.

Read straight, llama.cpp woke faster in the only measurement anyone took. But
the srv2 figure is **not a per-unit number and must not be quoted as one**:
`~/.mcgyvr/config/compose.srv2.yml` makes the 3B `depends_on` the 7B, so 120 s
covers two sequential engine boots plus CUDA graph capture on one card. It is
the wake time of the *card*, which is the number this design actually needs,
and it is not comparable with srv1's single unit.

**That number has since been taken, and so has the fleet's worst case**
(`records/measurements/wake-2026-09-08/`, same day, later). A single vLLM unit
alone on an empty card — srv2's 7B-AWQ with `depends_on` stripped — answered in
**82 s**. That is consistent with `servelib`'s "87 s to health on srv2"
(`src/mcgyvr/serving/servelib.py:29-31`) having been a per-unit figure, and it
lands *inside* llama.cpp's own band for the same rig class rather than above or
below it. **Neither engine is measurably faster to wake.** The premise this
section declined to repeat is not merely unsupported; it is now measured and
absent.

| what | rig | engine | size | host RAM | wake |
| --- | --- | --- | --- | --- | --- |
| Qwen3.6-35B-A3B, `-c 8192` | srv1 | llama.cpp | 12.3 GB | 15 GB | 50–80 s |
| Qwen3.6-35B-A3B, `-c 16384` (the live config) | srv1 | llama.cpp | 12.3 GB | 15 GB | **128 s** |
| KAT-Coder 35.5B/A3B — srv1's ceiling | srv1 | llama.cpp | 16.9 GB | 15 GB | **203 s** |
| 7B-AWQ alone on the card | srv2 | vLLM | 5.2 GB | 45 GB | **82 s** |
| Qwen3-Next 80B/A3B — srv2's ceiling | srv2 | llama.cpp | 35.7 GB | 45 GB | **97 s** |

**Wake time tracks RAM headroom, not model size, and that is the finding.** The
80B is 2.1× KAT's bytes and wakes in half the time: 35.7 GB into srv2's 45 GB
fits, 16.9 GB into srv1's 15 GB thrashes. llama.cpp mmaps and pages lazily, so
a wake pays for memory pressure. Every number a reader might try to extrapolate
from — engine, parameter count, file size — is the wrong axis. **The fleet's
worst wake is srv1's, and it is 203 s.** That is what N7 is priced against, and
it is the number §13 must keep distinguishable from a hung rig.

**What actually differs between the engines, from the record rather than from
folklore.** vLLM's startup does engine-core init, a weight load out of the HF
cache, and CUDA graph capture, and it is the engine whose startup failures this
repository already has a whole vocabulary for: `tools/bench/serving/knobs.py`
classifies launch outcomes into `accepted` / `refused` /
`refused_reason_lost` / `harness_defect` / `untried` (`:17-38`), where
`refused_reason_lost` exists precisely because vLLM's wrapper line — `Engine
core initialization failed. See root cause above` (`knobs.py:125`) — scrolls
the cause out of a truncated log, and `tests/test_knobs.py:52` pins that
wrapper-versus-cause distinction. The 2026-08-24 config sweep
(`records/evidence/2026-08-24-config-sweep`) refused 24 of 106 stage-1 cells.
llama.cpp with `--n-cpu-moe` streams most of its weights to host RAM instead.
Which of those two is faster to first-token-served is an empirical question,
not a design one, and this document asserts neither answer.

**There is no scope predicate, and `Source.engine` stays what it was** — a
statement about how a unit is launched (`src/mcgyvr/config.py:215-226`), not a
gate on whether its card may sleep. A mixed card is a card: it is woken whole,
because there is no half-way (D3.4), and the compose file `emit` wrote already
holds both engines' units in the order they have to start.

**The worked examples below are still srv2's, and now for the honest reason.**
srv2 is the **two**-unit card — `local_qwen2.5-coder-3b` and
`local_qwen2.5-coder-7b` co-resident on one RTX 3060 — so whole-card eviction
there takes down two rungs at once, while srv1 is the trivial single-unit case.
**The hard case is multiplicity, not engine.**

What the wake path must reproduce for that card, it reproduces by not
reproducing anything: it hands the door the compose file `emit` already wrote,
`depends_on` and all, so the 7B starts first and the 3B follows
(`emit._sequence_on_one_card`, `src/mcgyvr/emit.py:223`), and `hold_together`
(`serving/__init__.py:671`) already ran at emit time against the scan. A wake
re-runs no fit and re-derives no order. That is the whole benefit of D1.

**Did scoping to vLLM let anything be dropped? No, and that is why dropping
the scope costs nothing.** The wake path is a compose file, `serve up|down`,
and a `/v1/models` poll; all three are engine-agnostic and none of them ever
carried a llama.cpp branch to delete. `hold_together` and the `depends_on`
sequencing are needed for the multi-unit card either way. A scope would have
narrowed which cards the feature is offered for — one predicate on
`source.engine` — and simplified no code path. Generality that costs nothing is
kept, and the predicate that bought nothing is not written.

---

## 7. D5 — Sleep and wake are both queue decisions

**The owner's ruling replaces the first draft's D4 entirely.** That draft made
wake automatic, refused sleep any automatic trigger, and stated an invariant:
*mcgyvr may add serving capacity on its own and may never remove it.* **The
invariant does not stand.** Both directions are decisions of the queue
algorithm, and the owner's statement of that algorithm, verbatim, is the seed
this section grows into something implementable:

> **"work piles up on the top rung -> wake another >= rung."**

Nine words, and every one of them has to be given a number or a rule. Where
this document had to choose one the owner did not state, it is marked **(N*n*)**
and gathered in §16, one line each.

### 7.1 Where the switch lives, and why it is not a flag

**Decision. `serving.enable_sleep_wake`, a config key, default `false`. There
is no `mcgyvr run --enable-sleep-wake` flag.** The owner's name for the setting
is kept; what changed is which file it is written in.

The precedent the owner named is real and it points this way. `mcgyvr run
--config`'s own help text says: *"Which rung runs is this file's — the tier
order, each tier's `attempts` and the `budgets` ceilings — never a flag"*
(`src/mcgyvr/cli.py:2691`). Sleep/wake is not merely adjacent to that rule, it
is a stronger case for it, for three reasons that are each checkable:

1. **The config's digest is what a run is reproducible from.** `Config.digest`
   is taken over the loaded and validated tree (`src/mcgyvr/config.py:952`,
   owner's ruling R2), every journal row carries it, the result file carries it
   (`src/mcgyvr/result.py:76-79`), and the file itself is kept at
   `<journal>/configs/<digest>.yaml` so that `MCGYVR_CONFIG=<that>` re-selects
   the exact setup. A flag would let two runs share a digest where one of them
   started and stopped containers on a shared rig and the other did not. The
   rig side effect would sit outside the only record that explains the run.
2. **A `store_true` flag can never lose to a config key.** `--sandbox` is the
   repo's worked example of the honest shape, and its comment states the rule
   outright: it takes *no* default, "because `sandbox.mode` in the config is
   declared as where this comes from, and a flag that is never absent is a flag
   the config can never lose to" (`src/mcgyvr/cli.py:2704`). A boolean
   `--enable-sleep-wake` is present on every invocation as `False`. To coexist
   with a key it would have to be a tri-state (`--enable-sleep-wake` /
   `--no-enable-sleep-wake` / absent), which is a worse spelling of the key.
3. **Gate 1 already reads the profile from the file and not from an argument**
   (`gate-scripts/01-round.py:47-82`), for exactly this reason: a fact about
   the run that every later gate reads has to come from the thing that is
   digested.

**Which block.** `serving.`, beside `compose_dir` (D1) — the two are a pair,
and the feature is inert without the directory. It is *not* `ladder.`, because
`ladder.fanout` decides where work goes among rungs **that exist**, and this
decides whether rungs come into existence; those are two authorities and only
one of them touches a rig.

**But they interact, and the interaction has to be written down.** A woken
rung is only useful if something routes to it, and `Fanout.NONE` — the schema
default — starts every climb on the cheapest rung at or above the contract's
floor and reaches a higher one only by escalating on failure
(`src/mcgyvr/config.py:391-416`, `src/mcgyvr/route.py:236`). Under `none`, a
card woken because a *lower* rung was congested receives nothing until a
contract fails its way up to it. Under `idle` or `full` — "the cheapest rung
with a slot to spare" — the woken card reads as empty through
`Machine.load` and takes work immediately. The live config runs `fanout: idle`
(`~/.mcgyvr/config/mcgyvr.yaml`), so this is satisfied today. Whether
`enable_sleep_wake: true` with `fanout: none` should be a schema refusal or
just a documented pairing is **N8**; this design says documented, because the
refusal-driven wake (D6) is useful under every fanout mode and a refusal would
take that away too.

### 7.2 What "piling up" is, measured from what

mcgyvr already holds four kinds of pressure number and they are not
interchangeable:

| reading | what it counts | shared across processes? |
| --- | --- | --- |
| `Capacity.in_use` / `in_flight` (`capacity.py:913`, `:917`) | slots this capacity granted | **no** |
| `Capacity.load` (`:936`) = `in_use + reserved` | granted plus chosen-but-not-yet-admitted | **no** |
| `Usage.waited_seconds` (`:384`), `Concurrency` (`:421`) | this process's cost and peak | **no** |
| the `.slot` files under `/tmp/mcgyvr-capacity-<uid>/` | every mcgyvr process on this host | **yes** |

The module says this about itself, and it is not a defect to be repaired: "the
bound is the flock and is shared; this is bookkeeping for spreading the choices
one batch is making, and it only has to be right about those"
(`capacity.py:196-200`); `Usage` "are this *process's* observations… No
cross-process ledger is kept" (`:391-397`).

**Confronting it rather than working around it.** A ratio computed from
`load()` or `Usage` sees only its own share of the pressure. Twenty contracts
run as twenty `mcgyvr run` processes would each read a load of one on a
saturated rig and none of them would ever trip a threshold. So the ratio is
**not** computed from the per-process bookkeeping. It is computed from the one
reading that is shared:

* **`busy(b)`** — how many of bound *b*'s `limit(b)` slot files are locked
  right now, host-wide. Read by the same `LOCK_EX | LOCK_NB` sweep
  `_acquire_slot` already performs (`capacity.py:1248-1280`), counting instead
  of returning, releasing each descriptor immediately.
* **`waiting(b)`** — how many threads of *this* process are blocked on *b*
  right now. A new counter beside `_waited`, incremented before
  `_acquire_slot` and decremented after: it is the instantaneous form of the
  number `waited_seconds` is already the integral of.
* **`demand(b) = busy(b) + waiting(b)`**, and
  **`pressure(b) = demand(b) / limit(b)`.**

A *bound* here is whatever `Capacity._bound` decides — a source, or a rung that
declared its own width (`capacity.py:774`) — never a guess, for the reason
`Machine.load` gives: a reading taken against the source alone counts none of a
width-declaring rung's holds, "and the fan-out it was asked for is price order
wearing its name" (`route.py:340`ff).

**Two honesties about this reading.**

* **`demand` is a lower bound on the truth, deliberately.** `busy` counts every
  process's *granted* work; `waiting` counts only this process's *queued* work.
  Another mcgyvr process with nineteen threads blocked on a full rig
  contributes its granted slots and none of its queue. So the algorithm reads
  low, trips late, and never trips on pressure that is not there. For an action
  that costs 80–130 s on this ladder and takes hardware, late-and-certain is
  the right
  direction, and the alternative — a shared waiter count — would be a second
  rendezvous file written on every dispatch, which is a cost the whole module
  is organised to avoid.
* **The census is not free of side effects, and the cost is bounded.** There is
  no POSIX way to test a `flock` without taking it, so the sweep takes and
  immediately releases an exclusive lock on each *free* slot. A real acquirer
  sweeping in the same microsecond may read that slot as busy, sleep
  `_POLL_SECONDS` (0.02, `capacity.py:250`) and sweep again. That is the whole
  penalty, and it is paid once per wake evaluation rather than once per routing
  decision — which is exactly the cost `Machine.load` refused when it declined
  cross-process sensing: "a syscall per rung per choice… so if it is ever
  wanted it belongs in `Capacity`, beside the files it would have to read"
  (`route.py:326-333`). This design puts it there, and pays it at the rate that
  docstring's objection allows.

### 7.3 What trips a wake

**`pressure(b) >= WAKE_RATIO` continuously for `WAKE_SUSTAIN_S`.**

* **`WAKE_RATIO = 2.0` (N1).** Every slot of the bound busy, and as much work
  again queued behind them. A ratio of 1.0 is merely "full", which is what a
  correctly-sized rig looks like under load and is not a reason to start a
  container.
* **`WAKE_SUSTAIN_S = 45` (N2).** A wake that takes 80–130 s to land (§6) must not
  be started for a queue that would have cleared first, or it arrives after it
  was needed and the card is then idle. The window is anchored to the measured
  per-stream rates rather than chosen round: the 3B at width 8 holds 109.6
  tok/s per stream (2026-09-06 sweep, quoted in the live config), so a
  1024-token reply clears in about 9 s, while the srv1 rung at width 2 gives
  14.0 tok/s per stream and takes about 73 s. 45 s is above the first and below
  the second — long enough that ordinary queueing on a fast rung does not trip
  it, short enough that a genuinely stuck queue is not made to wait a full
  service time of the slowest rung before help is sent for.

**Where the evaluation runs, with no new thread and no daemon.** The waiter is
the pressure, so the waiter does the asking. `runner.dispatch` today enters
`Capacity.hold` with `timeout=None`, which means the capacity's own
`budgets.task_timeout_s` (`capacity.py:754`). Under this design it enters
`hold` with `timeout=WAKE_SUSTAIN_S` in a loop, and on each
`SlotUnavailableError` it takes the census, decides, and re-enters with the
remaining task budget. Three properties follow, and they matter:

* **The ceiling is unchanged.** The slices sum to the same `task_timeout_s` the
  single call would have waited.
* **`hold` is untouched.** `timeout` is already documented as the claim shape —
  "try for that long, then raise `SlotUnavailableError`" (`capacity.py:1135`ff)
  — and this is a caller using it as written.
* **The exception must never escape.** `drive` turns `SlotUnavailableError`
  into `Verdict.DECLINED` (`src/mcgyvr/drive.py:617`). A slice expiring is not
  a decline; it is the middle of a wait. `mcgyvr.wake` catches it inside
  `dispatch` and only the final, budget-exhausted one is allowed through, with
  the meaning it has today.

### 7.4 ">= rung": what orders rungs, and what happens when nothing qualifies

**The config's tier order is the capability order, and it is the only one
mcgyvr has.** `ladder.tiers` is cheapest-first and its schema says a tier "must
be measurably better than the one below or it is not a rung — binding a
faster-but-weaker model above a slower-but-stronger one inverts the ladder and
makes escalation actively harmful" (`src/mcgyvr/config.py:385-389`).
`propose.py` is what puts tiers in that order and states the rule it enforces:
a lower rung is kept only if it is at least `MIN_QUALITY_GAIN` (0.03,
`src/mcgyvr/propose.py:75`) below the rung above, and dominance "deliberately
does *not* rank on speed" (`propose.py:40-43`). `Plan.steps` is that order
(`route.py:526`).

So **"a `>=` rung" is "a rung at or above the congested rung's index in
`ladder.tiers`"**, and no new ordering, no new field and no scan is needed to
say so.

**Finding a candidate.** Walk `ladder.tiers` from the congested rung's index
upward. For each rung take its card (D1's `cards(config)`) and skip it when:

* the rung is an api rung — it has no card;
* the card is `up` — there is nothing to wake;
* the card is `down` rather than `asleep` (D2) — mcgyvr has no launch spec for
  it, and inventing one is the thing `emit`'s boundary forbids (§14).

The first survivor is woken, through the door, under D7's election. **One card
per trip**: the ratio is re-read after the wake lands, so a second card is only
woken if the pressure is still there — which is the cheapest possible damping
and it costs nothing to state.

**When every `>=` rung is already up, the answer is to do nothing and say so.**
mcgyvr does not create capacity the config never declared: there is no rung to
bind, no width to invent, and no unit to size — sizing is a judgement a person
reviews (`hold_together`, `--ctx-per-slot`, the measured
`--gpu-memory-utilization`), which is the whole of §14's second clause. So the
queue does exactly what it does today: it waits in `hold` against
`task_timeout_s`. What is added is that the run *learns why*. A ladder that is
fully up and sustainedly over `WAKE_RATIO` is a ladder that is too small for
the batch being asked of it, and that is a finding about the config, not an
action. It goes on the result file as such (D10.1).

### 7.5 What trips a sleep, and the daemon question answered plainly

**A card sleeps when `pressure` on every bound it holds has been at the floor
long enough, and the card has been up long enough to have been worth waking.**
All four conditions, all at once, for card *c*:

1. `busy(b) == 0` for **every** bound *b* of every rung on *c* — the shared
   census, so no other mcgyvr process on this host is using it;
2. `now - mtime(<host>.used) >= SLEEP_IDLE_S` — the shared last-use clock
   (D7), so a card another process finished with a second ago is not slept;
3. `now - mtime(<host>.wake) >= MIN_UPTIME_S` — it has been up long enough;
4. no transition of *c* within `COOLDOWN_S` — §7.6.

**The danger the first draft used to refuse this, restated so it is not lost.**
An idle timer needs a process that outlives a run, and mcgyvr has none:
`Availability`, `Cooldown` and `Capacity` are each "one instance per run, and
the state dies with it" (`src/mcgyvr/cooldown.py`). A timer would be the first
daemon in the product and its job would be to remove serving capacity with
nobody watching. `emit`'s docstring names the equivalent failure in the other
direction — a tool that sizes and starts "turns 'here is what would run' into
'something is now running on your desktop', which is not a question the caller
was asked" (`src/mcgyvr/emit.py:1-9`). Inverted: *something you were using is
gone, and nobody asked you.*

**The answer, and it is the load-bearing sentence of this section: the sleep
decision is evaluated only at moments mcgyvr is already awake and running.**
There are exactly two:

* **when a dispatch to some other card releases its slot** — the "the work has
  moved off this card while the batch continues" moment, which is the
  queue-pressure sleep the ruling asks for; and
* **once at the end of a `mcgyvr run`**, before the result file is written.

No timer, no thread, no daemon. And the consequence has to be said out loud
rather than discovered: **a card that goes idle because everything stopped is
slept by the last run that used it, or it is not slept at all.** If the owner
wants "release the card thirty minutes after the last work, whatever else is
happening", that is something that runs on its own — **it is a daemon, and this
design does not build one.** The honest non-daemon substitute already exists in
shape: `mcgyvr serve sleep --host srv2 --idle-for 30m`, run by a cron or
systemd timer *the operator wrote*, is the operator's process and not mcgyvr's,
and it reads the same clock in D7. Which of the two the owner wants is **N6**.

**On this fleet, sleep never funds a wake, and pretending otherwise would be a
lie.** VRAM is contended within a host, and `emit` writes one compose file per
host, so no card can be freed to make room for another — waking srv2 never
requires sleeping srv1. What sleep buys here is the card back for its owner:
another job, another experiment, a game. That is the trade §14 already names,
and it is a real reason; it is simply not a reallocation. If a future host ever
holds two alternative compose files, sleep-to-fund-a-wake becomes the natural
extension and this is where it hooks in.

### 7.6 Thrash, and the numbers that damp it

A wake costs 80–130 s of rig time on this ladder — 203 s at the fleet's
measured worst — and a card's worth of VRAM (§6). A ratio that
wakes and sleeps one card repeatedly costs minutes per cycle for nothing, and
the sequential case is the realistic one, not a corner: twenty contracts run as
twenty `mcgyvr run` processes back to back would, with no damping, sleep srv2
at the end of each run and wake it at the start of the next — twenty wakes,
forty minutes of boot, zero benefit.

Four dampers, three of them numbers the owner has not ruled on:

* **The shared census gates every sleep** (§7.5.1). It is what stops process
  *n* sleeping a card process *n+1* is dispatching to right now, and it is not
  a tunable — it is a correctness condition.
* **`SLEEP_IDLE_S = 600` (N3)** since the card last served anything, host-wide.
  Ten minutes is longer than any plausible gap between two runs of one batch
  and shorter than a coffee break. It is the damper that actually kills the
  twenty-runs case.
* **`MIN_UPTIME_S = 900` (N4).** A card that cost up to 130 s to wake stays up
  at least fifteen minutes, so the worst-case duty cycle of a pathological
  oscillation is bounded at about 14% boot time rather than 100%.
* **`COOLDOWN_S = 600` (N5)** since the card's last transition in *either*
  direction, which is the hysteresis proper: after a sleep, the next wake of
  that card is refused for ten minutes unless it comes from D6's
  refusal-driven path — a dispatch that has actually been aimed at the card and
  been refused by the port is not speculation, it is a request, and refusing it
  would turn the damper into an outage.

All four clocks are read from files in the rendezvous directory (D7), not from
process memory, because the whole point is that they must hold *across*
processes.

### 7.7 What this algorithm actually does on the live ladder today

This is the part a reader is owed before anyone implements it. With no engine
scope (D4), on `~/.mcgyvr/config/mcgyvr.yaml` as it stands:

| rung | index | card | engine | may sleep |
| --- | --- | --- | --- | --- |
| `local_qwen2.5-coder-3b` | 0 | srv2 | vLLM | yes |
| `local_qwen2.5-coder-7b` | 1 | srv2 | vLLM | yes |
| `local_qwen3.6-35b-a3b` | 2 (top) | srv1 | llama.cpp | yes |

**Sleep and the refusal-driven wake are live on both rigs on day one.** A card
goes idle for `SLEEP_IDLE_S`, the next `mcgyvr run` to finish takes it down
whole — srv2's two units in one `serve down`, srv1's one in another — and the
next dispatch at that URL gets connection refused and brings the card back.
That is exactly "release the card when nobody is using it, and take it back
without anyone typing anything", and it is worth having on its own terms.

**The pressure-driven wake still has no candidate, and now for a reason no
ruling can fix.** Take the owner's sentence literally — work piles up on the
top rung, wake another `>=` rung — and the top rung is
`local_qwen3.6-35b-a3b`: there is nothing above it, so nothing is woken and the
finding is "the ladder is too small" (§7.4). Take congestion on rung 0 or 1
instead, and every `>=` card is either srv2 itself (already up, since the
congested rung is on it) or srv1, whose card is the top rung's own. Dropping
the engine scope did not conjure a rung; **what it did was make the fleet's one
real upgrade reachable** — srv2 serves an 80B-A3B in 97 s under llama.cpp (§6),
which outranks srv1's 35B-A3B, on a rig the ladder already uses. Add that rung
and §7.3's wake fires without another design pass.

So the design is honest about its own shape: **today the ratio is the sleep
side's trigger and the wake side's dormant twin**, and the thing that wakes it
is a rung, not a ruling. It is specified in full because the owner asked for
the algorithm, and because the ladder is one config edit away from having a
candidate.

**What this ladder cannot yet express is the layout the owner wants**: srv1
alternating between DeepSeek-Coder-V2-Lite and Qwen3.6-35B, srv2 between its
vLLM pair and the 80B. Both are *sleep funding a wake* on one card, and §17
records why nothing can say it today — `emit` writes one compose file per host,
so no host holds a second spec to switch to. That is the next design's problem,
and dropping the engine scope was its precondition, not its solution.

---

## 8. D6 — Where a contract blocks, and against which budget

*(Approved by the owner as designed. The rigorous treatment is unchanged and
begins below; the owner asked for the mechanism to be stated simply first, and
that request was fair — this was the densest page in the draft.)*

### 8.1 In plain words

mcgyvr does not check whether a rig is awake before it sends work. It just
sends the work. If the rig is asleep there is nothing listening on the port, so
the connection is refused immediately — no waiting, no timeout, an answer in
under a millisecond. **That instant refusal is the wake signal.** mcgyvr starts
the rig, waits for it to come up, and sends the same request again. The retry
does not count as a failed attempt, because nothing was asked and nothing
answered.

That is the whole mechanism. A rig that is already awake pays nothing at all
for it, because the check *is* the request.

**Why there are three separate timers, when one would look simpler.** They
bound three different things, and a single knob would mean tuning all three
with one number:

* **`request_timeout_s`** — how long *one reply* may take. It is priced from
  tokens per second: a rung's speed times the reply length you allow.
* **`task_timeout_s`** — how long you will *wait for a free slot* on a server
  that is already running and busy with other work.
* **`wake_timeout_s`** — how long you will wait for a server *to exist at all*.

Sharing one knob between the first and the third would mean setting reply
length and boot time with the same number: raise it to survive a 130-second
boot and every hung request now hangs for 130 seconds too. Sharing it with the
second would mean a deep queue and a cold rig were the same fault. They are
three faults and they get three sentences (§13).

### 8.2 The seam, and why it is that one

**Decision. At the dispatch seam, outside the capacity hold, on a transport
refusal — never before it.**

`runner.dispatch` (`src/mcgyvr/runner.py:565`) is the one place that has the
endpoint (hence the URL, hence the host), the rung, and the capacity whose
rendezvous directory the wake lock will live in — and it is below the
execution seam, which is what keeps D1 true. `dispatch_role`
(`src/mcgyvr/runner.py:597`) gets the same treatment: a verifier sharing a card
with the ladder is on that card when it sleeps.

**Fail-first, not probe-first.** The happy path must cost nothing. A card that
is up costs zero extra bytes under this design: mcgyvr dispatches, and it
works. A card that is asleep answers *connection refused*, which
`availability.py`'s own docstring says "returns instantly" for a local port.
So the sequence is:

```
dispatch
  └─ transport refusal (refused / no route)
       └─ is this card asleep?  (D2: no file -> DOWN, unchanged)
            └─ wake (D7 elects one waker; the rest wait)
                 └─ dispatch again, ONCE
```

A probe-first design would pay `PROBE_TIMEOUT_S`
(`src/mcgyvr/availability.py:121`) or a model-list round trip on every
dispatch to learn something the dispatch itself reports for free. That is the
cost `Availability` exists to avoid, re-added per request.

**The retry after a wake spends no attempt.** Nothing was asked and nothing
answered, so it is not a failure — the same rule `drive` already applies to a
declined rung (`src/mcgyvr/drive.py:617`), and the same reason: a rung that
produced no verdict funded no escalation. A wake that *fails* is different and
is a real verdict against that rung.

**This path is exempt from the cooldown damper** (§7.6): a refusal here is a
request that was actually made, not a ratio's speculation, and refusing to
serve it would turn a thrash guard into an outage.

### 8.3 Against a new budget: `budgets.wake_timeout_s`

* Not `budgets.request_timeout_s` (120.0, `src/mcgyvr/config.py:535`). That
  number bounds a transport, and it was chosen against measured tok/s — "the
  top local rung gives 27.2 tok/s to one stream and 5.09 tok/s to each of
  eight". An 80-second wake charged to it would eat two thirds of a budget
  that was priced for generation, and the 120-second srv2 card wake measured on
  2026-09-08 would exhaust it outright.
* Not `budgets.task_timeout_s` (900 live), which is what `Capacity.of` hands
  `hold` as its queue ceiling (`src/mcgyvr/capacity.py:754`). That bounds a
  wait for a *slot* on a server that exists. A wake is a wait for the server.
* **Default 480.0 (N7, and the one item on that list a measurement settled
  rather than a ruling).** The door's own health budget is 360 s
  (`servelib.HEALTH_POLLS × HEALTH_INTERVAL_S`) and gates 1, 2, 3 and 5 run
  before the step. A caller budget *below* the door's would abandon a wake
  while the door was still working and leave a card half-up — so the schema
  refuses a `wake_timeout_s` under the door's own figure, by the same shape as
  `Capacity.of`'s width refusal: name the disagreement at the one moment both
  numbers are in hand, rather than quietly correcting it. **480 now also has a
  measurement behind it, not only that floor**: the fleet's worst wake is
  srv1's ceiling model at 203 s (§6), so the budget carries 2.4× headroom over
  the slowest thing the ladder can be asked to start. It was priced from the
  door and it survives the measurement; that is the strongest form this number
  was available in.

The wake budget bounds one wake and not their sum, exactly as
`queue_timeout_s` bounds one hold and not a climb's — and for the same reason
recorded at `src/mcgyvr/capacity.py:752-754`: charging a climb's waits against
one deadline needs a deadline threaded through the climb, which is not this
seam's.

---

## 9. D7 — The rendezvous, and the clocks the algorithm reads

*(The election was approved by the owner as designed. The two clock files are
new, and they are new because §7 made sleep a decision several processes have
to agree about rather than an operator's command.)*

Two mcgyvr processes on one host both find srv2 asleep. Exactly one may run
the door; the other must not dispatch until the card is up, and must not
report a failure.

**Part one, on this machine: the capacity rendezvous directory, and three
files keyed by host.** All three live in `/tmp/mcgyvr-capacity-<uid>/`, beside
the slot files, with `_slot_stem`'s naming discipline (`capacity.py:264`) — a
readable prefix plus a digest, "so that sanitizing cannot merge two rigs into
one" — and keyed by **host**, not by `base_url` and not by rung, because
eviction is whole-card. This is the one place in the codebase where a
host-keyed lock is correct, and it is below the seam.

| file | what it is | read by |
| --- | --- | --- |
| `<host-stem>.wake` | an exclusive `flock` held for the length of a transition; its **mtime** is the last transition time | the election; `MIN_UPTIME_S` and `COOLDOWN_S` (§7.6) |
| `<host-stem>.used` | no lock; its **mtime** is touched on every dispatch to a rung on this card | `SLEEP_IDLE_S` (§7.5) |
| `<host-stem>.<n>.slot` | the existing slot files, unchanged | the `busy(b)` census (§7.2) |

* The lock inherits the property a waker most needs and which the module
  already argues for: "The kernel releases a `flock` when its process dies,
  however it dies" (`capacity.py`, module docstring). A waker killed mid-wake
  strands nothing.
* The clocks are **files rather than process state** for the reason the whole
  section exists: twenty `mcgyvr run` processes have twenty memories and one
  filesystem, and a damper that lives in memory damps nothing across them.
  `os.utime` on `.used` is one syscall on the dispatch path, against a dispatch
  measured in seconds to minutes.
* Slot files are **not** reused for the election. A slot is a permit to
  dispatch; a waker taking every slot of a card would be indistinguishable
  from a saturating batch, and it would collide with the drain in D8, which
  needs those slots to mean what they mean.
* The files are never deleted, for the same unlink-race reason the slot files
  are not (`capacity.py`, module docstring). A `.used` with no mtime yet — the
  first run after a reboot — reads as "never used", which correctly forbids a
  sleep until something has used it.

**The loser does not fail and does not wake twice.** It blocks on the same
lock, and on acquiring it re-reads the state (D2). The winner will have
brought the card up, so the re-read says `up` and the loser dispatches without
a second door run. Double-checked, and the check is the cheap one. A loser of a
*sleep* election does the same and finds the card asleep, at which point D6's
refusal path is what brings it back — which is the one case where a sleep and a
wake can legitimately follow each other inside `COOLDOWN_S`.

**Part two, across machines and against a campaign: the rig lease, unchanged.**
`~/.mcgyvr/lease` lives *on the rig* — "because the rig is the contended
resource: a laptop and srv1 both reach it, and a file on either of them would
be a lock only one of them could see"
(`src/mcgyvr/serving/gatelib.py:357-361`). Gate 2 takes it with a
compare-and-swap on the lease id, a `set -C` write for a free rig, and R1
arbitration between profiles. A wake spawns the door, the door takes the
lease, and a wake that arrives while a measurement campaign holds srv2 is
resolved by R1 — not by a rule this design invents. The flock cannot see
another machine ("two *machines* dispatching at one rig are beyond what a file
lock can see"); the lease can, and it already does.

So: **no new rendezvous mechanism.** Two new files in an existing directory
with existing semantics, and one existing lease used as it stands.

---

## 10. D8 — The eviction rule

The prompt's original case — waking model B on srv2 takes model A down —
**does not arise under this design, and the reason is worth stating rather than
celebrating.**

The card is the compose file, and the compose file holds every unit on that
host. srv2's file holds both the 3B on `:8001` and the 7B on `:8002`, sequenced
largest-first by `depends_on` (`~/.mcgyvr/config/compose.srv2.yml`;
`src/mcgyvr/emit.py:223`). There is no per-model wake, so there is no wake that
displaces a neighbour. And a ladder whose units could not co-reside was never
emittable: `hold_together` (`src/mcgyvr/serving/__init__.py:671`) refuses it
before a file is written — "fit the card one at a time and not together".

That is what the owner's whole-card ruling actually buys. Whole-card eviction
does not solve partial eviction; it **deletes the case**. Gate 2 enforces the
same thing from the rig's side (D3.4): `serve up` refuses a rig that is not
idle, so there is no such thing as topping a card up.

**Whole-card eviction is unchanged by the ruling that made sleep automatic.** A
sleep decision — §7.5's, or an operator's `mcgyvr serve sleep --host srv2` —
takes down **every unit in that card's compose file**. On the live ladder that
is two rungs at once, `local_qwen2.5-coder-3b` and `local_qwen2.5-coder-7b`,
and a run holding work for either of them is a run this rule has to answer for.
The rule is the draft's, restated because automation makes it load-bearing
where an operator's typed command made it merely correct:

> **An eviction takes all of the card's slots before it takes the card down.
> It never interrupts a dispatch that is already in flight, and it is
> best-effort against processes the flock cannot see.**

Mechanically: the sleeper acquires every slot file of every bound on that card
— which is the drain primitive, and the slot files already exclude every
mcgyvr process on the host (#185) — then spawns the door's `down` step, then
releases. The drain is bounded by `budgets.request_timeout_s` (120 s): a
dispatch in flight either finishes or the transport gives up.

Note that under §7.5 the drain will almost always find every slot already free,
because condition 1 is that the shared census read zero. The drain is not
redundant for that: the census is a reading and the drain is a hold, and
between the two a dispatch can start. The census decides *whether* to sleep;
the drain is what makes the decision safe to act on.

Two honesties on top of it:

* `docker compose down` kills containers. A request from a *second machine*,
  or from something that is not mcgyvr, is not drained and is not asked. The
  lease is the guard there and it is a decision procedure, not a mutex on
  requests — a live run displaces a held rig and tears down what it displaced
  (R1). Sleep therefore *can* kill someone else's in-flight request, and the
  lease is what makes that a recorded decision rather than an accident. This
  was true of an operator's typed sleep and it is more true of an automatic
  one, which is a large part of why the whole feature is off by default
  (§7.1).
* If a later feature wants model **rotation** on one card — evict A to load B
  — this rule is the one it must extend, and it is the whole of the extension:
  drain the card's slots first, then swap. Rotation is out of scope, and it
  should stay out until someone has a measurement showing that two units which
  `hold_together` accepts are worse than one at a time.

---

## 11. D9 — A `dev` round may sleep and wake, and what the refusal was protecting

**The owner has overturned the draft's conclusion that under `dev` a sleeping
card is a decline.** This section re-reads the refusal, names what it protects,
and proposes the smallest change that keeps that protection.

### 11.1 What the refusal is, and what it is actually protecting

`gate-scripts/01-round.py:94-103` refuses `serve up|down` when
`RUN_PROFILE == dev`, before any rig is read: *"the live ladder is prod's (R1,
live outranks dev)"*. The schema states the same rule from the config's side —
a dev run "does not start or stop the live ladder, refuses a rig another run
holds, and yields the rig to a live run that takes it"
(`src/mcgyvr/config.py:664-672`).

Reading the gate against its neighbours, it protects **two different things**,
and only one of them is about measurement:

1. **Composition — a dev config must not install its own ladder on the shared
   rig.** `serve up` starts whatever compose file it was handed. A dev config
   is by definition a setup under development; its emitted units could carry
   different models, different `--gpu-memory-utilization`, a different image
   digest. Bring that up on srv2 and every subsequent live run, and every live
   measurement, is against a ladder nobody declared. *This is the measurement-
   integrity half, and it is real.*
2. **Availability — a dev run must not take the live ladder away.** `serve
   down` stops the units live runs dispatch to.

And it is worth being precise about what the refusal is **not** the only guard
for. Gate 2 already refuses a `dev` run any rig another run holds
(`02-rig.py:184-189`) and already refuses *any* run — dev or live — a rig that
is not idle for `serve up` (`:269`). A measured campaign run cannot even open
on a rig with the live ladder up, for the same reason. So the dev/live conflict
that gate 1 uniquely covers is the narrow one: **a dev run acting on a card
that no other run is holding.**

### 11.2 The smallest honest change

**Proposal: gate 1 stops keying on the profile and starts keying on whose
launch spec is being run.**

> Under `dev`, `serve up|down` is permitted **only when `RUN_COMPOSE` names a
> file inside the live config's `serving.compose_dir`, by `emit_all`'s
> per-host naming convention** — i.e. only when the spec being started or
> stopped is the live ladder's own. A dev run may **operate** the live ladder.
> It may never **install** one.

Why this is the right cut:

* It keeps protection (1) whole. The composition on the rig stays the live
  config's, because a dev run can only ever hand the door the live config's own
  file. A dev config's freshly-emitted `compose.srv2.yml` sitting in the dev
  tree is not in the live `compose_dir` and is refused exactly as today.
* It costs no rig time and needs no scan. Gate 1 already loads a config and
  already knows `configlib.user_config_path()` — it names that path in the very
  refusal being replaced. `RUN_COMPOSE` is in the environment before gate 1
  runs (`serving/run.py:775`). The check is a path comparison and a digest
  recorded in the envelope header.
* It leaves R1 untouched where R1 does the work. Gate 2 still makes a dev run
  yield a held rig, and gate 2's idle check still refuses a `serve up` onto a
  busy card. Nothing in the arbitration between profiles changes.
* It keeps the hand-typed case refused where it is dangerous. An operator under
  `dev` who has emitted their own units and types `serve up --compose
  ./compose.srv2.yml` still gets today's refusal, with today's message.

### 11.3 What is genuinely given up, stated so the owner can weigh it

**A dev run can now put the live ladder to sleep on a free rig.** That is the
residual, it is not eliminated by anything above, and it is the thing R1 was
written to prevent. Its cost is bounded and it is bounded by this design's own
machinery: a live run that arrives afterwards finds the card asleep, is refused
by the port, and wakes it (D6). So the price a live run pays for a dev run's
sleep is **one wake — 50 to 130 s — and not a failure.** It is recorded: the
wake leaves `serve-up.json` in the live run's own envelope, with the seconds
each unit took, and the result file says the run waited (D10).

Whether that price is acceptable is the owner's call and is **N11**. Two
alternatives, if it is not:

* **Direction-asymmetric dev.** Allow a dev round to `wake` (add capacity the
  live config declared) and keep refusing `sleep` (remove it). This is the
  first draft's overturned invariant applied to one profile only, and it costs
  the dev user nothing except the ability to free the card — which is
  arguably prod's to free.
* **Lease-scoped dev sleep.** Require a dev sleep to hold the rig lease and to
  wake the card back on the way out, so a dev round borrows the card rather
  than releasing it. This is more machinery and it makes the sleep pointless
  for the dev user's actual purpose, which is to get the 3060 back.

### 11.4 The distinction the owner asked about: a `dev` round versus a measured round

The owner asked whether a wake during a `dev` round might be fine where a wake
during a *measured* round is not. It is a real distinction and the tree already
draws it — in the run sequences rather than in the profiles.

`SERVE_SEQUENCE` and `SEQUENCE` are two different runs
(`serving/run.py:292-308`): the serve run is gates 1, 2, 3, 5 and the step, and
it deliberately omits gate 4 (the pinned workload) and the three data scripts
"about one model under measurement", because "a live ladder is not an
experiment, and the envelope it files under is the host's"
(`run.py:114-117`). A serve run *is not a measurement*, whatever profile it is
under, so waking a card cannot contaminate a benchmark row — there is no row.

And a measured campaign run cannot overlap a live ladder at all: gate 2's idle
check refuses a rig with `gpu_procs` or `containers` reading anything but
`none` (`02-rig.py:269-276`), so a `SEQUENCE` run against srv2 while the live
ladder is up already refuses today, and the lease refuses the reverse. **The
two are already mutually exclusive by the gates.** Sleep/wake does not weaken
that and does not need a rule of its own for it.

So the honest answer to the owner's question is: the profile was never the
right axis for measurement integrity — the sequence is, and it already
separates them. What `dev` versus `live` actually governs is *whose ladder runs
on the shared rig*, which is §11.2's cut.

---

## 12. D10 — What an operator sees, and why it is not another dead end

`Usage.waited_seconds` and `Concurrency` are computed in `mcgyvr.capacity` and
read by nothing: `cli.py`, `escalate.py` and `result.py` contain zero
references, and only `tests/test_capacity.py` touches them. The module's own
docstring argues they are essential — "A bound nobody can see is
indistinguishable from no bound" — and they are, and nobody sees them. This
design does not add a ninth signal to that pile.

Every sleep/wake signal goes somewhere that already has a reader:

1. **`RunResult`** (`src/mcgyvr/result.py:63`) gains one field —
   `capacity_changes: list[...]`, a small record per transition with the host,
   the direction, the seconds, the reason (`refused` / `pressure` / `idle` /
   `operator`) and the envelope path. The argument is already written on its
   neighbour `copy_errors` (`:100`): it is there "because the skill tells a
   caller to read this file rather than the scrollback, and 'your copy is
   short' is exactly the kind of fact a caller reading the file would otherwise
   never learn". *This run waited 84 seconds for srv2 to come up* and *this run
   put srv2 to sleep on its way out* are the same kind of fact, for the same
   reader — the `/mcgyvr` skill, which reads the result file and replans from
   it. The direction and the reason are on the record because a caller
   replanning after a slow run needs to know whether the slowness was a wake it
   caused, a wake it inherited, or a queue.
   **The undersized-ladder finding of §7.4 lands here too**, as a finding
   rather than a transition: *every rung at or above `local_qwen2.5-coder-3b`
   was already up and the queue stayed over the threshold for N seconds*. That
   is a fact about the config and it is exactly what the skill is meant to
   replan from.
2. **stderr, before the wait and after it.** One line at the start naming the
   card, the direction, the budget and the envelope path, so `tail -f` reaches
   the door's own output; one line at the end with the measured seconds. A hung
   rig prints nothing, which is precisely the difference (§13).
3. **The envelope**, written by the door whether mcgyvr asked for it or not:
   `records/evidence/live-<host>/<RUN_ID>/serve-up.json` (or `serve-down.json`),
   carrying per-unit `healthy` and `seconds` and `card_after`. This is the
   surface `okf/must-read/reading-results.md` and gate 8 already point at, and
   it is the reason an automatic sleep is auditable at all: **every transition
   this design makes leaves a write-once envelope naming the process that made
   it.** That is what replaces the withdrawn "never removes capacity"
   invariant as the safety property — not that mcgyvr cannot take a card down,
   but that it cannot take one down quietly.

Deliberately **not** added: a new `mcgyvr status` command, a card column in
`mcgyvr pool`, a metric. Each would be a fourth reader to keep alive, and the
three above are all consumed today.

---

## 13. How an 80-second block does not look like a hung rig

The measured numbers this must survive (§6): srv1's llama.cpp unit answered in
128 s at its live `-c 16384`, srv2's card — both vLLM units, one `compose up`,
sequential by `depends_on` — answered by 120 s, a single vLLM unit alone in
82 s, and srv1's ceiling model took 203 s. `budgets.request_timeout_s` is
120.0, which every one of those either exceeds or sits within seconds of. So a
wake and a hang overlap in duration, and duration cannot tell them apart. Three
things can:

1. **It announces itself at the moment it starts waiting** (D10.2), with the
   direction, the budget and the envelope path. A hung rig announces nothing —
   that is the entire experiential difference between the two, and it is free.
2. **It is bounded by a budget that is not the request budget** (D6), so an
   overrun fails as a wake — *srv2 did not answer 480 s after the door started
   it, see `<envelope>/serve-up.json`* — and never as a timeout, *no reply in
   120 s*. Two faults, two sentences. This is `availability.py`'s own
   discipline: its 401 arm and its 404 arm exist as separate arms because "each
   would look like an over-reaction if only the other kind existed".
3. **It leaves evidence that it was a wake**, with the seconds each unit
   actually took. A hang leaves an absence.

And the wait is paid once per card, not once per contract: the losers of the
wake election (D7) are released the moment the winner's door run returns, so a
batch of twenty contracts against a sleeping srv2 waits one wake, not twenty.

---

## 14. The boundary that replaces "emitting is writing a file"

`src/mcgyvr/emit.py:1`: *"Emitting is writing a file. It is never starting a
process… Nothing in this module shells out, and nothing in it may learn to."*

That sentence stays literally true. `mcgyvr.emit` is not touched by this
design; the module that spawns the door is `mcgyvr.wake`, and what it hands the
door is a file emit already wrote and a human already reviewed.

But the *spirit* — this repository does not reach into a rig from the run path
— does change, and pretending otherwise would be the dishonest version of this
document. The draft's replacement boundary had three clauses and the owner has
struck the third. What is left, and what replaces it:

> **mcgyvr starts and stops a process on a rig only through the door, only
> from a launch spec `emit` already wrote, only for serving capacity the config
> already declares, only when the config says it may, and never without leaving
> an envelope that says it did.**

Each clause carries weight, and each is checkable:

* **only through the door** — the seal at `src/mcgyvr/serving/run.py:14-32` is
  unchanged and mechanically enforced by the shims and by
  `tests/test_one_door.py`. This design adds a *caller* of the door, not a
  second door.
* **only from a spec emit already wrote** — a wake cannot invent a unit. No
  file means the card is `down`, not `asleep` (D2). So mcgyvr still never sizes
  and starts in one act, which is emit's actual objection: sizing is a
  judgement a person reviews (`hold_together`, `--ctx-per-slot`, the measured
  `--gpu-memory-utilization`), and a wake only ever re-runs the judgement that
  was already reviewed and committed. It is also why §7.4 does nothing when
  every `>=` rung is up: there is no capacity to add that a person has not
  already sized.
* **only when the config says it may** — `serving.enable_sleep_wake`, default
  `false`, in the file whose digest names the run (§7.1). The feature does not
  exist for an operator who did not ask for it, and an operator who did asked
  in the one place that is recorded.
* **never without an envelope** — every transition is a door run and every door
  run writes write-once evidence under `records/evidence/live-<host>/` (D10.3).
  **This is the clause that carries the weight the withdrawn invariant used to
  carry.** The first draft's safety was "mcgyvr cannot take capacity away". The
  owner has replaced it with something weaker and more useful: mcgyvr can take
  capacity away, and it cannot do so anonymously, unbudgeted, undamped, or
  without being asked.

What an operator gives up by turning this on: `mcgyvr run` can now start *and
stop* containers on srv2 without anyone typing `serve up` or `serve down`, and
on a rig shared with people who are not running mcgyvr, a sleep can take work
away from them (D8). What they get: a ladder that survives a rig reboot, and a
card that is released when nobody is using it and taken back when somebody is,
without editing the config to delete a rung. The trade is stated here so that a
future reader can reject it knowingly rather than discover it — and the default
is `false` precisely because it is a trade and not an improvement.

---

## 15. Shape of the change (for the plan that follows this one)

New:
* `src/mcgyvr/wake.py` — the card reading (D2), the ratio and the two
  decisions (D5), the election and the clocks (D7), the door invocation (D3).
  One module.
* `mcgyvr.serving.cards(config)` — the derivation (D1). One function, beside
  `units_for`.
* `mcgyvr.capacity` gains two readers and nothing else: `busy(bound)` — the
  `LOCK_NB` census `route.Machine.load` said belongs here (`route.py:326-333`)
  — and `waiting(bound)`, the instantaneous form of `_waited`. Both are
  readers; neither changes what `hold` does.
* Config: `serving.compose_dir`, `serving.enable_sleep_wake` (default
  `false`), `budgets.wake_timeout_s` (default 480.0, refused below the door's
  health budget).
* `mcgyvr serve sleep|wake --host H` — a thin front over the door's two steps,
  for the operator who wants to say it by hand. Unaffected by
  `enable_sleep_wake`, which governs only the automatic decisions.

Changed:
* `src/mcgyvr/runner.py:565` and `:597` — the refusal-triggered wake outside
  the hold (D6), the sliced `hold` that evaluates the ratio (§7.3), and the
  `os.utime` on `.used`.
* `src/mcgyvr/result.py:63` — one field (D10.1).
* `src/mcgyvr/cli.py` `_climb` — carries the waker beside the capacity it
  already builds at `:1354`, for the same reason it builds one capacity and
  not two; and the end-of-run sleep evaluation (§7.5).
* `src/mcgyvr/serving/gate-scripts/01-round.py:94-103` — the profile refusal
  becomes a spec-provenance refusal (§11.2).

**Dependency on work in flight, described rather than touched.** A per-rung
output cap is being implemented on `red/per-rung-output-cap`, touching
`config.py`, `contract.py`, `drive.py` and `gate/preflight.py`. This design
needs three things from `config.py` — two new keys and one new block — and one
thing from `drive.py`: that `SlotUnavailableError` keeps meaning
`Verdict.DECLINED` at `:617`, so that §7.3's sliced waits are caught before
they reach it. Neither file is edited here. If the cap lands first, the schema
additions are three `Field` entries against whatever `SCHEMA` then looks like,
and nothing about their content changes.

Untouched, and that is the point:
* `config.Tier`, `config.Source`, `pool.Endpoint`, `route.Plan`,
  `route.Machine`, `escalate.Ascent`, `escalate._widths`. Nothing above the
  execution seam learns that a card exists.
* `emit.py`. It still only writes files.
* `serving/run.py`, gates 2, 3, 5, the shims, the lease. A new caller and one
  gate condition, no new door.

---

## 16. Numbers and rules the owner has not ruled on

One line each. Every one of these was chosen by this document, not by the
owner, and every one is load-bearing.

| | what | proposed | why that, and what it costs to be wrong |
| --- | --- | --- | --- |
| **N1** | `WAKE_RATIO` | `2.0` | Full plus a full queue again. Lower wakes cards for ordinary saturation; higher never wakes. |
| **N2** | `WAKE_SUSTAIN_S` | `45` | Above the 3B's ~9 s service time at width 8, below srv1's ~73 s at width 2. Lower spends 80–130 s wakes on bursts; higher sends help after it was needed. |
| **N3** | `SLEEP_IDLE_S` | `600` | The damper that kills back-to-back `mcgyvr run` thrash. Lower thrashes; higher makes sleep useless. |
| **N4** | `MIN_UPTIME_S` | `900` | Bounds a pathological oscillation to ~14% boot time. |
| **N5** | `COOLDOWN_S` | `600` | Hysteresis on either direction; exempt for D6's refusal-driven wake, or a thrash guard becomes an outage. |
| **N6** | Is an idle-timer daemon wanted? | **no daemon** | §7.5 evaluates sleep only while mcgyvr is running, so a card idle after everything stops is slept by the last run or not at all. The alternative is a real daemon; the substitute is a cron the operator writes. |
| **N7** | `budgets.wake_timeout_s` | `480.0` | **Measured 2026-09-08** (`records/measurements/wake-2026-09-08/`). Priced from the door's 360 s health budget, and now also above the fleet's worst measured wake — 203 s, srv1's ceiling model — by 2.4×. §6 has the five figures. This was the one row a measurement rather than a ruling settled, and it settled in the proposal's favour. |
| **N8** | `enable_sleep_wake: true` with `fanout: none` | document, do not refuse | A woken card gets no work under `none` until something escalates onto it. Refusing would also take away D6's refusal-driven wake, which is useful under every mode. |
| **N9** | A half-up card | report, do not repair | `down`-then-`up` would fix it and is a repair of a machine mcgyvr found wrong, which run contract §4 forbids a cell. Whether the sleep/wake algorithm is exempt is the owner's. |
| **N10** | Widen the engine scope to llama.cpp? | **RULED 2026-09-08: there is no engine scope** | Not widened — removed. The wake measurement took both legs out from under "not yet": the engines are indistinguishable to wake (82 s for one vLLM unit against 50-128 s for llama.cpp on the same fleet, §6), and srv2 — already in the ladder — serves an 80B-A3B in 97 s under llama.cpp, the one rung this hardware can add above srv1. mcgyvr's own fit refuses the 14B AWQ (11.6 + 2.0 GB against 12.0 free), so there was no vLLM upgrade path at all. A predicate on `source.engine` would have bought no simplification (§6) and cost the ladder its ceiling. No rig is banned for the engine that serves it. |
| **N11** | A `dev` round may sleep the live ladder on a free rig | accept, at one wake | §11.3. The live run that follows pays 80–130 s, not a failure, and the wake is in its envelope. Alternatives: dev may wake but not sleep; or dev must hold the lease and wake it back. |
| **N12** | `capacity_changes` on `RunResult` | one field | D10.1. Alternative is stderr only, which the `/mcgyvr` skill does not read. |

---

## 17. Open questions this design does not settle

* **A wake mid-batch changes the widths.** A card that comes up serves what
  the compose file says, which may differ from what `Capacity` was built with
  at `src/mcgyvr/cli.py:1354`. Today a width disagreement is a refusal at
  build time; a disagreement discovered *after* a wake has nowhere to go.
  Simplest answer: a wake does not re-read widths, and the config remains the
  declaration — consistent with the rest of `capacity`, and a probe after wake
  is a separate question.
* **Whether `mcgyvr.wake` should also handle a card that is up but serving the
  wrong model** (a hand-started unit, a stale compose). It should not, in v1:
  that is a config-vs-rig disagreement and belongs with the width refusal, not
  with sleep. It is the same family as N9.
* **The ratio reads a lower bound on demand** (§7.2), because `waiting` is
  per-process while `busy` is shared. If multi-process batches turn out to be
  the normal case rather than the exception, a shared waiter count becomes
  worth its cost — one more file in the rendezvous directory, written on every
  queued dispatch. Nothing here forecloses it.
* **Sleep never funds a wake on this fleet** (§7.5), because `emit` writes one
  compose file per host and no two cards contend. The algorithm is symmetric
  anyway; whether the symmetry is worth its numbers before a host ever holds
  two alternative specs is a fair question to put back.
* ~~**A single vLLM unit's wake time is unmeasured**~~ — **taken 2026-09-08:
  82 s** (§6, N7, `records/measurements/wake-2026-09-08/`). `wake_timeout_s`'s
  480 stands, with 2.4× headroom over the fleet's worst wake of 203 s. What the
  measurement opened, the owner then closed: there is no engine scope (N10).
* ~~**Nothing refuses a model that does not fit its host's RAM**~~ — **fixed
  on this branch.** The same measurement found `fit` weighing spilled experts
  against `MemAvailable` with no headroom at all, so a 16.9 GiB blob was
  emitted onto a 15 GiB host and took 203 s to wake behind a thrashing page
  cache. `fit` now has two arms — blob plus headroom, else spilled experts plus
  headroom with `--load-mode none`, else refuse — and `unit_for` writes the
  mode the fit approved into the argv
  (`tests/test_a_blob_that_overflows_ram_is_emitted_unmapped.py`,
  `okf/must-read/touching-rigs.md`). It matters here because **a wake is a
  load**: what this design brings back at 03:00 is whatever `emit` wrote, and
  before this the thing it wrote could be a model the host cannot hold.
  Consequence for the live ladder: srv1's top rung now emits `--load-mode
  none`, so `emit --check` reports drift until the rig is re-emitted.
