# Board findings, 2026-08-31

Three crews (SESSION, BRANCH, CODE) produced ~135 proven claims against this
branch. Ten were contested. A three-seat board ruled on each independently, from
its own primary evidence, on live rigs. This is the tally and what it obliges.

Every claim below carries its proof. A claim without one was dropped.

---

## Tally

| item | seat 1 | seat 2 | seat 3 | ruling |
|---|---|---|---|---|
| D1 `--cpu-offload-gb` inert? | BOTH-SCOPED | BOTH-SCOPED | BOTH-SCOPED | **BOTH-SCOPED, 3-0** |
| D1 *mechanism* | quantisation | architecture | model runner | **architecture/runner, 2-1** |
| D2 vLLM width readback | B | B | B | **B, 3-0** |
| D3 cell count | B | B | B | **B, 3-0** |
| D4 `m_dsv2` kills srv1 | B | B | B | **B, 3-0 — CRITICAL** |
| D5 the "red" test | B | B | B | **B, 3-0** |
| D6 §8 ratios | B | B | B | **B, 3-0** |
| D7 GSP reserve | A | A | NEITHER | **A, 2-1** |
| D8 refused vs never-started | B | B | B | **B, 3-0** |
| D9 row deletion | NEITHER | NEITHER | NEITHER | **NEITHER, 3-0** |
| D10 top-3 defects | (a)(e)(g) | (e)(a)(g) | (g)(e)(a) | **{a,e,g}, 3-0 on the set** |

---

## D4 — CRITICAL. `m_dsv2-lcpp-srv1` takes srv1 down.

Unanimous. The runbook currently instructs the next session to trigger it again.

srv1's own boot table against the two rows' timestamps:

```
-5  Sat 2026-08-29 13:42:29 → Sun 2026-08-30 21:28:31    cell started 21:25:59 → died 152 s in
-3  Mon 2026-08-31 05:01:09 → Mon 2026-08-31 05:06:34    cell started 05:04:04 → died 150 s in
```

Both boots end mid-log-stream: no shutdown sequence, no OOM kill, no Xid, no MCE.
A hard power cut, twice, at n=2, on two different boots at two different commits.

**Mechanism** (seat 2): the entry declares `n_cpu_moe: 99` with `parallel: 8`
against `deepseek-coder-v2-16b.gguf` — **8,493 MiB of CPU-resident experts on a
15,393 MiB host**. The identical entry `m_dsv2-lcpp-srv2` — same weights, same
`n_cpu_moe`, same `parallel` — completes all four levels on srv2's 47,078 MiB.

**A correction to the case as I put it to the board.** I offered "wall clocks
matching to ~10 ms" as evidence. It is not. 327.669 s vs 327.660 s is the fixed
ramp budget, `RAMP_TIMEOUT_BASE_S 90 + 2 x 475/4 = 327.5 s` (`contract.py:1382`),
and 132.43 s is the client's URLError path. Those numbers match because they are
constants, not because the failure is reproducible. **The reproducibility of the
kill is the evidence**; the millisecond agreement is an artifact and should not
be cited again.

ACTION — RESUME.md §3's "All six are infrastructure losses. None indicates
anything about a model or a config" is false and must be struck. Two of the six
(`m_dsv2`, `m_gemma4`) are `n_cpu_moe: 99` cells that killed the host; the three
`refused` rows are stamped *inside* the 21:28:31–22:10:43 dead window and are
collateral. Either re-declare the cell at `parallel 2` (recording that it is then
a different instrument) or record it as a refusal with the RAM arithmetic, the
way `q7-vllm-srv1` already is.

---

## D1 — `--cpu-offload-gb` is architecture-dependent, and §8's evidence does not exist

Three seats, three mechanisms, one verdict: the flag is neither inert nor
universal.

**Seat 3 supplied the controlled experiment** — same model, same host, same
flag, only the runner forced:

```
7B AWQ, no flag                         Model loading took 5.29 GiB   nvidia-smi 10597 MiB
7B AWQ + --cpu-offload-gb 4             Model loading took 5.29 GiB   nvidia-smi 10597 MiB
7B AWQ + flag + VLLM_USE_V2_MODEL_RUNNER=0
    Offloader set to UVAOffloader
    Total CPU offloaded parameters: 3.16
                                        Model loading took 2.04 GiB   nvidia-smi  2277 MiB
```

`set_offloader(create_offloader(...))` exists only at
`vllm/v1/worker/gpu_model_runner.py:937`; the V2 runner has no such call. Path
selection is `VllmConfig.use_v2_model_runner`, architecture-dependent.

