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
