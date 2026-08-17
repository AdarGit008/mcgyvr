"""Run identity — one block, four groups, and the three states a field can be in.

ADR-0027 — *run identity is one block, and an unreadable field is a refusal* —
and issue `#265 <https://github.com/AdarGit008/mcgyvr/issues/265>`_.

**Why this is a module and not a tuple in three files.** Five lists disagreed
about what identity is: ``report.COMPARABLE`` (11 keys), ``report.read_cell``'s
required set (4), ``report.BOUND_MATCH`` (4), the breadth resume drift check
(every key it writes) and the bundle resume drift check (6). Three lanes were
queued to edit the first of them — #256 for the model, #262 for the bar, #231
check 2 for the condition — and the comparability key is a *single tuple*, so
three lanes each adding one field is three chances to name one field short. A
guard that names five fields does not refuse the sixth; it permits it silently,
which reads as having checked.

**The defect this closes.** ``require_comparable`` compared
``manifest.get(key)`` across cells, so a key absent from *every* cell yielded
one value and passed::

    model         {'"qwen2.5-coder:1.5b"'}  pass
    tasks_sha256  {'"aaa"'}                 pass
    model_sha256  {'null'}                  pass   <- nothing writes this field

Adding the three digests to a failing-open guard would have changed no behaviour
at all while reading, to every later reader, as having checked. So the shape and
the refusal land together: **a field the guard cannot read is a refusal, not a
match** (ADR-0027 D3).

**What is recorded and what is keyed are different questions.** #276 settled
that: recording is unconditional, and a field enters the *key* only once
perturbation shows it flips more verdicts than the declared bound. So
:data:`GROUPS` is what a run records; :data:`KEY` is the admitted subset, and it
does not widen because a field became available. The four bound-key fields —
model, tier, bar, build — are admitted by construction (#276 corollary 3),
because the rule cannot hold ``model`` fixed while varying ``model``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

__all__ = [
    "ABSENT",
    "BACKFILLED",
    "BOUND_MATCH",
    "BOUND_MATCH_PENDING",
    "CONTRAST",
    "GROUPS",
    "KEY",
    "MODEL_PROBE_FIELDS",
    "NO_FINGERPRINT",
    "OBTAINED",
    "PENDING",
    "PENDING_REASON",
    "RECORDED",
    "REFUSALS",
    "REFUSED",
    "VERIFIED",
    "IdentityError",
    "bar_digest",
    "digest",
    "drift",
    "inventory",
    "probe_model",
    "prompt_digest",
    "require_comparable",
    "state",
    "tag",
    "unfingerprinted",
]


class IdentityError(Exception):
    """Two records cannot be laid beside each other, or one cannot be read."""


# --- the three states (ADR-0027 D2) -----------------------------------------
#
# One rule, all four groups, so a reader can tell "not recorded" from "recorded
# as unknown" from "the endpoint could not say" — and no sentinel string, which
# would be a fourth state indistinguishable from a legitimate value.
State = Literal["obtained", "refused", "absent"]

OBTAINED: State = "obtained"  # a value: the world was asked and answered
REFUSED: State = "refused"  # null + a reason: asked, and it would not say
ABSENT: State = "absent"  # no key: the record predates the contract


# --- the four groups (ADR-0027 D1) ------------------------------------------
#
# ADR-0026 named three fields — the bar, the model and the condition. It was one
# short. The SERVER is the missing group and it has already cost a contrast:
# the scaffold ablation ran the 3B against srv1 on ollama 0.32.4 and the 7B
# against srv2 on 0.32.5, and nothing on disk said so.
#
# A name here is what the record CARRIES, not what the guard checks. Fields
# nothing writes yet are listed on purpose: the fan-out that computes a digest
# adds a writer, and flips one entry in KEY below, rather than inventing a field
# name of its own three months from now.
GROUPS: dict[str, tuple[str, ...]] = {
    # What answered. The tag is mutable and cannot be pinned — ollama's `@digest`
    # grammar exists in types/model/name.go and the parser discards it — so
    # identity is captured at request time or not at all.
    "model": (
        "model",
        "model_sha256",
        "quantization",
        "context_length",
        "vocabulary_sha256",
        "merges_sha256",
    ),
    # What it was asked, as sent. `bundle_sha256` hashes the SYSTEM prompt while
    # an ablation edits the USER message, so `prompt_sha256` is the field that
    # makes a condition content rather than a name.
    "request": (
        "protocol",
        "tier",
        "condition",
        "prompt_sha256",
        "bundle_sha256",
        "tasks_sha256",
        "draws",
        "greedy_temperature",
        "sampled_temperature",
        "max_output_tokens",
        "seed",
    ),
    # What served it. Observed, never assumed: two builds are two instruments
    # (ADR-0024), and concurrency decides whether greedy is reproducible at all.
    "server": (
        "endpoint",
        "serving_build",
        "template_sha256",
        "concurrency",
    ),
    # What judged it. Five rung names are byte-identical across 328 ruff rules
    # and 66 eslint, so the bar is hashed as the RESOLVED rule list. `round` and
    # `product_sha256` sit here because the revision they pin includes the
    # scorer AND the scorer's configuration — `pyproject.toml`,
    # `eslint.config.mjs` and the two lockfiles that decide which checker
    # applies them. It included only the scorer when this line was written,
    # which made the justification false for half of what it claimed; ADR-0032
    # (#291) put the configuration in `product.SURFACE` and this sentence is
    # now true rather than aspirational.
    "bar": (
        "gate_rungs",
        "gate_semantic",
        "bar_sha256",
        "mode",
        "round",
        "product_sha256",
    ),
}

RECORDED: tuple[str, ...] = tuple(f for fields in GROUPS.values() for f in fields)


# The axis a table is allowed to vary in. Named in the call rather than assumed,
# so a sweep that contrasts something else says which (ADR-0027 D5).
CONTRAST = "condition"


# The admitted subset. Every entry here is either one of the four bound-key
# fields (admitted by construction, #276 corollary 3) or was in
# `report.COMPARABLE` before this module existed — a manifest mutated in a 4x
# smaller output cap, a different temperature, a different wire protocol and an
# emptied task manifest once produced a byte-identical report.
#
# It does not widen because a field became writable. #276's rule admits, and
# nothing else does.
KEY: tuple[str, ...] = (
    "model",
    "endpoint",
    "serving_build",
    "tier",
    "gate_rungs",
    "max_output_tokens",
    "greedy_temperature",
    "protocol",
    "tasks_sha256",
    "round",
    "product_sha256",
)


# Recorded, not keyed. Each waits on a perturbation run under #276's rule, or on
# a writer. Listed so the gap is a state rather than an oversight — this is the
# list a reader should hold this module to when the fan-out lands.
PENDING: tuple[str, ...] = tuple(f for f in RECORDED if f not in KEY and f != CONTRAST)


# WHY each pending field is pending, which the list above could not say (#285).
# Two different states wore one name: "#276's rule has not admitted it" and
# "nothing in the repository computes it". Ten of the 27 declared fields were in
# the second state when ADR-0027 shipped, so the perturbation rule had nothing
# to perturb and the list read as though it did.
#
# Every pending field carries a reason, and the test suite holds this to the
# tree: a field pending on #276's rule must have a writer, and a field pending
# on #286 must not — so the day someone writes one without moving it here, the
# list stops agreeing with the repository and says so.
AWAITING_ADMISSION = "awaiting #276's perturbation rule"
AWAITING_PROBE_SET = "awaiting the `observed` probe set (#286)"

PENDING_REASON: dict[str, str] = {
    # Written by `probe_model` since #285. Recorded on every run made from here
    # on, and keyed only when perturbation admits them — which for the model
    # digest is the one experiment #276's rule cannot run on itself, since it
    # cannot hold `model` fixed while varying `model`. `model` is already a
    # bound-key field by corollary 3; these qualify it rather than replace it.
    "model_sha256": AWAITING_ADMISSION,
    "vocabulary_sha256": AWAITING_ADMISSION,
    "merges_sha256": AWAITING_ADMISSION,
    "template_sha256": AWAITING_ADMISSION,
    "bar_sha256": AWAITING_ADMISSION,
    # Keyed WITHIN a condition and never globally (D6, and `require_comparable`
    # does it). A global key would refuse `stock` against `norule`, which is the
    # contrast the bench exists to draw.
    "prompt_sha256": "keyed within a condition (D6), never globally",
    "bundle_sha256": AWAITING_ADMISSION,
    # #286's, not #285's: they are the probe set, captured comprehensively and
    # compared by nothing until someone promotes them.
    "quantization": AWAITING_PROBE_SET,
    "context_length": AWAITING_PROBE_SET,
    "concurrency": AWAITING_PROBE_SET,
    "seed": AWAITING_PROBE_SET,
    # Written since before this module existed, and pending for the ordinary
    # reason. Listed rather than left to a default: a field that falls through
    # to "the usual" is a field nobody decided about, and this dict is complete
    # by test so a name added to GROUPS cannot arrive unexplained.
    "draws": AWAITING_ADMISSION,
    "sampled_temperature": AWAITING_ADMISSION,
    "gate_semantic": AWAITING_ADMISSION,
    "mode": AWAITING_ADMISSION,
}


# What a declared reproducibility bound must match before it may describe a run.
# ADR-0019 D2 — the null is measured per target tier and does not transfer up the
# ladder; ADR-0024 — a serving build nothing recorded has already moved results
# twice; a bar that scores differently produces a different null.
#
# `tier` here is the LANGUAGE ARM — `bench-py` / `bench-ts`, as every run.json
# records it — and the axis the product ladder calls a tier is `model` (#289).
# D2's "per target tier" is therefore discharged by `model`, with language as an
# additional split.
#
# The matching note on `mcgyvr.config.Tier` is DEFERRED, not written: `src/mcgyvr`
# is inside `product.SURFACE`, so a docstring there moves `product_sha256` and
# re-baselines the open round. It lands with the identity range #276's sequencing
# already schedules before `r2` opens. Until then a reader of the ladder sense
# meets no cross-reference, which is why this one states both senses in full
# rather than pointing at a file.
BOUND_MATCH: tuple[str, ...] = ("model", "tier", "gate_rungs", "serving_build")

# Declared in the contract, not yet enforced here. ADR-0027 D9 put `cells` in
# the matching key — a rate keyed on everything but its own denominator
# transfers to subsets it never saw — and `reproducibility.json`'s `matching`
# prose already states five fields against this tuple's four.
#
# Listed rather than left implicit for the reason `PENDING` exists above: a gap
# a reader can see is a state, and a gap only one of two documents mentions is
# an oversight waiting to be satisfied twice. #231 owns closing it, and #289
# measured what it costs to honour — nothing, because a subset of an
# already-paired set is itself already paired, so a subset bound is a
# recomputation over verdicts on disk rather than a new dispatch.
#
# **It is not pending the way `PENDING` is, and promoting it is not the same
# move.** Every entry in `PENDING` is a recorded *manifest* field awaiting
# admission to `KEY`. `cells` is a field of a *bound record* — the denominator
# the bound was measured over — and appears in neither `KEY` nor `RECORDED`,
# because a run manifest does not carry it. So `BOUND_MATCH` gaining `cells`
# would break `set(BOUND_MATCH) <= set(KEY)`, which
# `tests/test_bench_identity.py` asserts today. Whoever closes D9 decides that
# invariant's fate first: either the bound key stops being a subset of the run
# key, or `cells` becomes a recorded field of the run it describes.
BOUND_MATCH_PENDING: tuple[str, ...] = ("cells",)


def digest(value: Any) -> str:
    """The hashing convention, in one place so three lanes cannot invent three.

    Canonical JSON — sorted keys, no incidental whitespace, UTF-8 — then sha256,
    hex, whole. Not truncated: a short digest saves bytes in a file that is
    already megabytes of rows, and buys a collision argument nobody wants to have
    about an identity field.

    Computed here and never passed in (ADR-0027 D4). ``--condition`` was a
    caller-supplied identity field, it reached dispatch and never ``record_run``,
    and eight manifests described a render nobody had run.
    """
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# --- the writers (#285) -----------------------------------------------------
#
# ADR-0026 decided that three fields change from a NAME to CONTENT. ADR-0027
# decided the record shape and shipped the module. Nothing wrote the content:
# ten of the 27 declared fields had no writer anywhere in the repository, so
# `PENDING` could not distinguish "#276's rule has not admitted it" from
# "nothing computes it", and the perturbation rule had nothing to perturb.
#
# Every one of these is computed HERE and called by the runner with raw
# material only (ADR-0027 D4). A runner that assembles a hash and passes it in
# is `--condition` with a longer hex string: a caller-supplied identity field
# that reached dispatch and never `record_run`, and eight manifests described a
# render nobody had run.

#: Where a refusal's reason lives. D2 says an unobtainable field is ``null``
#: **with a reason**, and the reason cannot go in the field itself without being
#: the sentinel string D2 forbids. One sibling block keyed by field name, so
#: :data:`GROUPS` stays exactly the names it declares — ten ``*_reason`` twins
#: would double it — and a reader finds the reason where they found the null.
REFUSALS = "identity_refusals"

#: Long, and deliberately not :func:`serving_build`'s two seconds. `/api/show`
#: with ``verbose`` returns the tokenizer arrays — 151,936 tokens and 151,387
#: merges on the 1.5B — and a timeout tuned for a version string would record
#: "unobtainable" for a model that answered perfectly well, slowly.
MODEL_PROBE_TIMEOUT_S = 30.0


def _refused(
    fields: tuple[str, ...], why: str
) -> tuple[dict[str, None], dict[str, str]]:
    """Every field in ``fields`` as ``null``, all for the same stated reason."""
    return ({f: None for f in fields}, {f: why for f in fields})


MODEL_PROBE_FIELDS: tuple[str, ...] = (
    "model_sha256",
    "vocabulary_sha256",
    "merges_sha256",
    "template_sha256",
)


def probe_model(
    endpoint: str, model: str, *, timeout: float = MODEL_PROBE_TIMEOUT_S
) -> tuple[dict[str, str | None], dict[str, str]]:
    """What the endpoint will say about the weights it is serving, hashed here.

    Returns ``(fields, reasons)``. Every field in :data:`MODEL_PROBE_FIELDS` is
    always present in ``fields`` — ``null`` where the endpoint would not answer,
    with the reason in ``reasons``. An **absent** key means the record predates
    the contract (D2), so a run made from here on must never produce one.

    **The `verbose` flag is load-bearing and is why this is a probe rather than
    a one-liner.** Without it `/api/show` returns ``tokenizer.ggml.tokens`` and
    ``tokenizer.ggml.merges`` as ``null`` rather than omitting them — measured
    on `qwen2.5-coder:1.5b`, 0 against 151,936. A probe that left the flag off
    would record "unobtainable" while the answer was one flag away, which reads
    as having checked.

    **`model_sha256` is the manifest digest, and it is over-sensitive.** It is
    the value `/api/tags` returns and `src/mcgyvr/detect.py` throws away, and it
    is the sha256 of ollama's *manifest file* — which lists five layers, so it
    moves when the template, the system prompt or the licence layer changes and
    the weights do not. The separable weights identity is the **model layer**
    digest, which `/api/show` and `/api/tags` do not expose; reading it needs
    manifest parsing on the serving host and is not something a dispatch can do.

    Over-sensitive is the safe direction for a comparability guard: it refuses a
    contrast that would have been sound, and it never permits one that is not.
    The unsafe direction is the one this cannot close — ``model_info`` and
    ``tensors`` carry name, shape and dtype rather than weight values, so a
    fine-tune has identical shapes. **Different digest implies a different
    model; the same digest does not imply the same model**, and the gap sits
    exactly where identity matters most, since #189 was a fine-tune contrast.

    ``vocabulary_sha256`` and ``merges_sha256`` are why the model group has six
    fields rather than one. They are the model's **own** content, out of the
    GGUF header, where the manifest digest is ollama's addressing of it — so two
    records that disagree on ``model_sha256`` while agreeing on both of these
    are a re-tag or a re-import rather than a different tokenizer, and a reader
    can tell those apart only because both are recorded.

    ``template_sha256`` is in the **server** group and not the model group, and
    the survey is the reason: `template` is ollama's rendering on top of the
    GGUF, not the GGUF. The same weights served under two templates are two
    instruments, which is `serving_build`'s argument applied one level in.
    """
    base = endpoint.rstrip("/")
    tags = _get_json(f"{base}/api/tags", timeout=timeout)
    show = _post_json(
        f"{base}/api/show", {"model": model, "verbose": True}, timeout=timeout
    )
    if show is None and tags is None:
        return _refused(
            MODEL_PROBE_FIELDS,
            f"{base} answered neither /api/tags nor /api/show; an endpoint that "
            "does not speak ollama's native API cannot be asked what weights it "
            "holds, and the OpenAI surface it does speak is identity-free",
        )

    fields: dict[str, str | None] = {}
    reasons: dict[str, str] = {}

    manifest_digest = _tag_digest(tags, model)
    if manifest_digest is None:
        fields["model_sha256"] = None
        reasons["model_sha256"] = (
            f"/api/tags listed no digest for {model!r}"
            if tags is not None
            else f"{base}/api/tags did not answer"
        )
    else:
        fields["model_sha256"] = manifest_digest

    if show is None:
        for field in ("vocabulary_sha256", "merges_sha256", "template_sha256"):
            fields[field] = None
            reasons[field] = f"{base}/api/show did not answer"
        return fields, reasons

    info = show.get("model_info")
    info = info if isinstance(info, dict) else {}
    for field, key in (
        ("vocabulary_sha256", "tokenizer.ggml.tokens"),
        ("merges_sha256", "tokenizer.ggml.merges"),
    ):
        value = info.get(key)
        if not isinstance(value, list) or not value:
            fields[field] = None
            reasons[field] = (
                f"/api/show returned no {key}; the array is null without "
                "verbose=true and absent on a model with no GGUF tokenizer "
                "header, and this probe sends the flag"
            )
        else:
            fields[field] = digest(value)

    template = show.get("template")
    if not isinstance(template, str) or not template:
        fields["template_sha256"] = None
        reasons["template_sha256"] = "/api/show returned no template"
    else:
        fields["template_sha256"] = digest(template)
    return fields, reasons


def _tag_digest(tags: Any, model: str) -> str | None:
    """The manifest digest `/api/tags` lists for ``model``, or None.

    Matched on ``name`` and on ``model``: ollama's listing carries both, they
    are the same string on every row measured here, and taking whichever is
    present costs nothing against a build that drops one.
    """
    if not isinstance(tags, dict):
        return None
    rows = tags.get("models")
    if not isinstance(rows, list):
        return None
    for row in rows:
        if not isinstance(row, dict):
            continue
        if model in (row.get("name"), row.get("model")):
            found = row.get("digest")
            return str(found) if found else None
    return None


def _get_json(url: str, *, timeout: float) -> Any | None:
    """GET a JSON document, or None on any failure at all.

    Every failure here means one thing to the caller — nothing usable answered —
    and the caller's job is to say which field went unrecorded and why, not to
    distinguish a refused connection from a 404.
    """
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        return None


def _post_json(url: str, body: dict[str, Any], *, timeout: float) -> Any | None:
    """POST a JSON body and read a JSON document, or None on any failure."""
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        return None


#: The solution filename each arm's checker is pointed at when the bar is
#: resolved. eslint resolves a config *per file*, so asking it for "the rules"
#: without naming one is asking a question it does not answer.
BAR_PROBE_FILE = {"python": "solution.py", "jsts": "solution.ts"}


def bar_digest(
    *,
    rungs: Sequence[str],
    language: str,
    stage_workspace: Callable[[Path], None],
) -> tuple[str | None, str | None]:
    """The bar as **resolved rules**, not as five names. Returns (digest, why).

    `gate_rungs` records five names — ``scope``, ``secrets``, ``structured``,
    ``adapters``, ``acceptance`` — and both bench arms write the same five. They
    are byte-identical across a ruff configuration selecting 251 rules and an
    eslint one selecting 66, so **two arms scored by two different rule sets are
    indistinguishable on disk**, and ADR-0026 measured what that costs: under
    the full bar the arms read py 8.9% / ts 12.8%, and on correctness alone they
    read py 27.3% / ts 23.9%. The bar reverses which arm leads.

    So the digest is over what the checkers *resolve to*, asked of the checkers
    themselves rather than derived from the config by re-implementing their
    resolution:

    * ``ruff check --show-settings`` → ``linter.rules.enabled``, every rule by
      name and code. The rest of that output is deliberately dropped: it carries
      ``linter.project_root``, an absolute path, and a digest that moves when
      the repository is checked out somewhere else is describing the machine.
    * ``eslint --print-config <file>`` → the resolved config, rules and
      severities, for the file the arm actually writes.
    * the version of every tool that resolved any of it, because ADR-0025's
      consequence is that pinning the toolchain makes the checker version part
      of the instrument — a rule that changes what it flags between two patch
      releases changes the bar without changing a line of configuration.

    **Per language, not per run.** ADR-0026's rule is that no figure pools
    across a stratum where the effect is heterogeneous, and the two arms' bars
    are the case it was written from. A single digest over both would restate
    `gate_rungs`' defect with more hex.

    **The workspace is staged by the caller** (ADR-0027 D4 in the other
    direction): the bench's bar is not the repository's `make lint` bar — it is
    whatever `score.stage_dir` puts in a workspace, which is `pyproject.toml`
    rendered from the project's `[tool.ruff]` and `eslint.config.mjs` copied
    beside a linked `node_modules`. Resolving the repository's settings instead
    would digest a bar no candidate is ever scored against. The caller passes
    its staging, not a hash.

    A resolver that will not answer makes this ``None`` with a reason rather
    than a digest over the half that did: a bar hashed from one of its two
    checkers is not the bar, and would read as having recorded one. On a real
    dispatch this cannot fire — `score.require_toolchain` refuses a run with a
    missing rung tool before the first candidate — so the ``None`` path is for
    off-rig callers, which is exactly who should not get a confident answer.
    """
    probe = BAR_PROBE_FILE.get(language)
    if probe is None:
        return None, (
            f"no bar probe file is declared for language {language!r}; "
            f"known: {', '.join(sorted(BAR_PROBE_FILE))}"
        )
    with tempfile.TemporaryDirectory(prefix="mcgyvr-bar-") as tmp:
        workspace = Path(tmp)
        try:
            stage_workspace(workspace)
        except Exception as error:  # the caller's staging, not ours to classify
            return None, f"the bar workspace could not be staged: {error}"
        (workspace / probe).write_text("", encoding="utf-8")

        material: dict[str, Any] = {"rungs": list(rungs), "language": language}
        if language == "python":
            rules, why = _ruff_rules(workspace)
            if rules is None:
                return None, why
            material["ruff_rules"] = rules
            for tool in ("ruff",):
                version, why = _tool_version(tool, workspace)
                if version is None:
                    return None, why
                material[f"{tool}_version"] = version
        else:
            config, why = _eslint_config(workspace, probe)
            if config is None:
                return None, why
            material["eslint_config"] = config
            for tool in ("eslint", "prettier"):
                version, why = _tool_version(tool, workspace)
                if version is None:
                    return None, why
                material[f"{tool}_version"] = version
    return digest(material), None


def _run(argv: list[str], cwd: Path) -> subprocess.CompletedProcess[str] | None:
    """Run a resolver, or None if it is not on PATH or does not come back."""
    try:
        return subprocess.run(
            argv, cwd=cwd, capture_output=True, text=True, timeout=BAR_PROBE_TIMEOUT_S
        )
    except (OSError, subprocess.SubprocessError):
        return None


#: Resolving a rule set is a config walk, not a lint run. Anything approaching
#: this is a broken toolchain rather than a slow one.
BAR_PROBE_TIMEOUT_S = 60.0


def _ruff_rules(workspace: Path) -> tuple[list[str] | None, str | None]:
    """Every rule ruff has enabled in this workspace, in ruff's own order.

    Parsed out of ``--show-settings`` rather than re-derived from ``select``:
    expanding ``E, F, W, I, N, UP, B, SIM, RUF`` into concrete rules is ruff's
    resolution, it changes between releases, and a second implementation of it
    here would drift from the one that actually scores.
    """
    proc = _run(["ruff", "check", "--show-settings"], workspace)
    if proc is None:
        return None, "ruff is not on PATH, so the Python bar cannot be resolved"
    if proc.returncode != 0:
        return None, f"ruff --show-settings failed: {proc.stderr.strip()[:200]}"
    rules: list[str] = []
    collecting = False
    for line in proc.stdout.splitlines():
        if line.startswith("linter.rules.enabled = ["):
            collecting = True
            continue
        if collecting:
            if line.startswith("]"):
                break
            rules.append(line.strip().rstrip(","))
    if not rules:
        return None, (
            "ruff --show-settings named no enabled rules; a bar that rejects "
            "nothing is not a bar this project would record a rate against"
        )
    return rules, None


def _eslint_config(workspace: Path, probe: str) -> tuple[Any | None, str | None]:
    """The config eslint resolves for the file this arm's worker writes."""
    proc = _run(["eslint", "--print-config", probe], workspace)
    if proc is None:
        return None, "eslint is not on PATH, so the JS/TS bar cannot be resolved"
    if proc.returncode != 0:
        return None, f"eslint --print-config failed: {proc.stderr.strip()[:200]}"
    try:
        return json.loads(proc.stdout), None
    except json.JSONDecodeError:
        return None, "eslint --print-config did not return JSON"


