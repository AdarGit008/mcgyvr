"""Run identity — one block, four groups, and the three states a field can be in.

*Run identity is one block, and an unreadable field is a refusal.*

**Why this is a module and not a tuple in several files.**
``report.COMPARABLE`` and ``report.BOUND_MATCH`` are aliases of :data:`KEY` and
:data:`BOUND_MATCH`, and the breadth and bundle resume drift checks call
:func:`drift`. A guard that names five fields does not refuse the sixth; it
permits it silently, which reads as having checked.

**A field the guard cannot read is a refusal, not a match.** A key absent from
*every* cell yields one value — ``null`` — across all of them, and a guard that
compared values alone would pass it.

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

from mcgyvr.gate.adapters import JavaScriptAdapter, PythonAdapter

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


# --- the three states ------------------------------------------------
#
# One rule, all four groups, so a reader can tell "not recorded" from "recorded
# as unknown" from "the endpoint could not say" — and no sentinel string, which
# would be a fourth state indistinguishable from a legitimate value.
State = Literal["obtained", "refused", "absent"]

OBTAINED: State = "obtained"  # a value: the world was asked and answered
REFUSED: State = "refused"  # null + a reason: asked, and it would not say
ABSENT: State = "absent"  # no key: the record predates the contract


# --- the four groups -------------------------------------------------
#
# A name here is what the record CARRIES, not what the guard checks.
GROUPS: dict[str, tuple[str, ...]] = {
    # What answered. A tag is mutable and, on the surfaces this build talks to,
    # cannot be pinned at all: the OpenAI-compatible protocol carries a name
    # and nothing else about the weights. So weights identity comes from a
    # digest pin or a ggufscan geometry, or not at all.
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
        # The retired bundle rig's resume-guard fields. Its two committed
        # manifests carry these names, so they sit inside the contract.
        # Recorded, never keyed.
        "language",
        "conditions_sha256",
    ),
    # What served it. Observed, never assumed: two builds are two
    # instruments, and concurrency decides whether greedy is reproducible at
    # all.
    "server": (
        "endpoint",
        "serving_build",
        "template_sha256",
        "concurrency",
        # `serving_build` names the engine; this names what the engine
        # RESOLVED. Both are needed and neither substitutes: one image digest
        # and one argument list can resolve different kernels on two hosts. The
        # digest is taken over `fingerprint.RESOLVED_READS`.
        "serving_resolved_sha256",
    ),
    # What judged it. Five rung names are byte-identical across two different
    # resolved rule sets (ruff's and eslint's), so the bar is hashed as the
    # RESOLVED rule list. `round` and `product_sha256` sit here because the
    # revision they pin (`product.SURFACE`) includes the scorer AND the
    # scorer's configuration — `pyproject.toml`, `eslint.config.mjs`,
    # `prettier.config.mjs` and the two lockfiles that decide which checker
    # applies them.
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
# so a sweep that contrasts something else says which.
CONTRAST = "condition"


# The admitted subset. It does not widen because a field became writable.
# #276's rule admits, and nothing else does.
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
    # **#358, and it is admitted by qualification rather than by perturbation.**
    # The paragraph above says the key does not widen because a field became
    # writable, and that rule stands. This is not a new field of the run: it is
    # `serving_build` measured properly. `serving_build` is a bound-key field
    # (#276 corollary 3) admitted because two builds are two instruments — and
    # the string it holds was demonstrated to be equal across two hosts running
    # different kernels, so it discharges that argument for the engine's NAME
    # and not for the instrument. A field that repairs a keyed field's stated
    # justification enters beside it; making it wait on a perturbation run would
    # leave the key admitting a claim its own evidence had refuted.
    #
    # **What it costs.** A record that carries no value for it makes a table
    # refuse on absence — `allow_unfingerprinted=True` is how a reader takes
    # such a record deliberately.
    "serving_resolved_sha256",
)


# Recorded, not keyed. Listed so the gap is a state rather than an oversight;
# `PENDING_REASON` says why for each.
PENDING: tuple[str, ...] = tuple(f for f in RECORDED if f not in KEY and f != CONTRAST)


# WHY each pending field is pending. Every pending field carries a reason, and
# the test suite holds this dict complete. The four probe-set fields are
# promoted by the owner, not by the perturbation rule.
AWAITING_ADMISSION = "awaiting #276's perturbation rule"
CAPTURED_IN_OBSERVED = (
    "captured in observed.json (#286) and compared by nothing; promotion into "
    "KEY is the owner's, not #276's perturbation rule"
)

PENDING_REASON: dict[str, str] = {
    # `probe_model` records these four as null with a reason on every run: the
    # OpenAI-compatible surface carries no weights identity. `model` is already
    # a bound-key field; these would qualify it rather than replace it.
    "model_sha256": AWAITING_ADMISSION,
    "vocabulary_sha256": AWAITING_ADMISSION,
    "merges_sha256": AWAITING_ADMISSION,
    "template_sha256": AWAITING_ADMISSION,
    # The digest of `bar_material`, as `bar_digest` computes it.
    "bar_sha256": AWAITING_ADMISSION,
    # Keyed WITHIN a condition and never globally (`require_comparable` does
    # it). A global key would refuse `stock` against `norule`, which is the
    # contrast the bench exists to draw.
    "prompt_sha256": "keyed within a condition, never globally",
    "bundle_sha256": AWAITING_ADMISSION,
    # The probe set, captured in `observed.json` by `tools/bench/observed.py`
    # and compared by nothing until the owner promotes one. Every field is
    # always present: a value, or null with a stated reason.
    "quantization": CAPTURED_IN_OBSERVED,
    "context_length": CAPTURED_IN_OBSERVED,
    "concurrency": CAPTURED_IN_OBSERVED,
    "seed": CAPTURED_IN_OBSERVED,
    # Pending for the ordinary reason. Listed rather than left to a default:
    # this dict is complete by test, so a name added to GROUPS cannot arrive
    # unexplained.
    "draws": AWAITING_ADMISSION,
    "sampled_temperature": AWAITING_ADMISSION,
    "gate_semantic": AWAITING_ADMISSION,
    "mode": AWAITING_ADMISSION,
    # The retired bundle rig's resume-guard fields: recorded so its committed
    # manifests sit inside the contract, and keyed by nothing.
    "language": "the retired bundle rig's resume-guard field: recorded, "
    "keyed by nothing — #240 retired both arms",
    "conditions_sha256": "the retired bundle rig's resume-guard field: "
    "recorded, keyed by nothing — #240 retired both arms",
}


# What a declared reproducibility bound must match before it may describe a run.
# The null is measured per target tier and does not transfer up the ladder; two
# serving builds are two instruments; a bar that scores differently produces a
# different null.
#
# `tier` here is the LANGUAGE ARM — `bench-py` / `bench-ts`, as every run.json
# records it — and the axis the product ladder calls a tier is `model`. "Per
# target tier" is therefore discharged by `model`, with language as an
# additional split.
BOUND_MATCH: tuple[str, ...] = ("model", "tier", "gate_rungs", "serving_build")

# Not enforced here. `reproducibility.json`'s `matching` prose names `cells` as
# a fifth matching field — a rate keyed on everything but its own denominator
# transfers to subsets it never saw — against this tuple's four.
#
# Listed rather than left implicit for the reason `PENDING` exists above: a gap
# a reader can see is a state.
#
# **It is not pending the way `PENDING` is, and promoting it is not the same
# move.** Every entry in `PENDING` is a recorded *manifest* field awaiting
# admission to `KEY`. `cells` is a field of a *bound record* — the denominator
# the bound was measured over — and appears in neither `KEY` nor `RECORDED`,
# because a run manifest does not carry it. So `BOUND_MATCH` gaining `cells`
# would break `set(BOUND_MATCH) <= set(KEY)`, which
# `tests/test_bench_identity.py` asserts. Whoever closes the gap decides that
# invariant's fate first: either the bound key stops being a subset of the run
# key, or `cells` becomes a recorded field of the run it describes.
BOUND_MATCH_PENDING: tuple[str, ...] = ("cells",)


def digest(value: Any) -> str:
    """The hashing convention, in one place so three lanes cannot invent three.

    Canonical JSON — sorted keys, no incidental whitespace, UTF-8 — then sha256,
    hex, whole. Not truncated: a short digest saves bytes in a file that is
    already megabytes of rows, and buys a collision argument nobody wants to have
    about an identity field.

    Computed here and never passed in.
    """
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# --- the writers -------------------------------------------------------------
#
# Every one of these is computed HERE and called by the runner with raw
# material only. A runner that assembles a hash and passes it in supplies an
# identity field nothing re-derives.

#: Where a refusal's reason lives. An unobtainable field is ``null`` **with a
#: reason**, and the reason cannot go in the field itself without being a
#: sentinel string. One sibling block keyed by field name, so :data:`GROUPS`
#: stays exactly the names it declares and a reader finds the reason where they
#: found the null.
REFUSALS = "identity_refusals"

#: The default of :func:`probe_model`'s ``timeout``. That function makes no
#: request, so nothing waits on it.
MODEL_PROBE_TIMEOUT_S = 30.0


def _refused(
    fields: tuple[str, ...], why: str
) -> tuple[dict[str, str | None], dict[str, str]]:
    """Every field in ``fields`` as ``null``, all for the same stated reason."""
    blanked: dict[str, str | None] = {f: None for f in fields}
    return (blanked, {f: why for f in fields})


MODEL_PROBE_FIELDS: tuple[str, ...] = (
    "model_sha256",
    "vocabulary_sha256",
    "merges_sha256",
    "template_sha256",
)


def probe_model(
    endpoint: str, model: str, *, timeout: float = MODEL_PROBE_TIMEOUT_S
) -> tuple[dict[str, str | None], dict[str, str]]:
    """What the endpoint will say about the weights it is serving: nothing.

    Returns ``(fields, reasons)`` with every field in
    :data:`MODEL_PROBE_FIELDS` ``null`` and one reason, which is the shape for
    a field the endpoint will not answer — never a sentinel string and never a
    plausible substitute.

    **The OpenAI-compatible surface is identity-free.** That is not a gap in
    this function: the protocol carries a model *name*, and a name is what
    `serving_build` and the pins exist to distrust. So a refusal here is a true
    statement about what the endpoints this build talks to will say. Weights
    identity comes from the ``weights_sha256`` pin a vLLM claim carries
    (``tools/bench/serving/backends/vllm.py``) and the ``ggufscan`` geometry
    an envelope carries, both of which read the weights rather than ask the
    server about them.

    Kept as a function returning refusals rather than deleted, because callers
    (``tools/breadth/measure.py``) write these four fields into every manifest
    and a record that silently stopped carrying them would read as a run that
    never asked.
    """
    return _refused(
        MODEL_PROBE_FIELDS,
        f"{endpoint.rstrip('/')} is asked over the OpenAI-compatible surface, "
        "which carries a model name and no weights identity. Weights identity "
        "comes from a digest pin or a ggufscan geometry, which read the file "
        "rather than ask the server; the removed native-API probe is in "
        "archive/forensic-ollama/",
    )


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
#: without naming one is asking a question it does not answer. The same
#: ``eslint.config.mjs`` resolves a different rule set for ``solution.js``.
BAR_PROBE_FILE = {"python": "solution.py", "jsts": "solution.ts"}

#: Where the readable bar sits in a run manifest. A sibling block, like
#: :data:`REFUSALS`, and for the same reason: it is not a comparability field —
#: ``bar_sha256`` is — it is the statement of what that digest hashed, so a
#: reader of a ts/py contrast can see *what* differed and not only *that* it did
#: (#262). Excluded from the resume drift check for the same reason: the digest
#: covers this material exactly, so comparing both refuses a resume twice for
#: one change.
BAR = "bar_resolved"


def bar_material(
    *,
    rungs: Sequence[str],
    language: str,
    stage_workspace: Callable[[Path], None],
) -> tuple[dict[str, Any] | None, str | None]:
    """What the bar actually contains, as content. Returns (material, why).

    :func:`bar_digest` hashes exactly this, so the digest and the readable block
    cannot describe two different bars — which is #262's own defect, one level
    in.

    The shape, per arm:

    * ``lint`` — the checker, its version, the config that decided it, the count
      of enabled rules, and the rules themselves.
    * ``format`` — the formatter, its version, and the configuration it read.
    * ``type_check`` — the command the **product's own adapter** locates for
      this workspace, or ``null``. Asked of the adapter rather than restated
      here, for the reason the rules are asked of ruff and eslint: a second
      implementation of the resolution drifts from the one that scores.

    **Both arms answer ``null`` for ``type_check``.** No ``tsconfig.json`` is
    staged, so ``tsc`` never runs; ``score.lint_config`` renders a
    ``pyproject.toml`` holding ruff's tables and nothing else, so
    ``_declares_mypy`` is false and the Python arm is not type-checked either.
    A repository declaring no type checker is correctly not type-checked, so
    this records the absence rather than adding a rung.

    ``rungs`` is carried through because five names remain what a manifest's
    ``gate_rungs`` says, and a reader needs the names beside the content to see
    that the names are not the bar.
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

        material: dict[str, Any] = {"language": language, "rungs": list(rungs)}
        build = _python_bar if language == "python" else _jsts_bar
        arm, why = build(workspace, probe)
        if arm is None:
            return None, why
        material.update(arm)
        material["type_check"] = _type_check(language, workspace)
    return material, None


