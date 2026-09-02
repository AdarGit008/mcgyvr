# reading-results

Reading a journal, a curve, or a ratio.

## Keys

**`run.py` emits `tokens_per_s`. `sweep.py` calls the same quantity
`agg_tok_s`.** Wrong key → `None` at every level → a healthy run reads as dead.
That cost a false alarm. `per_stream = tokens_per_s / n` is exact.
→ `contract.py:1415`, `sweep.py:200`

**`outcome: ok` is not sufficient on rows written before `d75d90fb`.** Judge the
levels: a cell can be `ok` with a barren level. Re-score with
`run.barren_levels()`, don't read the stored string.

**Anchor srv1's vLLM ladder at n=2, not n=1.** Wall clock is flat n=2→n=8 while
n=1 runs 2.4–3.2x faster per request. A real regime change, not noise.


## Measurements that mislead

**`prefill=` is not a measurement. It is `agg` times `ptok/otok`.** Both drivers
divide by the *same* `wall`: `agg = gen/wall` and `prefill = pin/wall`, so
`prefill/agg ≡ ptok/otok` identically — verified to three decimals on every row
of `2026-09-01-bandwidth-and-ncmoe-floor/srv1-nomma-dp4a-ab.tsv`. A row where
prefill "tracks" decode is saying nothing; a row where it does not would be an
arithmetic error. **Nothing in this repo has ever measured prefill separately.**
Use `llama-bench -p N` for that, and do not mix its numbers into a cross-engine
claim — it carries no workload digest.
→ `tools/runs/drivers/lcp_sweep.py:179-180`, `tools/runs/drivers/vllm_sweep.py`

**The prompt draw desyncs whenever the level list changes, and the error reaches
6.2%.** Lengths come from a per-process counter, so a cell that runs levels
`1,2,4,8` consumes two more UIDs than one that runs `1,4,8`, and every draw after
the n=2 rung differs. Same rig, same image, same hour, nominally the same stock
cells: d3b n=4 read 74.0 and 69.4 (**6.2%**), mling n=8 read 87.1 and 92.4
(**6.1%**), while every n=1 row agreed to ≤0.6% because n=1 always consumes UID 1.
**Two rows are comparable only if their `ptok` and `otok` match.** Check that
before quoting a ratio; equal `agg` across unequal draws is coincidence.
→ `2026-09-01-prompt-realism/srv1-lcpp-ladder.tsv` vs
  `2026-09-01-bandwidth-and-ncmoe-floor/srv1-nomma-dp4a-ab.tsv`

**One cell per process invocation is load-bearing and undocumented.** The UID
counter resets when the driver starts, so passing two cells in one argv silently
breaks position matching between arms. Every comparable file in the tree was
produced one cell at a time, by habit rather than by a guard.

**Every `agg=` measured before 2026-09-01 overstates real traffic by ~2.4x at
n=8.** Those sweeps sent one fixed 11-token prompt and a flat 475-token reply
(1:43 in:out); real traffic is 3:1. Measured on both rigs, new/old at n=8:
srv1 q15 0.43, q3 0.41; srv2 q15 0.41, q3 0.48, q34b 0.47 — every cell in
0.41–0.48 across two rigs, two KV dtypes, three model sizes and a 2x card
difference. The two workloads **agree at n=1** and diverge as concurrency rises,
because real prompts put prefill in contention with decode and an 11-token
prompt has none to contend. Do not compare a pre-2026-09-01 number with a
post one at any rung above 1.
→ `records/evidence/2026-09-01-prompt-realism/{srv1,srv2}-ladder-n32.tsv`

**`nvidia-smi memory.used` cannot see a vLLM offload.** It read
5294/5294/5324/5330 MiB across offload and no-offload runs, because
`gpu_memory_utilization` backfills freed weight space with KV cache.
Discriminators: `Model loading took`, the KV token count, host `Shmem`.

**Falling `MemAvailable` is not evidence of offload.** Reading a checkpoint does
it too — a run with the offloader provably absent drained 2.63 GiB. `Shmem` is
the honest signal; subtract it from `Cached` to control for page cache.
→ D1 supplemental

**A row with `otok=1` measured nothing, and says `failed=0/n` while it does.**
Both 2026-08-31 sweep scripts post to raw completion endpoints with no chat
template. Qwen3.6-35B emits a stop token immediately on that prompt shape, so
every one of its cells on both rigs returned a single token — 20 of 60 measured
rows, with `agg` of 0.1–0.6 reading as a throughput collapse. The same server
generated 48 tokens from a short prompt in the same hour.
→ `records/evidence/2026-09-01-moe-offload/diag-2026-09-01.log`

**Fixed, and all 20 re-measured.** Both drivers now post to
`/v1/chat/completions` with `SYSTEM` split off as the system message, and a
`DEGENERATE` guard refuses any cell whose warmup returns `otok <= 1` instead of
letting it record a ladder. Re-measured 2026-09-01: the collapse was **entirely**
the missing template — srv2's `ncmoe=99` went 0.4/0.5/0.5/0.5 → 21.0/27.6/29.8/
30.0, srv1's 0.2 → 12.6. Nothing about those checkpoints or rigs was slow.
Discard every `otok=1` row in `2026-09-01-moe-offload/`; the replacements are in
`2026-09-01-prompt-realism/`.
→ `records/evidence/2026-09-01-prompt-realism/{srv1,srv2}-q36-rerun.tsv`

**A model that tolerates an untemplated prompt is unaffected by the fix.**
srv1's q15 reads 30.4/25.4/36.7/46.0 against 30.3/28.7/37.2/47.7 on the raw
endpoint — within 5%. So the template switch is not a workload change to be
controlled for; it repaired the broken cells and left the rest where they were.

**`REFUSED` is a claim about the harness until you read the log.** Of four on
2026-09-01: two were a dangling symlink — the HF cache stores the GGUF as a
link into `../../blobs/`, and the sweep mounts only the snapshot directory, so
it breaks inside the container. Qwen3-Next-80B loaded on the first try off the
hub root. One captured an `INFO` banner, because the error tail takes the last
lines rather than the last error. One was real.

**The same cell run twice does not draw the same prompts.** Lengths come from a
per-process counter, so a cell run alone gets different work than the same cell
run after another. `s1-oss20 ncmoe=18 n=1` read 22.9 tok/s at `otok=460` and
13.6 at `otok=101`. Across runs compare survival, not throughput.
