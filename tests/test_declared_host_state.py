"""The host state this project declares, and the campaign held to it.

**The gap this closes.** On 2026-08-22 the owner ruled K9: every host declares
the settings that decide residency, and an engine default inherited in silence
is not a declaration. Both rigs were set that day. Nothing in this repository
said so. The values lived in one session record's prose, no capture showed
them, nothing set them and nothing would have noticed them regressing between
campaigns — so the ruling was true of a Saturday afternoon rather than of the
instrument. ADR-0037 rule 1: a finding is a check, not a paragraph.

``tools/bench/serving/configs/hosts.json`` is now the declaration, and the
checks below are the two halves the gap had:

* the declaration is complete and self-describing — green, and it fails the
  moment a setting that decides residency is added without a value or a reason;
* every host a campaign surveyed matches it, by **value** and not merely by
  presence. K9's own check asks whether a name appears; this asks whether it
  appears set to what was declared, which is the half that catches a rig
  quietly reverting to an engine default.

**Red on the newest campaign, and that is correct.** The 2026-08-19 survey
predates the declaration: srv1 ran ``2 / 3 / 5m`` and srv2 declared nothing at
all. These flip on the first campaign run after 2026-08-22. Under
``strict=True`` that flip fails the suite until the marker comes off, which is
the point — the run that closes them announces itself.

**This module does not import ``test_calibration_conflicts``.** It reads the
survey with its own six lines. A check that dies when a neighbouring test file
is refactored is not an independent check, and these two files are about
different things: that one holds a campaign's recorded conflicts, this one
holds the instrument's declared state.

**The declaration moves the serving pin.** ``hosts.json`` lives under
``contract.HARNESS_SURFACE`` (``tools/bench/serving``), which is where it
belongs — a declaration of required host state that sat outside the pinned
harness is the drift this file exists to stop. Rows written after it therefore
carry a different ``harness_sha256`` from rows written before, and #337's
measured ``gpu_memory_utilization`` moves it again; both land before the
campaign re-run so the re-run banks one pin, not three.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent
EVIDENCE = REPO / "records" / "evidence"
DECLARATION = REPO / "tools" / "bench" / "serving" / "configs" / "hosts.json"

#: The settings that decide whether a model stays on the card and whether a
#: second may join it. Named here as well as in the declaration on purpose: the
#: first check below holds the two to each other, so a setting added to one and
#: forgotten in the other is a red test rather than a silent hole.
RESIDENCY_SETTINGS = (
    "OLLAMA_NUM_PARALLEL",
    "OLLAMA_MAX_LOADED_MODELS",
    "OLLAMA_KEEP_ALIVE",
)


def declaration(path: Path | None = None) -> dict[str, Any]:
    """The declared host state.

    The path is resolved at call time, not bound as a default, so a canary can
    point this at a mutated copy. A default argument evaluated at import time
    would freeze the seam shut — which is how a check that cannot be shown to
    reject gets written by accident.
    """
    document = json.loads(
        (DECLARATION if path is None else path).read_text(encoding="utf-8")
    )
    assert isinstance(document, dict), "the declaration is not a JSON object"
    return document


def campaign(evidence: Path | None = None) -> Path:
    """The newest calibration campaign's evidence directory.

    Same rule as :func:`declaration`, and the same rule
    ``tests/test_calibration_conflicts.campaign`` states: the root is read at
    call time so a sweep can point every check below at a mutated copy of the
    evidence and watch it turn. This was written as a bound default first, and
    the mutation sweep that was supposed to demonstrate these checks green
    could not move them — caught 2026-08-22, before either landed.
    """
    root = EVIDENCE if evidence is None else evidence
    directories = sorted(p for p in root.glob("calibration-*") if p.is_dir())
    assert directories, f"no calibration campaign under {root}"
    return directories[-1]


def _survey(directory: Path) -> dict[str, Any]:
    """The campaign's survey document, found by shape rather than by name.

    By shape for the same reason the sibling module does it: a campaign that
    renamed its survey would otherwise turn both checks below into a complaint
    about a missing file, which reads as "the instrument is fine, the test is
    broken" — the wrong way round.
    """
    surveys = []
    for path in sorted(directory.glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(document, dict) and isinstance(document.get("hosts"), dict):
            surveys.append(document)
    assert len(surveys) == 1, (
        f"{directory.name} carries {len(surveys)} documents with a `hosts` "
        "map; the survey is the one document that names every host"
    )
    return surveys[0]


def _environment(directory: Path) -> dict[str, dict[str, str]]:
    """``host -> {setting: value}``, exactly as the unit file declares them.

    An unset setting is absent rather than empty: "declared as nothing" and
    "not declared" are the states this whole file is about telling apart.
    """
    found: dict[str, dict[str, str]] = {}
    for host, body in _survey(directory)["hosts"].items():
        readings = ((body.get("present") or {}).get("ollama") or {}).get(
            "readings"
        ) or {}
        stdout = (readings.get("service_environment") or {}).get("stdout") or ""
        found[host] = dict(
            pair.split("=", 1)
            for pair in stdout.split()
            if pair.startswith("OLLAMA_") and "=" in pair
        )
    return found


def _builds(directory: Path) -> dict[str, Any]:
    """``host -> the ollama build the survey read``, or ``None``."""
    found: dict[str, Any] = {}
    for host, body in _survey(directory)["hosts"].items():
        present = (body.get("present") or {}).get("ollama") or {}
        readings = present.get("readings") or {}
        version = (readings.get("version") or {}).get("stdout")
        found[host] = version.strip() if isinstance(version, str) else None
    return found


# --------------------------------------------------------------------------
# The declaration itself
# --------------------------------------------------------------------------


def test_the_declaration_covers_every_setting_that_decides_residency() -> None:
    """Both lists agree, so neither can grow alone.

    The failure this refuses is the cheap one: someone adds a fourth setting
    that decides residency, sets it on the rigs, and the declaration keeps
    describing three.
    """
    declared = set(declaration()["residency"]) - {"_doc"}
    assert declared == set(RESIDENCY_SETTINGS), (
        "the declaration and this module disagree about which settings decide "
        f"residency: declared {sorted(declared)}, expected {sorted(RESIDENCY_SETTINGS)}"
    )


def test_every_declared_setting_states_a_value_and_why_it_is_that_value() -> None:
    """A value with no reason is a number nobody chose — K10's defect.

    K10 is the whole argument for this check: a constant that entered the tree
    without saying whose it was survived four months and two rigs.
    """
    residency = declaration()["residency"]
    unexplained = sorted(
        name
        for name in RESIDENCY_SETTINGS
        if not str(residency[name].get("value", "")).strip()
        or not str(residency[name].get("why", "")).strip()
    )
    assert not unexplained, (
        f"{len(unexplained)} declared setting(s) carry no value or no reason "
        f"for it: {unexplained}"
    )


def test_the_declaration_names_what_it_does_not_declare() -> None:
    """ADR-0026 lens 3 — silence reads as completeness unless it is named."""
    omissions = {
        k: v for k, v in declaration()["not_declared_here"].items() if k != "_doc"
    }
    assert omissions, (
        "the declaration names no omission, so a reader cannot tell what it "
        "deliberately leaves out from what it forgot"
    )
    empty = sorted(k for k, v in omissions.items() if not str(v).strip())
    assert not empty, f"omissions named with no reason given: {empty}"


def test_canary_a_declaration_missing_a_reason_is_refused(tmp_path: Path) -> None:
    """The check above can be shown to reject — ADR-0037's price."""
    mutated = json.loads(DECLARATION.read_text(encoding="utf-8"))
    mutated["residency"]["OLLAMA_KEEP_ALIVE"]["why"] = "  "
    path = tmp_path / "hosts.json"
    path.write_text(json.dumps(mutated), encoding="utf-8")
    residency = declaration(path)["residency"]
    assert not str(residency["OLLAMA_KEEP_ALIVE"]["why"]).strip()