def bar_digest(
    *,
    rungs: Sequence[str],
    language: str,
    stage_workspace: Callable[[Path], None],
) -> tuple[str | None, str | None]:
    """The bar as **resolved rules**, not as five names. Returns (digest, why).

    `gate_rungs` records five names — ``scope``, ``secrets``, ``structured``,
    ``adapters``, ``acceptance`` — and both bench arms write the same five. They
    are byte-identical across ruff's resolved rule set and eslint's, so **two
    arms scored by two different rule sets are indistinguishable on disk** by
    those names alone.

    So the digest is over what the checkers *resolve to*, asked of the checkers
    themselves rather than derived from the config by re-implementing their
    resolution. :func:`bar_material` is that content and this is its hash; there
    is one function that gathers it so the digest and the readable block in a
    manifest cannot describe two different bars.

    **Per language, not per run.** No figure pools across a stratum where the
    effect is heterogeneous, and the two arms' bars are such a stratum. A single
    digest over both would restate `gate_rungs`' defect with more hex.

    **The workspace is staged by the caller**: the bench's bar is not the
    repository's `make lint` bar — it is whatever `score.stage_config` puts in a
    workspace, which is a `pyproject.toml` rendered from the project's
    `[tool.ruff]` beside `eslint.config.mjs`, `prettier.config.mjs` and a linked
    `node_modules`. Resolving the repository's settings instead would digest a
    bar no candidate is ever scored against. The caller passes its staging, not
    a hash.

    A resolver that will not answer makes this ``None`` with a reason rather
    than a digest over the half that did: a bar hashed from one of its two
    checkers is not the bar, and would read as having recorded one. The ``None``
    path is for a caller whose toolchain is missing, which is exactly who should
    not get a confident answer.
    """
    material, why = bar_material(
        rungs=rungs, language=language, stage_workspace=stage_workspace
    )
    if material is None:
        return None, why
    return digest(material), None


