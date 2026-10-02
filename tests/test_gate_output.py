"""The output checks — the evidence kinds a structural check makes itself.

``media_valid`` is the one check with a real validator in P1: it reads the
output file's own bytes and answers whether they are a file of the declared
media kind. Images are checked past the header — dimensions must be present
and positive, and the file must be structurally complete — and audio is
checked past the header too — duration must be determinable and positive for
WAV, FLAC and MP3 (for MP3, a valid frame header whose first frame body
fits), and page structure only for OGG, whose duration is deferred — while
video stays header-only until P2 adds its duration and decode checks.

The three other kinds (``safety_pass``, ``asr_wer``, ``grounded``) name
validators that land with P2; this file pins their check names and their
"not yet wired" behaviour. A check whose validator is missing is inconclusive
— a rejection — never a clean pass, so a contract declaring one never reads
as clean.
"""

from __future__ import annotations

import struct
import zlib
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


# Minimal, genuinely valid image and audio files, generated with the standard
# library so media_valid's deeper-than-header checks (dimensions and decode
# completeness for images, duration and structural completeness for audio)
# have a real file to accept. Video stays header-only for now.
def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def _png(width: int = 2, height: int = 2) -> bytes:
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + b"\x00" * (width * 3) for _ in range(height))
    return (
        signature
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", zlib.compress(raw))
        + _png_chunk(b"IEND", b"")
    )


def _jpeg_segment(marker: int, payload: bytes) -> bytes:
    return b"\xff" + bytes([marker]) + struct.pack(">H", len(payload) + 2) + payload


def _jpeg(width: int = 4, height: int = 3) -> bytes:
    return (
        b"\xff\xd8"
        + _jpeg_segment(0xDB, b"\x00" + b"\x10" * 64)  # DQT, 8-bit table 0
        + _jpeg_segment(
            0xC0, struct.pack(">BHHB", 8, height, width, 1) + b"\x01\x11\x00"
        )  # SOF0
        + _jpeg_segment(0xC4, b"\x00" + b"\x00" * 16)  # DHT, empty DC table
        + _jpeg_segment(0xDA, struct.pack(">B", 1) + b"\x01\x00" + b"\x00\x3f\x00")
        + b"\x00\x00\x00\x00"
        + b"\xff\xd9"
    )


def _gif(width: int = 1, height: int = 1) -> bytes:
    return (
        b"GIF89a"
        + struct.pack("<HH", width, height)
        + b"\x80\x00\x00"
        + b"\x00\x00\x00\xff\xff\xff"
        + b"\x2c"
        + struct.pack("<HHHH", 0, 0, width, height)
        + b"\x00"
        + b"\x02"
        + b"\x02\x44\x01"
        + b"\x00"
        + b"\x3b"
    )


def _bmp(width: int = 2, height: int = 2) -> bytes:
    dib = 40
    row_size = (width * 3 + 3) // 4 * 4
    pixel_bytes = row_size * height
    pixel_offset = 14 + dib
    file_size = pixel_offset + pixel_bytes
    file_header = (
        b"BM"
        + struct.pack("<I", file_size)
        + b"\x00\x00\x00\x00"
        + struct.pack("<I", pixel_offset)
    )
    dib_header = struct.pack(
        "<IiiHHIIiiII", dib, width, height, 1, 24, 0, pixel_bytes, 2835, 2835, 0, 0
    )
    return file_header + dib_header + b"\x00" * pixel_bytes


def _webp(width: int = 2, height: int = 2) -> bytes:
    payload = (
        b"\x00\x00\x00\x00"
        + (width - 1).to_bytes(3, "little")
        + (height - 1).to_bytes(3, "little")
    )
    chunk = b"VP8X" + struct.pack("<I", len(payload)) + payload
    return b"RIFF" + struct.pack("<I", 4 + len(chunk)) + b"WEBP" + chunk


def _webp_vp8(width: int = 2, height: int = 2) -> bytes:
    frame = (
        b"\x9d\x01\x2a"  # 3-byte frame tag
        + b"\x9d\x01\x2a"  # 3-byte start code
        + struct.pack("<H", (width - 1) & 0x3FFF)
        + struct.pack("<H", (height - 1) & 0x3FFF)
        + b"\x00"  # scale/version
    )
    chunk = b"VP8 " + struct.pack("<I", len(frame)) + frame
    return b"RIFF" + struct.pack("<I", 4 + len(chunk)) + b"WEBP" + chunk


def _webp_vp8l(width: int = 2, height: int = 2) -> bytes:
    w = width - 1
    h = height - 1
    header = bytes(
        [
            0x2F,
            w & 0xFF,
            ((w >> 8) & 0x3F) | ((h & 0x03) << 6),
            (h >> 2) & 0xFF,
            (h >> 10) & 0x0F,
        ]
    )
    chunk = b"VP8L" + struct.pack("<I", len(header)) + header
    return b"RIFF" + struct.pack("<I", 4 + len(chunk)) + b"WEBP" + chunk


