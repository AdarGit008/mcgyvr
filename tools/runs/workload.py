"""The one workload every sweep driver draws its prompts from.

Every driver under ``tools/runs/drivers/`` imports this module; none carries a
copy. ``WORKLOAD_DIGEST`` in ``tools/runs/rows.py`` pins it, gate 4 of the door
(``src/mcgyvr/serving/gate-scripts/04-workload.py``) re-derives the digest from
THIS file before a step starts, and ``tests/test_one_door.py`` holds the tree to
exactly one definition.

**The digest is over generated prompts, not over this file's text.**
``rows.workload_digest`` execs everything from the first decile list to the
end of this module and hashes 200 draws, so a ``ruff format`` pass cannot void a
comparison — and so nothing before the decile list, this docstring included, is
part of what is hashed.

**Where the numbers come from.** The deciles are pinned constants taken from
``prompt_tokens`` and ``completion_tokens`` in a deduplicated subset of
``records/measurements/**/results.jsonl``; a recompute over the current tree
does not reproduce them, and changing them moves ``WORKLOAD_DIGEST``. The
drivers reproduce that distribution instead of a single point.

SHARED PREFIX: ``records/measurements/bench-scaffold-ablation-3b-2026-08-11``
gives the scaffold size directly — the stock arm's median prompt is about two
hundred tokens longer than the noscaffold arm's — so that much system prompt is
IDENTICAL on every request. Each prompt is therefore ``SYSTEM`` (constant,
cacheable) + a unique task body, and prefix caching gets the hits it gets in
production: not zero (unique-at-head, too pessimistic), not total (one fixed
prompt).

Lengths are sampled per request from the empirical deciles, seeded by request
id, so request *k* always gets the same length — reproducible across levels
and across reruns without collapsing to a constant. The counter ``UID`` is
per-process state: a driver that must hand two servers the same draws rebinds
it (``vllm_cores.batch``), and every driver's level list changes what a later
request draws (``okf/must-read/reading-results.md``, the prompt draw desync).

Output length is the sampled cap; ``ignore_eos`` is not sent, so the model may
stop earlier on its own, exactly as in production.
"""

import itertools
import random
import threading

PROMPT_DECILES = [588, 608, 624, 653, 688, 719, 746, 799, 887]  # p10..p90
COMPL_DECILES = [78, 101, 130, 158, 189, 230, 281, 346, 460]  # p10..p90
SYS_TOK = 190  # measured scaffold size; the shared, cacheable prefix
TOK_PER_FIELD = 32  # calibration knob: tune until reported ptok= ~= 688
HDR_TOK = 60  # approx tokens in the task-body header lines
MAXLEN_NEED = 887 + 460  # worst sampled prompt + worst sampled reply

UID = itertools.count()
UIDLOCK = threading.Lock()

SYSTEM = (
    "You are a worker in an automated coding ladder. You receive one scoped\n"
    "task contract at a time and return exactly one artifact: the requested\n"
    "code, in a single fenced block, with no prose and no restatement of the\n"
    "contract. Follow the contract literally. Do not invent requirements it\n"
    "does not state, and do not omit any it does. Use type hints on every\n"
    "parameter and return. Include a docstring naming the arguments and the\n"
    "error conditions. Handle every error path the contract enumerates,\n"
    "raising the exact exception type named. Your output is checked by an\n"
    "automated gate that runs the contract's tests verbatim; prose outside\n"
    "the fenced block fails the gate.\n\n"
)


def mkprompt() -> tuple[str, int]:
    """SYSTEM (shared, cacheable) + a unique body sized from the real deciles."""
    with UIDLOCK:
        i = next(UID)
    rnd = random.Random(i)
    want_prompt = rnd.choice(PROMPT_DECILES)
    want_out = rnd.choice(COMPL_DECILES)
    nfield = max(1, (want_prompt - SYS_TOK - HDR_TOK) // TOK_PER_FIELD)
    fields = "\n".join(
        f"  - arg_{k:02d}: bounded by {(i * 31 + k) % 10000:04d}; on violation "
        f"raise ValueError(f'arg_{k:02d} out of range') and log the input."
        for k in range(nfield)
    )
    body = (
        f"CONTRACT option_pairs_{i % 100000:05d} / req {(i * 7919) % (16**8):08x}\n"
        f"Signature: def option_pairs(rows: list[dict], strict: bool = False) -> dict\n"
        f"Fields:\n{fields}\n\n"
        f"Implement it now.\n"
    )
    return SYSTEM + body, want_out