def _python_bar(
    workspace: Path, probe: str
) -> tuple[dict[str, Any] | None, str | None]:
    """ruff, twice: it is both this arm's linter and this arm's formatter.

    ``--show-settings`` rather than the config, because expanding the ``select``
    list into concrete rules is ruff's resolution and re-implementing it here
    would drift from the one that scores. A string prefix is not a ruff
    selector: ``E`` is also a prefix of ``EM``, ``EXE`` and ``ERA``.

    ``linter.rules.enabled`` is the only line taken from that output. The rest
    carries ``linter.project_root``, an absolute path, and a bar that moves when
    the repository is checked out somewhere else is describing the machine.
    """
    rules, why = _ruff_rules(workspace)
    if rules is None:
        return None, why
    version, why = _tool_version("ruff", workspace)
    if version is None:
        return None, why
    config = (workspace / "pyproject.toml").read_text(encoding="utf-8")
    return {
        "lint": {
            "tool": "ruff",
            "version": version,
            "config": "pyproject.toml",
            "config_source": config,
            "rules_enabled": len(rules),
            "rules": rules,
        },
        # The staged `pyproject.toml` carries `[tool.ruff.format]`. Recorded so
        # a reader comparing the two arms finds both entries present.
        "format": {
            "tool": "ruff format",
            "version": version,
            "config": "pyproject.toml",
            "config_source": config,
        },
    }, None