def _syncsafe(size: int) -> bytes:
    """An ID3v2 tag size as four syncsafe bytes (low seven bits, big-endian)."""
    return bytes(
        [(size >> 21) & 0x7F, (size >> 14) & 0x7F, (size >> 7) & 0x7F, size & 0x7F]
    )


def _wav(byte_rate: int = 88200) -> bytes:
    fmt_payload = struct.pack("<HHIIHH", 1, 1, 44100, byte_rate, 2, 16)
    fmt_chunk = b"fmt " + struct.pack("<I", len(fmt_payload)) + fmt_payload
    data_chunk = b"data" + struct.pack("<I", 4) + b"\x00" * 4
    body = b"WAVE" + fmt_chunk + data_chunk
    return b"RIFF" + struct.pack("<I", len(body)) + body


def _flac(sample_rate: int = 44100) -> bytes:
    info = (sample_rate << 44) | (1 << 41) | (15 << 36) | 44100
    payload = (
        struct.pack(">HH", 4096, 4096)
        + b"\x00\x00\x00"
        + b"\x00\x00\x00"
        + info.to_bytes(8, "big")
        + b"\x00" * 16
    )
    return b"fLaC" + b"\x80" + (34).to_bytes(3, "big") + payload


def _ogg() -> bytes:
    return (
        b"OggS"
        + b"\x00"
        + b"\x02"
        + struct.pack("<Q", 0)
        + struct.pack("<I", 1)
        + struct.pack("<I", 0)
        + struct.pack("<I", 0)
        + b"\x01"
        + b"\x01"
        + b"\x00"
    )


def _jpeg_without_sof() -> bytes:
    sos = _jpeg_segment(0xDA, struct.pack(">B", 1) + b"\x01\x00" + b"\x00\x3f\x00")
    return b"\xff\xd8" + sos + b"\xff\xd9"


def _bmp_with_unknown_dib() -> bytes:
    dib = 44
    pixel_offset = 14 + dib
    file_size = pixel_offset + 4
    file_header = (
        b"BM"
        + struct.pack("<I", file_size)
        + b"\x00\x00\x00\x00"
        + struct.pack("<I", pixel_offset)
    )
    return file_header + struct.pack("<I", dib) + b"\x00" * (dib - 4) + b"\x00" * 4


def _bmp_negative_width() -> bytes:
    dib = 40
    pixel_offset = 14 + dib
    pixel_bytes = 16
    file_size = pixel_offset + pixel_bytes
    file_header = (
        b"BM"
        + struct.pack("<I", file_size)
        + b"\x00\x00\x00\x00"
        + struct.pack("<I", pixel_offset)
    )
    dib_header = struct.pack(
        "<IiiHHIIiiII", dib, -5, 2, 1, 24, 0, pixel_bytes, 2835, 2835, 0, 0
    )
    return file_header + dib_header + b"\x00" * pixel_bytes


def _webp_without_a_vp8_chunk() -> bytes:
    payload = b"\x00" * 4
    chunk = b"EXIF" + struct.pack("<I", len(payload)) + payload
    return b"RIFF" + struct.pack("<I", 4 + len(chunk)) + b"WEBP" + chunk


PNG = _png()
JPEG = _jpeg()
GIF = _gif()
BMP = _bmp()
WEBP = _webp()

WAV = _wav()
# Structurally valid enough for the fields each check reads, not bit-accurate decodes.
MP3_FRAME = b"\xff\xfb\x90\x64" + b"\x00" * 413
MP3_ID3 = b"ID3\x04\x00\x00" + _syncsafe(16) + b"\x00" * 16 + MP3_FRAME
FLAC = _flac()
OGG = _ogg()

MP4 = b"\x00\x00\x00\x14" + b"ftyp" + b"mp42" + b"\x00" * 8
WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 16
AVI = b"RIFF" + b"\x00\x00\x00\x00" + b"AVI " + b"\x00" * 8