def _tool_version(tool: str, workspace: Path) -> tuple[str | None, str | None]:
    """``<tool> --version``, verbatim, or why it could not be had."""
    proc = _run([tool, "--version"], workspace)
    if proc is None:
        return None, f"{tool} is not on PATH, so its version is not part of the bar"
    if proc.returncode != 0:
        return None, f"{tool} --version failed: {proc.stderr.strip()[:200]}"
    return proc.stdout.strip(), None


def prompt_digest(rendered: Mapping[str, tuple[str, str]]) -> str:
    """The prompt **as sent**, whole, over every task the run will dispatch.

    ADR-0027 D6. What exists today is ``bundle_sha256``, and it hashes
    ``prompt.system`` — while the scaffold ablation edits the **user** message
    (`tools/breadth/measure.py:915`). So the field that is on disk does not move
    when the thing under test moves, and two cells that name one condition and
    render two different prompts compare equal. Prompt wording is the largest
    measured effect in the literature this campaign surveyed — up to 76pp — and
    we hash the system half.

    Both halves, keyed by task id, so a render that changes for one task moves
    the digest: the first task's prompt is not a description of a 498-task
    sweep, and hashing it would be the curated-subset defect at a smaller scale.

    **Not keyed globally, and this is not an omission.** D6 says the prompt is
    keyed *within a condition*, which is what :func:`require_comparable`'s
    per-condition loop already does. Putting this in :data:`KEY` would refuse
    every contrast the bench exists to draw — the ablation changes the render on
    purpose, so ``stock`` and ``norule`` differ here by construction, and a
    global key would read that as two records that may not be laid side by side.
    """
    return digest({task: [system, user] for task, (system, user) in rendered.items()})


