"""The four lenses as checks rather than as reading.

A defect found by a person or an agent re-reading is found one instance at a
time; a sweep that corrects every known instance and adds no check leaves the
next one to be found the same way.

So these are deliberately not assertions about known instances. Each one computes a
*population* and compares it against a declared allowlist, which means a new
instance fails the build even though nobody wrote it down. The allowlists are
the audit's findings, frozen: an entry is a fact of record, and removing one is
how a fix is proved.

Two classes, one check each:

* **the twin constant** — one value, two definitions, and only a comment
  holding them equal. ``test_duplicated_constants_are_declared``.
* **the underived constant** — a shipped number citing a measurement no test
  recomputes, so the figure and its evidence drift apart.
  ``test_estimate_reserve_is_derived``.

The reader of the checks the gate can emit (``_emitted_check_names``) is kept
with its control.

The cost of a wrong allowlist entry here is not a missed defect; it is a
published number nobody can re-derive.
"""

from __future__ import annotations

import ast
import collections
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SOURCE_ROOTS = (REPO / "src",)
# The vendored resolver engine is material, not code: its contents are pinned
# by digest and a sweep there measures the instrument, not the project.
SKIP_PARTS = ("tasks", "baseline", "reserve", "node_modules", ".venv")
# The semantic gate's resolver engine, copied byte for byte and pinned by digest
# in ``gate/semantic.py``: skipped by its exact path, not by a folder name.
SKIP_TREES = (REPO / "src" / "mcgyvr" / "gate" / "_engine",)


def _source_files() -> list[Path]:
    out: list[Path] = []
    for root in SOURCE_ROOTS:
        for path in sorted(root.rglob("*.py")):
            if any(part in SKIP_PARTS for part in path.parts):
                continue
            if any(path.is_relative_to(tree) for tree in SKIP_TREES):
                continue
            out.append(path)
    return out


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO))


def _where(path: Path, lineno: int) -> str:
    """A location, repo-relative when the file is in the repo at all."""
    stem = _rel(path) if path.is_relative_to(REPO) else str(path)
    return f"{stem}:{lineno}"


# --------------------------------------------------------------------------
# The twin constant — one value, two definitions
# --------------------------------------------------------------------------

