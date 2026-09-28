"""The host state this project declares.

The owner's K9 ruling: every host declares the settings that decide residency,
and an engine default inherited in silence is not a declaration. A finding is a
check, not a paragraph, so ``tools/runs/hosts.json`` is the declaration and the
checks below hold it complete and self-describing: they fail the moment a
setting that decides residency is added without a value or a reason.

No check in this module calls the survey helpers below (:func:`campaign`,
:func:`_survey`, :func:`_environment`, :func:`_builds`): the campaign half is
not held here, as the note at the end says.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
EVIDENCE = REPO / "records" / "evidence"
DECLARATION = REPO / "tools" / "runs" / "hosts.json"

#: The settings that decide whether a model stays on the card and whether a
#: second may join it. Named here as well as in the declaration on purpose: the
#: first check below holds the two to each other, so a setting added to one and
#: forgotten in the other is a red test rather than a silent hole.
#:
#: **Empty, and the emptiness is the declaration.** Both engines served take the
#: residency decisions on the command line the compose file carries — ``--parallel`` and
#: ``-c`` on llama.cpp, ``--max-num-seqs`` and ``--max-model-len`` on vLLM — so
#: there is no daemon-wide setting left for a rig to hold and for this file to
#: state. The checks below stay: they are what re-arms the moment one returns,
#: and an empty tuple still refuses a setting added to the declaration alone.
RESIDENCY_SETTINGS: tuple[str, ...] = ()


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
    call time so a sweep can point a check at a mutated copy of the evidence
    and watch it turn; a bound default would freeze it.
    """
    root = EVIDENCE if evidence is None else evidence
    directories = sorted(p for p in root.glob("calibration-*") if p.is_dir())
    assert directories, f"no calibration campaign under {root}"
    return directories[-1]


def _survey(directory: Path) -> dict[str, Any]:
    """The campaign's survey document, found by shape rather than by name.

    By shape for the same reason the sibling module does it: a campaign that
    renamed its survey would otherwise turn a check that reads it into a complaint
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

    The failure this refuses is the cheap one: someone adds a setting that
    decides residency, sets it on the rigs, and the declaration keeps describing
    the old list.
    """
    declared = set(declaration()["residency"]) - {"_doc", "_removed_2026_09_06"}
    assert declared == set(RESIDENCY_SETTINGS), (
        "the declaration and this module disagree about which settings decide "
        f"residency: declared {sorted(declared)}, expected {sorted(RESIDENCY_SETTINGS)}"
    )


def test_every_declared_setting_states_a_value_and_why_it_is_that_value() -> None:
    """A value with no reason is a number nobody chose — K10's defect.

    K10 is the whole argument for this check: a constant that entered the tree
    without saying whose it was.
    """
    unexplained = _unexplained(declaration()["residency"], RESIDENCY_SETTINGS)
    assert not unexplained, (
        f"{len(unexplained)} declared setting(s) carry no value or no reason "
        f"for it: {unexplained}"
    )


def _unexplained(residency: dict[str, Any], names: tuple[str, ...]) -> list[str]:
    """Which of ``names`` the declaration states without a value or a reason.

    Lifted out of the check above so the canary can exercise the same predicate
    on a declaration it builds. With :data:`RESIDENCY_SETTINGS` empty the check
    has nothing to iterate, and a check that cannot be shown to reject proves
    nothing — so the predicate is what is tested, not the loop.
    """
    return sorted(
        name
        for name in names
        if not str(residency.get(name, {}).get("value", "")).strip()
        or not str(residency.get(name, {}).get("why", "")).strip()
    )


def test_the_declaration_names_what_it_does_not_declare() -> None:
    """Silence reads as completeness unless it is named."""
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
    """The check above can be shown to reject.

    Against a setting this canary invents rather than one the declaration
    holds, because it holds none. Exercising the predicate keeps the canary
    true to what the check does, and keeps it working on the day a setting
    comes back.
    """
    mutated = json.loads(DECLARATION.read_text(encoding="utf-8"))
    mutated["residency"]["SOME_FUTURE_RESIDENCY_SETTING"] = {
        "value": "0",
        "why": "  ",
    }
    path = tmp_path / "hosts.json"
    path.write_text(json.dumps(mutated), encoding="utf-8")
    residency = declaration(path)["residency"]
    assert _unexplained(residency, ("SOME_FUTURE_RESIDENCY_SETTING",)) == [
        "SOME_FUTURE_RESIDENCY_SETTING"
    ]
    # And a setting that states both is not flagged, so the predicate is
    # discriminating rather than always-true.
    residency["SOME_FUTURE_RESIDENCY_SETTING"]["why"] = "because it was measured"
    assert _unexplained(residency, ("SOME_FUTURE_RESIDENCY_SETTING",)) == []


# --------------------------------------------------------------------------
# The campaign, held to the declaration
# --------------------------------------------------------------------------


# Not held here: that every surveyed host holds the DECLARED VALUE of each
# residency setting (K9's other half), and that both rigs run one declared
# engine build (K6). This project declares no daemon-wide setting for a host to
# hold. When a residency setting returns, `RESIDENCY_SETTINGS` above re-arms the
# completeness half, and the value half is written against whatever surveys the
# engine that carries it.