def _jsts_bar(workspace: Path, probe: str) -> tuple[dict[str, Any] | None, str | None]:
    """eslint for the lint half, prettier for the format half.

    ``config_source`` is the staged file
    verbatim rather than a resolved option dump, because prettier's CLI has no
    ``--print-config``: what it *can* be asked is where its configuration came
    from, and :func:`_prettier_config_path` asks exactly that, so a workspace
    where the file failed to stage answers ``null`` instead of quietly
    recording defaults under a declared name.
    """
    config, why = _eslint_config(workspace, probe)
    if config is None:
        return None, why
    versions: dict[str, str] = {}
    for tool in ("eslint", "prettier"):
        version, why = _tool_version(tool, workspace)
        if version is None:
            return None, why
        versions[tool] = version
    resolved, why = _prettier_config_path(workspace, probe)
    if resolved is None:
        return None, why
    declared = resolved != _PRETTIER_UNCONFIGURED
    return {
        "lint": {
            "tool": "eslint",
            "version": versions["eslint"],
            "config": "eslint.config.mjs",
            "config_source": config,
            "rules_enabled": _enabled_rules(config),
            "rules": config.get("rules", {}),
        },
        "format": {
            "tool": "prettier",
            "version": versions["prettier"],
            "config": resolved if declared else None,
            "config_source": (
                (workspace / resolved).read_text(encoding="utf-8") if declared else None
            ),
            # Kept nameable rather than inferred from a `null`: prettier
            # formatting on defaults is not the same fact as prettier failing
            # to run.
            "unconfigured": not declared,
        },
    }, None


