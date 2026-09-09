"""Identity belongs on the row, not in a header comment.

``lcpsweep28.py`` used the floating ``:server-cuda`` tag and two runs a month
apart could not be compared, with nothing in the record to say the binary had
moved. The fix was printing ``img=`` on the CONFIG row. This campaign found the
same defect one level down: in ``srv1-nomma-dp4a-ab.tsv`` the stock and no-MMA
arms carry **byte-identical labels**, and ``img=`` never appears on a measurement
row at all. Every reader in this repo collapses rows by label (``run.py:93``),
and against that file doing so keeps one arm and discards the other silently.

A locally built tag is worse than a registry tag, not better: ``llamacpp:...-v3``
exists on one machine and any rebuild silently re-points it, with no registry to
appeal to. So it must additionally resolve to a build stamp.
"""

from __future__ import annotations

import re

import pytest

from tests.sweeprows import owed

FLOATING = re.compile(r":(latest|main|server-cuda)$")
PINNED = {
    "ghcr.io/ggml-org/llama.cpp:server-cuda-b10644",
    "vllm/vllm-openai:v0.26.0",
}
LOCAL_PREFIX = "llamacpp:b10644-"
RUN_FILES = ("srv1-lcpp-arms.tsv", "srv1-moe-slots.tsv", "srv1-vllm-arms.tsv")
ARMS_TSV = "srv1-lcpp-arms.tsv"


@pytest.mark.parametrize("name", RUN_FILES)
def test_every_row_names_its_own_image_and_arm(name: str) -> None:
    sweep = owed(name)
    for row in sweep.rows:
        if row.kind == "SKIP":
            continue
        assert row.fields.get("arm"), f"line {row.lineno}: no arm= on {row.kind}"
        image = row.fields.get("img", "")
        assert image, f"line {row.lineno}: no img= on {row.kind} — {row.label!r}"
        assert not FLOATING.search(image), (
            f"line {row.lineno}: {image!r} is a floating tag. Two runs a month "
            "apart could not be compared the last time this happened."
        )
        assert (
            image in PINNED or image.startswith(LOCAL_PREFIX) or "@sha256:" in image
        ), f"line {row.lineno}: {image!r} is neither a pinned tag nor a digest"


def test_no_two_arms_share_a_label() -> None:
    sweep = owed(ARMS_TSV)
    arms_per_label: dict[str, set[str]] = {}
    for row in sweep.levels():
        arms_per_label.setdefault(row.label, set()).add(row.fields.get("arm", ""))
    collisions = {k: sorted(v) for k, v in arms_per_label.items() if len(v) > 1}
    assert not collisions, (
        f"{len(collisions)} label(s) are used by more than one arm: {collisions}. "
        "The arm belongs in the label, not only in a header line."
    )


def test_a_locally_built_image_names_the_source_that_produced_it() -> None:
    sweep = owed(ARMS_TSV)
    local = {
        r.fields.get("img", "")
        for r in sweep.rows
        if r.fields.get("img", "").startswith(LOCAL_PREFIX)
    }
    assert local, "no row was produced by a locally built image"
    for stamp in sweep.stamps("BUILD"):
        for field in (
            "arm",
            "commit",
            "image_sha256",
            "cuda_architectures",
            "force_mmq",
        ):
            assert stamp.get(field), f"### BUILD states no {field}: {stamp}"
    built = {s["arm"] for s in sweep.stamps("BUILD")}
    used = {
        r.fields["arm"]
        for r in sweep.rows
        if r.fields.get("img", "").startswith(LOCAL_PREFIX)
    }
    assert used <= built, (
        f"arms {sorted(used - built)} ran a local image with no ### BUILD stamp"
    )
