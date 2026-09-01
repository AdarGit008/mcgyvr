# ARTIFACT CONTRACT — srv1 kernel-arms run (2026-09-02)

What the twelve RED tests in `lcp-vllm-3-arm-run.md` actually parse. Written so a
run script can emit exactly this and nothing else. Every requirement below cites
the file and line that demands it. Nothing here is invented: if a field is not
cited, no test asks for it.

Authority for syntax: `tests/sweeprows.py`.
Ground truth for line shape: `records/evidence/2026-09-01-*/**.tsv`.

**Revised 2026-09-02** after the six contradictions in §6 were adjudicated
against `lcp-vllm-3-arm-run.md`'s nine guidelines. Every §6 entry now carries its
resolution, the guideline that decided it, and what changed in the parser or the
tests. Line citations were re-read against the post-resolution files.

Throughout, **⇥ denotes one literal TAB (U+0009)**. Nothing else in this document
is a tab.

---

## 1. Line syntax

`tests/sweeprows.py:225-251` (`read`) is the whole parser. There is no other.

### 1.1 Tokenisation

A file is read as UTF-8 and split into lines (`sweeprows.py:141`). For each line,
in this order:

1. **Blank / whitespace-only** → skipped entirely, but it still consumes a line
   number (`sweeprows.py:230-231`).
2. **Starts with `###`** → it is a **marker line**. It is recorded as
   `(lineno, full_line_text)` and becomes the "current marker" for every row that
   follows (`sweeprows.py:232-235`). Markers are never rows.
3. **Otherwise** → split on TAB (`line.split("\t")`, `sweeprows.py:236`). If it
   yields **fewer than 3 parts, the line is silently dropped**
   (`sweeprows.py:237-238`). A row therefore needs at least
   `host⇥label⇥kind`.
4. The first three parts are `host`, `label`, `kind`; everything after is `rest`
   (`sweeprows.py:239`).

`lineno` is 1-based over the raw file, counting blank lines and markers
(`sweeprows.py:229`). This matters: `VERDICT cited_line=` must be one of these
numbers (§2.9).

### 1.2 `key=value` fields

`rest` (the tab-separated tokens from column 4 onward) is passed to `_pairs`
(`sweeprows.py:36-42`), which tests each **whole token** against — note this is
the **row** rule; markers are stricter, see §1.6

```
_KV = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", re.DOTALL)   # sweeprows.py:33
```

Consequences, all load-bearing:

- Fields are separated by **TAB only**. A space never separates two fields.
- A key must start `[A-Za-z_]` and continue `[A-Za-z0-9_]`. `len`, `kv`, `n`,
  `fa`, `pp`, `tg` are all legal keys.
- A **value may contain spaces, `=`, `/`, `|`, `:` — anything except a TAB**,
  because the token is a whole tab-field and the value group is `(.*)` with
  `DOTALL`. `early_stop=0/1` and `reason=CUDA error: invalid argument` are both
  one field.
- **Last duplicate key wins** within a row (`sweeprows.py:38-41`, plain dict
  assignment).
- A token that does *not* match is not an error — it goes to `tail`.

### 1.3 `tail`

```python
tail = tuple(p for p in rest if not _KV.match(p))     # sweeprows.py:247
```

`tail` is every column-4+ token that is **not** `key=value`. It is the free-text
channel: refusal reasons, crash logs, skip explanations. Two rules follow:

- A reason whose first characters happen to look like `word=` will be eaten as a
  field and vanish from `tail`. Prefix such text with a non-identifier character
  (the drivers' log lines start with a digit, e.g. `0.01.431.610 E srv ...`,
  which is safe) or keep it as `reason=` (`test_a_crash_...:37` accepts either).
- `len(" ".join(row.tail)) > 40` is asserted twice
  (`test_an_ncmoe_floor_...:87`, `test_two_backends_...:56`), so a reason must be
  at least 41 characters after joining tail tokens with single spaces.

### 1.4 What a "kind" is

`kind` is **column 3, verbatim**. There is no enum in the parser; a kind is
recognised by exact string equality or by prefix:

| construct | definition | site |
|---|---|---|
| `Sweep.of_kind(k)` | `[r for r in rows if r.kind == k]` — exact match | `sweeprows.py:195-196` |
| `Row.n` | `int(kind[2:])` iff `kind.startswith("n=")`, else `None` | `sweeprows.py:115-117` |
| `Sweep.levels()` | every row whose `Row.n is not None` | `sweeprows.py:192-193` |

So a **level row** is any row whose third column is literally `n=<int>`; its
width is parsed from the kind, not from a field. `int()` must succeed, so
`n=08` is legal, `n=8x` raises.

Kinds asserted by name in the twelve tests: `CONFIG`, `n=<int>`, `CRASH`,
`REFUSED`, `BENCH`, `SKIP`. Kinds the existing drivers also emit and that the
parser will accept unchanged: `DEGENERATE`, `WIDTH`, `ABORT`
(`lcp_sweep_31-08-2026.py:189`, `vllm_sweep_31-08-2026.py:270`,
`vllm_cores_01-09-2026.py:321`). `SKIP` is the only kind exempted from the
per-row rules (`test_a_row_that_does_not_name_its_arm_...:39-40`,
`test_a_row_without_the_rigs_live_state_...:32`).

### 1.5 Derived accessors

| accessor | rule | site |
|---|---|---|
| `Row.tag` | `label.split(" ", 1)[0]` — the label's first word | `sweeprows.py:119-123` |
| `Row.cell` | `tag` with a leading `ARM-` removed if `ARM` fullmatches `ARM_PREFIX` = `[ABL][0-9]` | `sweeprows.py:124-139`, `:49` |
| `Row.num(k)` | `float(fields[k])`; asserts the key exists | `sweeprows.py:140-143` |
| `Row.frac(k)` | `"3/8"` → `(3, 8)`; asserts the key exists | `sweeprows.py:145-150` |
| `Row.draw()` | `(num("ptok"), num("otok"))` — the work **done** | `sweeprows.py:152-167` |
| `Row.requested()` | `(num("ptok"), num("otok_req"))` — the work **asked for** | `sweeprows.py:169-183` |

**`Row.cell` strips `A0`–`A9`, `B0`–`B9` and `L0`–`L9` prefixes** — every arm
this campaign names (`lcp-vllm-3-arm-run.md:37-54`). `L0-d3b` and `L3-d3b` both
have cell `d3b`, so **one labelling convention, `<ARM>-<cell>`, serves every
file**. Resolved: §6.1.

**`draw()` and `requested()` are different quantities and are not
interchangeable.** §6.2.

Nothing in this module deduplicates by label (`sweeprows.py:15-16`); a label may
repeat freely.

### 1.6 Marker (stamp) lines

Two helpers, and **both can raise** — a malformed stamp is a parse error, never
a silent `{}` and never a silent truncation (§6.6, §6.7).

```python
_stamp_name(lineno, line)      # sweeprows.py:52-75  — raises ValueError
_stamp_fields(lineno, line)    # sweeprows.py:77-101 — raises ValueError
```

- A stamp's **name is the first whitespace-delimited token after `###`**.
  `### START pl1_uw=...` is `stamp("START")`. `### AB START ...` is
  `stamp("AB")` — the 2026-09-01 files' habit
  (`records/.../srv1-nomma-dp4a-ab.tsv:1`) **must not be carried over**.
- **A malformed header raises.** `_stamp_name` is called on *every* marker in the
  file, for every lookup, and raises `ValueError` when the marker has no token
  after `###` (a bare `###`) or when its first token is itself `key=value`
  (`### digest=...`, a stamp that lost its name). Both used to return `{}`, which
  is indistinguishable from "that stamp is absent" — and absence is meaningful
  here: no `### END` means the run did not close (`test_a_row_without_...:44`).
- **A stamp value may not contain a space, and one that does raises.**
  `_stamp_fields` is called only on the markers whose name matches the lookup,
  and it rejects any token after the name that is not `key=value`.
  `uptime_since=2026-09-01 08:11:08`
  (`records/.../srv1-locktest-ling-60min.tsv:1`) used to parse as
  `uptime_since=2026-09-01`, dropping the clock — so START and END compared equal
  across two different moments and guideline 7's re-read passed on a run whose end
  state was never actually read. Use a `T`-joined or underscore-joined form.
  A row field may still hold spaces; only stamps are strict.