def state(manifest: dict[str, Any], field: str) -> State:
    """Which of the three states this manifest is in for this field."""
    if field not in manifest:
        return ABSENT
    return REFUSED if manifest[field] is None else OBTAINED


def unfingerprinted(
    manifest: dict[str, Any], fields: tuple[str, ...] | None = None
) -> list[str]:
    """The keyed fields this manifest cannot answer, in declaration order.

    Empty is the `verified` tag's precondition (ADR-0027 D8) — necessary and not
    sufficient, since a field can be recorded and wrong.

    ``fields`` defaults to :data:`KEY` and is resolved **at call time**, not as a
    default argument. A default is bound when the function is defined, so
    ``fields: tuple[str, ...] = KEY`` froze the key at import and D8's stated
    property — that a `verified` record demotes on its own when the key widens —
    could not be exercised without reimporting the module. It held in practice,
    because admitting a field means editing the literal above, and it was
    untestable and one refactor away from being false. The same shape cost
    `product._open_cli` a round entry describing two trees (#291).
    """
    return [
        f for f in (KEY if fields is None else fields) if state(manifest, f) != OBTAINED
    ]


# What a record must name before it is worth any tag at all — a pass rate that
# names no model on no rig names nothing.
#
# `report.read_cell` requires a fourth, `condition`, and this deliberately does
# not: a bench cell without one cannot be placed in a matrix, but 96 of the
# manifests on disk are rig sweeps that never had a condition to name. Folding
# "not a bench run" into "unidentifiable" would tag most of the corpus untrusted
# for a field its instrument does not have.
NAMES_ITS_SUBJECT: tuple[str, ...] = ("model", "endpoint", "tier")