#: What ``prettier --find-config-path`` says when it walked up and found
#: nothing. It exits non-zero and prints nothing, so the absence needs a name of
#: its own to be recordable.
_PRETTIER_UNCONFIGURED = ""


def _prettier_config_path(workspace: Path, probe: str) -> tuple[str | None, str | None]:
    """Which configuration prettier resolves for the file the arm writes.

    Returns the workspace-relative path, or :data:`_PRETTIER_UNCONFIGURED` when
    prettier found none — which is a legitimate recorded state and not a
    failure. ``None`` is reserved for prettier being unreachable, where a bar
    hashed without its formatter would read as having recorded one.
    """
    proc = _run(["prettier", "--find-config-path", probe], workspace)
    if proc is None:
        return None, "prettier is not on PATH, so the JS/TS format bar is unresolved"
    found = proc.stdout.strip()
    if proc.returncode != 0 or not found:
        return _PRETTIER_UNCONFIGURED, None
    return Path(found).name, None


def _enabled_rules(config: Any) -> int | None:
    """How many of a resolved eslint config's rules are actually on.

    ``--print-config`` lists every rule the plugins contribute, including those
    at severity 0. Counting the keys would overstate this arm's bar, which is
    the direction that makes the two arms look closer than they are.
    """
    rules = config.get("rules") if isinstance(config, dict) else None
    if not isinstance(rules, dict):
        return None
    return sum(1 for value in rules.values() if _severity(value) != 0)


def _severity(value: Any) -> int | None:
    head = value[0] if isinstance(value, list) and value else value
    if isinstance(head, bool):  # `True`/`False` predate eslint 9 and are not used
        return int(head)
    if isinstance(head, int):
        return head
    return {"off": 0, "warn": 1, "error": 2}.get(head)


