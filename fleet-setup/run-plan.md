# Fleet stamping run plan — a-solo, b-small, b-big

Goal: create three fleets on **dev** and stamp them to live via `mcgyvr fleet lock`.
Everything below is already decided by the owner. Work as dev (`profile: dev`);
do not touch the live ladder (both rigs are idle right now, card at 1 MiB).

Drafts live beside this file: `fleet.yaml`, `policy.yaml`. Correct and finalize
them as you measure — the placeholders are marked `<>` and every room/window is
a pin-to-dev-run, not a guess.

## Rig access

- `~/.ssh/config` defines `srv1` and `srv2` (tailnet). Both reachable, idle.
- Hardware: srv1 = GTX 1660 SUPER 6 GiB (sm_75, no tensor cores) + 16 GB RAM;
  srv2 = RTX 3060 12 GiB (sm_86) + 48 GB RAM. Declared in `tools/runs/hosts.json`.
- srv1 is lock-prone under heavy CPU-expert offload; it has been stable since
  2026-09-01. `--n-cpu-moe` up to ~30 is safe; do not push srv1 into swap.

## The fleets (decided)

- **a-solo** — long-context solo: `srv2_35b_256k` (Lidenburg fork, cache 120/256,
  `-c 256k`, width 1) + `srv1_35b_maxctx` (mainline, `--n-cpu-moe 28`, width 1,
  context swept 32768→65536). `next: []`.
- **b-small** — `srv2_3b`+`srv2_7b` (vLLM, gpu-mem-util 0.26/0.72) + `srv1_deepseek`
  (llama.cpp, ncmoe 19). `next: [b-big]`.
- **b-big** — `srv2_80b` (Qwen3-Next-80B-A3B Q3_K_M, ncmoe 36, width 4) +
  `srv1_35b_b` (ncmoe 30, width 2). `next: [b-small]`.

"sleep 3B+7B to fund 80B" is modeled as FREE slots (stop), not asleep — an asleep
unit keeps its room in the fleet model and Σ room would exceed the card. The
vLLM `/sleep` fast-wake is the serving-layer implementation of that stop.

## Prior art to harvest (do not re-measure what exists)

- `records/measurements/flexibility-2026-09-09/README.md` — Q10/Q12 (80B ladder,
  Λ(width)), Q14/Q15 (3B+7B sleep pair: warm decode 3B≈128 / 7B≈68.7, sleep/wake
  ~0.3 s, restarts), Q16 (three-way 3B/7B/80B), Q1 (deepseek/35B wake laws).
- `records/measurements/srv1-ncmoe-sweep-2026-09-13/README.md` — srv1 35B is
  software-maxed ~33 t/s; ncmoe 28 = 33.4 t/s, 5390 MiB.
- `records/measurements/lidenburg-expert-cache-2026-09-13/README.md` — srv2 35B
  cache 120/256 = 49 t/s @1k, 24 t/s @128k, 10,475 MiB peak (HOST binary, llama-cli).
- `records/measurements/measuring-gaps-2026-09-10/` — deepseek-coder-v2-16b wake
  ~79–87 s, decode ~32 t/s, card 5446 MiB.
- `records/measurements/fleet-identity-prefill-2026-09-12/` — prefill for 35B.
- `records/evidence/2026-09-09-live-srv1/`, `2026-09-09-live-srv2/` — exact
  compose argv for deepseek and 80B units (grep the serve-up records).

## The lock contract (what each combination/move must prove)