VERIFIED = "verified"  # every keyed field obtained
BACKFILLED = "backfilled"  # names its subject, fingerprint incomplete
NO_FINGERPRINT = "no_fingerprint"  # cannot say what produced it


def tag(manifest: dict[str, Any]) -> str:
    """The migration tag for one record (ADR-0027 D8), computed and never typed.

    Three tags, and the middle one is the one that needs its meaning stated,
    because its name invites the wrong reading:

    * ``verified`` — ran with a full fingerprint. It means **everything was
      recorded**. It does not mean the run reproduces, and nothing in this
      project may use it that way: greedy decoding is not deterministic under
      continuous batching, so re-run-and-compare is a positive signal only.
    * ``backfilled`` — the record names its subject and its fingerprint is
      incomplete. **Not clean, and never read.** It is a dormant insurance label
      against a future that finds a use for these rows, not a promotion path.
    * ``no_fingerprint`` — the record cannot say what produced it. Never
      trusted, no promotion path.

    Nothing is re-run to move a record between tags. Rig time goes to new runs
    done properly rather than to repairing old ones, so CLM-0011 stays dark until
    a fresh measurement and #256 waits for that rather than for a promotion.

    **The tag is a function of today's key, and moves when the key does.** Six
    records are ``verified`` against :data:`KEY` as it stands, and :data:`KEY`
    does not yet contain the three digests ADR-0026 asked for because nothing
    writes them. When the fan-out adds a writer and #276's rule admits the field,
    those six become ``backfilled`` — which is why this is computed on read
    rather than stamped into the manifests. A stamped tag would have claimed a
    fingerprint the run never carried.
    """
    if any(state(manifest, f) != OBTAINED for f in NAMES_ITS_SUBJECT):
        return NO_FINGERPRINT
    return VERIFIED if not unfingerprinted(manifest) else BACKFILLED


