# ADR-0039 — a serving memory declaration is bytes, not a fraction of the card

Status: Accepted
Supersedes: none
Superseded-by: none
Amends: none — no prior decision is changed; `gpu_memory_utilization = 0.85` was
never decided here, which is what #337 established and what this record replaces
Relates: ADR-0024 (comparability: one rig, one build — this names a declared
parameter that was silently different per rig), ADR-0026 (lens 3: a record
states the property it contains; lens 4: price the axes), ADR-0038 (D2 the
question approves its own scope; D4 an ignored difference is recorded on the
contrast), #337 (the issue this closes), #329 (the width-16 cross-rig claim this
bears on), #286 (the lane)
Date: 2026-08-22
Issue: #337

## Context

`gpu_memory_utilization = 0.85` appears at five sites in this tree. Its origin
is traced, in `records/evidence/calibration-2026-08-19/README.md`, to local-ai's
`AGENTS.md:126-127` — an OOM fix for srv2's 12 GB card, bundled with two other
changes and applied unchanged to srv1's 6 GB card. Nothing here chose it, and
K10 recorded that as a finding rather than a defect, because no measurement
existed either way.

The measurements now exist. Every figure below was read off the rigs on
2026-08-22 from `vllm/vllm-openai:v0.26.0` serving
`Qwen/Qwen2.5-Coder-1.5B-Instruct-AWQ` at `max_model_len 8192` with
`--enforce-eager`, which is the declared serve block of both `srv-full.json`
vLLM entries.

### What the parameter actually does

From vLLM v0.26.0's own source (`vllm/v1/worker/utils.py::request_memory`,
`vllm/v1/worker/gpu_worker.py`), not from its documentation:

```python
requested_memory = math.ceil(init_snapshot.total_memory * gpu_memory_utilization)
if init_snapshot.free_memory < requested_memory:
    raise ValueError("Free memory ... is less than desired GPU memory utilization")
...
available_kv_cache_memory_bytes = (
    self.requested_memory - profile_result.non_kv_cache_memory - cudagraph_estimate
)
```

Three consequences, each of which was assumed wrongly at some point on this lane:

1. **The budget is `total × util`.** Not `free × util`, and **not** reduced by
   what another process already holds. A widely-repeated claim that vLLM
   subtracts other processes' memory is false for this version.
2. **A neighbour does not shrink the budget; it makes vLLM refuse to start.**
   The precondition is `free >= total × util`. So under a fraction, co-residency
   fails as a launch error in one load order and as a silent partial offload in
   the other — the same declaration, two different failure modes by order.
3. **Everything not spent on weights and activation becomes KV cache**, so
   tightening the fraction spends down the KV cache and nothing else.

`--kv-cache-memory-bytes` sets the KV cache in bytes and **ignores
`gpu_memory_utilization` entirely** when set. vLLM prints the correct value for
the running configuration in its own startup log.

### The requirement is absolute and derivable

The KV cache a declaration can actually reach is
`max_num_seqs × max_model_len × bytes_per_token`. For this model
`bytes_per_token` is **28,672** — 28 layers × 2 KV heads × 128 head_dim × 2
(K and V) × 2 bytes (fp16) — confirmed against the measurement
(3.5 GiB ÷ 131,104 tokens = 28,665 B/token, the difference being block padding).

- `max_num_seqs = 8` → 65,536 tokens → **1,879,048,192 B (1,792 MiB)**
- `max_num_seqs = 16` → 131,072 tokens → **3,758,096,384 B (3,584 MiB)**

### Measured, in MiB of card

| declaration | rig | KV tokens | vLLM's own concurrency line | card |
|---|---|---|---|---|
| `util 0.85`, seqs 8 | srv1 | 131,104 | 16.00x — **cap is 8** | 4,916 MiB |
| `util 0.85`, seqs 8 | srv2 | 322,304 | 39.34x — **cap is 8** | 10,197 MiB |
| `util 0.85`, seqs 16 | srv1 | 131,088 | 16.00x | 4,956 MiB |
| `util 0.85`, seqs 16 | srv2 | 322,304 | 39.34x — cap is 16 | 10,219 MiB |
| `kv 1,879,048,192`, seqs 8 | srv1 | 65,536 | 8.00x | **3,130 MiB** |
| `kv 1,879,048,192`, seqs 8 | srv2 | 65,536 | 8.00x | **3,183 MiB** |
| `kv 3,758,096,384`, seqs 16 | srv1 | 131,072 | 16.00x | **4,986 MiB** |
| `kv 3,758,096,384`, seqs 16 | srv2 | 131,072 | 16.00x | **5,041 MiB** |

Non-KV memory is stable across every row: 1.1 GiB weights, 0.13 GiB peak
activation, 0.04 GiB (srv1) / 0.05 GiB (srv2) non-torch, 0.0 GiB CUDAGraph
(eager).

**What 0.85 costs, in MiB:**

| | seqs 8 | seqs 16 |
|---|---|---|
| srv1 | **1,786 MiB wasted** (2.0x the reachable KV) | 30 MiB saved by the fraction — a wash |
| srv2 | **7,014 MiB wasted** (4.9x) | **5,178 MiB wasted** (2.5x) |

