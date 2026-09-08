# Handoff — sleep/wake round, 2026-09-08

Everything below is on **`red/sleep-wake`** (PR #430), pushed. Ten commits past
`main`; nothing is on `main` yet. `records/plans/sleep-wake.md` is the design and
is current — it has been edited for both of today's rulings.

## Where the branch stands

```
ce9e9e69 RED: two models on one URL are alternatives, and each is its own launch spec
1bd6b8bd GREEN: a source is emitted at the window it declares
3cf8ae21 RED: a fleet of two windows is emitted at both
0509110f Live: srv1's top rung now reads its weights unmapped
a9c5109d Fix: nothing under records/ is executable
e141baf7 GREEN: the rig decides how the weights are read
5363e602 RED: a blob that overflows its host's RAM is emitted unmapped, or refused
c22cb584 Owner ruling: no rig is banned for the engine that serves it (N10)
019d47b0 Owner ruling: nothing loads onto a rig whose RAM cannot hold it
a708acb3 Measure the wake: N7 is settled, and N10 is reopened
```

**Test state: `uv run --no-sync pytest -q` gives exactly 19 failures**, all in the
four intentional RED sleep/wake files (`test_a_sleeping_rung_is_woken…`,
`test_sleeping_a_card_takes_every_rung…`, `test_a_wake_is_asked_for_in_the_config…`,
`test_a_dev_round_may_operate…`) plus the three open ones named below. They fail
because `src/mcgyvr/wake.py` does not exist. Anything else failing is new.
ruff, ruff format, mypy and `python -m mcgyvr.docgen --check` are clean.

## What was decided (owner rulings, do not re-litigate)

1. **N7 settled by measurement.** `budgets.wake_timeout_s = 480` stands: the
   fleet's worst measured wake is 203 s. `records/measurements/wake-2026-09-08/`.
2. **N10 ruled: there is no engine scope.** No rig is banned for the engine that
   serves it. The vLLM-only predicate is gone from the design and the tests.
3. **Nothing loads onto a rig whose RAM cannot hold it.** The rule and its
   evidence are in `okf/must-read/touching-rigs.md`; `serving.fit` enforces it.

## The three things still open, most decided first

### 1. Re-price the mapping threshold — owner said nothing yet, evidence is in

`fit` sends a model unmapped when `blob + 2 GiB > MemAvailable`. srv1 crossed
that by **0.11 GiB** (12.31 GiB blob against the 14.2 GiB its 2026-09-05 scan
records) and the A/B says it bought nothing: ±0.3% throughput against 5% of rig
drift, no wake difference, and 8.4 GiB of reclaimable memory given up
(`records/measurements/load-mode-2026-09-08/`).

**Recommendation on the table:** the *mode* decision compares the bare blob
(`blob > available` → unmapped); the *refusal* keeps the 2 GiB margin, because
that one gates a launch. Both measurements this fleet owns agree — 18.56 GB into
16 GB thrashed, 12.31 GiB into 14.2 GiB did not. Effect: srv1 goes back to
mapped, and KAT-Coder becomes unmapped rather than refused, since its 11.8 GiB
of experts do fit.

**srv1 is serving unmapped right now**, so this is live, not hypothetical.

### 2. GREEN the alternatives spec — RED is written and waiting

`tests/test_two_models_on_one_url_are_alternatives.py`, three failing. It is the
precondition for the owner's fleet layout (srv1 DeepSeek↔Qwen, srv2 vLLM
pair↔80B), which is *sleep funding a wake* — §17 of the design records it as
unbuildable while a host holds one launch spec.

Three changes, all named by the tests:

* `emit._planned` groups by host; alternatives (units sharing a host **and** a
  port) need one file each, `compose.<host>.<model>.yml`, one service per file.
  A host with no alternatives keeps `compose.<host>.yml` byte-identical.
* `serving.hold_together` sums every unit on a host against the card. It must
  sum co-residents only — alternatives never share it.
* `emit.check_all` and `cli._report_drift` must cover every file a host now has;
  `_report_drift` still hardcodes `compose.{host}.yml`.

Left to the owner deliberately: a host mixing alternatives and co-residents. The
test asks for a refusal that names it rather than a guess.

### 3. Sum host RAM across units — decided in principle, not written

`hold_together` sums VRAM **per card**. Nothing sums RAM, so two spilling units
on one host each pass against the same `MemAvailable`. Owner's ruling in
conversation: **RAM is summed per host** (every unit draws on one pool, whichever
card it uses), VRAM stays per card. Two wrinkles for whoever writes it:

* what a unit charges depends on the arm it took — the blob under mmap, the
  spilled experts under `--load-mode none` — so the sum comes after the modes are
  picked, with one host headroom applied once;
* `MemAvailable` itself depends on the mode: srv1 reads 13.4 GiB mapped and
  5.2 GiB unmapped. A scan taken while a unit serves unmapped would refuse the
  model that is running. `emit` reads a *recorded* scan
  (`~/.local/state/mcgyvr/scans/`, srv1's is from 2026-09-05), which is the only
  reason this has not bitten. The bench already evaluates after teardown
  (`tools/bench/serving/backends/llamacpp.py:607`); the product does not.

## Rig gotchas this session paid for

* **The door refuses to overwrite an envelope** (gate 5, write-once). A second
  `serve up`/`down` in one campaign directory is REFUSED until
  `records/evidence/<date>-live-<host>/serve-{up,down}.json` is moved aside
  deliberately. `--suffix` distinguishes the RUN_ID, not the artifact.
* **Check the door's exit status, and never filter its output.** A script that
  grepped for `up after` hid four consecutive refusals and produced an A/B that
  measured one process which never restarted. Assert the container's
  `StartedAt` moved, and read the running argv back off the container.
* **Do not edit `src/` while a door run or the full suite is in flight.** Gate 1
  hashes the product tree; editing mid-run opened round `r10-08-09-2026` and
  flaked `test_a_live_row_names_what_answered_it_and_under_which_round`.
* **The rig drifts ~5% between restarts.** Three samples per arm, and repeat the
  arms, or the drift is larger than what is being measured.

## Live state, as left

* srv1: Qwen3.6-35B-A3B, 2 slots × 8192, **`--load-mode none`**, 10 GiB
  anonymous, 5.2 GiB available. Serving.
* srv2: the 3B + 7B vLLM pair, `--max-model-len 4096`. Untouched today.
* `mcgyvr emit --check --out ~/.mcgyvr/config` — **no flag** — is clean on both
  hosts. It could not be run fleet-wide before `1bd6b8bd`.

## Research that never finished

The session hit the web-search limit. Outstanding, in the owner's own order:
HuggingFace survey of max-total/min-active code MoEs against 45 GiB and 15 GiB
budgets; vLLM sleep-mode docs read against our v0.26.0 (level 1 parks weights in
host RAM, which collides with the RAM rule; level 2 discards them and is the one
that composes with an 80B on srv2); and `napmany/llmsnap`'s sleep/wake config
shape — a llama-swap fork with `/models/sleep/:model_id`, five months stale
against its parent, worth reading and not adopting.

Both models the owner asked for are already on srv1 and need no download:
`deepseek-coder-v2-16b.gguf` (8.29 GiB) and
`gemma-4-26B-A4B-it-UD-IQ3_XXS.gguf` (10.63 GiB).