- Markers whose name does **not** match the lookup are not field-checked, so a
  free-text marker (`### control: committed s1-d3b ...`,
  `### IMAGE ghcr.io/...`) coexists with stamps as long as its first token is not
  `key=value`.
- `Sweep.stamp(word)` returns the **LAST** matching marker in the file
  (`sweeprows.py:198-204`). `Sweep.stamps(word)` returns **all** of them in file
  order (`sweeprows.py:206-212`). `Sweep.stamped_before(row, word)` returns the
  **nearest preceding** one, `{}` if none (`sweeprows.py:214-222`).
- A missing stamp is `{}`. A *malformed* one is an exception.

### 1.7 Existence

`artifact(path, behaviour)` (`sweeprows.py:318-333`) calls
`pytest.fail(f"{rel} does not exist. {behaviour}", pytrace=False)` when the file
is absent. It never skips. The two JSON artifacts (§4) are read with a bare
`Path.read_text`, so their absence is an unhandled `FileNotFoundError`, not a
message.

Every test now reaches an artifact through `owed(name)` (`sweeprows.py:336-342`),
which looks the behaviour string up in the `BEHAVIOUR` registry
(`sweeprows.py:307-316`) — **one file, one script**. §6.5.

`RUN = records/evidence/2026-09-02-srv1-kernel-arms` (`sweeprows.py:295`).

---

## 2. Stamp blocks, by name

Only these stamp names are read by any of the twelve tests. Values shown in
`CODE` are **literal string comparisons** — the artifact must emit that exact
byte sequence.

### 2.1 `### WORKLOAD`
Read with `stamp()` (last wins) in `test_one_workload_or_no_comparison.py:55,86`.

| key | required in | value | cite |
|---|---|---|---|
| `digest` | `srv1-lcpp-arms.tsv`, `srv1-moe-slots.tsv`, `srv1-vllm-arms.tsv` | literal `2f2bb7932a0b660653def819` | `test_one_workload_...:56`; constant at `sweeprows.py:277` |
| `driver` | same three | a repo-relative path that `is_file()` and whose `workload_digest()` re-computes to `digest` | `test_one_workload_...:60-67` |
| `digest` | `srv1-llama-bench.tsv` **and `srv1-build-ladder.tsv`** | literal `none` | `test_one_workload_...:87` |
| `comparable_with` | same two | literal `microbenchmark-only` | `test_one_workload_...:91` |

`driver` must be one of the three that hash correctly today — verified green:
`vllm_sweep_31-08-2026.py`, `lcp_sweep_31-08-2026.py`, `vllm_cores_01-09-2026.py`
(`test_one_workload_...:32-46`). The path must contain no space (§1.6).
`workload_digest` execs the source region from `PROMPT_DECILES` to `def sh(`
(`sweeprows.py:280-291`), so the named driver must still contain both markers.

**Both microbenchmark files are stamped digest-free**, not only the one named
after the tool: `MICROBENCH = ("srv1-llama-bench.tsv", "srv1-build-ladder.tsv")`
(`test_one_workload_...:38`). They hold the same `llama-bench` measurement (§6.4),
and guideline 4 keeps either of them from being read as a serving claim.

Neither carries a `driver=` requirement — only the two literals above.

### 2.2 `### RIG`
Read with `stamped_before()` in
`test_a_row_without_the_rigs_live_state_is_not_comparable.py:30-32`. Required in
`srv1-lcpp-arms.tsv`, `srv1-moe-slots.tsv`, `srv1-vllm-arms.tsv`.

Every non-`SKIP` row must have a preceding `### RIG` for which `rig_gaps()`
(`sweeprows.py:270-271`) is empty — i.e. all six keys present and **non-blank
after `.strip()`**:

`cpu_max_mhz`, `ram_mt_s`, `pl1_uw`, `pl2_uw`, `driver`, `gpu_reserve_mib`
(`sweeprows.py:260-267`).

Note `driver` here is the **GPU driver version**, and it collides in name with
`WORKLOAD driver=` (§2.1) — they live in different stamps, so this is legal, but
do not merge the two stamps. Emit one `### RIG` before the first row of the file
and re-stamp per arm (`test_a_row_without_...:9-11`).

### 2.3 `### START` and `### END`
Read with `stamp()` in `test_a_row_without_the_rigs_live_state_...:43`. Required
in the same three files.

| key | rule | cite |
|---|---|---|
| `pl1_uw` | present on START **and** byte-equal on END | `:47-52` |
| `pl2_uw` | same | `:47-52` |
| `uptime_since` | same — **the value must not contain a space, and a spaced one now raises** (§1.6, §6.7) | `:47-52` |
| `cpu_max_mhz` | same | `:47-52` |
| `ram_mt_s` | same | `:47-52` |
| `pl1_source` | START only; literal `constraint_0_power_limit_uw` | `:53-57` |

`### END` must exist and be non-empty (`:44-46`). **RIG-ONLY**: the equality of
start and end is a property of the machine over the run, not of the emitter.

### 2.4 `### BUILD`
Read with `stamps()` (all of them) in two files with two different key sets.

In **`srv1-lcpp-arms.tsv`** — every `### BUILD` needs all five
(`test_a_row_that_does_not_name_its_arm_...:75-83`, unchanged):
`arm`, `commit`, `image_sha256`, `cuda_architectures`, `force_mmq`.
And `{s["arm"] for s in stamps("BUILD")}` must cover every arm that ran a
`llamacpp:b10644-` image (`:84-91`).

In **`srv1-build-ladder.tsv`** — the stamp set must cover arms `L0 L1 L2 L3 L4`
(`test_a_six_variable_diff_...:39,54-55`), and each stamp is compared on
(`test_a_six_variable_diff_...:64-70`):
`cuda_architectures`, `force_mmq`, `ggml_native`, `cpu_all_variants`, `patched`.
For each of the pairs `(L0,L1)`, `(L1,L2)`, `(L2,L3)` **exactly one** of those
five keys may differ (`:73-79`). `L4` is stamped and benched but is not on the
one-variable chain (`:73` lists only three pairs).

Safest emission: one `### BUILD` per arm carrying the **union** of both key sets
(`arm commit image_sha256 cuda_architectures force_mmq ggml_native
cpu_all_variants patched`) in both files.

### 2.5 `### KERNELS`
`srv1-build-ladder.tsv` only, read with `stamps()`
(`test_a_six_variable_diff_...:90`). Each stamp needs `arm`, plus:

| arm | `tensor_core_instructions` | cite |
|---|---|---|
| `L0` | literal `present` | `:91-95` |
| `L1` | literal `present` | `:91-95` |
| `L2` | literal `absent` | `:96-101` |
| `L3` | literal `absent` | `:96-101` |

**RIG-ONLY** — the values come from `cuobjdump` on the built libraries.

### 2.6 `### BOUNDARY`
`srv1-moe-slots.tsv` only, `stamp()` (last wins)
(`test_a_crash_not_reproduced_...:63-66`).

| key | value |
|---|---|
| `arm` | literal `L2` |
| `first_failing_n` | any non-empty string (truthiness only) |

### 2.7 `### NULL`
`srv1-aa-null.tsv` only, `stamp()`
(`test_one_observation_is_not_an_effect.py:118`).

| key | rule | cite |
|---|---|---|
| `spread_pct` | non-empty, `float()`-parseable, and within `0.5` of `max((max(agg)-min(agg))/median(agg)) * 100` computed over the file's own level rows grouped by `(cell, n)` | `:118-123` |

### 2.8 `### FLOOR`
`srv1-ncmoe-floor.tsv` only, `stamps()`
(`test_an_ncmoe_floor_is_derived_and_not_copied.py:39,64`).

At least **two** stamps carrying distinct `arm` values (`:39-40`). Each stamp
needs all of (`:42-43`):
`usable_mib`, `cuda_ctx_mib`, `nonexpert_mib`, `kv_mib`, `expert_total_mib`,
`n_layers` (`:27-34`), plus `predicted` and `measured`.

The arithmetic must reproduce to within `1.0` (`:44-56`):

```
budget    = usable_mib - cuda_ctx_mib - nonexpert_mib - kv_mib
resident  = budget / expert_total_mib
predicted = (1 - resident) * n_layers
```

And no two arms reporting the same `measured` may have byte-identical tuples of
the six inputs (`:65-74`).

### 2.9 `### VERDICT`
`srv1-vllm-arms.tsv` only, `stamp()`
(`test_two_backends_on_one_checkpoint_is_the_only_pair.py:136`).