The srv1/seqs-16 cell is why 0.85 survived: on the small card at the largest
declared width it is very nearly the right number. It is the only one of the
four that is.

### Two findings that follow, and neither is about waste

**A fraction cannot express a per-model requirement.** The same absolute
requirement — 1,792 MiB — is `util 0.565` on srv1 and `util 0.273` on srv2. One
number cannot be right for two cards, and a declaration that must be restated
per rig is a declaration that will drift per rig. Bytes are card-independent.

**Under a fraction, `max_num_seqs` stops being a declared parameter.** The KV
budget is `total × util − non_kv`; `max_num_seqs` enters only through activation,
which moved the srv1 figure by 16 tokens out of 131,104. So `q15-vllm-s8` and
`q15-vllm-s16` — two entries whose entire difference is their width — allocate
**the same KV cache**. The instrument does not distinguish the two instruments
it was built to distinguish.

**#329's width-16 contrast is not one instrument.** At the declared 0.85 with
`max_num_seqs 16`, srv1 gets 131,088 tokens against the 131,072 that width 16
requires — a margin of **16 tokens**, 0.012%. srv2 gets 322,304 tokens, a margin
of 146%. The two arms of that contrast differ by **2.46x in KV cache** from the
same declared setting, and nothing in any row records it. `#329`'s open question
is whether the width-16 gap is hardware or configuration; "hardware, not
configuration" is no longer a safe reading of it, and this record does not
settle which it is — it removes the assumption that the configuration was equal.

### A trap this record does not fix

`0.85` also appears in `configs/d7-campaign.json` as `min_vram_fraction`, four
times. That is the **placement floor** — an unrelated quantity that happens to
share the literal. A grep for `0.85` finds nine sites and five of them are a
different decision. Recorded here so the next reader does not conflate them; no
rename is proposed, because renaming a value inside a frozen campaign config
would edit what those cells say they ran under.

## Decision

> **DECIDED (2026-08-22, owner).** A serving memory declaration is stated in
> **bytes**, and the bytes are derived from the entry's own declared shape.
>
> 1. **A vLLM entry declares `kv_cache_memory_bytes` and does not declare
>    `gpu_memory_utilization`.** The two are mutually exclusive: an entry
>    declaring both is a refusal, not a precedence rule, because a precedence
>    rule is how a config comes to believe it declared something it did not.
> 2. **The bytes are `max_num_seqs × max_model_len × bytes_per_token`**, and
>    `bytes_per_token` is a per-model constant recorded with its derivation
>    beside the model, not a magic number. An entry whose declared bytes
>    disagree with its own declared shape is a refusal.
> 3. **There is no default.** `vllm._start` previously fell back to `0.85` for
>    an entry that declared nothing, which is how an undecided number reached
>    five sites. An entry that declares neither field is a refusal that names
>    both.
> 4. **The footprint is recorded in MiB per rig, measured, never computed.**
>    The arithmetic above predicts the KV cache; only the card says what the
>    process took. Both are recorded and they are not the same field.
> 5. **`gpu_memory_utilization` remains legal for a run whose question is the
>    fraction itself.** It is not banned, it is un-defaulted: a fraction is a
>    statement about a card, and any entry using one says which card and why.

## Consequences

- **Co-residency becomes arithmetic instead of luck.** With the declaration,
  srv1 holds vLLM at 3,130 MiB and `qwen2.5-coder:1.5b` at **fraction 1.000**,
  4,326 MiB of 6,144 total. The same cell at 0.85 placed the ollama model at
  **fraction 0.068** — 93% on the CPU — under `load_http=200`.
- **The two declared entries become two instruments.** `s8` and `s16` now differ
  by 1,856 MiB of card instead of by nothing.
- **Every existing vLLM figure is re-baselined.** Cells measured under 0.85 are
  not comparable to cells measured under a byte declaration; which cells, and
  against what, is #337's serving-pin re-baseline and is recorded there.
- **The price is a per-model constant to maintain.** `bytes_per_token` is a
  property of the architecture and the KV dtype; a model whose constant is not
  recorded cannot be declared, which is the intended failure.
- **This buys no throughput.** Nothing here makes a model faster. It makes the
  declared footprint match the declaration, which is what makes a neighbour's
  room a number rather than a hope.

## Amendment, 2026-08-23 — a byte declaration travels, and travelling is not fitting (#354)

**The rule above is unchanged.** Nothing in the Decision is withdrawn, corrected
or narrowed. What is added is its reach, which the record did not state and the
rigs then found.

Phase 0 of the footprint campaign
(`records/evidence/2026-08-23-phase0-footprint/`) ran 25 cells. Three refused,
all three vLLM, all three on an **empty** card, all three
`torch.OutOfMemoryError` inside `_allocate_kv_cache`:

