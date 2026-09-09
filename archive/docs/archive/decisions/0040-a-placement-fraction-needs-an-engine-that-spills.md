# ADR-0040 — a placement fraction needs an engine that spills, so vLLM reports the card it holds

Status: Accepted
Supersedes: none
Superseded-by: none
Amends: none — the serving-memory record governs what a vLLM entry *declares it
wants*; this governs what a run *reports about what it got*, and no clause of
that record changes (see Relates)
Relates: ADR-0039 (the memory declaration is bytes — the same engine, the other
half of the same question), ADR-0038 (D4: an ignored difference is recorded on
the contrast, never on the cell; D5: a one-armed cell is first class),
ADR-0027 (D2: a null carries the reason it is null), ADR-0030 (clause 1: no
second instrument), ADR-0026 (lens 1: record what is unrecoverable; lens 3: a
record states the property it contains), #345 (the issue this closes), #335
(the ollama half of this reading), #343 and #346 (the cross-engine layer this
deliberately does not build), #286 (the lane)
Date: 2026-08-23
Issue: #345

## Context

#335 box 5 made every ollama resident's placement a recorded fact, because "it
loaded" and "it fits" turned out to be different facts: ollama answers
`load_http=200` with 93% of a model on the CPU, and the spilled model still
returns correct code. The verdict `coresidency_arranged` was built from an HTTP
200 and a list of names, and said `true` either way.

vLLM had no half of that reading at all. `run.py:568` calls
`backend.residents(host)`; only ollama defined it, so **a vLLM co-residency cell
recorded an `AttributeError` as its evidence**. Since box 5 landed, the same
cell also writes `coresidency_after.placements: null` — honest, and not a
measurement. The campaign's first `void_if` is *"any cell records a verdict
without the placement of every resident on it"*, so phase 0's vLLM arm — 3 cells
on srv1, 4 on srv2 — could not run.

### What the reading is, measured rather than assumed

`nvidia-smi --query-compute-apps=pid,used_memory` was already captured in
`contract.snapshot` and **read by nothing** — one of the three idle readings this
lane keeps finding minted and unwired. Whether it can carry this reading depends
on a fact nobody had checked: what the process holding the card is called.

Taken on both rigs, 2026-08-22, serving `Qwen/Qwen2.5-Coder-1.5B-Instruct-AWQ`
at `max_model_len 8192`, `max_num_seqs 8`, `kv_cache_memory_bytes 1879048192`,
`--enforce-eager` — the declared serve block of `srv-full.json`'s `q15-vllm-s8`:

| rig | deployed as | compute-app pid | **that pid's own command line** | its parent's command line | driver's MiB | card total |
|---|---|---|---|---|---|---|
| srv1 | pip, `vllm 0.26.0` | 1133972 | `VLLM::EngineCore` | `/usr/bin/python3 /home/adaramir/.local/bin/vllm serve Qwen/…` | 3,126 | 3,130 |
| srv2 | docker, `v0.26.0` | 364842 | `VLLM::EngineCore` | `/usr/bin/python3 /usr/local/bin/vllm serve Qwen/…` | 3,174 | 3,183 |

**The pid that holds the card names no model.** vLLM renames its GPU worker with
`setproctitle`, so the process the driver attributes the memory to has a command
line of exactly `VLLM::EngineCore` — no model, no flags, nothing to join on. The
model is on the **immediate parent**, and the two deployment shapes differ only
in the path to the `vllm` binary. One join covers both, and it had to be measured
to be known: a reading assembled from the pid's own line would have returned
`None` on every rig and looked like an empty card.

Measured in the same session, srv1 with `qwen2.5-coder:1.5b` co-resident: the
card reads 4,326 MiB and the driver attributes 3,126 MiB to vLLM's worker and
1,196 MiB to a `llama-server` whose parent is `ollama serve`. **A per-process
figure is not the card**: 4 MiB on srv1 and 9 MiB on srv2 are held by the card
and attributed to nobody, so the two numbers are recorded as two fields and
never substituted for each other.

### The design question: there is no denominator

ollama reports `size_vram / size` because llama.cpp **spills** — its pre-flight
fit check is guarded by `len(s.loaded) > 0`, its *own* models, so a foreign
allocation is invisible to it and llama-server auto-fits into whatever is left.
A fraction is meaningful precisely because a model can be partly on the card.