| key | value | cite |
|---|---|---|
| `hypothesis` | literal `tensor-core-emulation` | `:137` |
| `status` | one of literals `supported`, `refuted`, `unresolved` | `:138` |
| `cited_line` | `int()`-parseable, and equal to the `lineno` of some **row** in the file (not a marker, not a blank line) | `:139-143` |

Cross-rule: if any `REFUSED` row carries `arm=B2`, `status` may **not** be
`supported` (`:144-149`).

### 2.10 `### TOOL`
`srv1-llama-bench.tsv` only, `stamp()`
(`test_a_prefill_verdict_...:31`).

| key | value |
|---|---|
| `name` | literal `llama-bench` |

---

## 3. Per-row fields, by name

Every entry cites the test line that reads it. "kinds" is where it must appear.

| field | file(s) | row kinds that must carry it | cite |
|---|---|---|---|
| `arm` | `srv1-lcpp-arms`, `srv1-moe-slots`, `srv1-vllm-arms` | **every row except `SKIP`**, non-empty | `test_a_row_that_does_not_name_its_arm_...:39-41` |
| `arm` | `srv1-lcpp-arms` | level rows — groups the replicate count and the interleave order | `test_one_observation_...:45,60` |
| `arm` | `srv1-moe-slots` | `CRASH` and level rows — selects `L2` / `L3` | `test_a_crash_...:34,55,57,73,82` |
| `arm` | `srv1-vllm-arms` | `CONFIG`, `REFUSED`, level rows — keys `B1`/`B2` | `test_two_backends_...:79,80,113,126,127,144` |
| `arm` | `srv1-llama-bench` | `BENCH` — groups the `fa` coverage check | `test_a_prefill_...:67` |
| `arm` | `srv1-build-ladder` | `BENCH` — must cover `L0..L4` | `test_a_six_variable_diff_...:56-57` |
| `img` | `srv1-lcpp-arms`, `srv1-moe-slots`, `srv1-vllm-arms` | **every row except `SKIP`** | `test_a_row_that_does_not_name_its_arm_...:42-50` |
| `ptok` | `srv1-lcpp-arms` | level rows (skipped if absent) | `test_one_observation_...:88,92`; `sweeprows.py:183` |
| `otok_req` | `srv1-lcpp-arms` | level rows carrying `ptok`. **The requested output budget** — a plan, equal across arms in one `(cell, n, rep)` group | `test_one_observation_...:92`; `sweeprows.py:169-183` |
| `otok` | `srv1-lcpp-arms` | level rows. **Generated output** — an outcome; it is *expected* to differ across arms and nothing asserts otherwise (§6.2) | `sweeprows.py:152-167` |
| `otok` | `srv1-moe-slots` | `L3` level rows at the killed widths; must be `> 1` (generated, not requested) | `test_a_crash_...:92` |
| `agg` | `srv1-aa-null` | every level row | `test_one_observation_...:110` |
| `rep` | `srv1-lcpp-arms` | level rows; `int()`-parseable, defaults `"0"` if absent | `test_one_observation_...:91` |
| `n` | `srv1-moe-slots` | `CRASH` rows — `int()`-parseable, **required** (bare `r.fields["n"]`) | `test_a_crash_...:52,74` |
| `trials` | `srv1-moe-slots` | `L3` level rows at killed widths; `int()`, defaults `"1"`; the sum per `(cell, width)` must be `>= 60` | `test_a_crash_...:85-90` |
| `failed` | `srv1-moe-slots` | `L3` level rows at killed widths; `x/y` form, numerator `0` | `test_a_crash_...:92`; `sweeprows.py:145-150` |
| `http_000` | `srv1-moe-slots` | `CRASH` rows with `arm=L2`; `x/y` form with `x == y` | `test_a_crash_...:44-45` |
| `reason` | `srv1-moe-slots` | `CRASH` rows — optional; the crash marks may live in `tail` instead | `test_a_crash_...:37` |
| `pp` | `srv1-llama-bench` | `BENCH` (or level rows if any exist) | `test_a_prefill_...:34-39` |
| `tg` | `srv1-llama-bench` | same | `test_a_prefill_...:40-42` |
| `reps` | `srv1-llama-bench` | `BENCH`; `int()`, `>= 9`. **This file only** — the ladder's `BENCH` rows are the same measurement re-filed and nothing reads `reps` there (§6.4) | `test_a_prefill_...:52-55` |
| `stddev` | `srv1-llama-bench` | `BENCH`; presence only. This file only | `test_a_prefill_...:56` |
| `fa` | `srv1-llama-bench` | `BENCH`; per arm the set must contain both `"0"` and `"1"`. This file only | `test_a_prefill_...:65-71` |
| `tries` | `srv1-ncmoe-floor` | `REFUSED`; `int()`, `>= 3`, defaults `"1"` | `test_an_ncmoe_floor_...:83-86` |
| `tries` | `srv1-vllm-arms` | `REFUSED`; `int()`, `>= 3`, defaults `"1"` — guideline 8, same bar (§6.3) | `test_two_backends_...:61-65` |
| `model` | `srv1-vllm-arms` | `CONFIG`; equal on `B1` and `B2` **when both launched** | `test_two_backends_...:43,94` |
| `weights_sha256` | `srv1-vllm-arms` | `CONFIG`; equal on `B1` and `B2` when both launched | `test_two_backends_...:43,94` |
| `util` | `srv1-vllm-arms` | `CONFIG`; equal on `B1` and `B2` when both launched | `test_two_backends_...:43,94` |
| `len` | `srv1-vllm-arms` | `CONFIG`; equal on `B1` and `B2` when both launched | `test_two_backends_...:43,94` |
| `seqs` | `srv1-vllm-arms` | `CONFIG`; equal on `B1` and `B2` when both launched | `test_two_backends_...:43,94` |
| `kv` | `srv1-vllm-arms` | `CONFIG`; equal on `B1` and `B2` when both launched | `test_two_backends_...:43,94` |
| `kernel_observed` | `srv1-vllm-arms` | `CONFIG`; `"marlin" in value.lower()` for `B1`, `"exllama" in value.lower()` for `B2`. Read from the engine's `Using {Marlin,Exllama}LinearKernel for AutoGPTQLinearMethod`; an arm with no `CONFIG` is skipped | `test_two_backends_...:114-120` |
| `checkpoint_quant` | `srv1-vllm-arms` | `REFUSED` with `arm=B2`; non-empty | `test_two_backends_...:57-60` |

### 3.1 The `img=` value grammar
`test_a_row_that_does_not_name_its_arm_is_not_a_measurement.py:24-29,44-50`.
A value passes iff **all** of:

- non-empty (`:43`);
- does **not** match `:(latest|main|server-cuda)$` (`:24`, `:44-47`);
- **and** one of:
  - exactly `ghcr.io/ggml-org/llama.cpp:server-cuda-b10644` (`:26`) — note this
    is *not* caught by the floating-tag regex, which is anchored at `$`;
  - exactly `vllm/vllm-openai:v0.26.0` (`:27`);
  - starts with `llamacpp:b10644-` (`:29`);
  - contains the substring `@sha256:` (`:49`).

So every locally built arm (`L0 L1 L2 L3 L4 A3`) must be tagged
`llamacpp:b10644-<suffix>`, and at least one row of `srv1-lcpp-arms.tsv` must
carry such a tag (`:74`).

### 3.2 Label rules

**One convention, every file: the label is `<ARM>-<cell> <settings...>`.** With
`ARM_PREFIX = [ABL][0-9]` (§1.5) the arm is in the label *and* the cell aligns
across arms, which is what the two rules below each needed and could not both
get before (§6.1).

- `srv1-lcpp-arms.tsv`: **no label may be used by two different `arm=` values**
  across level rows (`test_a_row_that_does_not_name_its_arm_...:54-63`). Satisfied
  because the arm is the label's prefix: `L0-d3b np=8 ...` ≠ `L2-d3b np=8 ...`.
- `srv1-moe-slots.tsv`: `test_a_crash_...:78-84` matches an `L3` row to an `L2`
  crash by `Row.cell` equality. Satisfied because `L2-mling` and `L3-mling` both
  have cell `mling`. **Do not** share the raw label across the two arms — that
  would break the lcpp-arms rule if the same emitter is reused, and it is no
  longer needed.