| cell | card | free at start | declared KV | weights |
|---|---|---|---|---|
| srv1 / `thewimo/Qwen3-4B-AWQ` | 6,144 MiB | 5.54 GiB | 9.0 GiB | 2.5 GiB |
| srv2 / `thewimo/Qwen3-4B-AWQ` | 12,288 MiB | 11.52 GiB | 9.0 GiB | 2.5 GiB |
| srv2 / `Qwen2.5-Coder-14B-AWQ` | 12,288 MiB | 11.52 GiB | 12.0 GiB | 9.38 GiB |

**Each declaration is arithmetically correct.** Qwen3-4B's own `config.json` on
the rig gives 36 layers, 8 KV heads, 128 head_dim, bfloat16, so
36 × 8 × 128 × 2 × 2 = **147,456 B/token**, and 65,536 tokens of it is
**exactly** the declared 9,663,676,416. The 14B comes out at 196,608 B/token and
exactly its declared 12,884,901,888 by the same route. Rule 2 was applied
correctly in every case and produced a number these cards cannot hold.

Why it took a campaign to find: **every vLLM figure this project held came from
the 1.5B**, whose geometry is 28 layers × **2** KV heads — four times narrower
per layer than Qwen3-4B's. The rule was validated on the one model whose
declaration happened to fit everywhere it was carried, and "bytes travel across
cards" was read as though travelling and fitting were the same property. They
are not: bytes are a property of the *model*, and whether they fit is a property
of the *card*. Rule 2 settles the first and says nothing about the second, which
is correct — and left the second unowned.

### What this adds

**Rule 6.** A vLLM entry's declared KV cache is checked against the card it
targets **before the launch**, and an entry that cannot fit is refused with the
arithmetic in the message: the declared bytes, the weights, the card's free
memory, and the shortfall. The refusal names the two declarations that *would*
fit — a narrower `max_num_seqs`, or a shorter `max_model_len`, each with its
figure — and **takes neither**, because which one to give up is the entry's
decision and a launcher that chose silently is how a run comes to measure a
configuration nobody declared.

**Rule 7.** The weights are a per-model constant recorded with its derivation,
exactly as `bytes_per_token` is under rule 2 — `weights_bytes` with a
`_weights_bytes_note` quoting the engine's own `Model loading took X GiB` line.
An entry that declares KV bytes and gives the check nothing to weigh them
against is refused. Rule 4's distinction is kept and is what makes the check
cheap: a host with a **measured** `_footprint_mib` is judged on that figure and
not on the prediction, because a footprint the card produced needs no model of
why it fits.

`NON_KV_OVERHEAD_MIB = 910` is what a vLLM process holds besides weights and KV:
470 MiB driver and CUDA context (the gap between `nvidia-smi`'s free and the
engine's own "Initial free memory" — 470 on srv1, 491 on srv2, the smaller taken
because over-stating this term refuses cells that would have run), 133 MiB peak
activation and 51 MiB non-torch from the table above, and one 256 MiB allocator
block, which is the size all three refusals died trying to allocate. Phase 0's
seven vLLM cells admit **any value from 511 to 1,793 MiB** without changing a
verdict; 910 sits inside that window with room on both sides, and the check
below fails if a later measurement narrows it rather than only if the number
moves.

### What this does not claim

The 3B and 7B cells' weights are **derived**, not measured — `footprint − KV −
residue`, with the residue solved from each rig's 1.5B row — because vLLM's
weights line was captured only for the cells that failed. They set the window's
upper edge and nothing else. A campaign that captures the weights line on every
vLLM start would replace the derivation with a reading; nothing here depends on
it beyond that edge.

This buys no throughput and changes no measurement. It converts a three-minute
engine crash into a millisecond of arithmetic, over figures that already existed
the moment phase 0 finished.

## Checks

- `tests/test_serving_memory_declaration.py::test_a_vllm_entry_declares_bytes_and_the_bytes_match_its_own_shape`
  — rules 1 and 2, over every serving config in the tree.
- `tests/test_serving_memory_declaration.py::test_there_is_no_silent_default_and_both_fields_together_are_a_refusal`
  — rules 1 and 3, against `vllm._start`'s argument builder.
- `tests/test_serving_memory_declaration.py::test_every_declared_model_records_how_its_bytes_per_token_was_derived`
  — rule 2's second half.
- `tests/test_serving_memory_declaration.py::test_the_pre_check_agrees_with_the_card_on_every_phase_0_cell`
  — rule 6, over all seven of phase 0's vLLM cells: four admitted, three refused.
- `tests/test_serving_memory_declaration.py::test_the_overhead_constant_sits_inside_the_window_the_measurements_allow`
  — the 511–1,793 MiB window, derived from the campaign rather than restated.
- `tests/test_serving_memory_declaration.py::test_the_refusal_names_both_ways_out_and_takes_neither`
  — rule 6's second half, including that the entry is not edited.
- `tests/test_serving_memory_declaration.py::test_a_declaration_is_checked_after_the_release_and_before_the_launch`
  — the call site's two neighbours, which are the whole of its value.
- `tests/test_serving_memory_declaration.py::test_every_vllm_entry_can_be_checked_against_a_card`
  — rule 7, over every vLLM entry in every serving config.
- `tests/test_decisions.py::test_each_number_is_claimed_once_and_titles_agree`
  — this record's header and number.
