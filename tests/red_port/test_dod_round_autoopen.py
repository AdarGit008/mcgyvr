"""A tree that has moved off the open round opens the next one, and is not refused.

Gate 1 refuses a door run whose tree does not match the digest the open round
pins (``tools/bench/product.require_pinned``). That refusal is check 3's teeth
against two revisions landing in one table — but it is enforced by stopping the
operator, and the operator's only move is to type the ``--open`` line the
refusal prints. Measured on 2026-09-06: `serve up` and `serve down` could not
run at all from this branch, because ten product files had moved since
``r7-05-09-2026`` was pinned.

Owner's ruling, 2026-09-06: **do not block.** A round is a boundary in the
record, not a permission to work. The door opens the next round itself when the
tree has moved, pins the digest it is about to run against, and continues. There
is no ceiling on how many rounds a day holds; the pins are what a reader traces
a measurement back through, and a round nobody opened by hand is still a round
with one revision in it.

What must be observably true: a run against a moved tree gets a *new round*
rather than a refusal, that round pins the digest actually being run, and the
identifier still reads ``r<N>-DD-MM-YYYY`` so the existing record stays one
sequence. What must NOT change: two revisions never share a round.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from tests.red_port.conftest import required

#: ``r7-05-09-2026`` — a counter, then the day the boundary was drawn.
ROUND_ID = re.compile(r"^r\d+-\d{2}-\d{2}-\d{4}$")


def _product() -> Any:
    import importlib

    return importlib.import_module("tools.bench.product")


def _rounds_file(tmp_path: Path, digest: str) -> Path:
    """A rounds file whose open round pins ``digest``."""
    product = _product()
    data = json.loads(Path(product.ROUNDS_FILE).read_text(encoding="utf-8"))
    data["rounds"][-1] = {**data["rounds"][-1], "product_sha256": digest}
    path = tmp_path / "rounds.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_a_moved_tree_opens_the_next_round_instead_of_refusing(
    tmp_path: Path,
) -> None:
    """The case that stopped the door on 2026-09-06.

    The pin says one thing and the tree says another. Today that is a
    ``ProductError``; it must be a new round pinned to the tree in hand.
    """
    product = _product()
    repo = Path(product.REPO)
    path = _rounds_file(tmp_path, digest="0" * 64)

    ensure = required(
        "open the next round when the tree has moved, instead of refusing the run",
        lambda: product.ensure_open,
    )
    round_id, digest = ensure(repo, path)

    assert digest == product.digest(repo), (
        "the round the run proceeds under must pin the tree it is about to run"
    )
    assert ROUND_ID.match(round_id), (
        f"a round opened by the door still reads r<N>-DD-MM-YYYY, got {round_id!r}"
    )
    rounds = json.loads(path.read_text(encoding="utf-8"))["rounds"]
    assert rounds[-1]["id"] == round_id, "the new round is appended, not substituted"
    assert rounds[-2]["product_sha256"] == "0" * 64, (
        "the round that was open keeps its own pin — a boundary is a record, "
        "and rewriting the old pin would lose what the earlier arms ran against"
    )


def test_an_unmoved_tree_opens_nothing(tmp_path: Path) -> None:
    """No round per run. A boundary is drawn where the product actually moved."""
    product = _product()
    repo = Path(product.REPO)
    path = _rounds_file(tmp_path, digest=product.digest(repo))
    before = json.loads(path.read_text(encoding="utf-8"))["rounds"]

    ensure = required(
        "open the next round when the tree has moved, instead of refusing the run",
        lambda: product.ensure_open,
    )
    round_id, _ = ensure(repo, path)

    after = json.loads(path.read_text(encoding="utf-8"))["rounds"]
    assert len(after) == len(before), "an unmoved tree draws no boundary"
    assert round_id == before[-1]["id"]


def test_a_round_still_holds_exactly_one_revision(tmp_path: Path) -> None:
    """The rule auto-opening must not weaken.

    Opening a round automatically is a convenience about *who types it*. It is
    not permission for a round to span two revisions, which is the property the
    whole pin exists for.

    Asserted on the round this call opened, not across the whole file. A sweep
    of every round ever recorded would forbid a legitimate revert — returning
    the tree to an earlier revision pins that digest again, correctly — and
    would start failing for reasons that have nothing to do with `ensure_open`.
    """
    product = _product()
    repo = Path(product.REPO)
    path = _rounds_file(tmp_path, digest="0" * 64)
    before = len(json.loads(path.read_text(encoding="utf-8"))["rounds"])

    ensure = required(
        "open the next round when the tree has moved, instead of refusing the run",
        lambda: product.ensure_open,
    )
    round_id, digest = ensure(repo, path)
    rounds = json.loads(path.read_text(encoding="utf-8"))["rounds"]

    assert len(rounds) == before + 1, "one boundary, not several"
    opened = rounds[-1]
    assert opened["id"] == round_id
    assert opened["product_sha256"] == digest == product.digest(repo), (
        "the round this call opened pins exactly the revision it opened for"
    )