def drift(
    first: dict[str, Any], second: dict[str, Any], fields: tuple[str, ...] | None = None
) -> list[str]:
    """Keyed fields on which two records disagree — the resume check's question.

    Absence is not agreement here either: a manifest that does not carry a field
    is not thereby the same as one that does. The one exception a caller may
    make is ADR-0024's — a field that did not exist when the directory was
    written is adopted forward by the caller *before* this is called, so the
    adoption is visible at the call site rather than hidden in a comparison.

    ``fields`` resolves at call time for the reason :func:`unfingerprinted`
    gives.
    """
    return sorted(
        f
        for f in (KEY if fields is None else fields)
        if state(first, f) != state(second, f) or first.get(f) != second.get(f)
    )


def require_comparable(
    manifests: list[dict[str, Any]],
    contrast: str = CONTRAST,
    allow_unfingerprinted: bool = False,
) -> None:
    """Refuse a table whose records differ in anything but the contrast axis.

    Two refusals, and the second is the one this module was written for:

    * **they differ** in a keyed field — a contrast between them would vary two
      things and attribute the result to one, which is the defect #189 shipped
      and ADR-0024 closes;
    * **a keyed field is not obtained** — absent, or ``null``. Two unknowns are
      not a match. An endpoint that would not name its build might have named
      two different builds, and a record written before the contract cannot say
      anything at all.

    ``allow_unfingerprinted`` exists so the second can be waived, and it is a
    parameter rather than a default because ADR-0027 D3 permits the waiver only
    where it is explicit. Reading pre-contract records is a legitimate thing to
    want; doing it without saying so is what produced a shipped -3.1pp headline
    across a corpus nobody had compared.

    **A single record is never refused for absence.** The defect is two records
    agreeing *by shared absence*, and one record agrees with nothing. This keeps
    ADR-0024's consequence intact — an endpoint that will not name its build
    records ``null``, and a rate from it is still a rate — while withdrawing the
    half of it that does not survive: ``null`` is a recorded fact about a run and
    is **not** a match between two of them, because an endpoint that would not
    answer twice may have answered differently twice. The caller states what it
    could not check either way; :func:`unfingerprinted` is what it asks.
    """
    if contrast in KEY:
        raise IdentityError(
            f"{contrast!r} is both the contrast axis and a keyed field, so this "
            "table would refuse the difference it exists to show"
        )
    if not manifests:
        raise IdentityError("no records to compare")

    if len(manifests) > 1 and not allow_unfingerprinted:
        for index, manifest in enumerate(manifests):
            missing = unfingerprinted(manifest)
            if missing:
                detail = ", ".join(f"{f} ({state(manifest, f)})" for f in missing)
                raise IdentityError(
                    f"record {index} cannot answer {detail}. Absence is not "
                    "agreement: a field no record carries compared equal under "
                    "the old guard, which read as having checked. Tag the run "
                    "and pass allow_unfingerprinted=True to read it under the "
                    "old key deliberately (ADR-0027 D3, D8)."
                )

    for field in KEY:
        seen = {json.dumps(m.get(field), sort_keys=True) for m in manifests}
        if len(seen) > 1:
            raise IdentityError(
                f"these records differ in {field!r}: {', '.join(sorted(seen))}. "
                "A contrast between them would vary two things and attribute "
                "the result to one — the defect #189 shipped and ADR-0024 "
                "closes. Re-run the odd record, or report them separately."
            )

    # Within one condition the prompt as sent must not move (ADR-0027 D6). This
    # needs no admission experiment because the contrast is *inside* the axis
    # rather than across it: two cells that name the same condition and were
    # sent different bytes are mislabelled, whatever the effect size turns out
    # to be. Prompt wording is the largest effect in the surveyed literature —
    # up to 76pp — and until the fan-out lands, `bundle_sha256` hashes the
    # system half only, so this check is weaker than it reads.
    #
    # `bundle_sha256` stays OUT of KEY, decided rather than deferred (ADR-0032
    # clause 6). #276's rule admits a field only once perturbation shows it
    # flips more verdicts than the declared bound; no such run has been done,
    # and corollary 1 is explicit that an untested field is recorded and not
    # keyed. What made this look urgent — the prompt files sitting outside the
    # round pin — is closed at the other end instead: `src/mcgyvr/prompts/*.md`
    # is now inside `product_sha256`, which IS keyed. The check below is a
    # mislabelling refusal inside the contrast axis, not an admission.
    for field in ("prompt_sha256", "bundle_sha256"):
        present = [m for m in manifests if state(m, field) == OBTAINED]
        by_condition: dict[Any, set[str]] = {}
        for manifest in present:
            by_condition.setdefault(manifest.get(contrast), set()).add(
                str(manifest[field])
            )
        for condition, values in sorted(
            by_condition.items(), key=lambda kv: str(kv[0])
        ):
            if len(values) > 1:
                raise IdentityError(
                    f"two records name {contrast} {condition!r} and differ in "
                    f"{field!r}: {', '.join(sorted(values))}. One condition was "
                    "rendered two ways, so the label is not the experiment."
                )