- At least **two distinct cells** must appear among `srv1-moe-slots.tsv`'s `CRASH`
  and level rows (`test_a_crash_...:100-101`). Note this is now a real check: with
  the old parser `L2-mling` and `L3-mling` counted as two cells, so **one**
  checkpoint driven under two arms would have passed a test about **two**
  checkpoints. It no longer does.

### 3.3 Ordering rules (`srv1-lcpp-arms.tsv`)

- Every `(arm, cell, n)` triple must appear **at least 5 times**
  (`test_one_observation_...:36,40-49`).
- Over the file's level rows in order, the number of arm-runs
  `1 + count(a != b for adjacent pairs)` must be `>= len(distinct arms) * 5`
  (`:59-65`). Concatenating whole per-arm blocks fails this; the emitter must
  interleave at row granularity.
- Every `(cell, n, rep)` group must contain exactly one distinct
  **`(ptok, otok_req)`** pair — `Row.requested()`, the work asked for (`:70-99`).
  `otok` is not compared: it is what came back. Resolved: §6.2.

---

## 4. The artifact files

**Nine files. Seven TSV, two JSON.** The `behaviour` string is printed verbatim
in the RED failure message (`sweeprows.py:329-332`). It now lives in **one**
place, the `BEHAVIOUR` registry (`sweeprows.py:307-316`), reached through
`owed(name)` (`:336-342`) — one artifact, one script (§6.5).

| file | `behaviour` string | cite |
|---|---|---|
| `srv1-lcpp-arms.tsv` | `run tools/runs/srv1-kernel-arms.sh` | `sweeprows.py:308` |
| `srv1-moe-slots.tsv` | `run tools/runs/srv1-moe-slots.sh` | `sweeprows.py:309` |
| `srv1-vllm-arms.tsv` | `run tools/runs/srv1-vllm-arms.sh` | `sweeprows.py:310` |
| `srv1-llama-bench.tsv` | `run tools/runs/srv1-llama-bench.sh` | `sweeprows.py:311` |
| `srv1-build-ladder.tsv` | `run tools/runs/srv1-build-ladder.sh` | `sweeprows.py:312` |
| `srv1-aa-null.tsv` | `run tools/runs/srv1-aa-null.sh` | `sweeprows.py:313` |
| `srv1-ncmoe-floor.tsv` | `run tools/runs/srv1-ncmoe-floor.sh` | `sweeprows.py:314` |
| `placement-null.json` | *(none — read with `Path.read_text`)* | `test_placement_...:38,52` |
| `correctness.json` | *(none — read with `Path.read_text`)* | `test_a_faster_arm_...:32,50` |

The seven shell scripts named — `srv1-kernel-arms.sh`, `srv1-moe-slots.sh`,
`srv1-vllm-arms.sh`, `srv1-llama-bench.sh`, `srv1-build-ladder.sh`,
`srv1-aa-null.sh`, `srv1-ncmoe-floor.sh` — do not exist; `tools/runs/` is absent
from the tree today. Nothing asserts they exist; the strings are message text
only. They map onto the campaign's step list
(`lcp-vllm-3-arm-run.md:111-128`) one script per step, which is why the file is
announced as the output of the step that produces it and not of the campaign.

### 4.1 `placement-null.json`
`test_placement_is_not_declared_output_neutral_without_a_measurement.py:50-89`.
Top-level object with:
`model` (truthy), `tier` (truthy), `cells`,
`run_a` and `run_b`, each an object with `n_cpu_moe` and `serving_build` — the
two `n_cpu_moe` values as a set must equal `{0, 99}` (**integers**, `:54`) and
the two `serving_build` values must be equal (`:57`);
`flips == 0` (`:60`); `acceptance_drift == 0` (`:65`);
`bound` — an object with `serving_build` equal to `run_a.serving_build` (`:84`)
and `cells` equal to the top-level `cells` (`:88`).

### 4.2 `correctness.json`
`test_a_faster_arm_that_answers_differently_has_not_won.py:48-95`.
Top-level object with:
`arms` — a list; each entry has `arm`, `serving_build`, `cells`, `drift_pp`,
`acceptance_drift == 0`, optional `is_reference` (**exactly one** entry truthy,
`:80-83`), and `self_null` — an object with `serving_build` equal to the arm's
(`:65`), `cells` equal to the arm's (`:70`), and `bound_pp` (`:87`);
`verdicts` — a list; each entry has `question` and `winner`, and every `winner`
must appear in `{a["arm"] for a in arms}` (`:51-57`).
For every non-reference arm, `drift_pp <= max(own bound_pp, reference bound_pp)`
(`:87-92`).

---

## 5. Per-file readers and illustrative shapes

> **ILLUSTRATIVE SHAPE, NOT DATA.** Every number, hash, path and reason below is
> a placeholder chosen to make the structure legible. None of it was measured.
> **⇥ = one literal TAB.**

### 5.1 `srv1-lcpp-arms.tsv`

Read by: `test_one_workload_or_no_comparison` (parametrised),
`test_a_row_that_does_not_name_its_arm_is_not_a_measurement` (all three tests),
`test_a_row_without_the_rigs_live_state_is_not_comparable` (both, parametrised),
`test_one_observation_is_not_an_effect` (first three tests).

```
### WORKLOAD digest=2f2bb7932a0b660653def819 driver=lcp_sweep_31-08-2026.py
### START uptime_since=2026-09-02T06:00:00Z pl1_uw=95000000 pl2_uw=120000000 pl1_source=constraint_0_power_limit_uw cpu_max_mhz=4600 ram_mt_s=3600
### RIG cpu_max_mhz=4600 ram_mt_s=3600 pl1_uw=95000000 pl2_uw=120000000 driver=580.173.02 gpu_reserve_mib=377
### BUILD arm=L0 commit=PLACEHOLDER40HEX image_sha256=PLACEHOLDER64HEX cuda_architectures=75-real;75-virtual force_mmq=OFF ggml_native=OFF cpu_all_variants=ON patched=no
### BUILD arm=L2 commit=PLACEHOLDER40HEX image_sha256=PLACEHOLDER64HEX cuda_architectures=61-virtual;80-virtual force_mmq=ON ggml_native=OFF cpu_all_variants=ON patched=no
srv1⇥L0-d3b np=8 ctx_slot=2048 c=16384 ncmoe=0⇥CONFIG⇥arm=L0⇥img=llamacpp:b10644-L0⇥real_ctx_slot=2048⇥vram=0⇥warm_ptok=0
srv1⇥L2-d3b np=8 ctx_slot=2048 c=16384 ncmoe=0⇥CONFIG⇥arm=L2⇥img=llamacpp:b10644-L2⇥real_ctx_slot=2048⇥vram=0⇥warm_ptok=0
srv1⇥L0-d3b np=8 ctx_slot=2048 c=16384 ncmoe=0⇥n=1⇥arm=L0⇥img=llamacpp:b10644-L0⇥rep=1⇥agg=0.0⇥ptok=0⇥otok_req=0⇥otok=0⇥early_stop=0/1⇥failed=0/1⇥wall=0.0
srv1⇥L2-d3b np=8 ctx_slot=2048 c=16384 ncmoe=0⇥n=1⇥arm=L2⇥img=llamacpp:b10644-L2⇥rep=1⇥agg=0.0⇥ptok=0⇥otok_req=0⇥otok=0⇥early_stop=0/1⇥failed=0/1⇥wall=0.0
srv1⇥L0-d3b np=8 ctx_slot=2048 c=16384 ncmoe=0⇥n=1⇥arm=L0⇥img=llamacpp:b10644-L0⇥rep=2⇥agg=0.0⇥ptok=0⇥otok_req=0⇥otok=0⇥early_stop=0/1⇥failed=0/1⇥wall=0.0
srv1⇥L2-d3b np=8 ctx_slot=2048 c=16384 ncmoe=0⇥n=1⇥arm=L2⇥img=llamacpp:b10644-L2⇥rep=2⇥agg=0.0⇥ptok=0⇥otok_req=0⇥otok=0⇥early_stop=0/1⇥failed=0/1⇥wall=0.0
srv1⇥L0-d3b np=8 ctx_slot=2048 c=16384 ncmoe=0⇥n=1⇥arm=L0⇥img=llamacpp:b10644-L0⇥rep=3⇥agg=0.0⇥ptok=0⇥otok_req=0⇥otok=0⇥early_stop=0/1⇥failed=0/1⇥wall=0.0
srv1⇥L2-d3b np=8 ctx_slot=2048 c=16384 ncmoe=0⇥n=1⇥arm=L2⇥img=llamacpp:b10644-L2⇥rep=3⇥agg=0.0⇥ptok=0⇥otok_req=0⇥otok=0⇥early_stop=0/1⇥failed=0/1⇥wall=0.0
srv1⇥L0-d3b np=8 ctx_slot=2048 c=16384 ncmoe=0⇥n=1⇥arm=L0⇥img=llamacpp:b10644-L0⇥rep=4⇥agg=0.0⇥ptok=0⇥otok_req=0⇥otok=0⇥early_stop=0/1⇥failed=0/1⇥wall=0.0
srv1⇥L2-d3b np=8 ctx_slot=2048 c=16384 ncmoe=0⇥n=1⇥arm=L2⇥img=llamacpp:b10644-L2⇥rep=4⇥agg=0.0⇥ptok=0⇥otok_req=0⇥otok=0⇥early_stop=0/1⇥failed=0/1⇥wall=0.0
srv1⇥L0-d3b np=8 ctx_slot=2048 c=16384 ncmoe=0⇥n=1⇥arm=L0⇥img=llamacpp:b10644-L0⇥rep=5⇥agg=0.0⇥ptok=0⇥otok_req=0⇥otok=0⇥early_stop=0/1⇥failed=0/1⇥wall=0.0
srv1⇥L2-d3b np=8 ctx_slot=2048 c=16384 ncmoe=0⇥n=1⇥arm=L2⇥img=llamacpp:b10644-L2⇥rep=5⇥agg=0.0⇥ptok=0⇥otok_req=0⇥otok=0⇥early_stop=0/1⇥failed=0/1⇥wall=0.0
### END uptime_since=2026-09-02T06:00:00Z pl1_uw=95000000 pl2_uw=120000000 cpu_max_mhz=4600 ram_mt_s=3600
```