# Module-level literal constants that are defined in more than one place.
#
# A duplicate is not automatically a defect — sometimes the coupling is real and
# importing across it would be worse, which `worker/reply.py` says out loud
# before duplicating the extension tuples on purpose. What is never acceptable
# is an *undeclared* duplicate, because the only thing keeping the copies equal
# is that nobody has edited one of them yet.
#
# Each entry is (constant name, whether the copies must hold equal values).
# `False` marks a name collision across unrelated meanings — two modules that
# happen to have picked the same word — which this check must not force into
# agreement.
DECLARED_DUPLICATES: dict[str, bool] = {
    # Must agree: ``serving/rigscan.py`` is shipped to the rig as text
    # (``python3 -``) and cannot import mcgyvr, so it restates the scan's
    # measured constants rather than importing them. If a copy drifts, the far
    # end measures by a different instrument than ``mcgyvr.scan``, and the same
    # rig reports two different facts.
    "COPY_MIB": True,
    "COPY_MIB_TIGHT": True,
    "COPY_PASSES": True,
    "GPU_NOT_DETERMINED": True,
    "GPU_ROW_UNREAD": True,
    "MIB_PER_GB": True,
    "NVIDIA_SMI_QUERY": True,
    "TIGHT_RAM_GB": True,
    "WEIGHTS_DIR_ENV": True,
    # Two serving backends, added 2026-08-30. Each names the engine it drives,
    # so three of these four MUST differ and are declared False for that reason
    # rather than as an unreconciled conflict.
    # Different engines ship different images; equal values here would mean one
    # backend was launching the other's container.
    "CONTAINER_IMAGE": False,
    # Must agree: the container mount point and the host tree behind it are one
    # deployment fact seen from two sides — the bench backend launches with
    # `-v $HOME/models:/models`, and the door's geometry script translates a
    # container path back to the host one to read a header OUTSIDE any
    # container. Not made one definition of the other on purpose: the door
    # would then import a bench backend, which is the dependency the door
    # exists to remove. If these two stop agreeing, ggufscan reads a path that
    # is not the blob the step serves, and the placement describes another file.
    "CONTAINER_MODELS": True,
    "HOST_MODELS": True,
    # Must agree: llama.cpp's status page is one path of one server, read by
    # the runner beside a dispatch (how many slots are at work) and by the rig
    # agent's relay before it hangs up on a head (what the slot at work made).
    # The rig agent states the few things it needs rather than importing the
    # runner, which would bring the whole dispatch path into the agent. If the
    # two stop agreeing, one of them reads a page the server does not have and
    # falls back in silence: a unit read as unread, or a relay with no counts.
    "SLOTS_PATH": True,
    # Must differ: one name for both would have the two backends tear down and
    # reuse each other's container, which is the collision `release()` exists to
    # make impossible.
    "CONTAINER_NAME": False,
    # 40 against 60. How much log each keeps on a refusal is tuned to how much
    # that engine prints before it fails; there is no quantity here they share.
    "LAUNCH_LOG_LINES": False,
    # Must agree: both express the same thing — how long a launch may take
    # before the cell is refused — and a run that allowed one engine longer than
    # the other would report the difference as the engine's.
    "START_TIMEOUT_S": True,
    # Must agree. Asserted in a comment in `orchestrator/repo.py` and by nothing
    # else; git's empty-tree SHA-1 is the same fact on both sides of the seam.
    "_EMPTY_TREE": True,
    # Must agree. `orchestrator/symbols.py` says the names match the gate
    # adapters — if they stop matching, the index and the gate disagree about
    # which files are JavaScript, silently.
    "_TS_EXTENSIONS": True,
    "_TSX_EXTENSIONS": True,
    # Must agree: deterministic.py restates the gate's Python extensions rather
    # than importing them (G4 — importing the adapters drags tree-sitter into a
    # planning-only process), and worker/reply.py carries the same pair.
    "_PY_EXTENSIONS": True,
    # Must agree, and cannot be derived. `mcgyvr.cli` writes this as the `tier`
    # of every deterministic-floor row; a journal indexer filters the table by
    # it, and if the two drifted the query for "how much work
    # finished without a model" would silently return nothing. The reviewer
    # tool is deliberately not an importer of the CLI — it reads journals other
    # installs and other versions wrote, and importing `mcgyvr.cli` to learn one
    # string would drag the whole command surface into a read-only tool — so the
    # duplication is declared rather than removed. `tests/
    # test_a_floor_run_is_in_the_corpus_too.py` holds the value to the catalog's
    # own family name at the writing end.
    "DETERMINISTIC": True,
    # Must agree. Both rigs clone the same frames for the same corpus.
    "CLONE_DEPTH": True,
    "REMOTES": True,
    # Must agree: the two rigs sweep the same ladder.
    "LADDER": True,
    # Two copies, and they are not the same quantity. Live admission rehearses
    # the ceiling that will score it, while a retired instrument's rows were
    # measured under another. Declared False rather than forced equal.
    "ACCEPTANCE_TIMEOUT_S": False,
    # Known to disagree, and filed: `detect` and `availability` hold different values,
    # under the `availability` module docstring calling the two "the same trick ... for
    # the same reason". Weaker than the timeout above — the prose is about concurrency
    # rather than the value — but it is the same shape.
    "PROBE_TIMEOUT_S": False,
    # Inherited rather than derived, in two rigs at once. Equal; the defect is
    # that neither copy is derived from anything.
    "MAX_OUTPUT_TOKENS": True,
    # Three independent schema versions that happen to be 1. They version
    # different schemas and are NOT required to agree — but a reader sees one
    # number in three files, so it is declared rather than left to be noticed.
    "SCHEMA_VERSION": False,
    # Each rig's declared resume field set (#287): one name by design — the
    # tests that hold a manifest's keys to the declaration read the same shape
    # in both rigs — and two values by design, because the rigs record
    # different identity blocks. What must agree is not the tuples but their
    # membership in `identity.RECORDED`, which each rig's declared-set test
    # asserts against the one contract module.
    "IDENTITY_FIELDS": False,
    # One per serving backend, and duplicated BY CONSTRUCTION: the serving
    # backend contract requires every backend to declare its own name and
    # default port, and a backend may not name another backend, so
    # there is nowhere shared for either to live. They must NOT agree — two
    # backends sharing a name or a port would be one backend — which is the
    # opposite of the usual reason for declaring a duplicate, and is why this is
    # stated rather than left to be noticed.
    "NAME": False,
    "PORT": False,
    # Name collisions across unrelated meanings.
    "CHECK": False,  # the gate's own per-module check name
    "ARMS": False,  # each rig's arms are its own
    "TIMEOUT_S": False,  # unrelated tools, unrelated ceilings
    # workload.py's bench system prompt vs propose.py's decomposition prompt:
    # two prompts for two different callers that happen to share a name.
    "SYSTEM": False,
    "_CACHE": False,
    "_DRIVER": False,
    # reply.py and deterministic.py carry the whole family; symbols.py is JS only
    "_JS_EXTENSIONS": False,
    "__all__": False,  # every package has one
}