`src/mcgyvr/fleet/lock.py:write` refuses unless, per combination: a dev run with
`passed: true`, `overhead_mib` (measured CUDA contexts + driver reserve, NOT the
planner's headroom), `restarts` all 0, and per awake unit `warm_decode_tok_s` +
`prefill_tok_s` (+ `baseline_tok_s` for the NVMe check; llama.cpp also
`card_peak_mib`; vLLM also pinned `kv_cache_memory_bytes` and a reported
`attention_backend` equal to the pinned one). Per switch: a passing rig move with
`downtime_s` + `wake_s`. Σ unit room + overhead ≤ `rigs.<rig>.card_mib`.

Evidence JSON shape (see `tests/test_the_fleet_lock_is_written_only_from_passing_dev_runs.py`
fixture `EVIDENCE`, and `tests/test_the_lock_pins_each_combinations_headroom_card_peak_backend_and_prefill.py`):

```json
{
  "rigs": {"srv1": {"card_mib": 6144}, "srv2": {"card_mib": 12288}},
  "combinations": [
    {"rig": "srv2", "slots": [["srv2_35b_256k","awake"]], "passed": true,
     "overhead_mib": 0, "restarts": {"srv2_35b_256k": 0},
     "warm_decode_tok_s": {"srv2_35b_256k": 49.0}, "baseline_tok_s": {},
     "prefill_tok_s": {"srv2_35b_256k": 0}, "card_peak_mib": {"srv2_35b_256k": 0},
     "validated_at": "…", "envelope": "records/evidence/…"}
  ],
  "moves": [
    {"rig": "srv2", "from": [["srv2_3b","awake"],["srv2_7b","awake"]],
     "to": [["srv2_80b","awake"]], "passed": true, "downtime_s": 0, "wake_s": {"srv2_80b": 0}}
  ]
}
```

Lock command: `mcgyvr fleet lock --fleet fleet-setup/fleet.yaml --policy fleet-setup/policy.yaml --evidence <evidence.json> --root .` (writes `records/fleet/`). Tolerances come from `mcgyvr.derived.warm_decode_tolerances()` — do not hand-set them.

## Identity digests (rig-/unt-)

`src/mcgyvr/fleet/ids.py:digest(prefix, fields)` is the primitive (prefix + sha256
of a canonical YAML tree; key order is not identity). The exact field sets are the
resolved launch for `unt-` and host+hardware+system for `rig-` (fleet-identity.md
§1). Read `src/mcgyvr/scan.py` (hardware/system scan, `os_machine_id`) and
`tests/test_a_fleet_id_is_a_prefixed_content_digest.py` for the shape, then compute
each `unit_id`/`rig_id` and fill the placeholders. The `cmb-` ids are derived by
the lock, not written by hand.

## Task order

1. **Build the Lidenburg docker image on srv2.** Fork is at
   `/home/adaramir/llama.cpp-lidenburg` (HEAD `e85e4d9`), has `.devops/cuda.Dockerfile`.
   Add `liburing-dev` (the fork's io_uring disk tier needs it to compile; our
   RAM tier does not exercise it). Tag `llamacpp-lidenburg:e85e4d9`. The expert
   cache is runtime ENV (GGML_EXPERT_CACHE_MAX/GGML_EXPERT_RAM_CACHE_MAX/
   GGML_OP_OFFLOAD_MIN_BATCH), not a build flag.
2. **Sweep srv1 max-context** (fleet a): `llama-server -ngl 99 --n-cpu-moe 28
   -fa on -ctk q8_0 -ctv q8_0` at width 1, `-c 32768` then `65536`, record
   warm decode, prefill, card, and stop at the RAM ceiling. Pin `srv1_35b_maxctx.window`.
3. **Validate srv2 Lidenburg via llama-server** (fleet a): run the image from (1)
   as a server at 256k width 1; record warm decode (expect ~49 @1k, decays with
   ctx), prefill, overhead, card peak, restarts.
4. **Validate the four b-fleet combinations** (3B+7B, deepseek, 80B, 35b_b): run
   each combination, record the lock fields above (harvest warm decode from
   prior art; measure overhead + prefill fresh; pin vLLM kv_cache_memory_bytes).
5. **Validate the four switch moves** (b-small⇄b-big, 2 rigs each): record
   downtime_s + wake_s. Reuse Q16's method (three-way off-door).
6. **Compute digests, finalize fleet.yaml/policy.yaml, assemble evidence.json,
   run `mcgyvr fleet lock`**, iterate on every refusal until it writes
   `records/fleet/` (a-solo.json, b-small.json, b-big.json, rigs/*/cmb-*.json).
7. **Report**: the final fleet.yaml/policy.yaml, the evidence.json, the lock
   output, and a per-combination/per-move table of the pinned numbers with
   evidence paths. Flag anything that could not be pinned.

## Guardrails

- dev profile only; rigs are idle, do not leave anything running.
- srv1: stay ≤ ncmoe 30, watch MemAvailable/swap, never let it page (Q7).
- Every number must come from a run you actually did (or a cited prior-art file),
  never a guess. `make check` and `make docs-check` still pass if you touch `src/`
  (you should not need to).
- Record the plan's outcomes under `records/measurements/fleet-setup-<date>/`.
