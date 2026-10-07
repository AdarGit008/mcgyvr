"""A refusal with no server answering names that cause, not the cards.

init proposes only from the models a running server lists, so card memory
plays no part in why nothing was bound. The refusal once read "With 12 GB of
VRAM, no unit can be proposed" on a machine of several 12 GB cards with no
server up: it blamed the cards, and named one card's size as the machine's.

So the refusal says no server answered on the endpoints tried, lists every
card with its size as the cards of the machine the command runs on, and never
implies that the cards of a rig swept over the network were read.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from mcgyvr.detect import Detection, Gpu, targets_for
from mcgyvr.initialize import InitError, initialize
from tests.machine_shapes import Shape, detection, shape


def _refusal(path: Path, found: Detection) -> str:
    with pytest.raises(InitError) as exc:
        initialize(path, detection=found)
    return str(exc.value)


def _far_rig_serving_nothing() -> Shape:
    far = shape("bare-remote-server")
    return dataclasses.replace(far, servers=())


def test_the_refusal_says_no_server_answered_on_the_endpoints_tried(
    tmp_path: Path,
) -> None:
    found = detection(shape("four-equal"))
    assert not found.backends and found.gpus

    text = _refusal(tmp_path, found)
    tried = ", ".join(target.base_url for target in targets_for())
    assert f"No model server answered on any endpoint tried ({tried})" in text
    assert "nothing to bind" in text
    assert "of VRAM" not in text, "card memory is not why nothing was bound"


def test_the_refusal_lists_every_card_as_this_machines(tmp_path: Path) -> None:
    found = detection(shape("four-equal"))
    text = _refusal(tmp_path, found)
    cards = "; ".join(f"{gpu.name}, {gpu.size}" for gpu in found.gpus)
    assert len(found.gpus) == 4
    assert "This machine's GPUs (the machine running mcgyvr; " in text
    assert f"): {cards}." in text


def test_a_refusal_after_sweeping_a_rig_says_its_cards_were_not_read(
    tmp_path: Path,
) -> None:
    far = _far_rig_serving_nothing()
    found = detection(shape("four-equal"), reached=(far,))
    assert not found.backends

    text = _refusal(tmp_path, found)
    tried = ", ".join(t.base_url for t in targets_for(("localhost", far.host)))
    assert f"No model server answered on any endpoint tried ({tried})" in text
    assert f"the cards of {far.host} are not read from here" in text
    assert "No local backend" not in text


def test_a_refusal_with_no_card_says_so_of_this_machine(tmp_path: Path) -> None:
    text = _refusal(tmp_path, detection(shape("bare")))
    assert "This machine, the one running mcgyvr" in text
    assert "has no GPU this build can see" in text


def test_a_refusal_from_a_detection_that_names_no_sweep_still_says_why(
    tmp_path: Path,
) -> None:
    """A detection built by hand records no endpoint; the cause still holds."""
    found = Detection(gpus=(Gpu(name="Example Card", vram_gb=12.0, how="stated"),))
    text = _refusal(tmp_path, found)
    assert "No model server answered, so there is nothing to bind" in text
    assert "Example Card, 12 GB." in text
