# Sleep does fund a wake on this fleet — measured, with two conditions

Taken 2026-09-09. §7.5 of `records/plans/sleep-wake.md` records that **"sleep
never funds a wake on this fleet"**, and §17 asks whether the symmetry in the
algorithm is worth its numbers while nothing can reach it. Both were true of the
fleet as configured. Neither is true of the fleet as it *can* be configured.

**The owner's case works: srv2's 3B and 7B both `/is_sleeping: true`, handing
their card to a llama.cpp 80B that serves on it, in 100 s.** The two conditions
are that the vLLM units are launched `--enable-sleep-mode`, and that the 80B is
emitted one expert block lighter than `emit` currently writes it.

## Sleep and wake are sub-second

vLLM 0.26.0, `--enable-sleep-mode` plus `VLLM_SERVER_DEV_MODE=1`. Without those
flags `/sleep`, `/wake_up` and `/is_sleeping` are 404 — which is how the live
ladder runs today, so none of this is reachable on it.

| | sleep | wake | VRAM used after | MemAvailable after |
|---|---|---|---|---|
| baseline, both serving | — | — | 10,641 MiB | 39.18 GiB |
| L1 sleep 3B | 1.39 s | 0.41 s | 7,065 | 36.06 |
| L1 sleep 7B | 3.99 s | 0.79 s | 4,065 | 25.74 |
| L2 sleep 3B | 0.25 s | 0.24 s | 7,065 | 25.72 |
| L2 sleep 7B | 0.30 s | 0.31 s | 4,065 | 25.73 |
| **L2, both asleep** | 0.24 / 0.30 s | 0.24 / 0.30 s | **503 MiB** | 25.72 |

Against a **168 s** container restart of the same pair (measured three times
today), sleep/wake is roughly **500× faster**. It is a different mechanism, not a
faster version of the same one: the process, its CUDA context and its Python
runtime never die.

**Level 2 is strictly better than level 1 here.** It is faster (0.25 s against
1.39 s), releases the same VRAM, and costs no host RAM.

## Level 1 never gives the host RAM back

`MemAvailable` went 39.18 → 36.06 GiB when the 3B slept at level 1 — the weights
parked in host RAM, as documented. **It stayed at 36.06 after the wake**, and
after one level-1 cycle on each unit the host was down 13.46 GiB with both units
awake and serving. The buffer is retained for the process's lifetime.

This is the collision the handoff predicted, and it is worse than "level 1 holds
RAM while asleep": it holds RAM *from the first sleep onward*, awake or not. On
srv1, where `records/measurements/ram-headroom-2026-09-09/` shows the refusal
gate guards a cliff at −1 GiB against the experts, a level-1 sleeper would be
unbudgeted RAM that nothing in `fit` or `hold_together` accounts for.

**Use level 2. Level 1 should be refused rather than offered.**

## The 551 MiB that decides it

With both units asleep the card reads **503 MiB used, 11,409 MiB free**. The
503 is two live CUDA contexts (234 + 228 MiB) — a sleeping vLLM process gives
back its weights and its KV pool, not its context.

`emit` writes the 80B at `--n-cpu-moe 35`, which wants **11,960 MiB**. That is
551 MiB more than the sleepers leave.

| attempt | asks | card free | result |
|---|---|---|---|
| `--n-cpu-moe 35`, as `emit` writes it | 11,960 MiB | 11,409 | **fails at 28 s**, `failed to create_context`, then crash-loops |
| `--n-cpu-moe 36`, one block lighter | ~11,228 MiB | 11,409 | **serves after 100 s** |

One expert block is 0.715 GiB (34.31 GiB of experts over 48 layers), so moving
one more block to RAM buys 732 MiB of card — more than the 551 needed.

**So the fleet can do this, and `emit` cannot express it.** The 80B's placement
is computed against a card assumed idle. Funding it from sleepers needs the
placement computed against *the card a sleeping co-resident leaves*, which is a
different number and one only the runtime knows.

## Waking into a full card fails well

With the 80B serving and 248 MiB free, waking the 3B:

```
http 500 in 395 ms
{"error":{"message":"Call to wake_up method failed: CUDA Error: out of memory ...",
          "type":"InternalServerError"}}
```

The unit stayed asleep, the 80B kept serving, the card never moved, and all
three containers stayed up. **395 ms to a named refusal** — the one loud, fast,
safe failure found all day, and the opposite of the silent −68% the RAM refusal
gate guards.

It is also the argument for the owner's ruling that **a wake must read the
target's live GPU and RAM state**: the engine will refuse correctly, but only
after the scheduler has already decided to wake something it cannot.

## A sleeping unit passes a health check and then hangs

The trap, and the reason this cannot be bolted on:

| probe | sleeping unit |
|---|---|
| `GET /v1/models` | **200** |
| `GET /is_sleeping` | `{"is_sleeping":true}` |
| `POST /v1/chat/completions` | **hangs — no response in 60 s** |

`serve-up.py` polls `/v1/models`, so **the door would call a sleeping rig
healthy**, and gate 7 would call the run green. A contract dispatched to it does
not fail — it hangs until `budgets.request_timeout_s`.

Anything that treats a unit as serving must consult `/is_sleeping`, not
`/v1/models`. That is a new liveness question the ladder has never had to ask,
because until now a unit that was up was serving.

## What this changes

* **§7.5 is false as a statement about the fleet's capability.** It is true only
  of the fleet as launched: no `--enable-sleep-mode`, and an 80B sized for an
  idle card. Both are config, not physics.
* **§17's question answers itself.** The symmetry is worth its numbers, because
  this is the case it was written for and the case now measured to work.
* **Three things `fit` and `emit` do not model**, each independently enough to
  break the layout: the loading mode's VRAM cost
  (`records/measurements/ram-headroom-2026-09-09/`); the residual VRAM a sleeping
  co-resident holds; and a placement computed against anything other than an idle
  card.
* **`wake_timeout_s` is the wrong shape for this.** 480 s is sized for container
  restarts. A vLLM wake is 0.24 s and an out-of-memory refusal is 0.4 s; an 80B
  behind them is 100 s. One budget cannot mean all three.

## The files

| | |
|---|---|
| `vllm_sleep.py` | the per-unit matrix: both levels, each unit alone, then both |
| `vllm-sleep-results.json` | every step's VRAM, MemAvailable, `is_sleeping` and reachability |
| `compose.srv2.sleepmode.yml` | the live pair plus `--enable-sleep-mode` and `VLLM_SERVER_DEV_MODE=1` |
| `compose.srv2-80b-ncmoe36.yml` | the 80B one expert block lighter — the one that fits |

The live ladder was restored to its declared compose afterwards; `/is_sleeping`
is 404 on it again, and `emit --check` is clean on both hosts.