def inventory(root: Path) -> list[tuple[Path, str, list[str]]]:
    """Every manifest under ``root``, its tag, and what it could not answer.

    Read rather than written. A tag committed into a file goes stale the moment
    a record or the key moves, and a stale tag is worse than none — it is a
    claim about a run that nothing re-derives. The migration ADR-0027 D8 decides
    is therefore *tagging in place*, with this as the tag.

    Records that are not machine-written manifests are skipped rather than
    tagged: three of the directories on disk hold hand-authored evidence whose
    ``protocol`` is a paragraph of prose, and they are excluded by shape rather
    than by an exception list that would need maintaining.
    """
    found: list[tuple[Path, str, list[str]]] = []
    for path in sorted(root.glob("**/run.json")):
        try:
            recorded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(recorded, dict) or not isinstance(
            recorded.get("protocol"), str
        ):
            continue
        found.append((path, tag(recorded), unfingerprinted(recorded)))
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "root",
        nargs="?",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "records" / "measurements",
        help="the directory of run directories to tag (default: records/measurements)",
    )
    args = parser.parse_args()
    found = inventory(args.root)
    if not found:
        print(f"no machine-written manifests under {args.root}", file=sys.stderr)
        return 2
    counts: dict[str, int] = {}
    for _, name, _ in found:
        counts[name] = counts.get(name, 0) + 1
    for path, name, missing in found:
        detail = f"  ({', '.join(missing)})" if missing else ""
        print(f"{name:<15} {path.parent}{detail}")
    print()
    for name in (VERIFIED, BACKFILLED, NO_FINGERPRINT):
        print(f"{name:<15} {counts.get(name, 0)} of {len(found)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
