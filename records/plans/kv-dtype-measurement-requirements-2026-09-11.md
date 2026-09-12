# The unified measurement campaign — KV dtype + reserve + scratch — 2026-09-11

**One combined rig run, tracked by PR #443.** This plan is the umbrella for the
measurements three RED specifications and one plan still wait on, scoped as one
window on the rigs so nothing is torn down twice:

- **#443 (KV dtype)** — the fp8-vs-auto and q8_0-vs-f16 answers and speeds, arms
  R1–R5 below;
- **#446 (measured scratch)** — one qwen35moe scratch reading taken at `-ub 512`;
- **#439 (card reserve bound)** — the two-boot `gpu_reserve_mib` readings that pin
  the bound width (the GREEN sets the number; this run supplies both readings);
- **#438 (fleet identity)** — the same two-boot readings for `gpu_reserve_mib`,
  and confirmation that `tolerances.json` is complete against plan §12 and the
  B-number tests.

**Status.** Authorised by the owner on 2026-09-11 ("measure + green → origin/main",
one combined run). Rig admission is done first: srv1 reads `gpu_reserve_mib` 399 MiB
after the 2026-09-11 reboot against the declared 401, so the #439 stopgap re-declares
srv1 at 399 and gate 2 is verified open (round `r28-11-09-2026`; "srv1 matches its
declaration on 11 keys"). The real fix — a moving reserve is still the same rig — is
the green session's, not this run's.

**Data points, not verdicts.** The records below stand as measured, each under its
own conditions. Nothing here re-labels, ranks or supersedes them; the arms are the
conditions no record covers.

---

## What is already on record (folded, not re-measured)

The 2026-09-11 fleet-identity campaign (`records/measurements/fleet-identity-2026-09-11/`,
branch `red/fleet-identity-measurements`, folded into #438) already read the card
reserve idle on two boots per rig, in `results-reserve.json`:

| rig | boot (`uptime_since`) | reserve | source |
|---|---|---|---|
| srv1 | 2026-09-01T08:11:08Z | 401 MiB | the value `hosts.json` declared since 2026-09-03 |
| srv1 | 2026-09-11T06:34:36Z | 399 MiB | `results-reserve.json` on `red/fleet-identity-measurements` |
| srv2 | 2026-09-01T05:20:12Z | 377 MiB | ditto |
| srv2 | 2026-09-11T07:25:46Z | 377 MiB | ditto |

Every other declared key read identical on both boots; the card and driver are the
same across boots. This is the "two boots per rig" that plan §12 of
`records/plans/fleet-identity.md` asked for, and the two srv1 readings (399 / 401)
that pin #439's bound width. **No new reserve reading is taken** — the numbers are
folded into #439 and #438 as-is, and the plan §12 open question closes: the reserve
moved 2 MiB across a reboot (srv1) and did not move (srv2), so it does not belong in
the `rig-` identity and gate 2's literal comparison is what #439's GREEN replaces.

The 2026-09-11 campaign also produced `tolerances.json` (vLLM 1%, llama.cpp 1%,
CPU experts 48%) — complete against plan §12 and the B-number tests, confirmed in the
fold step. The 48% needs an owner ruling; it is carried, not re-derived.

---

## The two KV-dtype data points on the same unit

Both are srv2, vLLM, `Qwen/Qwen2.5-Coder-7B-Instruct-AWQ`, `--kv-cache-dtype fp8`.

| condition | 2026-08-28 setup selection | 2026-09-11 M5 |
|---|---|---|
| what was measured | aggregate tok/s over a concurrency ladder | bench-py greedy passes, card, KV tokens, backend, warm decode |
| KV dtypes | `fp8` only | `auto` and `fp8` |
| image | `vllm/vllm-openai:v0.26.0` (tag) | `vllm/vllm-openai@sha256:ffb2d59b…` (digest; tag not recorded) |
| `--gpu-memory-utilization` | 0.9 | 0.72 |
| `--max-model-len` | 1024 | 4096 |
| `--max-num-seqs` | 128 | 8 |
| launch | `docker run --gpus all -p 8095:8000 --ipc=host`, HF cache mounted rw | compose, `network_mode: host`, `HF_HUB_OFFLINE=1`, HF cache ro, `restart: unless-stopped` |
| request | one fixed prompt, 475 tokens, `ignore_eos`, temperature 0, `/v1/completions` | 257 bench-py cells, greedy temperature 0, `max_output_tokens` 768 |
| repeats | one cold start, one ladder | 3 cold starts per dtype; bench-py a/b per dtype |
| attention backend | not recorded | `FLASH_ATTN` (auto), `FLASHINFER` (fp8), from vLLM's own log line |
| result | 67.1 tok/s at n=1 → 1,608.0 at n=128, 0/128 truncated | passes 68/257 (auto, both runs) vs 6/257 (fp8, both runs); 62 flips, 0-flip own nulls, bound 1.47 pp; KV 37,248 → 74,512 tok; decode 68.84 → 67.43 tok/s |

→ 08-28: `records/evidence/2026-08-28-setup-selection/README.md:16-17,25,41,69`,
`drivers/run-srv2.sh:35`, `drivers/vllmsweep28.py:8,10,18-19,35-42`,
`raw/results-srv2.txt:149-157`
→ M5 (on `red/fleet-identity`, PR #438): `records/measurements/fleet-identity-2026-09-11/README.md:117-145`,
`compose.srv2-7b-alone.yml`, `compose.srv2-7b-fp8.yml`, `fp8-quality.json`,
`bench-7b-{auto,fp8}-{a,b}/bench-py/`

Other KV-dtype data points on record: vLLM q15 auto vs fp8, 2.000× pool and
−5.3% n=1 (`okf/config/vllm.md:91-96`,
`records/evidence/2026-09-01-prompt-realism/srv2-fp8-ab-and-lcp-smoke.tsv`);
vLLM q34b 2.000× pool and −3.5% warm decode with the FLASH_ATTN→FLASHINFER swap
(`records/measurements/measuring-gaps-2026-09-10/README.md:42-59`); llama.cpp
q8_0 exactly 17/32 of f16 with no decode cost on deepseek/srv1 (same file,
`:17-40`); llama.cpp q8_0 freeing 36 MiB at `-c 4096` on srv2, "it also changes
numerics, so it would have needed separate scoring"
(`records/measurements/serving-sweep-2026-08-25/README.md:63-66`).

The live srv2 pair declares no `--kv-cache-dtype`
(`records/evidence/2026-09-10-live-srv2/serve-up-restore-live.json`). The bench
serving config declares `fp8` on all four srv2 vLLM entries
(`tools/bench/serving/configs/srv-vllm-n1248-srv2.json:28-29,67-68,106-107,145-146`).

---

## What no record measures

Every bench-py run on `main` served through ollama (`:11434`,
`qwen2.5-coder:{1.5b,3b,7b}`, 2026-08-10…14 — e.g.
`records/measurements/bench-null-gate-7b-a-2026-08-14/bench-py/run.json`) or
llama.cpp (the 2026-09-02 `placement-ling-*` and 2026-09-03 `srv1-correct-*`
runs, neither of which records `-ctk`). M5 is the only bench-py record on vLLM,
and it is one model.

| # | requirement | why no record covers it |
|---|---|---|
| R1 | answers under `fp8` vs `auto` for the other srv2 vLLM units that declare `fp8`: 1.5B, 3B, Qwen3-4B AWQ | no vLLM bench-py run exists for them under either dtype |
| R2 | whether the 7B's M5 answer difference holds at the 08-28 serving shape | util, len, seqs, image and launch all differ between the two data points |
| R3 | speed under `auto` KV at the 08-28 shape, n up to 128, for the four units | 08-28 ran `fp8` only; `auto` halves the pool, so the n=64/128 levels may queue |
| R4 | answers under llama.cpp `-ctk q8_0 -ctv q8_0` vs `f16` | Q1 measured allocation and decode; the 08-25 sweep says scoring was never done |
| R5 | attention backend and image digest on every arm | 08-28 recorded neither; M5 showed the backend changes with the dtype |
| S1 | the qwen35moe scratch+context at `-ub 512` | today's `MEASURED_SCRATCH_MIB` 302.7 MiB is read at `-ub 256`; units run at 512 |

The cause M5 names — uncalibrated KV scales on the FlashInfer path — is marked
UNVERIFIED there. An arm that tests a cause must use a flag the pinned image's
own `--help` lists, recorded as it printed.

---

## Arms

Common to every arm: through the door, on a rig with no live or campaign unit
up; KV dtype **declared on every arm** (`--kv-cache-dtype auto` spelled out, never
implied by omission; `-ctk f16 -ctv f16` likewise); image by digest; the
attention-backend line and the engine's KV line captured verbatim; card figure;
cold starts named. Quality instrument: bench-py greedy (temperature 0) over the
same 257-cell bundle as M5 (`bundle_sha256` recorded), with an a/b run per arm
as its own null, scored as flips vs own-null 95% Wilson upper
(`records/evidence/2026-09-03-srv1-kernel-arms/correctness.json`, the method
`fp8-quality.json` names).

### R1 — fp8 vs auto answers, the other srv2 vLLM units *(12 bench runs)*

| arms | rig | model | flags | instrument | records |
|---|---|---|---|---|---|
| 1–4 | srv2 | `Qwen/Qwen2.5-Coder-1.5B-Instruct-AWQ` | M5's shape: util 0.72, len 4096, seqs 8; `--kv-cache-dtype auto` a/b, `fp8` a/b | bench-py greedy | passes, flips, null flips, bound, backend, KV tokens, card |
| 5–8 | srv2 | `Qwen/Qwen2.5-Coder-3B-Instruct-AWQ` | same | same | same |
| 9–12 | srv2 | `thewimo/Qwen3-4B-AWQ` | same | same | same |

M5's shape is held so each unit's delta is read against the same conditions as
the 7B's.

### R2 — the 7B at the 08-28 shape *(4 bench runs)*

| arms | rig | model | flags | instrument | records |
|---|---|---|---|---|---|
| 1–4 | srv2 | `Qwen/Qwen2.5-Coder-7B-Instruct-AWQ` | util 0.9, len 1024, seqs 128; `auto` a/b, `fp8` a/b | bench-py greedy | as R1, plus replies truncated by the 1024 window |

The 1024 window must hold a bench-py prompt plus 768 output tokens; a cell that
does not fit is recorded as truncated, not dropped. If the 08-28 tag's digest is
recoverable it is used; otherwise the digest used is recorded beside the tag.

### R3 — speed under auto KV at the 08-28 shape *(4 units × 2 dtypes × 2 cold starts)*

| arms | rig | model | flags | instrument | records |
|---|---|---|---|---|---|
| 1–16 | srv2 | 1.5B, 3B, Qwen3-4B, 7B AWQ | util 0.9, len 1024, seqs 128 (1.5B/3B/Qwen3-4B were re-run at 128 on 08-28); `auto` and `fp8`; 2 cold starts each | the `vllmsweep28.py` ladder, n = 1…128, 475 tokens, `ignore_eos` | pool tokens, maxconc, agg tok/s and p50 per n, truncated count, backend, card |

`fp8` is re-run beside `auto` so the pair is one day, one image, one driver.

### R4 — llama.cpp q8_0 answers *(4 bench runs per unit)*

| arms | rig | unit | flags | instrument | records |
|---|---|---|---|---|---|
| 1–4 | srv1 | the live srv1 unit, `Qwen3.6-35B-A3B-UD-IQ3_XXS`, on the image and at the placement the live unit runs (both recorded) | `-ctk f16 -ctv f16` a/b, `-ctk q8_0 -ctv q8_0` a/b; `--n-cpu-moe`, `-np`, `-c`, `-ub` fixed at the live values | bench-py greedy | passes, flips, bound, `llama_kv_cache` line, card |

`--n-cpu-moe` is a semantic key (`okf/config/llama.cpp.md`), so the placement is
held fixed across all four runs and only the cache type moves.

### S1 — qwen35moe scratch+context at `-ub 512` *(one probe, 3 reps)*

| arms | rig | unit | flags | instrument | records |
|---|---|---|---|---|---|
| 1 | srv1 | the live srv1 unit, `Qwen3.6-35B-A3B-UD-IQ3_XXS`, `llamacpp:b10644-L3` | `-ub 512 -b 512`, `--n-cpu-moe`, `-c`, `-np` fixed at the live values, `--verbose` | `buffer-probe.sh` (`records/evidence/2026-09-04-srv1-ncmoe-floor/`) | `sched_reserve: CUDA0 compute buffer size`, and the residue (card − idle − model − kv − rs) so scratch+context = compute + residue |

The value this arm produces is the one the GREEN of #446 folds into
`MEASURED_SCRATCH_MIB["qwen35moe"][512]`. The compute half is already on record
(214.00 MiB at 512, `srv1-buffer-probe.tsv`); this arm re-reads it beside the
residue under one cold start so the pair is one measurement, and the 256 row of
the same probe is the control that must reproduce 302.7 MiB.

### R5 — carried by every arm above

No separate arms. An arm that lacks the backend line or the image digest is
re-run, not reported.

---

## Order and contention

1. **Rig admission first** (done): stopgap + gate 2 verified. Rigs are idle and
   the window is this session's, per the owner's 2026-09-11 ruling.
2. srv2 arms before srv1 (R1–R3 hold srv2; R4 + S1 hold srv1), and R1/R2 before
   R3: the answer measurements decide which dtype rows a speed comparison is about.
3. Both rigs are left as found: no `mcgyvr-*` container up, swap on, nothing declared
   in `hosts.json` moved beyond the stopgap.

Results land in `records/measurements/kv-dtype-2026-09-11/` with a README, the raw
`results-*.json`, the scripts and composes that took them, and the per-arm bench
directories, as the earlier campaigns did.