Ten level rows over two arms give `blocks = 10 >= 2 * 5` (`:63`) and five
replicates each (`:47`). `L0-d3b` and `L2-d3b` now share cell `d3b`, so each
`(d3b, 1, rep)` group holds **both** arms' rows and the requested-draw check
(`:93`) is a real comparison: the two rows must agree on `ptok` and `otok_req`.
They need not agree on `otok`, and are not expected to.

### 5.2 `srv1-moe-slots.tsv`

Read by: `test_one_workload_or_no_comparison`,
`test_a_row_that_does_not_name_its_arm_is_not_a_measurement` (first test only),
`test_a_row_without_the_rigs_live_state_is_not_comparable` (both),
`test_a_crash_not_reproduced_is_not_a_crash_fixed` (all four).

Labels carry the arm and the **cell** is shared across `L2` and `L3`:
`L2-mling` and `L3-mling` both resolve to cell `mling` (§1.5, §3.2). `L2` must be
present at every width `n=1..12` — as a `CRASH` row with `n=` or as a level row
(`:51-62`). Two distinct **cells** minimum (`:101`), which means two checkpoints,
not two arms.

```
### WORKLOAD digest=2f2bb7932a0b660653def819 driver=lcp_sweep_31-08-2026.py
### START uptime_since=2026-09-02T06:00:00Z pl1_uw=95000000 pl2_uw=120000000 pl1_source=constraint_0_power_limit_uw cpu_max_mhz=4600 ram_mt_s=3600
### RIG cpu_max_mhz=4600 ram_mt_s=3600 pl1_uw=95000000 pl2_uw=120000000 driver=580.173.02 gpu_reserve_mib=377
srv1⇥L2-mling np=8 ctx_slot=2048 c=16384 ncmoe=0⇥n=1⇥arm=L2⇥img=llamacpp:b10644-L2⇥agg=0.0⇥ptok=0⇥otok=0⇥failed=0/1⇥trials=1
srv1⇥L2-mling np=8 ctx_slot=2048 c=16384 ncmoe=0⇥CRASH⇥arm=L2⇥img=llamacpp:b10644-L2⇥n=8⇥http_000=8/8⇥0.00.000.000 E CUDA error: invalid argument in ggml_cuda_mul_mat_vec_q at PLACEHOLDER
srv1⇥L3-mling np=8 ctx_slot=2048 c=16384 ncmoe=0⇥n=8⇥arm=L3⇥img=llamacpp:b10644-L3⇥trials=60⇥agg=0.0⇥ptok=0⇥otok=2⇥failed=0/8
srv1⇥L2-d3b np=8 ctx_slot=2048 c=16384 ncmoe=0⇥CRASH⇥arm=L2⇥img=llamacpp:b10644-L2⇥n=9⇥http_000=9/9⇥0.00.000.000 E CUDA error: invalid argument in ggml_cuda_mul_mat_vec_q at PLACEHOLDER
srv1⇥L3-d3b np=8 ctx_slot=2048 c=16384 ncmoe=0⇥n=9⇥arm=L3⇥img=llamacpp:b10644-L3⇥trials=60⇥agg=0.0⇥ptok=0⇥otok=2⇥failed=0/9
### BOUNDARY arm=L2 first_failing_n=8
### END uptime_since=2026-09-02T06:00:00Z pl1_uw=95000000 pl2_uw=120000000 cpu_max_mhz=4600 ram_mt_s=3600
```

(The real file needs `L2` rows at every one of `n=1..12`; two are shown.)
The crash reason must contain both `ggml_cuda_mul_mat_vec_q` and
`invalid argument` (`:28,37-43`) — **RIG-ONLY**, the text comes from the engine
log. `http_000` numerator must equal denominator (`:44-45`). `otok` on the `L3`
rows is *generated* output and must exceed 1 (`:92`) — that the patched build
produced tokens, not that it produced the same ones.

### 5.3 `srv1-vllm-arms.tsv`

Read by: `test_one_workload_or_no_comparison`,
`test_a_row_that_does_not_name_its_arm_is_not_a_measurement` (first test),
`test_a_row_without_the_rigs_live_state_is_not_comparable` (both),
`test_two_backends_on_one_checkpoint_is_the_only_pair` (all four).

```
### WORKLOAD digest=2f2bb7932a0b660653def819 driver=vllm_sweep_31-08-2026.py
### START uptime_since=2026-09-02T06:00:00Z pl1_uw=95000000 pl2_uw=120000000 pl1_source=constraint_0_power_limit_uw cpu_max_mhz=4600 ram_mt_s=3600
### RIG cpu_max_mhz=4600 ram_mt_s=3600 pl1_uw=95000000 pl2_uw=120000000 driver=580.173.02 gpu_reserve_mib=377
srv1⇥B1-gptq util=0.90 len=2048 seqs=8 kv=auto⇥CONFIG⇥arm=B1⇥img=vllm/vllm-openai:v0.26.0⇥model=PLACEHOLDER/checkpoint⇥weights_sha256=PLACEHOLDER64HEX⇥util=0.90⇥len=2048⇥seqs=8⇥kv=auto⇥kernel_observed=gptq_marlin⇥vram=0
srv1⇥B2-gptq util=0.90 len=2048 seqs=8 kv=auto⇥CONFIG⇥arm=B2⇥img=vllm/vllm-openai:v0.26.0⇥model=PLACEHOLDER/checkpoint⇥weights_sha256=PLACEHOLDER64HEX⇥util=0.90⇥len=2048⇥seqs=8⇥kv=auto⇥kernel_observed=exllama⇥vram=0
srv1⇥B1-gptq util=0.90 len=2048 seqs=8 kv=auto⇥n=1⇥arm=B1⇥img=vllm/vllm-openai:v0.26.0⇥agg=0.0⇥ptok=0⇥otok_req=0⇥otok=0⇥failed=0/1
srv1⇥B2-gptq util=0.90 len=2048 seqs=8 kv=auto⇥n=1⇥arm=B2⇥img=vllm/vllm-openai:v0.26.0⇥agg=0.0⇥ptok=0⇥otok_req=0⇥otok=0⇥failed=0/1
### VERDICT hypothesis=tensor-core-emulation status=unresolved cited_line=6
### END uptime_since=2026-09-02T06:00:00Z pl1_uw=95000000 pl2_uw=120000000 cpu_max_mhz=4600 ram_mt_s=3600
```

`cited_line=6` is the `lineno` of the first `CONFIG` row above (lines 1-3 are
markers). Recount it whenever the file changes — the check is exact (`:139-143`).