def _module_level_constants(
    files: list[Path] | None = None,
) -> dict[str, dict[str, list[str]]]:
    """name -> {repr(value): [locations]} for every literal module constant.

    ``files`` is injectable so the canary below can hand it a synthetic tree.
    A check that cannot be shown to reject is the defect this file is about.
    """
    found: dict[str, dict[str, list[str]]] = collections.defaultdict(
        lambda: collections.defaultdict(list)
    )
    for path in _source_files() if files is None else files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover - a syntax error is its own failure
            continue
        for node in tree.body:
            names: list[str]
            value: ast.expr | None
            if isinstance(node, ast.Assign):
                names = [t.id for t in node.targets if isinstance(t, ast.Name)]
                value = node.value
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                names = [node.target.id]
                value = node.value
            else:
                continue
            if value is None:
                continue
            try:
                literal = ast.literal_eval(value)
            except (ValueError, SyntaxError, TypeError):
                continue
            for name in names:
                found[name][repr(literal)].append(_where(path, node.lineno))
    return found


def _duplicated(
    constants: dict[str, dict[str, list[str]]],
) -> dict[str, dict[str, list[str]]]:
    """The subset defined in more than one place."""
    return {
        name: values
        for name, values in constants.items()
        if sum(len(locs) for locs in values.values()) > 1
    }


def test_duplicated_constants_are_declared() -> None:
    """A constant defined twice is declared here, or it is a new instance.

    This is the check the ``_EMPTY_TREE`` comment stands in for. The comment
    states a claim; this states the property, so the twelfth instance fails the
    build instead of waiting to be read.
    """
    duplicated = _duplicated(_module_level_constants())
    undeclared = sorted(set(duplicated) - set(DECLARED_DUPLICATES))
    assert not undeclared, (
        "a module-level constant is now defined in more than one place and is "
        "not declared in DECLARED_DUPLICATES:\n"
        + "\n".join(
            f"  {name}: "
            + "; ".join(
                f"{value} at {', '.join(locs)}"
                for value, locs in sorted(duplicated[name].items())
            )
            for name in undeclared
        )
        + "\n\nEither make one definition the source of the "
        "other, or declare the duplication and say whether the copies must "
        "hold equal values."
    )


def test_declared_duplicates_that_must_agree_do_agree() -> None:
    """The half of the class a comment cannot enforce: the values are equal.

    ``ACCEPTANCE_TIMEOUT_S`` is why this exists. Its comment claimed sameness
    for long enough that a second module built a claim on top of it, and the
    two values were never equal.
    """
    constants = _module_level_constants()
    broken: list[str] = []
    for name, must_agree in sorted(DECLARED_DUPLICATES.items()):
        if not must_agree:
            continue
        values = constants.get(name)
        if values is None:  # the duplication was resolved — nothing to hold
            continue
        if len(values) > 1:
            broken.append(
                f"  {name} disagrees: "
                + "; ".join(
                    f"{value} at {', '.join(locs)}"
                    for value, locs in sorted(values.items())
                )
            )
    assert not broken, (
        "a constant declared as needing to hold equal values does not:\n"
        + "\n".join(broken)
    )


