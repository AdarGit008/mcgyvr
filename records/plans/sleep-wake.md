# Sleep and wake for the local ladder

Design only. Nothing here is implemented, and no line of `src/` changes on the
branch that carries this file.

**The owner's ruling, which this design starts from and does not revisit: on
sleep, mcgyvr evicts the ENTIRE GPU. Not one model, not a share of VRAM — the
whole card comes down.**

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
the compose file.** Everything below is about the four things that are
genuinely missing — knowing which rungs a card holds, telling "asleep" from
"broken", electing one waker, and deciding who may ask.

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
        compose_dir holds a file for its host -> queue and wake (D5)
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
config with no `serving.compose_dir` has no sleeping cards at all, so the
feature is off by omission rather than by a flag.

**Where the reading lives.** In the same family and at the same seam as its
two neighbours: a view that satisfies the one-method `pool.SourceProbe`
question, wrapping an `Availability` or a `Cooldown` the way `Cooldown` wraps
an `Availability` — "an availability view that also *learns*"
(`src/mcgyvr/cooldown.py`). This one is an availability view that also
**acts**. One new module, `src/mcgyvr/wake.py`; zero new vocabulary in the
config beyond D1's directory; nothing above the seam learns anything.

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
(`src/mcgyvr/serving/servelib.py:30-31`), six minutes, chosen because "a vLLM
server measured 87 s to health on srv2 and llama.cpp 54-129 s on srv1
(2026-09-05)". That is the measured wake this design must survive, already
bounded, already recorded.

**What the envelope costs, and why it is a benefit and not a tax.** The door
has a heavy contract: it mints its own `RUN_*` vocabulary and refuses to start
under an inherited one; it runs `SERVE_SEQUENCE` — gates 1, 2, 3, 5 and the
step (`src/mcgyvr/serving/run.py:292`ff) — with no way to skip an entry; and
it writes write-once evidence under `records/evidence/live-<host>/`
(`RUN_CAMPAIGN = f"live-{opts.host}"`, `src/mcgyvr/serving/run.py:770`). Three
consequences, all accepted:

1. **Every wake leaves `serve-up.json`** with the compose text, per-unit
   `healthy` and `seconds`, and `card_after` from `nvidia-smi`
   (`servelib.card`, `:166`). That is the operator signal D8 needs, in a place
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

**And one refusal the design inherits and must not paper over.** Gate 1
refuses `serve up|down` under the `dev` profile, before any rig is read
(`src/mcgyvr/serving/gate-scripts/01-round.py:93-97`): "the live ladder is
prod's (R1, live outranks dev)". **Therefore: under `dev`, a sleeping card is
a decline, not a wake.** `mcgyvr.wake` reads the profile the same way gate 1
does and declines locally rather than spawning a door that will refuse — same
outcome, one fewer subprocess, and the decline says *why* (`dev does not start
the live ladder`) rather than reporting a gate refusal the operator did not
cause.

---

## 6. D4 — Wake is automatic. Sleep is not. That asymmetry is the safety property

**Decision. Nothing in mcgyvr ever decides on its own to take a card down. A
card sleeps because an operator said so: `mcgyvr serve sleep --host srv2`, a
thin front for the door's `down` step. Waking is automatic, at dispatch, for
the card a chosen rung sits on.**

Against the three candidate signals:

* **Idle timer — refused.** It needs a process that outlives a run, and mcgyvr
  has none: `Availability`, `Cooldown` and `Capacity` are each "one instance
  per run, and the state dies with it" (`src/mcgyvr/cooldown.py`). A timer
  would be the first daemon in the product, and its job would be to remove
  serving capacity with nobody watching. `emit`'s docstring names the
  equivalent failure in the other direction — a tool that sizes and starts
  "turns 'here is what would run' into 'something is now running on your
  desktop', which is not a question the caller was asked"
  (`src/mcgyvr/emit.py:1-9`). Inverted: *something you were using is gone, and
  nobody asked you.*
* **Capacity pressure — refused, and incoherent.** Sleeping reduces capacity.
  A pressure signal that evicts a card is a design for model *rotation*, which
  is a different feature (see §9).