The pair is `--linear-backend marlin` (B1) against `--linear-backend exllama`
(B2) on one checkpoint. `kernel_observed=` is parsed from the engine's
`Using {Marlin,Exllama}LinearKernel for AutoGPTQLinearMethod`.

**If `B2` never launches** — srv1 holds no GPTQ file, so the arm is behind a
fetch and may still be refused — drop both its `CONFIG` row and its level row and
emit a refusal instead (§6.3):

```
srv1⇥B2-gptq util=0.90 len=2048 seqs=8 kv=auto⇥REFUSED⇥arm=B2⇥img=vllm/vllm-openai:v0.26.0⇥checkpoint_quant=gptq⇥tries=3⇥0.00 ExllamaLinearKernel cannot implement due to: PLACEHOLDER reason text of at least forty-one characters
```

That row is now what a missing `CONFIG` costs: `checkpoint_quant`, a reason over
40 characters, and `tries>=3` (`:56-65`). `B1` must still have a `CONFIG`
(`:81-84`), and `status` must then not be `supported` (`:144-149`).

### 5.4 `srv1-llama-bench.tsv`

Read by: `test_one_workload_or_no_comparison::test_microbenchmarks_are_filed_...`,
`test_a_prefill_verdict_needs_an_instrument_that_measures_prefill` (all three).

Emit **no `n=<int>` rows** in this file, so that `sweep.levels()` is empty and
`rows = sweep.levels() or list(sweep.of_kind("BENCH"))` (`:34`) resolves to the
`BENCH` rows that also carry `reps`/`stddev`/`fa`.

It also needs `### WORKLOAD digest=none comparable_with=microbenchmark-only`
(§2.1) — shown below.

```
### TOOL name=llama-bench
### WORKLOAD digest=none comparable_with=microbenchmark-only
srv1⇥L0-p512⇥BENCH⇥arm=L0⇥fa=0⇥pp=0.00⇥tg=0.00⇥reps=9⇥stddev=0.00
srv1⇥L0-p512⇥BENCH⇥arm=L0⇥fa=1⇥pp=0.00⇥tg=0.00⇥reps=9⇥stddev=0.00
srv1⇥L1-p512⇥BENCH⇥arm=L1⇥fa=0⇥pp=0.00⇥tg=0.00⇥reps=9⇥stddev=0.00
srv1⇥L1-p512⇥BENCH⇥arm=L1⇥fa=1⇥pp=0.00⇥tg=0.00⇥reps=9⇥stddev=0.00
srv1⇥L2-p512⇥BENCH⇥arm=L2⇥fa=0⇥pp=0.00⇥tg=0.00⇥reps=9⇥stddev=0.00
srv1⇥L2-p512⇥BENCH⇥arm=L2⇥fa=1⇥pp=0.00⇥tg=0.00⇥reps=9⇥stddev=0.00
srv1⇥L3-p512⇥BENCH⇥arm=L3⇥fa=0⇥pp=0.00⇥tg=0.00⇥reps=9⇥stddev=0.00
srv1⇥L3-p512⇥BENCH⇥arm=L3⇥fa=1⇥pp=0.00⇥tg=0.00⇥reps=9⇥stddev=0.00
srv1⇥A3-p512⇥BENCH⇥arm=A3⇥fa=0⇥pp=0.00⇥tg=0.00⇥reps=9⇥stddev=0.00
srv1⇥A3-p512⇥BENCH⇥arm=A3⇥fa=1⇥pp=0.00⇥tg=0.00⇥reps=9⇥stddev=0.00
```

`ARMS = ("L0","L1","L2","L3","A3")` is declared at
`test_a_prefill_...:25` and **never referenced by any test**; no test constrains
which arms appear. The `fa` rule applies to whatever arms *do* appear (`:65-71`).
No `RIG`/`START`/`END`/`arm`/`img` per-row rules reach this file.

These rows are the campaign's step 3 (`lcp-vllm-3-arm-run.md:117-118`) and this
file is their authoritative record: the spread (`reps`, `stddev`) and the
`-fa 0,1` coverage are asserted here and nowhere else (§6.4).

### 5.5 `srv1-build-ladder.tsv`

Read by: `test_a_six_variable_diff_does_not_attribute_a_gain` (all three).

```
### WORKLOAD digest=none comparable_with=microbenchmark-only
### BUILD arm=L0 commit=PLACEHOLDER40HEX image_sha256=PLACEHOLDER64HEX cuda_architectures=75-real;75-virtual force_mmq=OFF ggml_native=OFF cpu_all_variants=ON patched=no
### BUILD arm=L1 commit=PLACEHOLDER40HEX image_sha256=PLACEHOLDER64HEX cuda_architectures=75-real;75-virtual force_mmq=ON ggml_native=OFF cpu_all_variants=ON patched=no
### BUILD arm=L2 commit=PLACEHOLDER40HEX image_sha256=PLACEHOLDER64HEX cuda_architectures=61-virtual;80-virtual force_mmq=ON ggml_native=OFF cpu_all_variants=ON patched=no
### BUILD arm=L3 commit=PLACEHOLDER40HEX image_sha256=PLACEHOLDER64HEX cuda_architectures=61-virtual;80-virtual force_mmq=ON ggml_native=OFF cpu_all_variants=ON patched=yes
### BUILD arm=L4 commit=PLACEHOLDER40HEX image_sha256=PLACEHOLDER64HEX cuda_architectures=75-real;75-virtual force_mmq=OFF ggml_native=ON cpu_all_variants=OFF patched=no
### KERNELS arm=L0 tensor_core_instructions=present
### KERNELS arm=L1 tensor_core_instructions=present
### KERNELS arm=L2 tensor_core_instructions=absent
### KERNELS arm=L3 tensor_core_instructions=absent
### KERNELS arm=L4 tensor_core_instructions=present
srv1⇥L0-p512⇥BENCH⇥arm=L0⇥img=llamacpp:b10644-L0⇥pp=0.00⇥tg=0.00
srv1⇥L1-p512⇥BENCH⇥arm=L1⇥img=llamacpp:b10644-L1⇥pp=0.00⇥tg=0.00
srv1⇥L2-p512⇥BENCH⇥arm=L2⇥img=llamacpp:b10644-L2⇥pp=0.00⇥tg=0.00
srv1⇥L3-p512⇥BENCH⇥arm=L3⇥img=llamacpp:b10644-L3⇥pp=0.00⇥tg=0.00
srv1⇥L4-p512⇥BENCH⇥arm=L4⇥img=llamacpp:b10644-L4⇥pp=0.00⇥tg=0.00
```

Note `L0→L1` moves only `force_mmq`, `L1→L2` only `cuda_architectures`, `L2→L3`
only `patched` (`:73-79`). `L4` is on no checked pair. The `KERNELS` values are
**RIG-ONLY** (`cuobjdump` output); `L4`'s `KERNELS` stamp is not asserted.

The `BENCH` rows are the **same** `llama-bench` measurement as §5.4, projected to
one row per rung and re-filed beside the stamps that make the ladder readable in
one place (§6.4). They carry no `fa`/`reps`/`stddev` — nothing reads those here —
and the file is stamped digest-free, because a rung quoted as a serving gain is
exactly the misreading guideline 4 blocks.

### 5.6 `srv1-aa-null.tsv`

Read by: `test_one_observation_is_not_an_effect::test_the_instrument_was_priced_...`
only.

Requires level rows carrying `agg=`, at least one `(cell, n)` group with two or
more rows, and a `### NULL spread_pct=` within `0.5` of the observed maximum
percentage spread (`:107-123`). No `arm`, `img`, `RIG`, `WORKLOAD` rule reaches
this file. It is an A/A null, so all rows are one arm and the label prefix is
`L3-`; grouping is by `(cell, n)` and the prefix strips.

```
### NULL spread_pct=0.0
srv1⇥L3-d3b np=8 ctx_slot=2048 c=16384 ncmoe=0⇥n=1⇥arm=L3⇥rep=1⇥agg=100.0⇥ptok=0⇥otok_req=0⇥otok=0
srv1⇥L3-d3b np=8 ctx_slot=2048 c=16384 ncmoe=0⇥n=1⇥arm=L3⇥rep=2⇥agg=100.0⇥ptok=0⇥otok_req=0⇥otok=0
srv1⇥L3-d3b np=8 ctx_slot=2048 c=16384 ncmoe=0⇥n=4⇥arm=L3⇥rep=1⇥agg=100.0⇥ptok=0⇥otok_req=0⇥otok=0
srv1⇥L3-d3b np=8 ctx_slot=2048 c=16384 ncmoe=0⇥n=4⇥arm=L3⇥rep=2⇥agg=100.0⇥ptok=0⇥otok_req=0⇥otok=0
```

