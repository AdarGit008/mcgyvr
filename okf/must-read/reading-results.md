# reading-results

Reading a journal, a curve, or a ratio.

## Keys and levels

**The drivers do not agree on what the throughput key is called.** A wrong key
reads as null at every level, and a healthy run reads as dead. Confirm the key
against the driver that wrote the file before concluding anything from a column
of nulls. Per-stream throughput is the aggregate over the width, exactly.

**An `ok` outcome is not sufficient on older rows.** A cell can be `ok` and
still carry a barren level. Re-score the levels; do not read the stored string.

**Anchor srv1's vLLM ladder above width 1.** Wall clock is flat across the lower
rungs while width 1 runs several times faster per request. That is a real regime
change, not noise, and anchoring on width 1 misreads it.

## Measurements that mislead

**A reported prefill figure is not a measurement.** Both drivers divide prefill
tokens and generated tokens by the *same* wall clock, so the ratio of the two
is identically the ratio of the token counts. A row where prefill "tracks"
decode is saying nothing; a row where it did not would be an arithmetic error.
**Nothing in this repo has ever measured prefill separately.** Use the
microbenchmark's prompt-processing mode for that, and do not mix its numbers
into a cross-engine claim — it carries no workload digest.

**The prompt draw desyncs whenever the level list changes.** Lengths come from a
per-process counter, so a cell that runs an extra rung consumes extra draws and
every draw after that rung differs. Same rig, same image, same hour, nominally
the same cells have disagreed by several percent this way — while the lowest
rung agreed closely, because it always consumes the same draw. **Two rows are
comparable only if their prompt and output token counts match.** Check that
before quoting any ratio; equal aggregates across unequal draws are coincidence.

**One cell per process invocation is load-bearing and undocumented.** The
counter resets when the driver starts, so passing two cells in one argv silently
breaks position matching between arms. Every comparable file in the tree was
produced one cell at a time, by habit rather than by a guard.

**The same cell run twice does not draw the same prompts.** A cell run alone
gets different work than the same cell run after another. Across runs, compare
survival, not throughput.

**A workload change invalidates comparison above width 1.** Sweeps that send one
short fixed prompt and a long fixed reply overstate real traffic substantially
at width, because real prompts put prefill in contention with decode and a short
prompt has none to contend. Such sweeps agree with realistic ones at width 1 and
diverge as concurrency rises. Do not compare across a workload change at any
rung above 1.

## Reading the card and the host

**Card memory used cannot see a vLLM offload.** It reads flat across offload and
no-offload runs, because the utilisation budget backfills freed weight space
with KV cache. Discriminate on the engine's own model-loading line, the KV token
count, and host shared memory instead.

**Falling available host memory is not evidence of offload.** Merely reading a
checkpoint does it too, by gigabytes, with the offloader provably absent. Shared
memory is the honest signal; subtract it from the page cache to control for the
read.

## Rows that measured nothing

**A row with a single output token measured nothing, and reports no failures
while it does.** Posting to a raw completion endpoint with no chat template
makes some models emit a stop token immediately; every cell then returns one
token, with an aggregate that reads as a throughput collapse. The drivers now
post to the chat endpoint with the system prompt split off, and a guard refuses
any cell whose warmup returns a degenerate output rather than letting it record
a ladder. When this was repaired the collapse proved **entirely** to be the
missing template — nothing about those checkpoints or those rigs was slow.

**A model that tolerates an untemplated prompt is unaffected by the fix**, so
the template switch is not a workload change to be controlled for. It repaired
the broken cells and left the rest where they were.

**`REFUSED` is a claim about the harness until you read the log.** Of a batch
examined, most were environmental — a dangling symlink, where the cache stores
the blob outside the directory the run mounts, and an error tail that captured
an informational banner because it takes the last lines rather than the last
error. One was real. Read the log before believing any of them.