vLLM cannot be partly on the card. `vllm/v1/worker/utils.py::request_memory` is
`requested = ceil(total_memory * util)` behind a hard `free >= requested`
precondition: the engine takes its whole allocation or **refuses to start**.
`size_vram / size` therefore has no vLLM analogue — a `vllm.placements()` would
answer *"how much of the card does this process hold"*, which is a different
fact wearing the same field name.

Three shapes were put to the owner: `fraction: null` with bytes; `fraction: 1.0`,
true by the engine's own contract; or a separately named field, letting the
frontier carry two kinds of cell.

## Decision

> **DECIDED (2026-08-23, owner).** A vLLM placement reports **what the process
> holds**, and refuses the fraction in the record rather than manufacturing one.
>
> 1. **Every vLLM placement row carries `fraction: null`, with the reason on the
>    row.** Not `1.0`. `1.0` is true by this engine's contract and is the one
>    value a reader would compare against an ollama `0.068` as though the two
>    were one measurement — an ignored difference silently resolved *on the
>    cell*, which is exactly what ADR-0038 D4 puts on the contrast instead.
> 2. **The absolute figure is reported in MiB**, as the driver attributes it per
>    process. Not bytes: `nvidia-smi` attributes to the MiB, so a byte count here
>    would be precision nobody measured, and the tree already records serving
>    footprints in MiB (`srv-full.json`'s `_footprint_mib`). ADR-0039 governs the
>    **declaration**, which is a derived quantity and is stated in bytes; this is
>    a **reading**, and a reading is stated in the units it was taken in.
> 3. **A holder this engine cannot name is a row, not a silence.** `name: null`
>    with its reason — never guessed to be ours, and never dropped, because a
>    stray holder is the fact that explains a figure nobody predicted.
> 4. **A model served but attributed no memory is also a row**, `card_mib: null`
>    with its reason. Absent is not zero and it is not one; that is the same rule
>    #335 wrote for the caller and it holds at the producer.
> 5. **Recorded, never gated.** No placement enters `ok`, on either engine. A
>    shared card is the frontier this campaign exists to map, and a claim that
>    refused one would refuse its own question.
> 6. **`residents()` answers about this engine only** — and so does ollama's. A
>    neighbour served by the other engine is absent from both lists. That is
>    #343 and #346's layer; naming it here would make this module speak for an
>    engine it must not name.

## Consequences

- **Phase 0's vLLM arm can run**: 3 cells on srv1, 4 on srv2, needing no other
  change. It is the only one of the four cross-engine issues that pays off alone.
- **The frontier carries two kinds of cell**, by construction. An ollama cell's
  headline number is a fraction; a vLLM cell's is MiB. Any contrast across the
  two states which it used — the fraction is not missing there, it is refused,
  and the row says so.
- **The unwired-idle-reading count goes from three to two.**
  `contract.COMPUTE_APPS_COMMAND` is now declared once and read by two callers:
  `snapshot`, which records the line, and `vllm.placements`, which computes from
  it. The run contract's §3 warning was not to add a fourth; this adds a
  consumer instead.
- **A claim costs two more ssh round trips**, and the post-ramp re-read two more
  — roughly four seconds a cell against a ~510 minute campaign.
- **What this does not buy**: a cross-engine neighbour is still invisible to both
  backends' `residents()`, so a mixed-engine cell still reads `held: false` after
  its ramp. #343, #344 and #346 are that work, and this record does not pretend
  to it.

## Checks

- `tests/test_serving.py::test_a_vllm_placement_reports_the_card_it_holds_and_refuses_the_fraction`
  — rules 1 and 2, over the lines both rigs really printed.
- `tests/test_serving.py::test_the_pid_that_holds_the_card_names_no_model_so_the_owner_is_the_parent`
  — the join, against the measured `VLLM::EngineCore` command line.
- `tests/test_serving.py::test_a_card_holder_this_engine_cannot_name_is_a_row_and_not_a_silence`
  — rule 3, against the co-resident `llama-server` reading.
- `tests/test_serving.py::test_a_served_model_the_driver_attributed_nothing_to_is_recorded_as_unplaced`
  — rule 4.
- `tests/test_serving.py::test_an_unread_card_is_refused_and_never_an_empty_placement_list`
  — the sentinel: an empty card and an unread card are not the same answer.
- `tests/test_serving.py::test_a_vllm_claim_records_where_everything_on_the_card_sits_and_gates_on_none_of_it`
  — rule 5, on the claim side.
- `tests/test_serving.py::test_the_compute_apps_reading_is_declared_once_and_has_a_consumer`
  — the wiring, so the constant cannot go back to being a string nothing reads.