* **Explicit command — taken.** It is the only signal whose author can be
  named in the evidence, and the door already records who held the lease.

The invariant this buys, stated so a later change has to argue against it:
**mcgyvr may add serving capacity on its own and may never remove it.** Every
automatic action in this design is idempotent-toward-up.

A later `mcgyvr serve sleep --idle-for 30m` that reads last-dispatch times off
the journal and is *run by an operator or a cron the operator wrote* is
compatible with this and is not a daemon. It is out of scope here.

---

## 7. D5 — Where a contract blocks, and against which budget

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
            └─ wake (D6 elects one waker; the rest wait)
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

**Against a new budget: `budgets.wake_timeout_s`, default 480.0.**

* Not `budgets.request_timeout_s` (120.0, `src/mcgyvr/config.py:535`). That
  number bounds a transport, and it was chosen against measured tok/s — "the
  top local rung gives 27.2 tok/s to one stream and 5.09 tok/s to each of
  eight". An 80-second wake charged to it would eat two thirds of a budget
  that was priced for generation, and the 120-second llama.cpp wake measured
  on srv1 would exhaust it outright.
* Not `budgets.task_timeout_s` (900 live), which is what `Capacity.of` hands
  `hold` as its queue ceiling (`src/mcgyvr/capacity.py:754`). That bounds a
  wait for a *slot* on a server that exists. A wake is a wait for the server.
* 480.0 because the door's own health budget is 360 s
  (`servelib.HEALTH_POLLS × HEALTH_INTERVAL_S`) and gates 1-5 run before the
  step. A caller budget *below* the door's would abandon a wake while the door
  was still working and leave a card half-up — so the schema refuses a
  `wake_timeout_s` under the door's own figure, by the same shape as
  `Capacity.of`'s width refusal: name the disagreement at the one moment both
  numbers are in hand, rather than quietly correcting it.

The wake budget bounds one wake and not their sum, exactly as
`queue_timeout_s` bounds one hold and not a climb's — and for the same reason
recorded at `src/mcgyvr/capacity.py:754`: charging a climb's waits against one
deadline needs a deadline threaded through the climb, which is not this seam's.

---

## 8. D6 — The rendezvous, in two parts, both of which already exist

Two mcgyvr processes on one host both find srv2 asleep. Exactly one may run
the door; the other must not dispatch until the card is up, and must not
report a failure.

**Part one, on this machine: one more file in the capacity rendezvous
directory.** `/tmp/mcgyvr-capacity-<uid>/<host-stem>.wake`, an exclusive
`flock` held for the length of the wake.

* Same directory, same naming discipline as `_slot_stem`
  (`src/mcgyvr/capacity.py:264`) — a readable prefix plus a digest, "so that
  sanitizing cannot merge two rigs into one".
* Keyed by **host**, not by `base_url` and not by rung, because eviction is
  whole-card. This is the one place in the codebase where a host-keyed lock is
  correct, and it is below the seam.
* It inherits the property a waker most needs and which the module already
  argues for: "The kernel releases a `flock` when its process dies, however it
  dies" (`src/mcgyvr/capacity.py`). A waker killed mid-wake strands nothing.
* Slot files are **not** reused for this. A slot is a permit to dispatch; a
  waker taking every slot of a card would be indistinguishable from a
  saturating batch, and it would collide with the drain in D7, which needs
  those slots to mean what they mean.

**The loser does not fail and does not wake twice.** It blocks on the same
lock, and on acquiring it re-reads the state (D2). The winner will have
brought the card up, so the re-read says `up` and the loser dispatches without
a second door run. Double-checked, and the check is the cheap one.

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

So: **no new rendezvous mechanism.** One new file in an existing directory
with existing semantics, and one existing lease used as it stands.

---

## 9. D7 — The eviction rule

The prompt's case — waking model B on srv2 takes model A down — **does not
arise under this design, and the reason is worth stating rather than
celebrating.**

The card is the compose file, and the compose file holds every unit on that
host. srv2's file holds both the 3B on `:8001` and the 7B on `:8002`, sequenced
largest-first by `depends_on` (`~/.mcgyvr/config/compose.srv2.yml`;
`src/mcgyvr/emit.py:223`). There is no per-model wake, so there is no wake that
displaces a neighbour. And a ladder whose units could not co-reside was never
emittable: `hold_together` (`src/mcgyvr/serving/__init__.py:671`) refuses it
before a file is written — "fit the card one at a time and not together".

