# Resuming the 2026-08-30 concurrency run

**29 cells declared, 25 measured, 4 outstanding.** (The header said "18 measured,
6 outstanding" until 2026-08-31; 18+6 does not reach 29, and 18 corresponds to no
state of this tree at any commit -- it omitted srv1's five llama.cpp cells.)
This file is both the runbook and a prompt you can paste into a fresh session.

---

## Paste this

> Finish the 2026-08-30 serving concurrency run in this repo. Four cells are
> outstanding; 18 are measured and committed. Read
> `records/evidence/serving-2026-08-30/RESUME.md` first — it names the cells,
> the two traps that will silently corrupt a resume, and the exact commands.
> Start by running the status check in that file and tell me what it reports
> before you launch anything. Do not resume against a rig you have not just
> proven reachable: every one of the six losses came from measuring a host that
> had gone away, and the harness recorded some of them as `ok`.

---

## 1. Check the rigs BEFORE anything else

Both outages produced cells that looked measured and were not. Prove
reachability first, from this repo's host:

```bash
for h in srv1 srv2; do
  echo -n "$h: "
  timeout 12 ssh -o ConnectTimeout=10 -o BatchMode=yes "$h" \
    'echo UP; uptime -p; nvidia-smi --query-gpu=memory.used,memory.reserved --format=csv,noheader' \
    2>&1 | tr '\n' ' '; echo
done
```

Expect `UP`, and a near-idle card: single-digit MiB used, ~400 MiB reserved on
srv1 / ~380 MiB on srv2. A timeout means stop — see §5.

**Do not gate on those figures exactly.** Measured 2026-08-30: 401/380 reserved
with 17 MiB used. Measured 2026-08-31 after both rigs rebooted, same driver on
srv1 (580.173.02): **399/377 reserved with 1 MiB used**. The GSP reserve drifts
a couple of MiB across boots and the 17 MiB was a desktop session these headless
boots do not have. The carveout is fixed in magnitude, not bit-stable; a card in
the wrong state is off by hundreds of MiB, not by two. `CARD` in
`tests/test_card_memory_accounting.py` still pins 401/380 — a 2 MiB drift on a
6 GB card changes no conclusion in §8, and re-pinning measured constants to
whatever this boot happens to say is how a measurement becomes a tautology.

## 2. Status check: what is actually done

`outcome: ok` is not sufficient on rows written before commit `d75d90fb`. Judge
the levels directly:

```bash
uv run --no-sync python - <<'PY'
import json, glob, importlib.util, sys
spec = importlib.util.spec_from_file_location("sr", "tools/bench/serving/run.py")
m = importlib.util.module_from_spec(spec); sys.modules["sr"] = m; spec.loader.exec_module(m)
for host in ("srv1", "srv2"):
    cfg = json.load(open(f"tools/bench/serving/configs/srv-lcpp-n1248-{host}.json"))
    last = {}
    for line in open(f"records/evidence/serving-2026-08-30/lcpp-{host}.jsonl"):
        if line.strip():
            r = json.loads(line)
            if r.get("label"):
                last[r["label"]] = r
    print(f"\n=== {host} ===")
    todo = []
    for label in [e["label"] for e in cfg["models"]]:
        r = last.get(label)
        if r is None:
            print(f"  {label:26} NEVER RAN"); todo.append(label); continue
        barren = m.barren_levels(r.get("concurrency") or {})
        if r.get("outcome") == "ok" and not barren:
            print(f"  {label:26} ok")
        else:
            ns = [b["n"] for b in barren]
            print(f"  {label:26} {r.get('outcome'):13} barren={ns or '-'}")
            todo.append(label)
    print(f"  -> {len(todo)} outstanding: {todo}")
PY
```

## 3. The outstanding cells

| host | cell | state | action |
|---|---|---|---|
| srv1 | `m_gemma4-lcpp-srv1` | `ok` with n=8 barren, written before `d75d90fb` | `--retry-failed` (see §4) |
| srv1 | `m_q36iq2-lcpp-srv1` | **`refused`** — `backend_would_not_yield_card` | `--retry-failed` |
| srv1 | `m_oss20-lcpp-srv1` | **`refused`** — same | `--retry-failed` |
| srv2 | `m_next-lcpp-srv2` | never ran | `--resume` |

`m_kat-lcpp-srv2` was measured 2026-08-31 and is no longer outstanding.

**Corrections to what this section used to say.**

*"never started" was wrong for two cells.* `m_q36iq2` and `m_oss20` carry explicit
`refused` rows with `reasons: ["backend_would_not_yield_card"]`. Both are stamped
21:49 and 21:52, inside srv1's 21:28:31--22:10:43 dead window, and both report
`ollama=None MiB, vllm=None MiB` -- the probe returned nothing because the host
was off. The prose blames a co-resident engine for holding a card on a machine
with no power. **Operationally this matters: `completed()` counts a `refused` row
as done, so a plain `--resume` skips them forever. `--retry-failed` is not
optional for these two.**

*"All six are infrastructure losses. None indicates anything about a model or a
config" was false, and it was the most expensive sentence in this file.*
`m_dsv2-lcpp-srv1` froze srv1 **six times** across 2026-08-30 and 2026-08-31, at
n=2, on separate boots, at `parallel 8` and at `parallel 2`. The boots end
mid-log-stream with no shutdown, no OOM kill, no Xid and no MCE. Measured at the
moment of one freeze: 13.6 GB RAM free, card at 1,462 of 6,144 MiB, 54 C, 42 W --
RAM, card and GPU thermals are all uninvolved. The cause is sustained all-core
CPU load from `n_cpu_moe: 99` expert offload; srv1's package power limits were
`4095 W` (unlimited) and it drew 90-120 W sustained on a 95 W part. Setting
PL1 95 W / PL2 120 W **in BIOS** (OS-level RAPL writes are overridden) took it
from dying at 61-85 s to completing a full ladder.

**Do not re-run an `n_cpu_moe` cell on srv1 without confirming the BIOS power
limits are in place.** `cat /sys/class/powercap/intel-rapl:0/constraint_0_power_limit_uw`
must read `95000000`, not `4095000000`.

*A note on `m_dsv2-lcpp-srv1`'s standing row.* It reports `ok` with a complete
four-level curve and zero errors at `parallel 8` -- but its `ended_at`
(12:16:13Z) brackets an srv1 outage that began 11:58:44Z. The level data may have
been collected before the freeze or partly after the host returned; the row
cannot say which. Treat it as provisional and re-measure when convenient.

## 4. The barren-`ok` trap, and why you no longer edit the journal

`--retry-failed` re-measures entries whose outcome is not `ok`. A row written
before the barren-level downgrade landed (`d75d90fb`) can read `ok` while
carrying a level that measured nothing, and the fix does not rewrite existing
rows -- so such a row was skipped as good.

**This file used to tell you to delete those rows by hand. Do not.** That
procedure ran on 2026-08-31 and turned the tree green while five cells were
outstanding -- the exact state the guard exists to refuse -- because the test
that judges the grid only judges rows that are present.

`completed()` now re-scores the curve instead of trusting the stored string:

```python
# tools/bench/serving/run.py
if retry_failed:
    rows = {
        k: v for k, v in rows.items()
        if v.get("outcome") == "ok"
        and not barren_levels(v.get("concurrency") or {})
    }
```

So `m_gemma4-lcpp-srv1` is re-measured by `--retry-failed` with the journal left
append-only. Nothing needs dropping. Verify with:

```bash
uv run --no-sync python -c "
import importlib.util,sys
sp=importlib.util.spec_from_file_location('sr','tools/bench/serving/run.py')
m=importlib.util.module_from_spec(sp); sys.modules['sr']=m; sp.loader.exec_module(m)
from pathlib import Path
d=m.completed(Path('records/evidence/serving-2026-08-30/lcpp-srv1.jsonl'), True)
print(sorted(k.split(chr(0))[1] for k in d))"
```

`m_gemma4-lcpp-srv1` must NOT appear in that list.

## 5. Resume

Both rigs are independent machines; run them concurrently.

```bash
for h in srv1 srv2; do
  nohup uv run --no-sync python tools/bench/serving/run.py \
    --config  tools/bench/serving/configs/srv-lcpp-n1248-$h.json \
    --out     records/evidence/serving-2026-08-30/lcpp-$h.json \
    --journal records/evidence/serving-2026-08-30/lcpp-$h.jsonl \
    --resume --retry-failed \
    >> records/evidence/serving-2026-08-30/lcpp-$h.log 2>&1 &
done
```

Use `run.py`, never `sweep.py` — only `run.py` has resume (`run.py:319`, keyed
on `(host, label)`), and only `run.py` emits the schema this evidence uses.

Watch for the failure signatures, not just progress:

```bash
tail -F records/evidence/serving-2026-08-30/lcpp-srv{1,2}.log \
  | grep -E --line-buffered "concurrency ramp|ramp_failed|REFUSED|TimeoutError|URLError|Traceback|wrote records"
```

`TimeoutError` or `URLError` means the host went away mid-cell. Stop, fix the
host, drop the affected rows, resume. Do not let it keep writing.

## 6. Reading the results

The key is `tokens_per_s`, **not** `agg_tok_s`. `run.py` emits
`tokens_per_s` and `completion_tokens_total`; `sweep.py` names the same
quantity `agg_tok_s`. A reader using the wrong key sees `None` at every level
and reads a healthy run as dead. `per_stream = tokens_per_s / n` is exact.

`key = tokens_per_s x total_params`, per the run request.

**Anchor srv1's vLLM ladder at n=2, not n=1.** Its wall clock is flat from n=2
to n=8 while n=1 runs 2.5–3.2x faster per request, on all three models with
zero errors. Anchored at n=1 srv1 looks like it caps at 2.4–3.1x; anchored at
n=2 it scales 3.88x against a theoretical 4x. This is a real regime change, not
noise — the run request predicted it for one model and guessed wrong about why.

## 7. Done looks like

- §2 reports 0 outstanding on both hosts.
- `uv run --no-sync python -m pytest tests/ -q` is **green** when the grid is
  complete. It is currently red on **two** assertions in
  `tests/test_card_memory_accounting.py`, by design, and they agree with each
  other and with §2:

  - `test_the_recorded_run_measured_the_grid_it_was_asked_for` — every cell whose
    **latest** row says `ok` carries a rate at every n. Fails on
    `m_gemma4-lcpp-srv1`, whose n=8 is barren.
  - `test_every_declared_cell_is_present_in_its_journal` — every declared cell
    has a clean `ok` row. Names all four outstanding cells.

  Both read the journal **last-write-wins per label**, the way `run.completed()`
  does. That matters: an append-only journal must be able to keep the record of
  a failure it later fixed. Judging superseded rows is what made the old §4
  remedy "delete the row", and deleting rows is what turned the tree green over
  five outstanding cells on 2026-08-31.

  Both clear when the four cells are measured, and must not be silenced any
  other way.

- `uv run --no-sync ruff check tools/ tests/` clean. **`ruff` is not on `PATH`**
  — it lives in `.venv/bin` and the bare `ruff check` in earlier drafts of this
  file exits `command not found`, which a pipeline reading only the last lines
  reports as success.

## 8. What is already settled — do not re-derive

- **vLLM 7.37–7.67x** n=1→n=8 **on srv2 only**, flat across 1.5B..7B. On srv1
  the same ladder is **2.42–3.11x** from n=1 and **3.76–3.91x** anchored at n=2
  (§6). The unqualified figure here was srv2's, carried without a host.
- **llama.cpp 2.22–3.67x** on card across 11 cells — ten span 2.22–2.74x and
  `d7b-lcpp-srv2` is the 3.67x outlier, which the old range omitted.
  **1.11–1.74x** offloaded across all six `n_cpu_moe: 99` cells; the old
  "1.41–1.47x" was the three middle cells with both extremes dropped.
- **CPU offload is the cause, not MoE.** `m_ling-lcpp-srv1` — a MoE small
  enough to stay resident on srv1's 6 GB card — scales 2.27x, like dense.
- **`--parallel` defaults to 4 slots**, which makes n=8 run as two batches of 4
  and produces a plateau indistinguishable from saturation. Every config sets
  `parallel 8`; `total_slots` is read back from `/props`. Assert it.
- **`-c` is total and divides across slots.** `-c 4096 --parallel 8` gives 512
  tokens/slot against a 475-token completion. The floor is 987/slot.
- **A card has four buckets:** `total = reserved + used + free`. The reserve is
  GSP firmware — 401 MiB srv1, 380 MiB srv2, fixed, not proportional. Weigh
  full-GPU cells against total-less-reserve.
- **`--cpu-offload-gb` is architecture-dependent, not inert.** It relocates
  weights to host RAM when vLLM selects the **V1** model runner, and is accepted
  and ignored under **V2**. Measured 2026-08-31 on one model, one host, one
  flag: V2 → weights 1.95 GiB on card, KV 87,584 tokens, Shmem 14 MB; V1 →
  weights 0.93 GiB, KV 117,152 tokens, Shmem 1.5 GB, with
  `Total CPU offloaded parameters: 1.01` in the log. Qwen2/AWQ takes V2 on both
  rigs, which is why every cell here saw no effect. Verify with the
  `uva.py` offloader log line, never with free RAM -- reading a checkpoint
  drains `MemAvailable` on its own.
  **The "three launches at 0/4/6 GiB" this bullet used to cite exist in no log,
  journal, or commit anywhere in `records/`.** The one committed
  `Model loading took 9.38 GiB` line is a 2026-08-23 control run with no
  `cpu_offload_gb` in its arguments. The gate still refuses correctly for these
  AWQ cells; only its stated reason was wrong.