**RIG-ONLY** for the value: `spread_pct` must equal the file's own measured
spread; a script cannot pick it.

### 5.7 `srv1-ncmoe-floor.tsv`

Read by: `test_an_ncmoe_floor_is_derived_and_not_copied` (all three).

```
### FLOOR arm=L3 usable_mib=5500 cuda_ctx_mib=400 nonexpert_mib=900 kv_mib=700 expert_total_mib=4000 n_layers=28 predicted=8.4 measured=9
### FLOOR arm=A3 usable_mib=5300 cuda_ctx_mib=650 nonexpert_mib=900 kv_mib=700 expert_total_mib=4000 n_layers=28 predicted=11.9 measured=12
srv1⇥L3-mling np=8 ctx_slot=2048 c=16384 ncmoe=8⇥REFUSED⇥arm=L3⇥img=llamacpp:b10644-L3⇥tries=3⇥0.00.000.000 E srv load_model: failed to create_context with model PLACEHOLDER at ncmoe=8, out of memory
srv1⇥L3-mling np=8 ctx_slot=2048 c=16384 ncmoe=9⇥CONFIG⇥arm=L3⇥img=llamacpp:b10644-L3⇥vram=0
srv1⇥A3-mling np=8 ctx_slot=2048 c=16384 ncmoe=11⇥REFUSED⇥arm=A3⇥img=llamacpp:b10644-A3⇥tries=3⇥0.00.000.000 E srv load_model: failed to create_context with model PLACEHOLDER at ncmoe=11, out of memory
srv1⇥A3-mling np=8 ctx_slot=2048 c=16384 ncmoe=12⇥CONFIG⇥arm=A3⇥img=llamacpp:b10644-A3⇥vram=0
```

Check the arithmetic: L3 gives `(1 - (5500-400-900-700)/4000) * 28 = 3500/4000
→ 0.875 → 0.125 * 28 = 3.5`, which is **not** within 1.0 of `predicted=8.4` —
the numbers above are placeholders and deliberately do not reconcile. The run
must emit inputs that reproduce their own `predicted` to `±1.0` (`:52-56`).
**RIG-ONLY**: `measured` and the refusal text come from launches.

---

## 6. CONFLICTS — resolved 2026-09-02

Requirements that pulled against each other. Each is now decided, by the
guideline named, in `tests/sweeprows.py` and the twelve tests. Nothing was
weakened: every test still checks what it checked, and all twelve remain
`xfail(strict=True)` with their dated reasons — they are RED until the rig runs.

### 6.1 `Row.cell` stripped `[AB][0-9]-` but the ladder arms are named `L0`–`L4`

**Was.** `sweeprows.py` removed the tag prefix only when it fullmatched
`[AB][0-9]`, so `L0-d3b` had cell `L0-d3b` while `A3-d3b` had cell `d3b`. Two
tests then needed opposite labelling conventions:
`test_a_row_that_does_not_name_its_arm_...:54-63` wants the arm *in* the label
(no label shared by two arms), and `test_a_crash_...:78-84` wants an `L3` row and
an `L2` `CRASH` row to share a **cell**, which for `L` arms was only reachable by
sharing the whole label. One emitter could not do both.

**Decided by guideline 2** — "two rows are comparable only if `ptok` and `otok`
match". That rule pairs rows before it compares them, and the pairing key is
`(cell, n, rep)`; a cell that changes identity with the arm cannot pair anything.
Guideline 1's interleaved replicates need the same pairing to mean anything. The
`L` arms were outside it by an accident of one regex, not by intent —
`sweeprows.py`'s own docstring already said the prefix is stripped "so arms can
be aligned".

**Resolution.** `ARM_PREFIX = [ABL][0-9]` (`sweeprows.py:49`) — every arm this
campaign names (`lcp-vllm-3-arm-run.md:37-54`) strips. That collapses the two
conventions into one: **`<ARM>-<cell> <settings...>` on every label, in every
file** (§3.2). The arm is in the label, so no label is shared; the cell is not,
so `L2-mling` and `L3-mling` align. No test assertion changed.

**Second defect it closed.** `test_a_crash_...:100-101` asserts two distinct
cells, meaning two MoE checkpoints with different expert geometry. Under the old
parser `L2-mling` and `L3-mling` counted as two cells, so one checkpoint driven
under two arms would have passed a test about two checkpoints. It no longer does.

### 6.2 Draw-matching demanded `otok` equality that the campaign says cannot hold

**Was.** `test_one_observation_...:63-77` (pre-fix) required every `(cell, n, rep)` group to
hold exactly one `(ptok, otok)` pair, while
`test_a_faster_arm_that_answers_differently_has_not_won.py:5-8` records as the
campaign's premise that the arms run different kernels and the 2026-09-01 A/B
already reads `otok` **214 against 221 on one cell at `temperature: 0`**. Where
the cells aligned, the assertion was unsatisfiable by an honest run; where they
did not (the `L` arms, before §6.1), it was vacuous. §6.1 makes the cells align
everywhere, so this had to be settled or it would have become unsatisfiable
everywhere.

**Decided by guideline 2** — and by reading it for the quantity it names.
Guideline 2 is about **draw sync**: "the prompt draw comes from a per-process
counter; changing the level list desyncs it, measured at 6.2%". That is the work
*requested* — the prompt drawn and the output budget asked for. What test 11 is
about is **answers differing**: generated output, an outcome of the kernel. These
are two quantities that the drivers happened to print under one name.

**Resolution — they are different, and now have different names.**

- `otok_req` is new: the per-request output budget the driver asked for. A plan,
  equal across arms by construction, and therefore a real check when it is not.
- `otok` keeps its meaning: tokens actually generated. Expected to differ across
  arms; **nothing asserts otherwise**.
- `Row.requested()` → `(ptok, otok_req)` (`sweeprows.py:169-183`) is guideline 2's
  quantity and is what `test_one_observation_...:70-99` now groups on.
- `Row.draw()` → `(ptok, otok)` (`:152-167`) is unchanged and keeps its one live
  caller, `test_a_row_parser_...:72`, which uses it to show that
  `prefill/agg ≡ ptok/otok` — a statement about a single row's arithmetic, where
  the emitted count is exactly the right quantity.

Neither test was weakened: test 7 still demands matched draws, test 11 still
scores the answers through the gate against a bound each arm measured. The
campaign's own division of labour — guideline 2 for honesty, guideline 9 for
correctness — is now visible in the field names.

### 6.3 A `REFUSED` `B2` had to also produce a `CONFIG` row it never earned

**Was.** `test_two_backends_...:43` asserted `{"B1","B2"} <= set(configs)` and
`:45-48` compared seven held fields between the two `CONFIG` rows — but `:69-79`
and the file's docstring hold that `B2` may legitimately never launch, and the
drivers print `CONFIG` only *after* a successful launch and warm-up. Satisfying
`:43` for a refused `B2` meant emitting a `CONFIG` row describing an engine that
never came up, carrying a `kernel_observed=` for a kernel that never ran.

**Decided by guideline 8** — "a refusal is a result. Retry three times before
believing it, and record the reason." A result is a thing the file *says*, not a
hole it leaves. So B2 is exempt from `CONFIG`, and the exemption has a price.

**Resolution** (`test_two_backends_...:46-100`):

- `B1` must have a `CONFIG` row. It is the default Marlin path; without it there
  is no baseline and no contrast.
- `B2` must appear as **either** a `CONFIG` row **or** a `REFUSED` row. A dropped
  arm and a refused arm leave an identical hole, and only one is a result.
- The seven held fields are compared **only when both arms produced a `CONFIG`**.
- A `B2` with no `CONFIG` must clear `a_recorded_refusal()` (`:46-66`):
  `checkpoint_quant`, a reason over 40 characters, and `tries>=3` — guideline 8's
  own bar, the same one `test_an_ncmoe_floor_...:83-86` already applies, and the
  reason two REFUSED rows on 2026-09-01 turned out to be a dangling HF-blob
  symlink read as a capability limit.
- `kernel_observed` stays conditional (`:114-117`, unchanged): an arm with no
  `CONFIG` has no engine log line to read. That skip is no longer a loophole,
  because the arm it excuses has already been made to produce a refusal.

