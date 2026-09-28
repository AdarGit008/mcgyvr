# reading-results

Reading a journal, a curve, or a ratio.

## Keys and levels

**The drivers do not agree on what the throughput key is called** — the sweep
drivers write `agg=` in TSV rows, the bench harness writes `agg_tok_s` in JSON.
A wrong key reads as null at every level, and a healthy run reads as dead.
Confirm the key against the driver that wrote the file before concluding
anything from a column of nulls. Per-stream throughput is the aggregate over the
width, exactly.

**An `ok` outcome is not sufficient.** A cell can be `ok` and still carry a
barren level. Re-score the levels; do not read the stored string.

**Truncation is `stop_reason`, never `overran_cap`.** `overran_cap` asks whether
more tokens came back than were allowed, and is correctly false on a reply that
stopped exactly at the ceiling. Filtering on it keeps every truncated cell.

**Check width 1 before anchoring a ladder on it.** Where wall clock is flat
across the lower rungs while width 1 runs several times faster per request, that
is a regime change, not noise. Anchor the ladder on the rung above.

**Read a knob's effect at each width both cells ran, never as one number.** The
same knob can cost at low width and pay at high width, or the reverse; a single
per-knob figure hides both.

## Measurements that mislead

**A sweep driver's prefill figure is not a measurement.** Both sweep drivers
divide prefill tokens and generated tokens by the *same* wall clock, so the
ratio of the two is identically the ratio of the token counts. A row where
prefill "tracks" decode is saying nothing. Measure prefill with the
microbenchmark's prompt-processing mode (`llama-bench -p`) or the fleet probe's
own prefill samples, and do not mix the microbenchmark's numbers into a
cross-engine claim — it carries no workload digest.

**The first request after a load is cold.** Page cache and host-side experts are
still faulting in, and it reads a fraction of steady decode. Discard a warm-up,
then take several samples; never read decode from a single first request.

**The prompt draw desyncs whenever the level list changes.** Lengths come from a
per-process counter, so a cell that runs an extra rung consumes extra draws and
every draw after that rung differs, while the lowest rung still agrees because
it always consumes the same draw. **Two rows are comparable only if their prompt
and output token counts match.** Check that before quoting any ratio; equal
aggregates across unequal draws are coincidence.

**Run one cell per driver invocation.** The counter resets when the driver
starts, so passing two cells in one argv silently breaks position matching
between arms. Nothing guards it.

**The same cell run twice does not draw the same prompts.** A cell run alone
gets different work than the same cell run after another. Across runs, compare
survival, not throughput.

**A workload change invalidates comparison above width 1.** Sweeps that send one
short fixed prompt and a long fixed reply overstate real traffic at width,
because real prompts put prefill in contention with decode and a short prompt
has none to contend. Such sweeps agree with realistic ones at width 1 and
diverge as concurrency rises. Do not compare across a workload change at any
rung above 1.

**Temperature 0 is not byte-reproducible under concurrency.** Under continuous
batching the batch shape depends on other traffic and the kernels are not
batch-invariant, so one prompt can decode differently run to run. Price any
output comparison against a same-config null first, and compare verdicts, not
reply bytes. vLLM's lever is batch invariance (`VLLM_BATCH_INVARIANT=1`, compute
capability 8.0 and up); unmeasured here — price it against the null before
adopting.

**Both arms of a comparison run on one backend and one card.** A delta taken
across a backend change measures the backend; a cross-rig replication bounds
hardware sensitivity and is not a second sample.

**Price the tie bar per tolerance class, from repeated samples of one identical
cell.** The classes are vLLM, llama.cpp on the card, and llama.cpp with experts
on the CPU, and their run-to-run spread differs by class and by judged field.
Never
borrow one class's bar for another; the measured bars live in
`tools/runs/derived.json`.

**The comparative rigs send their own output cap, not the contract's.** A
truncation or refusal rate from a breadth or bundle sweep is a property of the
instrument. Pass `--max-output-tokens` and check that nothing stopped at the cap
before reading a row as capability. A capped run cannot be re-analysed into an
uncapped one — a truncated reply's length is censored.

## Reading the card and the host

**Card memory used cannot see a vLLM offload.** It reads flat across offload and
no-offload runs, because the utilisation budget backfills freed weight space
with KV cache. Discriminate on the engine's own model-loading line, the KV token
count, and host shared memory instead.

**Falling available host memory is not evidence of offload.** Merely reading a
checkpoint does it too. Shared memory is the honest signal; subtract it from the
page cache to control for the read.

## Rows that measured nothing

**A row with a single output token measured nothing, and reports no failures
while it does.** Posting to a raw completion endpoint with no chat template
makes some models emit a stop token immediately; every cell then returns one
token, with an aggregate that reads as a throughput collapse. Post to the chat
endpoint with the system prompt split off; a cell whose warm-up returns a
degenerate output is refused, not recorded.

**A model that tolerates an untemplated prompt is unaffected by the template**,
so the chat endpoint is not a workload change to be controlled for.

**`incomplete-reply` reports the output budget, not the reply format.** The
parser refuses on the stop reason before it scans a fence, so it never looked at
the text. Count how many refusals sit exactly at the cap before opening work on
the parser.

**`REFUSED` is a claim about the harness until you read the log.** A dangling
cache symlink — the cache stores the blob outside the directory the run mounts —
and an error tail that caught an informational banner both read as refusals.
Keep the whole log, not a tail.

## Records

**Recorded rows are never edited.** A re-score or a withdrawal lands beside
them, where the figure is derived.

**Re-pin the reply corpus after any run, parser or instrument change, and only
after the sweep exits.** `tools/replies/pin.py` walks every run under
`records/measurements/` and refuses a candidate it cannot join to a row; a sweep
in flight has unflushed rows, so the pin fails for as long as it runs. An edited
or lost reply file is corpus rot — restore the file, never re-pin around it.
