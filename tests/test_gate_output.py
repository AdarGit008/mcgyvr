"""The output checks — the evidence kinds a structural check makes itself.

``media_valid`` is the one check with a real validator in P1: it reads the
output file's own bytes and answers whether they are a file of the declared
media kind. A worker cannot fake a header, and a wrong-kind or empty output is
refused by name rather than left for a downstream tool to trip over.

The three other kinds (``safety_pass``, ``asr_wer``, ``grounded``) name
validators that land with P2; this file pins their check names and their
"not yet wired" behaviour, so a contract declaring one never reads as clean.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.contract import loads
from mcgyvr.drive import output_checks_for
from mcgyvr.gate.output import (
    MEDIA_AUDIO,
    MEDIA_IMAGE,
    MEDIA_VALID,
    MEDIA_VIDEO,
    SAFETY_PASS,
    OutputChecks,
    media_valid,
)

# One minimal, structurally-valid header per known format. The bytes after the
# signature are irrelevant to media_valid, which reads only the header.
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16
GIF = b"GIF89a" + b"\x00" * 16
BMP = b"BM" + b"\x00" * 16
WEBP = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 8

WAV = b"RIFF" + b"\x00\x00\x00\x00" + b"WAVE" + b"\x00" * 8
MP3_ID3 = b"ID3\x04\x00" + b"\x00" * 16
MP3_FRAME = b"\xff\xfb\x90\x64" + b"\x00" * 16
FLAC = b"fLaC" + b"\x00" * 16
OGG = b"OggS" + b"\x00" * 16

MP4 = b"\x00\x00\x00\x14" + b"ftyp" + b"mp42" + b"\x00" * 8
WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 16
AVI = b"RIFF" + b"\x00\x00\x00\x00" + b"AVI " + b"\x00" * 8


def _file(tmp_path: Path, name: str, data: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


@pytest.mark.parametrize(
    "data",
    [PNG, JPEG, GIF, BMP, WEBP],
)
def test_every_known_image_header_is_a_valid_image(tmp_path: Path, data: bytes) -> None:
    assert media_valid(_file(tmp_path, "out.bin", data), MEDIA_IMAGE) == []


@pytest.mark.parametrize(
    "data",
    [WAV, MP3_ID3, MP3_FRAME, FLAC, OGG],
)
def test_every_known_audio_header_is_valid_audio(tmp_path: Path, data: bytes) -> None:
    assert media_valid(_file(tmp_path, "out.bin", data), MEDIA_AUDIO) == []


@pytest.mark.parametrize(
    "data",
    [MP4, WEBM, AVI],
)
def test_every_known_video_header_is_valid_video(tmp_path: Path, data: bytes) -> None:
    assert media_valid(_file(tmp_path, "out.bin", data), MEDIA_VIDEO) == []


def test_a_text_file_declared_as_an_image_is_refused_by_name(tmp_path: Path) -> None:
    path = _file(tmp_path, "out.png", b"not an image at all\n")
    findings = media_valid(path, MEDIA_IMAGE)
    assert len(findings) == 1
    assert findings[0].check == "media_valid"
    assert "image" in findings[0].message


def test_a_wrong_kind_is_refused_even_when_the_header_is_another_media_kind(
    tmp_path: Path,
) -> None:
    """A PNG is a valid image and an invalid audio file; the declared kind is
    the bar, not 'is this media of some kind'."""
    findings = media_valid(_file(tmp_path, "out.wav", PNG), MEDIA_AUDIO)
    assert len(findings) == 1
    assert findings[0].check == "media_valid"


def test_an_empty_output_is_refused_by_name(tmp_path: Path) -> None:
    findings = media_valid(_file(tmp_path, "out.png", b""), MEDIA_IMAGE)
    assert len(findings) == 1
    assert findings[0].check == "media_valid"


def test_an_unknown_kind_is_refused_not_guessed(tmp_path: Path) -> None:
    """A kind the gate was not asked to know is a defect to fix, not a guess."""
    with pytest.raises(ValueError, match="kind"):
        media_valid(_file(tmp_path, "out.bin", PNG), "hologram")


# --- the output-checks rung -------------------------------------------------


def test_the_media_valid_check_runs_over_the_artifact(tmp_path: Path) -> None:
    _file(tmp_path, "out.bin", PNG)
    report = OutputChecks(
        checks=("media_valid",),
        workspace=tmp_path,
        target="out.bin",
        media_kind=MEDIA_IMAGE,
    ).run()
    assert report.findings == ()
    assert report.environment_issues == ()


def test_the_media_valid_check_refuses_a_wrong_artifact(tmp_path: Path) -> None:
    _file(tmp_path, "out.bin", b"plain text")
    report = OutputChecks(
        checks=("media_valid",),
        workspace=tmp_path,
        target="out.bin",
        media_kind=MEDIA_IMAGE,
    ).run()
    assert len(report.findings) == 1
    assert report.findings[0].check == MEDIA_VALID


def test_a_check_whose_validator_is_not_wired_is_skipped_by_name(
    tmp_path: Path,
) -> None:
    """A P2 check reports 'not available', never clean — the gate's one rule."""
    report = OutputChecks(
        checks=(SAFETY_PASS,), workspace=tmp_path, target="out.bin"
    ).run()
    assert report.findings == ()
    assert len(report.environment_issues) == 1
    assert SAFETY_PASS in report.environment_issues[0]
    assert "not available" in report.environment_issues[0]