**Still live** (verified 2026-09-02, see `B2-CHECKPOINT.md`): `--linear-backend`
does exist in v0.26.0 with `exllama` among its choices — the August AWQ refusal
was the kernel rejecting uint4, not a missing flag — but srv1 holds **no GPTQ
checkpoint at all**, so B2 sits behind a fetch and "B2 never launched" remains an
outcome this conditional must handle. The pair is `--linear-backend marlin`
against `--linear-backend exllama`; the run doc's `--quantization gptq` vs
`gptq_marlin` fallback moves nothing in v0.26.0.

### 6.4 Two files must both carry `BENCH` rows for `L0`–`L3`

**Was.** `test_a_six_variable_diff_...:56-57` needs `BENCH` rows for `L0..L4` in
`srv1-build-ladder.tsv`; `test_a_prefill_...:52-71` needs `BENCH` rows with
`reps`, `stddev` and both `fa=0` and `fa=1` in `srv1-llama-bench.tsv`. Nothing
said whether these were one measurement or two.

**Decided by guideline 4** — "microbenchmarks carry no workload digest. File them
apart; never mix them into a serving claim."

**Resolution: one measurement, two filings, and the rule reaches both files.**
Both sets of rows are step 3 (`lcp-vllm-3-arm-run.md:117-118`), which the run doc
routes to tests #5 *and* #6. So:

- `srv1-llama-bench.tsv` is the **instrument record**: every `-p`/`-fa`
  combination, with `reps>=9` and `stddev`. The spread and `-fa 0,1` coverage are
  asserted here and nowhere else.
- `srv1-build-ladder.tsv` re-files a **projection** — one `BENCH` row per rung —
  beside the `BUILD` and `KERNELS` stamps, so the one-variable chain and the
  static mechanism check read in one place. It carries `pp`/`tg` and no
  `fa`/`reps`/`stddev`, because nothing reads those there.
- **Both** are now stamped `### WORKLOAD digest=none comparable_with=microbenchmark-only`.
  `test_microbenchmarks_are_filed_where_no_cross_engine_claim_can_reach_them` is
  parametrised over `MICROBENCH = ("srv1-llama-bench.tsv", "srv1-build-ladder.tsv")`
  (`test_one_workload_...:38,71-91`). Stamping only the file named after the tool
  would have left the ladder — the file a reader goes to for "what is this rung
  worth" — free to be read as a serving claim, which is the misreading that
  produced "the arch spoof is worth 1.7x".

The two files must not disagree; the ladder's rows are copied from the
instrument's, never re-measured.

### 6.5 `srv1-moe-slots.tsv` and `srv1-vllm-arms.tsv` each carried two behaviour strings

**Was.** `artifact()` was called on `srv1-moe-slots.tsv` with
`run tools/runs/srv1-kernel-arms.sh` from three files and with
`run tools/runs/srv1-moe-slots.sh` from a fourth; `srv1-vllm-arms.tsv` likewise.
The string is never compared, so nothing broke — which is why it drifted. A
reader of the RED output was told two different scripts produce one file.

**Decided by guideline 5** — "the `L`/`A` arms and the `B` arms are two studies
sharing a rig and a workload" — read together with the campaign's step list
(`lcp-vllm-3-arm-run.md:111-128`), which is explicitly ordered so that each step
can be run and lost independently. An artifact names the one step that produces
it, not the campaign it belongs to.

**Resolution.** One registry, `BEHAVIOUR` (`sweeprows.py:307-316`), reached
through `owed(name)` (`:336-342`). Every test now takes its artifact by file name
and cannot supply its own string. `srv1-moe-slots.tsv` → `srv1-moe-slots.sh`
(the crash study, step 7); `srv1-vllm-arms.tsv` → `srv1-vllm-arms.sh` (the vLLM
capability study, step 8); `srv1-lcpp-arms.tsv` → `srv1-kernel-arms.sh` (the
serving sweep, step 4). Full table in §4.

### 6.6 A malformed stamp header read as an absent stamp

**Was.** `parts and parts[0] == word` returned `{}` for a bare `###` line and for
a marker whose first token was `key=value` (`### digest=...`, a stamp that lost
its name). `{}` is also what an *absent* stamp returns, and absence is meaningful:
`test_a_row_without_...:44` reads a missing `### END` as "the run did not close,
or the pipe died with it". A broken emitter and a hard lock produced the same
message.

**Decided by guideline 7** — "stamp the rig on every row, and re-read it at the
end". A stamp that cannot be read is not a stamp that is missing.

**Resolution.** `_stamp_name(lineno, line)` (`sweeprows.py:52-75`) raises
`ValueError` for both cases, on every marker in the file, for every lookup.
Free-text markers still coexist (`### IMAGE ghcr.io/...`,
`### control: committed ...`) — only a *nameless* header raises.

### 6.7 A stamp value containing a space silently lost its tail

**Was.** A marker is `.split()` on whitespace, so
`uptime_since=2026-09-01 08:11:08`
(`records/.../srv1-locktest-ling-60min.tsv:1`) parsed as
`uptime_since=2026-09-01` and dropped the clock — silently. START and END then
compared **equal** across two different moments, and guideline 7's re-read passed
on a run whose end state was never actually read. That is the exact failure mode
`test_a_row_without_the_rigs_live_state_is_not_comparable` exists to catch,
passing through the parser that implements it.

**Decided by guideline 7**, same clause, and by the choice between "robust" and
"loud": a continuation rule (append a non-`k=v` token to the previous value)
would have guessed, and a guess here is a rig state nobody read.

**Resolution.** `_stamp_fields(lineno, line)` (`sweeprows.py:77-101`) raises
`ValueError` on any token after the stamp name that is not `key=value`. It runs
only on markers whose name matches the lookup, so an unrelated free-text marker
elsewhere in the file does not poison a `stamp("RIG")`. Row fields are unaffected
— a tab-delimited row value may still contain spaces (§1.2). Emit `T`-joined or
underscore-joined stamp values.

## 7. Notes for the emitter, from the existing drivers

- The three drivers print `host⇥label⇥kind⇥k=v...` today
  (`lcp_sweep_31-08-2026.py:197-224`, `vllm_sweep_31-08-2026.py:277-306`) and
  emit **none** of `arm`, `rep`, `otok_req`, `trials`, `http_000`, `model`,
  `weights_sha256`, `kernel_observed`, `checkpoint_quant`, `tries`, `pp`, `tg`,
  `reps`, `stddev`, `fa`. Every one of those is new.
- `vllm_sweep_31-08-2026.py:165` puts `util`, `len`, `seqs`, `kv` in the **label**
  only. `test_two_backends_...:43,94` reads them as **row fields**. They must be
  emitted twice, or moved.
- `vllm_cores_01-09-2026.py:202-208` prints a **five-column** row
  (`host⇥pair⇥tag⇥phase⇥n=N⇥...`), which puts the tag in the `kind` column and
  demotes `n=N` to a field. Rows in that shape are **not** level rows under
  `sweeprows.py:115-117` and will not be seen by `levels()`. Do not reuse that
  layout for any file in this contract.
- `lcp_sweep_31-08-2026.py:214` prints `n=<N>⇥ERR` on a dead cell. That is a
  level row with no `ptok`; it is skipped by
  `test_one_observation_...:88-89` but still counted by `:45` and `:60`, and it
  still needs `arm=` and `img=` under
  `test_a_row_that_does_not_name_its_arm_...:41-43`.
- Do not edit
  `records/evidence/2026-09-01-bandwidth-and-ncmoe-floor/srv1-nomma-dp4a-ab.tsv`.
  `test_a_row_parser_that_reads_nothing_proves_nothing.py:23-78` pins it at
  exactly 18 level rows, 17 with `ptok`, two `img=` values, colliding labels, and
  **no `arm=` field** (`:48-50`). It is the suite's only live exercise of the
  parser, and the only caller of `Row.draw()`.
- That file's own markers would now raise if any test read them as stamps:
  `### AB START ... uptime_since=2026-09-01 08:11:08` is `stamp("AB")` with a
  spaced value (§6.6, §6.7). No test does, and none should — the habit is not to
  be carried into this run's files.
- Level rows in this run must carry `otok_req=` alongside `ptok=` and `otok=`
  (§3, §6.2). The drivers print the requested cap nowhere today; it is the
  `max_tokens` the client asked for, and it is what makes two arms comparable.
