"""The behavioural scan's pairing rule (#268).

The scan itself is a long cross-execution over the corpus and is not run here.
What is pinned is the part that decides *which* pairs are ever executed, because
a prune that is too tight produces a clean report rather than a failure — and
that is precisely how two known families were missed.

Until 2026-08-17 the prune was shape **equality**: two tasks were compared only
if they declared the same arity per function. ``b333-pace-split`` declares
``pace_list/1`` and ``pace_of/2``; ``b302-stock-take`` and ``b277-fuel-legs``
each declare one function of arity 2. Equality never compared them, and the
containment chain ``b302 ⊂ b277 ⊂ b333`` that #268's body reports was invisible
to the tool that was supposed to find it.

So the three cases below are the prune's contract: containment holds in the
direction a reference can actually stand in, the alias binds by arity, and the
corpus pair that exposed the defect is executed and comes back positive.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _by_path(name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


fam = _by_path("families", REPO / "tools" / "bench" / "families.py")


def _task(ident: str, *functions: tuple[int, str]) -> object:
    """A task reduced to what pairing reads. The directory is never touched by
    `covers` or `aliases`, so a placeholder states that rather than hiding it."""
    return fam.Task(ident, REPO, tuple(sorted(functions)))


def test_containment_is_directed_and_a_helper_does_not_block_it() -> None:
    """A task declaring a helper as well as the function under test can stand in
    for one that declares the function alone — and not the reverse.

    This is the whole of the 2026-08-17 fix. Under shape equality both
    directions read `False`, and the pair was never executed at all.
    """
    two_functions = _task("b333-pace-split", (1, "pace_list"), (2, "pace_of"))
    one_function = _task("b302-stock-take", (2, "unit_price"))

    assert fam.covers(two_functions, one_function)
    assert not fam.covers(one_function, two_functions)


def test_equal_shapes_still_cover_each_other_in_both_directions() -> None:
    """The old rule was not wrong, it was a special case. Nothing it admitted
    may stop being admitted, or the fix trades two families for others."""
    a = _task("b094-relay-chain", (2, "trace_relay"))
    b = _task("b172-trace-relay", (2, "trace_relay"))

    assert fam.covers(a, b)
    assert fam.covers(b, a)


def test_arity_alone_decides_and_a_mismatch_is_not_papered_over() -> None:
    """Two functions of the same *count* but different arities do not cover.

    Worth its own case because `shape` is a sorted tuple: without the per-arity
    count, `(1, 2)` and `(2, 2)` compare as "two functions each" and the alias
    would bind a one-argument reference to a two-argument import.
    """
    one_and_two = _task("x", (1, "first"), (2, "second"))
    two_and_two = _task("y", (2, "left"), (2, "right"))

    assert not fam.covers(one_and_two, two_and_two)
    assert not fam.covers(two_and_two, one_and_two)


def test_the_alias_binds_by_arity_and_spends_each_source_function_once() -> None:
    """The helper must not be bound to the import the function under test owns.

    `pace_of/2` is the only arity-2 function `b333` has, so it is what
    `unit_price/2` must resolve to; `pace_list/1` has no import to serve and is
    simply carried along in the reference body.
    """
    source = _task("b333-pace-split", (1, "pace_list"), (2, "pace_of"))
    target = _task("b302-stock-take", (2, "unit_price"))

    assert fam.aliases(source, target) == [("pace_of", "unit_price")]


def test_a_source_short_of_functions_is_never_asked_for_an_alias() -> None:
    """`aliases` is only defined where `covers` holds, and it says so by raising
    rather than by silently binding fewer names than the acceptance imports."""
    source = _task("x", (2, "only"))
    target = _task("y", (2, "first"), (2, "second"))

    assert not fam.covers(source, target)
    with pytest.raises(fam.FamilyError, match="no unspent function of arity 2"):
        fam.aliases(source, target)


def test_the_corpus_pair_the_old_prune_hid_reads_as_a_family() -> None:
    """The regression, executed rather than asserted.

    `b333`'s reference is written as the solution, `pace_of` aliased to
    `unit_price`, and `b302`'s own acceptance run against it. A pass means the
    two are not independent evidence, which is the finding #268 exists to make.
    Costs one interpreter start, so it is affordable in the suite where the full
    scan is not.

    The reverse is not executed and could not be: `b302` declares one function
    and `b333`'s acceptance imports two, so containment does not hold that way.
    That asymmetry is what makes this a family rather than a duplicate.
    """
    tasks = fam.load("bench-py")
    superset, subset = tasks["b333-pace-split"], tasks["b302-stock-take"]

    assert fam.covers(superset, subset)
    assert not fam.covers(subset, superset)
    assert fam.satisfies("bench-py", superset, subset)