def test_one_unwired_check_does_not_hide_another_checks_findings(
    tmp_path: Path,
) -> None:
    """media_valid's finding must survive safety_pass raising, so a bad artifact
    is not accepted because a second check happened to be unwired."""
    _file(tmp_path, "out.bin", b"plain text")
    report = OutputChecks(
        checks=(MEDIA_VALID, SAFETY_PASS),
        workspace=tmp_path,
        target="out.bin",
        media_kind=MEDIA_IMAGE,
    ).run()
    assert [f.check for f in report.findings] == [MEDIA_VALID]
    assert any(SAFETY_PASS in e for e in report.environment_issues)


def test_an_unknown_check_name_is_refused_not_guessed(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="check"):
        OutputChecks(checks=("vibes",), workspace=tmp_path, target="out.bin").run()


# --- the drive wiring --------------------------------------------------------


def test_output_checks_for_is_none_for_a_coding_contract() -> None:
    """A coding type declares no structural output kind, so there is no rung."""
    contract = loads(
        """
id: t
task_type: function_implementation
task: Do the thing.
target: src/pkg/f.py
stop_conditions: ["An unknown."]
acceptance: ["pytest -q"]
scope:
  allow: ["src/**"]
"""
    )
    assert output_checks_for(contract, Path(".")) is None


def test_output_checks_for_maps_declared_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    fake_type = SimpleNamespace(
        name="image_generation",
        deterministic=False,
        needs_acceptance_commands=False,
        needs_demonstration_commands=False,
        required_evidence=(
            SimpleNamespace(name="gate", needs_commands=False, baseline="pass"),
            SimpleNamespace(name="media_valid", needs_commands=False, baseline="pass"),
        ),
        guarantee="a media artifact is produced",
    )
    monkeypatch.setattr(
        "mcgyvr.contract.catalog",
        lambda: SimpleNamespace(
            names=("function_implementation",), require=lambda _name: fake_type
        ),
    )
    contract = loads(
        """
id: img
task_type: function_implementation
task: Produce an image.
target: out.png
stop_conditions: ["No image model is bound."]
media_kind: image
scope:
  allow: ["out.png"]
"""
    )

    output = output_checks_for(contract, tmp_path)

    assert output is not None
    assert output.checks == ("media_valid",)
    assert output.media_kind == "image"
    assert output.target == "out.png"