# --------------------------------------------------------------------------
# The unmapped rung — a declared bar naming checks the gate cannot emit
# --------------------------------------------------------------------------


def _emitted_check_names(gate: Path | None = None) -> dict[str, list[str]]:
    """Every literal a ``Finding(check=...)`` can carry, resolved by AST."""
    emitted: dict[str, list[str]] = collections.defaultdict(list)
    gate = REPO / "src" / "mcgyvr" / "gate" if gate is None else gate
    for path in sorted(gate.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        constants: dict[str, str] = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
                for target in node.targets:
                    if isinstance(target, ast.Name) and isinstance(
                        node.value.value, str
                    ):
                        constants[target.id] = node.value.value
        for call in ast.walk(tree):
            if not isinstance(call, ast.Call):
                continue
            func = call.func
            name = (
                func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            )
            if name != "Finding":
                continue
            for keyword in call.keywords:
                if keyword.arg != "check":
                    continue
                value = keyword.value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    emitted[value.value].append(_where(path, value.lineno))
                elif isinstance(value, ast.Name) and value.id in constants:
                    emitted[constants[value.id]].append(_where(path, value.lineno))
    return dict(emitted)


# --------------------------------------------------------------------------
# The controls
# --------------------------------------------------------------------------
#
# A check is two-sided: a declaration of content, *and* a positive
# control proving the declaration is live. A digest with no control records
# precisely which inert bar was applied. Every check above therefore has a
# canary here — a synthetic new instance it must reject. If a canary stops
# failing, the check above it has gone inert and is reporting health while
# applying nothing, which is the state this whole file exists to detect.


def test_control_an_undeclared_twin_is_rejected(tmp_path: Path) -> None:
    """The duplicate sweep rejects a constant it has never seen."""
    (tmp_path / "one.py").write_text("NEW_SHARED_CEILING_S = 5.0\n", encoding="utf-8")
    (tmp_path / "two.py").write_text("NEW_SHARED_CEILING_S = 9.0\n", encoding="utf-8")
    duplicated = _duplicated(
        _module_level_constants([tmp_path / "one.py", tmp_path / "two.py"])
    )
    assert "NEW_SHARED_CEILING_S" in duplicated
    assert sorted(duplicated["NEW_SHARED_CEILING_S"]) == ["5.0", "9.0"]
    assert "NEW_SHARED_CEILING_S" not in DECLARED_DUPLICATES


def test_control_a_must_agree_twin_that_drifts_is_rejected(tmp_path: Path) -> None:
    """The must-agree half rejects two copies that stopped being equal."""
    (tmp_path / "a.py").write_text("_EMPTY_TREE = 'aaa'\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("_EMPTY_TREE = 'bbb'\n", encoding="utf-8")
    constants = _module_level_constants([tmp_path / "a.py", tmp_path / "b.py"])
    assert DECLARED_DUPLICATES["_EMPTY_TREE"] is True
    assert len(constants["_EMPTY_TREE"]) > 1, (
        "two different values for a must-agree constant did not register as a "
        "disagreement — test_declared_duplicates_that_must_agree_do_agree is inert"
    )


def test_control_a_rung_that_maps_to_no_check_is_rejected(tmp_path: Path) -> None:
    """The rung check rejects a declared name that maps to no emitted check."""
    gate = tmp_path / "gate"
    gate.mkdir()
    (gate / "only.py").write_text(
        'CHECK = "acceptance"\n'
        "def f():\n"
        '    return Finding(check="scope", path="p", message="m")\n'
        "def g():\n"
        '    return Finding(check=CHECK, path="p", message="m")\n',
        encoding="utf-8",
    )
    emitted = _emitted_check_names(gate)
    # Both forms resolve: the literal, and the module constant `check=CHECK`
    # that `acceptance.py` and `semantic.py` actually use.
    assert set(emitted) == {"scope", "acceptance"}
    # `adapters` is exactly the shape the real GATE_RUNGS carries: a category
    # name that is not itself a check. Without RUNG_COVERAGE it maps to nothing.
    assert "adapters" not in emitted