That is what the owner's ruling actually buys. Whole-card eviction does not
solve partial eviction; it **deletes the case**.

**The rule for the case that remains — an operator sleeping a card while work
is in flight on it:**

> **An eviction takes all of the card's slots before it takes the card down.
> It never interrupts a dispatch that is already in flight, and it is
> best-effort against processes the flock cannot see.**

Mechanically: `mcgyvr serve sleep` acquires every slot file of every bound on
that card — which is the drain primitive, and the slot files already exclude
every mcgyvr process on the host (#185) — then spawns the door's `down` step,
then releases. The drain is bounded by `budgets.request_timeout_s` (120 s): a
dispatch in flight either finishes or the transport gives up.

Two honesties on top of it:

* `docker compose down` kills containers. A request from a *second machine*,
  or from something that is not mcgyvr, is not drained and is not asked. The
  lease is the guard there and it is a decision procedure, not a mutex on
  requests — a live run displaces a held rig and tears down what it displaced
  (R1). Sleep therefore *can* kill someone else's in-flight request, and the
  lease is what makes that a recorded decision rather than an accident.
* If a later feature wants model **rotation** on one card — evict A to load B
  — this rule is the one it must extend, and it is the whole of the extension:
  drain the card's slots first, then swap. Rotation is out of scope, and it
  should stay out until someone has a measurement showing that two units which
  `hold_together` accepts are worse than one at a time.

---

## 10. D8 — What an operator sees, and why it is not another dead end

`Usage.waited_seconds` and `Concurrency` are computed in `mcgyvr.capacity` and
read by nothing: `cli.py`, `escalate.py` and `result.py` contain zero
references, and only `tests/test_capacity.py` touches them. The module's own
docstring argues they are essential — "A bound nobody can see is
indistinguishable from no bound" — and they are, and nobody sees them. This
design does not add a ninth signal to that pile.

Every wake signal goes somewhere that already has a reader:

1. **`RunResult`** (`src/mcgyvr/result.py:63`) gains one field —
   `woke: list[str]`, or a small record per wake with host, seconds and the
   envelope path. The argument is already written on its neighbour
   `copy_errors` (`:100`): it is there "because the skill tells a caller to
   read this file rather than the scrollback, and 'your copy is short' is
   exactly the kind of fact a caller reading the file would otherwise never
   learn". *This run waited 84 seconds for srv2 to come up* is the same kind
   of fact, for the same reader — the `/mcgyvr` skill, which reads the result
   file and replans from it.
2. **stderr, before the wait and after it.** One line at the start naming the
   card, the budget and the envelope path, so `tail -f` reaches the door's own
   output; one line at the end with the measured seconds. A hung rig prints
   nothing, which is precisely the difference (§11).
3. **The envelope**, written by the door whether mcgyvr asked for it or not:
   `records/evidence/live-<host>/<RUN_ID>/serve-up.json`, carrying per-unit
   `healthy` and `seconds` and `card_after`. This is the surface
   `okf/must-read/reading-results.md` and gate 8 already point at.

Deliberately **not** added: a new `mcgyvr status` command, a card column in
`mcgyvr pool`, a metric. Each would be a fourth reader to keep alive, and the
three above are all consumed today.

---

## 11. How an 80-second block does not look like a hung rig

The measured numbers this must survive: srv1's unit answered 50-80 s after
recreation this session and both srv2 units at ~120 s; the door records 87 s
for vLLM on srv2 and 54-129 s for llama.cpp on srv1 (2026-09-05,
`src/mcgyvr/serving/servelib.py:29-31`). `budgets.request_timeout_s` is 120.0.
So a wake and a hang overlap in duration, and duration cannot tell them apart.
Three things can:

1. **It announces itself at the moment it starts waiting** (D8.2), with the
   budget and the envelope path. A hung rig announces nothing — that is the
   entire experiential difference between the two, and it is free.
2. **It is bounded by a budget that is not the request budget** (D5), so an
   overrun fails as a wake — *srv2 did not answer 480 s after the door started
   it, see `<envelope>/serve-up.json`* — and never as a timeout, *no reply in
   120 s*. Two faults, two sentences. This is `availability.py`'s own
   discipline: its 401 arm and its 404 arm exist as separate arms because "each
   would look like an over-reaction if only the other kind existed".
3. **It leaves evidence that it was a wake**, with the seconds each unit
   actually took. A hang leaves an absence.

And the wait is paid once per card, not once per contract: the losers of the
wake election (D6) are released the moment the winner's door run returns, so a
batch of twenty contracts against a sleeping srv2 waits one wake, not twenty.

---

## 12. The boundary that replaces "emitting is writing a file"

`src/mcgyvr/emit.py:1`: *"Emitting is writing a file. It is never starting a
process… Nothing in this module shells out, and nothing in it may learn to."*

That sentence stays literally true. `mcgyvr.emit` is not touched by this
design; the module that spawns the door is `mcgyvr.wake`, and what it hands the
door is a file emit already wrote and a human already reviewed.

But the *spirit* — this repository does not reach into a rig from the run path
— does change, and pretending otherwise would be the dishonest version of this
document. The replacement boundary, in one sentence:

> **mcgyvr starts a process on a rig only through the door, only from a launch
> spec `emit` already wrote, and only to make available serving capacity the
> config already declares — never to remove it.**

Each clause carries weight, and each is checkable:

* **only through the door** — the seal at `src/mcgyvr/serving/run.py:14-32` is
  unchanged and mechanically enforced by the shims and by
  `tests/test_one_door.py`. This design adds a *caller* of the door, not a
  second door.
* **only from a spec emit already wrote** — a wake cannot invent a unit. No
  file means the card is `down`, not `asleep` (D2). So mcgyvr still never sizes
  and starts in one act, which is emit's actual objection: sizing is a
  judgement a person reviews (`hold_together`, `--ctx-per-slot`, the measured
  `--gpu-memory-utilization`), and wake only ever re-runs the judgement that
  was already reviewed and committed.
* **never to remove it** — D4. The automatic direction is the safe one.

What an operator gives up by adopting this: `mcgyvr run` can now cause a
container to start on srv1 or srv2 without anyone typing `serve up`. What they
get: a ladder that survives a rig reboot, and a card that can be released for
other work without editing the config to delete a rung. The trade is stated
here so that a future reader can reject it knowingly rather than discover it.

---

## 13. Shape of the change (for the plan that follows this one)

New:
* `src/mcgyvr/wake.py` — the card reading (D2), the wake election (D6), the
  door invocation (D3). One module.
* `mcgyvr.serving.cards(config)` — the derivation (D1). One function, beside
  `units_for`.
* `serving.compose_dir` (config), `budgets.wake_timeout_s` (config, default
  480.0, refused below the door's health budget).
* `mcgyvr serve sleep|wake --host H` — a thin front over the door's two steps,
  and the only way a card goes down (D4).

Changed:
* `src/mcgyvr/runner.py:565` and `:597` — the refusal-triggered wake, outside
  the hold (D5).
* `src/mcgyvr/result.py:63` — one field (D8.1).
* `src/mcgyvr/cli.py` `_climb` — carries the waker beside the capacity it
  already builds at `:1354`, for the same reason it builds one capacity and
  not two.

Untouched, and that is the point:
* `config.Tier`, `config.Source`, `pool.Endpoint`, `route.Plan`,
  `route.Machine`, `escalate.Ascent`, `escalate._widths`. Nothing above the
  execution seam learns that a card exists.
* `emit.py`. It still only writes files.
* `serving/run.py`, the gates, the shims, the lease. A new caller, no new door.

---

## 14. Open questions this design does not settle

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
  with sleep.
* **The `dev`-profile decline (D3) is a hard stop for a whole class of users.**
  A developer running `mcgyvr run` against a sleeping live ladder gets a
  decline and an explanation. That is R1 working as ruled; whether it is the
  behaviour the owner wants for *wake* specifically — as opposed to for a
  measurement campaign — is a question for the owner, not for this document.