**Seat 2 corroborated the mechanism and refuted seat 1's:** its control was
`Qwen2.5-Coder-3B-AWQ` with and without the flag —

```
control:              Model loading took 1.95 GiB   GPU KV cache 38,752 tokens
+ --cpu-offload-gb 2  Model loading took 1.95 GiB   GPU KV cache 38,752 tokens
```

byte-identical, no `Total CPU offloaded parameters:` line — while NemotronH on
the same host and build reached the offloader and died inside it:

```
+ get_offloader().wrap_modules(
  File ".../vllm/model_executor/offloader/uva.py", line 99, in _maybe_offload_to_cpu
    cpu_data = cpu_data.pin_memory()
torch.AcceleratorError: CUDA error: out of memory
```

Seat 1 proposed quantisation as the discriminator (bf16 offloads, AWQ does not),
proven by `nemotron-4b-bf16` going 7.47 → 3.39 GiB at budget 4. That correlation
is real but is a **proxy**: seat 3 got an AWQ model to offload by changing only
the runner. Ruled 2-1 for architecture/runner.

### The finding §8 rests on was never recorded

Seat 2, searching the whole evidence tree for the three launches §8 cites:

```
$ grep -rEho "'cpu_offload_gb':[^,}]*|\"cpu_offload_gb\": *[0-9.]+|cpu-offload-gb[\"', ]+[0-9.]+" records/ | sort | uniq -c | sort -rn
    123 "cpu_offload_gb": 0.0
      1 cpu-offload-gb 0
      1 'cpu_offload_gb': 12.0        <- added 2026-08-31
```

No 4. No 6. `git log --all -S"'cpu_offload_gb': 4"` returns nothing — no commit
ever contained it. The one committed `Model loading took 9.38 GiB` line
(`records/evidence/2026-08-23-phase0-footprint/engine-refusals/srv2-vllm-qwen2.5-coder-14b-awq.docker-logs.txt:35`)
has **no `cpu_offload_gb` in its non-default args at all** — it is the control,
not an offload arm.

ACTION — §8 is entitled to assert only that one 2026-08-23 control launch of the
14B AWQ loaded 9.38 GiB and OOMed. Strike "three launches at 0/4/6 GiB" from
RESUME.md §8, `vllm.py:1237-1251`, and `srv-vllm-n1248-srv2.json`'s `_refused`.
Keep `_CPU_OFFLOAD_IS_NOT_A_DISCOUNT = True` — the gate's behaviour is right for
the Qwen2/AWQ cells — but record compressed-tensors/NemotronH as **unmeasured**
rather than covered.

### The proposition I asserted, ruled NEITHER

I told the user "RAM went to zero, which only happens if weights actually moved."
That is invalid. Seat 2 measured the confound directly: under the offload run
srv1 reads `buff/cache 14476` alongside `shared 14308`, and `available 0` cannot
separate page cache from a host mapping. Worse, seat 1 found the offload-12 log
carries **no `Model loading took` line at all** — the engine OOMed before weight
load finished, so that run measured zero offloaded bytes and refutes nothing.

The valid proof was three lines away in the same log: the `uva.py:99
_maybe_offload_to_cpu → pin_memory()` frame, which no amount of page cache can
produce. Cite the traceback, never the RAM figure.

### The measurement that settles it — and the two that would have misled

Seat 3, returning with a controlled series on srv1 (page cache dropped before
each run, same model, same engine, only the code path changed). Logs and 0.5 s
sample streams are committed at
`records/evidence/2026-08-31-inventory/board3-srv1-*.{log,samples}`.

| run | on-card weights | KV cache | Shmem | RssShmem |
|---|---|---|---|---|
| no offload (V2) | **1.95 GiB** | 3.01 GiB / 87,584 tok | 14,660 kB | 14,340 kB |
| `--cpu-offload-gb 1` (V2) | **1.95 GiB** | 3.01 GiB / 87,584 tok | 14,688 kB | 14,340 kB |
| `--cpu-offload-gb 1` (V1) | **0.93 GiB** | 4.02 GiB / 117,152 tok | **1,573,244 kB** | **1,572,868 kB** |
| `--cpu-offload-gb 2` (V1) | **0.59 GiB** | 4.36 GiB / 127,056 tok | **2,091,416 kB** | **2,091,012 kB** |

```
Offloader set to UVAOffloader
Total CPU offloaded parameters: 1.01   ->  Model loading took 0.93 GiB
Total CPU offloaded parameters: 1.34   ->  Model loading took 0.59 GiB
```

**The page-cache confound, broken by arithmetic.** Linux counts Shmem inside
Cached, so subtract it:

```
                    Cached      - Shmem      = real file cache
no offload        4,005,416     -    14,660  = 3,990,756 kB
offload 1 (V2)    3,983,072     -    14,688  = 3,968,384 kB
offload 1 (V1)    5,537,972     - 1,573,248  = 3,964,724 kB
offload 2 (V1)    6,056,964     - 2,091,420  = 3,965,544 kB
```

File caching is constant to within **0.7%** across all four runs — it must be,
they read the same checkpoint. Every kilobyte of the `MemAvailable` difference
between the V1 and V2 runs is shared memory, and it tracks the offload.

**And the direct falsifier of the RAM argument** — a run with the offloader
provably absent still drains available RAM:

```
Qwen2.5-Coder-3B-AWQ, NO --cpu-offload-gb, caches dropped first
  baseline  MemAvailable 14,977,916 kB
  loaded    MemAvailable 12,221,328 kB     -> fell 2.63 GiB, zero bytes offloaded
```

**Where `shared` comes from.** Not `/dev/shm` — `--shm-size` is irrelevant.
`uva.py:99` calls `pin_memory()` then `get_accelerator_view_from_cpu_tensor()`;
the driver backs pinned/UVA host allocations with a shared-memory object, which
the kernel accounts as `Shmem`. It shows in `free`'s **shared** column and in
`RssShmem`, and never in `RssAnon`.

**Two measurements that would have misled.** `nvidia-smi memory.used` was flat
at 5294 / 5294 / 5324 / 5330 MiB across all four runs — `gpu_memory_utilization`
backfills freed weight space with KV cache, so **a real offload is invisible in
`memory.used`**. The quantities that discriminate are vLLM's own `Model loading
took` (a measured GPU delta), the KV token count, and host `Shmem`.

**Scope correction this forces.** srv1 selects the V2 runner for Qwen2 exactly as
srv2 does. So the inert path is not a property of srv1, srv2, sm75, sm86,
`--enforce-eager`, or AWQ — it is model-runner selection alone. The NemotronH
runs took V1 because NemotronH is not a default-V2 architecture; both of them
offloaded successfully, and both then failed because srv1 is too small for a
16.6 GiB model either way.

---

## D2 — the readback exists; the plan doc cites the line that refutes it

`docs/serving-vllm-n32-plan-2026-08-31.md:13` claims vLLM's batch width is
uncatchable, citing `backends/vllm.py` lines 32, 822 and 1669. Line 1669:

```
**E5, revised 2026-08-19.** The first version concluded there was no observed
source because no HTTP endpoint carries ``max_num_seqs`` — which is true, and
was the wrong place to stop looking. The harness has ssh, and the flag is in
the running process's own argv on the pip rig and in the container's
``Config.Cmd`` on the docker rig.
```

It is not theoretical. Every vLLM row in the committed run records the readback:

```
"declared_slots": {"value": 8, "provenance": "observed",
                   "source": "--max-num-seqs in the server's process arguments",
                   "dispatched": 8, "refused": null}
```

and `declared_slots()` refuses on mismatch with `provenance: "contradicted"`.

**The real gap is a different one.** `grep -n "levels" tools/bench/serving/backends/vllm.py`
returns nothing: unlike `llamacpp.py:674/707`, no code asserts
`max_num_seqs >= max(concurrency.levels)`. `launched_width()` catches "the flag
did not take"; nothing catches `max_num_seqs 8` correctly applied while the ramp
offers 32 — the queueing plateau the n=16/32 run exists to avoid.

ACTION — rewrite §0. Replace both proposed guards with one config-time assertion,
`serve.max_num_seqs >= max(concurrency.levels)`, for every vLLM entry.

---

## D3 — 29 declared, 24 measured, 5 outstanding

"18 measured, 6 outstanding" is wrong and internally inconsistent: 18+6 = 24
against 29 declared. Counted by all three seats independently, scoring with
`run.py`'s own `barren_levels`:

```
                     HEAD a9cf4ee6      working tree
  lcpp-srv1              5                  5
  lcpp-srv2             11                 12   (m_kat appended)
  vllm-srv1              3                  3
  vllm-srv2              4                  4
  TOTAL                 23 / 6 out         24 / 5 out     (declared 29)