def _file(tmp_path: Path, name: str, data: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


@pytest.mark.parametrize(
    "data",
    [
        PNG,
        JPEG,
        GIF,
        BMP,
        WEBP,
        _webp_vp8(),
        _webp_vp8(1, 1),
        _webp_vp8l(),
        _webp_vp8l(1, 1),
    ],
    ids=[
        "png",
        "jpeg",
        "gif",
        "bmp",
        "webp-vp8x",
        "webp-vp8",
        "webp-vp8-1x1",
        "webp-vp8l",
        "webp-vp8l-1x1",
    ],
)
def test_every_known_image_header_is_a_valid_image(tmp_path: Path, data: bytes) -> None:
    assert media_valid(_file(tmp_path, "out.bin", data), MEDIA_IMAGE) == []


# --- deeper-than-header image checks ----------------------------------------


@pytest.mark.parametrize(
    "data",
    [
        _png(width=0, height=2),
        _jpeg_without_sof(),
        b"GIF89a" + struct.pack("<HH", 0, 2) + b"\x3b",
        _bmp_with_unknown_dib(),
        _webp_without_a_vp8_chunk(),
        _bmp_negative_width(),
    ],
    ids=["png", "jpeg", "gif", "bmp", "webp", "bmp-negative-width"],
)
def test_a_zero_or_missing_image_dimension_is_refused_by_name(
    tmp_path: Path, data: bytes
) -> None:
    findings = media_valid(_file(tmp_path, "out.bin", data), MEDIA_IMAGE)
    assert [f.code for f in findings] == ["bad-dimensions"]


@pytest.mark.parametrize(
    "data",
    [
        _png()[:-8],
        _jpeg()[:-2],
        _gif()[:-1],
        _bmp()[:53],
        _webp()[:-1],
    ],
    ids=["png", "jpeg", "gif", "bmp", "webp"],
)
def test_a_truncated_image_is_refused_by_name(tmp_path: Path, data: bytes) -> None:
    findings = media_valid(_file(tmp_path, "out.bin", data), MEDIA_IMAGE)
    assert [f.code for f in findings] == ["truncated"]


def test_a_jpeg_with_a_dnl_marker_is_valid(tmp_path: Path) -> None:
    dnl = _jpeg_segment(0xDC, struct.pack(">H", 1))
    data = (
        b"\xff\xd8"
        + _jpeg_segment(0xC0, struct.pack(">BHHB", 8, 2, 2, 1) + b"\x01\x11\x00")
        + dnl
        + _jpeg_segment(0xDA, struct.pack(">B", 1) + b"\x01\x00" + b"\x00\x3f\x00")
        + b"\xff\xd9"
    )
    assert media_valid(_file(tmp_path, "out.jpg", data), MEDIA_IMAGE) == []


def test_a_png_whose_idat_stream_does_not_decompress_is_refused(
    tmp_path: Path,
) -> None:
    ihdr = struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0)
    data = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", b"not a zlib stream")
        + _png_chunk(b"IEND", b"")
    )
    findings = media_valid(_file(tmp_path, "out.png", data), MEDIA_IMAGE)
    assert [f.code for f in findings] == ["truncated"]
    assert "does not decompress" in findings[0].message


@pytest.mark.parametrize(
    "data",
    [WAV, MP3_ID3, MP3_FRAME, FLAC, OGG],
)
def test_every_known_audio_header_is_valid_audio(tmp_path: Path, data: bytes) -> None:
    assert media_valid(_file(tmp_path, "out.bin", data), MEDIA_AUDIO) == []


@pytest.mark.parametrize(
    "data",
    [
        _wav(byte_rate=0),
        _flac(sample_rate=0),
        b"ID3\x04\x00\x00" + _syncsafe(16) + b"\x00" * 16 + b"\x00" * 32,
        b"ID3\x04\x00\x00" + _syncsafe(0) + b"\xff\xeb\x90\x64",
    ],
    ids=[
        "wav-zero-byte-rate",
        "flac-zero-sample-rate",
        "mp3-no-frame-header",
        "mp3-reserved-frame-header",
    ],
)
def test_audio_with_no_duration_info_is_refused(tmp_path: Path, data: bytes) -> None:
    findings = media_valid(_file(tmp_path, "out.bin", data), MEDIA_AUDIO)
    assert [f.code for f in findings] == ["bad-duration"]


@pytest.mark.parametrize(
    "data",
    [
        _wav()[:-1],
        _flac()[:20],
        b"OggS" + b"\x00" * 10,
        b"\xff\xfb\x90\x64" + b"\x00" * 10,
    ],
    ids=[
        "wav-riff-size-mismatch",
        "flac-streaminfo-cut-short",
        "ogg-short-page",
        "mp3-header-only",
    ],
)
def test_a_truncated_audio_file_is_refused(tmp_path: Path, data: bytes) -> None:
    findings = media_valid(_file(tmp_path, "out.bin", data), MEDIA_AUDIO)
    assert [f.code for f in findings] == ["truncated"]


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


def test_a_check_whose_validator_is_missing_is_inconclusive_not_clean(
    tmp_path: Path,
) -> None:
    """A missing validator is inconclusive, never clean — the gate's one rule."""
    report = OutputChecks(
        checks=(SAFETY_PASS,), workspace=tmp_path, target="out.bin"
    ).run()
    assert report.findings == ()
    assert len(report.inconclusive) == 1
    assert report.inconclusive[0].rung == SAFETY_PASS
    assert report.inconclusive[0].tool == "safety-classifier"
    assert len(report.environment_issues) == 1
    assert SAFETY_PASS in report.environment_issues[0]
    assert "is inconclusive" in report.environment_issues[0]
    assert "not available" in report.environment_issues[0]
    assert "skipped" not in report.environment_issues[0]


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
    assert [r.rung for r in report.inconclusive] == [SAFETY_PASS]


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