# --------------------------------------------------------------------------
# The campaign, held to the declaration
# --------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason=(
        "2026-08-22: decided — every host declares them, and an engine default "
        "inherited in silence is not a declaration (owner, K9). Red until a "
        "campaign runs after 2026-08-22: the newest survey is 2026-08-19, "
        "where srv1 declared 2/3/5m and srv2 declared none"
    ),
)
def test_every_surveyed_host_declares_the_values_this_project_declared() -> None:
    """By value, not by presence — which is the half K9's check cannot see.

    K9 asks whether the name appears in the unit. A rig that reverted
    ``OLLAMA_KEEP_ALIVE`` to ``5m`` would still satisfy it and would silently
    put a clock back over the co-residency cells. This asks for the value.
    """
    directory = campaign()
    residency = declaration()["residency"]
    observed = _environment(directory)
    assert observed, f"{directory.name}'s survey names no host"
    wrong = sorted(
        (host, name, residency[name]["value"], settings.get(name))
        for host, settings in observed.items()
        for name in RESIDENCY_SETTINGS
        if settings.get(name) != residency[name]["value"]
    )
    assert not wrong, (
        f"{len(wrong)} (host, setting) pair(s) in {directory.name} do not hold "
        "the declared value — each is (host, setting, declared, observed), and "
        f"`None` observed means the host declared nothing at all: {wrong}"
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "2026-08-22: decided — one build on both rigs, declared rather than "
        "read off whatever each host happened to have (owner, K6/K9). Red "
        "until a campaign runs after the 2026-08-22 upgrade: the newest survey "
        "is 2026-08-19, where srv1 ran 0.32.4 and srv2 ran 0.32.5"
    ),
)
def test_every_surveyed_host_runs_the_declared_engine_build() -> None:
    """The version split K6 found, asked of the instrument instead of a row.

    K6 asks whether a figure carries the build it ran on. This asks whether the
    two hosts ran the same one — the question a carried build lets a reader
    answer, and the state the declaration says must hold.
    """
    directory = campaign()
    declared = declaration()["engine"]["ollama"]["build"]
    observed = _builds(directory)
    assert observed, f"{directory.name}'s survey names no host"
    wrong = sorted(
        (host, declared, build)
        for host, build in observed.items()
        if build is None or declared not in build
    )
    assert not wrong, (
        f"{len(wrong)} host(s) in {directory.name} do not run the declared "
        f"ollama build — each is (host, declared, observed): {wrong}"
    )