```

18 is reproducible as 23 less srv1's five llama.cpp cells. It corresponds to no
state of this tree at any commit.

ACTION — RESUME.md:3 should read: **29 cells declared; 24 measured with a rate at
every n; 5 outstanding — four on srv1 (`m_dsv2`, `m_gemma4`, `m_q36iq2`,
`m_oss20`), one on srv2 (`m_next`), all on the llama.cpp half.**

---

## D5 — the tree is green because a row was deleted

```
$ uv run --no-sync python -m pytest tests/test_card_memory_accounting.py -q
.........F..                                                             [100%]
FAILED tests/test_card_memory_accounting.py::test_every_declared_cell_is_present_in_its_journal
```

`test_the_recorded_run_measured_the_grid_it_was_asked_for` **passes**. In a clean
worktree at HEAD it fails:

```
E  AssertionError: lcpp-srv1.jsonl:m_dsv2-lcpp-srv1: n=2 carries no `tokens_per_s`
```

It went green because §4's procedure deleted the row it judged — not because
anything was measured. That is precisely the failure mode the new assertion
exists to catch, and the new assertion is uncommitted.

ACTION — §7 must say **one** assertion is red, naming **five** cells. Commit
`test_every_declared_cell_is_present_in_its_journal` before anyone runs
`--resume`, or the tree is green with five cells outstanding.

---

## D6 — all three §8 ratios are wrong

Recomputed from the journals as `tokens_per_s(n=8) / tokens_per_s(n=1)`, cells
classified by whether the config sets `n_cpu_moe`:

**On card, 11 cells** — §8 says 2.22–2.74x:
```
srv1  d4b 2.215  docr7b 2.227  m_ling 2.273  d3b 2.303  d7b 2.394
srv2  docr7b 2.586  d4b 2.716  d3b 2.726  d8b 2.740  d14b 2.743  d7b 3.667  <-- omitted
```

**Offloaded, 6 cells, all srv2** — §8 says 1.41–1.47x, which is the three middle
cells; it omits both extremes:
```
m_qc30 1.112  m_q36iq3 1.204  m_dsv2 1.410  m_kat 1.457  m_oss20 1.465  m_qc30q4 1.741
```

**vLLM** — §8's figure is srv2-only and the line carries no host:
```
srv2  q15 7.599  q3 7.659  q34b 7.365  q7 7.670        -> 7.37-7.67
srv1  q15 2.416  q3 3.107  q34b 3.064                  -> 2.42-3.11
srv1 anchored at n=2: 3.884 / 3.905 / 3.764            -> 3.76-3.91  (not "3.88x")
```

ACTION — the three lines should read: **"llama.cpp 2.22–3.67x on card across 11
cells (`d7b-lcpp-srv2` at 3.67x is the outlier; the other ten span
2.22–2.74x)"**; **"1.11–1.74x offloaded across all six `n_cpu_moe: 99` cells"**;
**"vLLM 7.37–7.67x n=1→n=8 on srv2 only, flat across 1.5B–7B; srv1 is 2.42–3.11x
from n=1 and 3.76–3.91x anchored at n=2."**

The "do not re-derive" banner is what let three wrong ranges stand. Strike the
banner, not the numbers.

---

## D7 — the reserve is boot-stable, not load-dependent

Ruled A, 2-1. Measured across a 10 GiB occupancy swing:

```
srv1  used    17 MiB / reserved 401     srv2  used     1 MiB / reserved 377
srv1  used  1188 MiB / reserved 401     srv2  used  5645 MiB / reserved 377
srv1  used  3958 MiB / reserved 401     srv2  used 10597 MiB / reserved 377
srv1  used  5326 MiB / reserved 401     srv2  used  9891 MiB / reserved 377
```

`reserved` does not move with card load. Seat 3 then sampled it 475 times at
0.5 s across four engine configurations while the card swept 17 → 5,330 MiB:

```
srv1-nooff     165 samples -> 165 x 401 MiB
srv1-off1      165 samples -> 165 x 401 MiB
srv1-off1v1    153 samples -> 153 x 401 MiB
srv1-off2v1    157 samples -> 157 x 401 MiB
```

Zero readings of 399. Across boots it does move: srv1 read 401 (08-30), 399
(boot of 05:50), 401 (boot of 06:46) — same driver. The single 399 in the repo
is `srv1-scan.txt:43`, stamped `06:27:24Z` with `up 37 min`, i.e. boot −2; the
current boot began 06:46:21.

**Two corrections to my own §1 edit.** Crew SESSION claimed the reserve returned
to 401 within one boot; `uptime -s` shows a reboot between those readings, so
that is false. And my sentence "the 17 MiB was a desktop session these headless
boots do not have" is contradicted by srv1 reading 17 MiB right now, headless,
with `--query-compute-apps` empty. Delete it.

ACTION — keep `CARD` pinned at 401/380 (re-pinning per boot makes the constant a
tautology). Reword §1 to "constant within a boot, ±3 MiB across boots, unaffected
by card load", and note srv2 currently reads 377.

---

## D8 — refused, not never-started, and `--retry-failed` is mandatory

```
"outcome": "refused",
"refusal": {"reasons": ["backend_would_not_yield_card"], "stage": "exclusion",
  "prose": "['ollama', 'vllm'] would not give up the card before m_q36iq2-lcpp-srv1:
            ollama=None MiB, vllm=None MiB. ..."}
```

`ollama=None MiB` means the probe returned nothing — the host was already off.
Both rows are stamped 21:49:17 and 21:52:02, inside srv1's dead window. The
prose blames a co-resident engine for holding a card on a machine with no power.

Operational consequence, `run.py:124-159`: `completed()` treats a refused row as
**done**. **Plain `--resume` skips both cells forever and reports the run
finished.** Only `--resume --retry-failed` reaches them.

ACTION — fix §3's table, and make the refusal prose distinguish "probe returned
nothing" from "engine held the card".

---

## D9 — nothing was destroyed, and the deletion was unnecessary

Unanimous NEITHER. The docket's premise was wrong, and so was my alarm:

```
$ git show HEAD:records/evidence/serving-2026-08-30/lcpp-srv1.jsonl | diff - lcpp-srv1.jsonl.bak
  (no output)   -> the .bak is byte-identical to HEAD
HEAD row 11: m_gemma4-lcpp-srv1 | ok | [(1, 24.7), (2, 30.7), (4, 23.0), (8, None)]
```

The curve is in git. The `.bak` is redundant and should not be committed.

On necessity: of the three deleted rows, only `m_gemma4`'s `ok`-with-barren-n8
row would have blocked a re-measure. `m_dsv2`'s superseding `ramp_failed` row
already wins under last-write-wins and is re-run by `--retry-failed` — deleting
its older row bought nothing and cost the record of the first outage.

ACTION — restore all three rows and fix the cause instead:

```python
# run.py:157
if retry_failed:
    rows = {
        k: v
        for k, v in rows.items()
        if v.get("outcome") == "ok" and not barren_levels(v.get("concurrency") or {})
    }
```

Then delete §4's drop procedure. It is what turned the tree green in D5.

---

## D10 — the three defects to fix before any resume

All seven confirmed at their cited lines. All three seats put the same three
first, in different orders; the set is unanimous.

**(e) `contract.py:1415` — a level with no rate is not barren.**
```
"ok": len(good),
"tokens_per_s": (round(tokens / wall, 1) if wall and counted else None),
```
`good` counts replies; `counted` counts replies carrying `usage`. A level where
every reply arrived without a `usage` block has `ok > 0` and `tokens_per_s: None`.
`barren_levels` tests only `level.get("ok")`, so the row stays `ok` and
`--retry-failed` skips a cell with a hole in its curve. Same class as the bug
`d75d90fb` fixed, left open on the other branch. Judge on `counted`.

**(a) `run.py:580` — an empty `levels` list silently becomes nine rungs.**
```
tuple(concurrency.get("levels") or contract.RAMP_LEVELS)
# RAMP_LEVELS = (1, 2, 3, 4, 6, 8, 12, 16, 24)
```
`[]` is falsy and indistinguishable from absent. llama.cpp is protected by
accident (`width < max(levels)` refuses at 24 > 8); **vLLM is not**, so a typo
ramps to n=24 against 8 scheduler slots and records the exact false plateau the
run exists to avoid — stamped `ok`. Directly in the path of the n=16/32 plan.
Use `is None`.

**(g) `tests/test_run_outcome_vocabulary.py:138` — the test asserts the opposite
of its docstring.**
```python
def test_an_empty_ramp_is_not_silently_whole() -> None:
    """A ramp that emitted no levels at all states no rate either. It must not
    pass for want of anything to iterate."""
    assert run_module.barren_levels({}) == []
    assert run_module.barren_levels({"levels": []}) == []
```
`== []` means no barren levels, so the row keeps `ok`. The test named for the
guard pins the hole open.

Then, in rough consensus order: **(f)** `run.py:636` — the co-residency re-read
is gated on `outcome == "ok"` and so is suppressed by a barren downgrade,
exactly when a neighbour most likely walked off (live in Phase C of the n=32
plan); **(d)** `run.py:982` reads `declared["value"]` while
`llamacpp.declared_slots` returns `slots`, so no llama.cpp cell has ever printed
a declared width to the console; **(c)** `serve.levels` and `concurrency.levels`
are different fields kept in sync only by a test parametrised over the two
committed configs; **(b)** `llamacpp.py:707` compares the readback to
`max(levels)` under a message that says `--parallel {width}`.