def _type_check(language: str, workspace: Path) -> list[str] | None:
    """The type-check command the product's own adapter locates here, or None.

    Asked of the adapter for the reason the rules are asked of ruff and eslint:
    a second implementation of "does this repository declare a type checker"
    would drift from the one the gate runs. Both arms answer ``None`` on a bench
    workspace — see :func:`bar_material`.
    """
    adapter = JavaScriptAdapter() if language == "jsts" else PythonAdapter()
    return adapter.locate_type_check_command(workspace)


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
    expanding selectors into concrete rules is ruff's resolution, it changes
    between releases, and a second implementation of it here would drift from
    the one that actually scores.
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

    ``bundle_sha256`` hashes ``prompt.system`` only, while the scaffold ablation
    edits the **user** message (``ablate`` in ``tools/breadth/measure.py``);
    this digest covers both halves, so a condition is content rather than a
    name.

    Both halves, keyed by task id, so a render that changes for one task moves
    the digest: the first task's prompt is not a description of the whole
    sweep.

    **Not keyed globally, and this is not an omission.** The prompt is keyed
    *within a condition*, by :func:`require_comparable`'s per-condition loop.
    Putting this in :data:`KEY` would refuse
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

    Empty is the `verified` tag's precondition — necessary and not
    sufficient, since a field can be recorded and wrong.

    ``fields`` defaults to :data:`KEY` and is resolved **at call time**, not as a
    default argument. A default is bound when the function is defined, so
    ``fields: tuple[str, ...] = KEY`` would freeze the key at import, and a
    `verified` record could not demote on its own when the key widens.
    """
    return [
        f for f in (KEY if fields is None else fields) if state(manifest, f) != OBTAINED
    ]


# What a record must name before it is worth any tag at all — a pass rate that
# names no model on no rig names nothing.
#
# `report.read_cell` requires a fourth, `condition`, and this deliberately does
# not: a bench cell without one cannot be placed in a matrix, but a rig sweep
# never had a condition to name. Folding "not a bench run" into
# "unidentifiable" would tag those records untrusted for a field their
# instrument does not have.
NAMES_ITS_SUBJECT: tuple[str, ...] = ("model", "endpoint", "tier")

VERIFIED = "verified"  # every keyed field obtained
BACKFILLED = "backfilled"  # names its subject, fingerprint incomplete
NO_FINGERPRINT = "no_fingerprint"  # cannot say what produced it


def tag(manifest: dict[str, Any]) -> str:
    """The migration tag for one record, computed and never typed.

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

    Nothing is re-run to move a record between tags.

    **The tag is a function of today's key, and moves when the key does** —
    which is why it is computed on read rather than stamped into the manifests.
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
    make: a field that did not exist when the directory was written is
    adopted forward by the caller *before* this is called, so the
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
      things and attribute the result to one;
    * **a keyed field is not obtained** — absent, or ``null``. Two unknowns are
      not a match. An endpoint that would not name its build might have named
      two different builds, and a record written before the contract cannot say
      anything at all.

    ``allow_unfingerprinted`` exists so the second can be waived, and it is a
    parameter rather than a default so the waiver is explicit at the call site.
    Reading pre-contract records is a legitimate thing to want; doing it without
    saying so is not.

    **A single record is never refused for absence.** The defect is two records
    agreeing *by shared absence*, and one record agrees with nothing. An
    endpoint that will not name its build records ``null``, and a rate from it
    is still a rate; but ``null`` is a recorded fact about a run and
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
                    "agreement: a field no record carries is not a match. Pass "
                    "allow_unfingerprinted=True to read such a record "
                    "deliberately."
                )

    for field in KEY:
        seen = {json.dumps(m.get(field), sort_keys=True) for m in manifests}
        if len(seen) > 1:
            raise IdentityError(
                f"these records differ in {field!r}: {', '.join(sorted(seen))}. "
                "A contrast between them would vary two things and attribute "
                "the result to one. Re-run the odd record, or report them "
                "separately."
            )

    # Within one condition the prompt as sent must not move. This needs no
    # admission experiment because the contrast is *inside* the axis rather
    # than across it: two cells that name the same condition and were sent
    # different bytes are mislabelled, whatever the effect size turns out to
    # be. `bundle_sha256` hashes the system half only; `prompt_sha256` covers
    # the prompt as sent, and both are checked.
    #
    # `bundle_sha256` stays OUT of KEY: #276's rule admits a field only once
    # perturbation shows it flips more verdicts than the declared bound, and an
    # untested field is recorded and not keyed. `src/mcgyvr/prompts/*.md` is
    # inside `product_sha256`, which IS keyed. The check below is a
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
    claim about a run that nothing re-derives. Migration is therefore *tagging
    in place*, with this as the tag.

    Records that are not machine-written manifests are skipped rather than
    tagged: a ``run.json`` that is not an object with a string ``protocol`` is
    hand-authored evidence, excluded by shape rather than by an exception list
    that would need maintaining.
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
