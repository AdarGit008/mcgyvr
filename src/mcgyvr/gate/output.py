"""Output-checks rung: judge the artifact itself, not the source that made it.

A contract that promises media evidence names the checks it wants, and this
module runs them over the produced file. ``media_valid`` reads the file's
own bytes and decides whether they are a structurally valid image, audio or
video file of the declared kind, looking past the magic bytes for
dimensions, duration and completeness. ``safety_pass`` runs the safety
classifier over the artifact and reports an unsafe verdict. ``asr_wer``
transcribes the audio with whisper and reports a word error rate above the
contract's ceiling.

Each check returns ``Finding`` values and reports a missing or failing tool
as an environment fault; ``OutputChecks`` turns such a fault into an
inconclusive rung, so a check that could not run never reads as a pass.
"""

from __future__ import annotations

import shutil
import struct
import subprocess
import zlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from mcgyvr.gate.adapter import ToolFailedError, ToolUnavailableError
from mcgyvr.gate.findings import Finding

if TYPE_CHECKING:
    from mcgyvr.gate.runner import InconclusiveRung

#: The media kinds a `media_valid` contract may declare, one word each; the
#: kind decides which formats count as a valid output.
MEDIA_IMAGE = "image"
MEDIA_AUDIO = "audio"
MEDIA_VIDEO = "video"
MEDIA_KINDS = (MEDIA_IMAGE, MEDIA_AUDIO, MEDIA_VIDEO)

#: Names of the output checks, declared in a contract's evidence names.
MEDIA_VALID = "media_valid"

#: The two tool-backed checks: `safety_pass` asks the safety classifier about
#: the artifact, and `asr_wer` compares a whisper transcription of the
#: artifact against the transcript the contract states.
SAFETY_PASS = "safety_pass"
ASR_WER = "asr_wer"

#: RIFF form codes, the four bytes at offset 8 of a RIFF file. WEBP, WAVE and
#: AVI share the `RIFF` magic at offset 0, so the form is what tells the three
#: media kinds apart.
_RIFF_FORMS = {b"WEBP": MEDIA_IMAGE, b"WAVE": MEDIA_AUDIO, b"AVI ": MEDIA_VIDEO}

#: Magic-byte prefixes per kind: the cheap first test in _is_kind, which
#: accepts a head that starts with one of its kind's prefixes.
#: MP3 lists one prefix per accepted frame sync (0xFFFB, 0xFFF3, 0xFFF2 and
#: 0xFFFA) because a first frame may start with any of them. MP4 is absent on
#: purpose: its `ftyp` box sits at offset 4, so _MP4_FTYP matches it, and a
#: bare `ftyp` head cannot appear at offset 0.
_PREFIXES: dict[str, tuple[bytes, ...]] = {
    MEDIA_IMAGE: (
        b"\x89PNG\r\n\x1a\n",
        b"\xff\xd8\xff",
        b"GIF87a",
        b"GIF89a",
        b"BM",
    ),
    MEDIA_AUDIO: (
        b"ID3",
        b"\xff\xfb",
        b"\xff\xf3",
        b"\xff\xf2",
        b"\xff\xfa",
        b"fLaC",
        b"OggS",
    ),
    MEDIA_VIDEO: (b"\x1a\x45\xdf\xa3",),
}

#: The box type that opens an MP4 at offset 4, which `_is_kind` reads to spot
#: an ISO base media file before `_mp4_findings` walks its boxes.
_MP4_FTYP = b"ftyp"


def media_valid(path: Path, kind: str, label: str = "") -> list[Finding]:
    """Judge whether `path` is a structurally valid file of `kind`.

    The file is read whole and its header must match one of the known formats
    for `kind`; the matching format's own check then reads as far as it must to
    accept the file. `label` names the artifact in the findings and defaults to
    `str(path)`. An unreadable or empty file is a finding, not an exception;
    only an unknown `kind` raises.
    """
    if kind not in MEDIA_KINDS:
        raise ValueError(f"media_valid: unknown media kind {kind!r}")
    name = label or str(path)
    try:
        data = path.read_bytes()
    except OSError:
        return [
            Finding(
                check=MEDIA_VALID,
                path=name,
                code="unreadable",
                message=(
                    f"the output could not be read, so it cannot be judged a "
                    f"valid {kind}"
                ),
            )
        ]
    if not data:
        return [
            Finding(
                check=MEDIA_VALID,
                path=name,
                code="empty",
                message=f"the output is empty and is not a valid {kind}",
            )
        ]
    if _is_kind(data, kind):
        if kind == MEDIA_IMAGE:
            return _image_findings(name, data)
        elif kind == MEDIA_AUDIO:
            return _audio_findings(name, data)
        elif kind == MEDIA_VIDEO:
            return _video_findings(name, data)
        return []
    return [
        Finding(
            check=MEDIA_VALID,
            path=name,
            code=f"not-{kind}",
            message=(
                f"the output is not a valid {kind}: its header does not match "
                f"any known {kind} format"
            ),
        )
    ]


def _is_kind(data: bytes, kind: str) -> bool:
    """Return whether `data` looks like a file of `kind`.

    A video counts as MP4 when the box type at offset 4 is `ftyp` and the first
    box declares a size the file can hold, any kind counts when the RIFF form at
    offset 8 is that kind's, and otherwise the head must start with one of
    `_PREFIXES[kind]`. Only the head is consulted; the per-format checks look
    deeper.
    """
    if kind == MEDIA_VIDEO and len(data) >= 8 and data[4:8] == _MP4_FTYP:
        box_size = int.from_bytes(data[:4], "big")
        # The first box must declare a size the file can hold: 0 and 1 are the two
        # escape values meaning "to the end of the file" and "a 64-bit size
        # follows", and any other size must be at least the 8-byte box header and no
        # longer than the file itself.
        return box_size in (0, 1) or 8 <= box_size <= len(data)
    if data[:4] == b"RIFF" and len(data) >= 12 and _RIFF_FORMS.get(data[8:12]) == kind:
        return True
    return any(data.startswith(prefix) for prefix in _PREFIXES[kind])


def _finding(name: str, code: str, message: str) -> Finding:
    """Build a `media_valid` finding from `name`, `code` and `message`."""
    return Finding(check=MEDIA_VALID, path=name, code=code, message=message)


def _image_findings(name: str, data: bytes) -> list[Finding]:
    """Send an image to the check for the format its header names.

    PNG, JPEG, GIF, BMP and WEBP are recognised; the empty list is returned only
    for a header that no branch knows.
    """
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return _png_findings(name, data)
    if data.startswith(b"\xff\xd8"):
        return _jpeg_findings(name, data)
    if data.startswith((b"GIF87a", b"GIF89a")):
        return _gif_findings(name, data)
    if data.startswith(b"BM"):
        return _bmp_findings(name, data)
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return _webp_findings(name, data)
    return []


def _audio_findings(name: str, data: bytes) -> list[Finding]:
    """Send audio to the WAV, FLAC, OGG or MP3 check its header names."""
    if data.startswith(b"RIFF") and len(data) >= 12 and data[8:12] == b"WAVE":
        return _wav_findings(name, data)
    if data.startswith(b"fLaC"):
        return _flac_findings(name, data)
    if data.startswith(b"OggS"):
        return _ogg_findings(name, data)
    if data.startswith(b"ID3") or (
        len(data) >= 2 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0
    ):
        return _mp3_findings(name, data)
    return []


def _video_findings(name: str, data: bytes) -> list[Finding]:
    """Send video to the MP4, WEBM or AVI check its header names."""
    if len(data) >= 8 and data[4:8] == b"ftyp":
        return _mp4_findings(name, data)
    if data.startswith(b"\x1a\x45\xdf\xa3"):
        return _webm_findings(name, data)
    if data.startswith(b"RIFF") and len(data) >= 12 and data[8:12] == b"AVI ":
        return _avi_findings(name, data)
    return []


def _mp4_findings(name: str, data: bytes) -> list[Finding]:
    """Walk the MP4's boxes and require the ones that carry a real duration.

    Every box must fit the file, and the top level must hold both a `moov` and
    an `mdat` box; `moov` must in turn hold a version 0 `mvhd` box whose
    timescale and duration are both non-zero. A box that overruns the file is a
    `truncated` finding, a missing box or unusable figure a `bad-duration` one.
    """

    def boxes(start: int, end: int) -> tuple[list[tuple[bytes, int, int]], bool]:
        found: list[tuple[bytes, int, int]] = []
        offset = start
        while offset < end:
            if offset + 8 > end:
                return [], True
            size = int.from_bytes(data[offset : offset + 4], "big")
            box_type = data[offset + 4 : offset + 8]
            payload = offset + 8
            if size == 1:
                if offset + 16 > end:
                    return [], True
                size = int.from_bytes(data[offset + 8 : offset + 16], "big")
                payload = offset + 16
                box_end = offset + size
            elif size == 0:
                box_end = end
            else:
                box_end = offset + size
            if box_end > end:
                return [], True
            found.append((box_type, payload, box_end))
            offset = box_end
        return found, False

    top, truncated = boxes(0, len(data))
    if truncated:
        return [
            _finding(
                name,
                "truncated",
                "the MP4 is truncated: a box overruns the end of the file",
            )
        ]
    moov = next((box for box in top if box[0] == b"moov"), None)
    mdat = next((box for box in top if box[0] == b"mdat"), None)
    if moov is None:
        return [
            _finding(
                name,
                "bad-duration",
                "the MP4 declares no duration: it has no moov box",
            )
        ]
    if mdat is None:
        return [
            _finding(
                name,
                "truncated",
                "the MP4 is truncated: it has no mdat box",
            )
        ]
    children, truncated = boxes(moov[1], moov[2])
    if truncated:
        return [
            _finding(
                name,
                "truncated",
                "the MP4 is truncated: a box overruns the end of the file",
            )
        ]
    mvhd = next((box for box in children if box[0] == b"mvhd"), None)
    if mvhd is None:
        return [
            _finding(
                name,
                "bad-duration",
                "the MP4 declares no duration: it has no mvhd box",
            )
        ]
    payload = data[mvhd[1] : mvhd[2]]
    if len(payload) < 20 or payload[0] != 0:
        return [
            _finding(
                name,
                "bad-duration",
                "the MP4 declares no duration: its mvhd box is short or not version 0",
            )
        ]
    timescale = int.from_bytes(payload[12:16], "big")
    duration = int.from_bytes(payload[16:20], "big")
    if timescale == 0 or duration == 0:
        return [
            _finding(
                name,
                "bad-duration",
                "the MP4 declares no duration: its timescale or duration is zero",
            )
        ]
    return []


def _webm_findings(name: str, data: bytes) -> list[Finding]:
    """Walk the WEBM's EBML elements and require a positive Duration.

    The EBML header and the Segment element must be present and fit the file, a
    missing Segment element being `bad-duration`, and an element walk of the
    Segment must reach the Duration element (0x4489) as a 4-byte big-endian
    float greater than zero. An element that overruns its parent or the file is
    `truncated`; a missing or unusable Duration is `bad-duration`.
    """

    def vint_len(first: int) -> int:
        length = 1
        while length < 8 and not (first & (1 << (8 - length))):
            length += 1
        return length

    def read_element(offset: int, end: int) -> tuple[int, int, int] | None:
        if offset + 1 > end:
            return None
        id_len = vint_len(data[offset])
        if id_len > 4 or offset + id_len > end:
            return None
        elem_id = int.from_bytes(data[offset : offset + id_len], "big")
        size_offset = offset + id_len
        if size_offset + 1 > end:
            return None
        size_len = vint_len(data[size_offset])
        if size_len > 8 or size_offset + size_len > end:
            return None
        value = int.from_bytes(data[size_offset : size_offset + size_len], "big")
        size = value & ~(1 << (7 * size_len))
        payload_start = size_offset + size_len
        return (elem_id, size, payload_start)

    def find_duration(offset: int, end: int) -> tuple[tuple[int, int] | None, bool]:
        spans = [(offset, end)]
        while spans:
            start, stop = spans.pop()
            offset = start
            while offset < stop:
                element = read_element(offset, stop)
                if element is None:
                    return None, True
                elem_id, size, payload_start = element
                payload_end = payload_start + size
                if payload_end > stop:
                    return None, True
                if elem_id == 0x4489:
                    return (payload_start, payload_end), False
                spans.append((payload_start, payload_end))
                offset = payload_end
        return None, False

    header = read_element(0, len(data))
    if header is None or header[0] != 0x1A45DFA3:
        return [
            _finding(
                name,
                "truncated",
                "the WEBM is truncated: its EBML header runs off the end of the file",
            )
        ]
    header_size = header[1]
    segment = read_element(header[2] + header_size, len(data))
    if segment is None or segment[0] != 0x18538067:
        if segment is None:
            return [
                _finding(
                    name,
                    "truncated",
                    "the WEBM is truncated: its Segment element runs off the end "
                    "of the file",
                )
            ]
        return [
            _finding(
                name,
                "bad-duration",
                "the WEBM declares no duration: it has no Segment element",
            )
        ]
    segment_size = segment[1]
    segment_payload = segment[2]
    if segment_payload + segment_size > len(data):
        return [
            _finding(
                name,
                "truncated",
                "the WEBM is truncated: its Segment element overruns the end "
                "of the file",
            )
        ]
    duration_slice, truncated = find_duration(
        segment_payload, segment_payload + segment_size
    )
    if truncated:
        return [
            _finding(
                name,
                "truncated",
                "the WEBM is truncated: an element overruns the end of the file",
            )
        ]
    if duration_slice is None:
        return [
            _finding(
                name,
                "bad-duration",
                "the WEBM declares no duration: it has no Duration element",
            )
        ]
    start, duration_end = duration_slice
    if duration_end - start != 4:
        return [
            _finding(
                name,
                "bad-duration",
                "the WEBM declares no duration: its Duration element is not 4 bytes",
            )
        ]
    duration = struct.unpack(">f", data[start:duration_end])[0]
    if duration <= 0:
        return [
            _finding(
                name,
                "bad-duration",
                "the WEBM declares no duration: its duration is not positive",
            )
        ]
    return []


def _avi_findings(name: str, data: bytes) -> list[Finding]:
    """Walk the AVI's chunks and require the header that carries the duration.

    The RIFF size must equal the file length and no chunk may overrun it, and
    the `hdrl` list must hold an `avih` chunk of at least 56 bytes whose
    `microsec_per_frame` and `total_frames` are both non-zero. A chunk that
    overruns the file is `truncated`; the missing header or a zero figure is
    `bad-duration`.
    """

    def chunks(start: int, end: int) -> tuple[list[tuple[bytes, int, int]], bool]:
        found: list[tuple[bytes, int, int]] = []
        offset = start
        while offset < end:
            if offset + 8 > end:
                return [], True
            fourcc = data[offset : offset + 4]
            size = int.from_bytes(data[offset + 4 : offset + 8], "little")
            payload_start = offset + 8
            payload_end = payload_start + size
            if payload_end > end:
                return [], True
            found.append((fourcc, payload_start, payload_end))
            offset = payload_end + (size % 2)
        return found, False

    riff_size = int.from_bytes(data[4:8], "little")
    if riff_size + 8 != len(data):
        return [
            _finding(
                name,
                "truncated",
                "the AVI is truncated: its RIFF size does not match the file length",
            )
        ]
    top, truncated = chunks(12, len(data))
    if truncated:
        return [
            _finding(
                name,
                "truncated",
                "the AVI is truncated: a chunk overruns the end of the file",
            )
        ]
    avih_payload = b""
    for fourcc, payload_start, payload_end in top:
        if (
            fourcc == b"LIST"
            and payload_end - payload_start >= 4
            and data[payload_start : payload_start + 4] == b"hdrl"
        ):
            inner, truncated = chunks(payload_start + 4, payload_end)
            if truncated:
                return [
                    _finding(
                        name,
                        "truncated",
                        "the AVI is truncated: a chunk overruns the end of the file",
                    )
                ]
            for inner_fourcc, inner_payload_start, inner_payload_end in inner:
                if inner_fourcc == b"avih":
                    avih_payload = data[inner_payload_start:inner_payload_end]
                    break
            if avih_payload:
                break
    if len(avih_payload) < 56:
        return [
            _finding(
                name,
                "bad-duration",
                "the AVI declares no duration: it has no complete avih chunk",
            )
        ]
    microsec_per_frame = int.from_bytes(avih_payload[0:4], "little")
    total_frames = int.from_bytes(avih_payload[16:20], "little")
    if microsec_per_frame == 0 or total_frames == 0:
        return [
            _finding(
                name,
                "bad-duration",
                "the AVI declares no duration: its microsec_per_frame or "
                "total_frames is zero",
            )
        ]
    return []


def _png_findings(name: str, data: bytes) -> list[Finding]:
    """Require a PNG whose IHDR, dimensions and image data are all usable.

    The first chunk must be a full 13-byte IHDR declaring a positive width and
    height, every chunk must fit the file, at least one IDAT must be present, and
    the concatenated IDAT stream must decompress with zlib, so a header-only or
    truncated image is refused rather than accepted on its magic bytes alone.
    """
    if (
        len(data) < 24
        or int.from_bytes(data[8:12], "big") != 13
        or data[12:16] != b"IHDR"
    ):
        return [
            _finding(
                name,
                "bad-dimensions",
                "the PNG declares no dimensions: its first chunk is not a "
                "complete 13-byte IHDR header",
            )
        ]
    width = int.from_bytes(data[16:20], "big")
    height = int.from_bytes(data[20:24], "big")
    if width <= 0 or height <= 0:
        return [
            _finding(
                name,
                "bad-dimensions",
                "the PNG declares a zero or negative width or height in its "
                "IHDR header",
            )
        ]
    idat = bytearray()
    offset = 8
    while offset + 8 <= len(data):
        length = int.from_bytes(data[offset : offset + 4], "big")
        payload_end = offset + 8 + length
        if payload_end + 4 > len(data):
            return [
                _finding(
                    name,
                    "truncated",
                    "the PNG is truncated: a chunk overruns the end of the file",
                )
            ]
        if data[offset + 4 : offset + 8] == b"IDAT":
            idat += data[offset + 8 : payload_end]
        offset = payload_end + 4
    if offset != len(data):
        return [
            _finding(
                name,
                "truncated",
                "the PNG is truncated: a chunk header runs off the end of the file",
            )
        ]
    if not idat:
        return [
            _finding(name, "truncated", "the PNG is truncated: it has no IDAT data")
        ]
    try:
        zlib.decompress(bytes(idat))
    except zlib.error:
        return [
            _finding(
                name,
                "truncated",
                "the PNG is truncated: its IDAT stream does not decompress",
            )
        ]
    return []


def _jpeg_findings(name: str, data: bytes) -> list[Finding]:
    """Walk the JPEG's marker segments and require a decodable frame header.

    The file must end with the EOI marker, its marker stream must stay inside the
    file, the stream must reach an SOS marker, and a start-of-frame segment
    before that point must declare a positive width and height. A marker or
    segment that runs off the end is `truncated`; missing or zero dimensions are
    `bad-dimensions`.
    """
    if not data.endswith(b"\xff\xd9"):
        return [
            _finding(
                name,
                "truncated",
                "the JPEG is truncated: it does not end with the EOI marker",
            )
        ]
    offset = 2
    sof_width: int | None = None
    sof_height: int | None = None
    saw_sos = False
    while offset < len(data):
        while offset < len(data) and data[offset] == 0xFF:
            offset += 1
        if offset >= len(data):
            return [
                _finding(
                    name,
                    "truncated",
                    "the JPEG is truncated: its marker stream runs off the end "
                    "of the file",
                )
            ]
        marker = data[offset]
        offset += 1
        if marker == 0xD9:
            break
        if marker == 0xDA:
            saw_sos = True
            break
        if marker == 0xD8 or marker == 0x01 or 0xD0 <= marker <= 0xD7:
            continue
        if offset + 2 > len(data):
            return [
                _finding(
                    name,
                    "truncated",
                    "the JPEG is truncated: a marker length runs off the end "
                    "of the file",
                )
            ]
        seg_len = int.from_bytes(data[offset : offset + 2], "big")
        offset += 2
        if seg_len < 2 or offset + seg_len - 2 > len(data):
            return [
                _finding(
                    name,
                    "truncated",
                    "the JPEG is truncated: a segment overruns the end of the file",
                )
            ]
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            if seg_len - 2 < 5:
                return [
                    _finding(
                        name,
                        "bad-dimensions",
                        "the JPEG declares no dimensions: its SOF marker is malformed",
                    )
                ]
            sof_height = int.from_bytes(data[offset + 1 : offset + 3], "big")
            sof_width = int.from_bytes(data[offset + 3 : offset + 5], "big")
        offset += seg_len - 2
    if not saw_sos:
        return [
            _finding(
                name,
                "truncated",
                "the JPEG is truncated: it has no SOS (start-of-scan) marker",
            )
        ]
    if sof_width is None or sof_height is None:
        return [
            _finding(
                name,
                "bad-dimensions",
                "the JPEG declares no dimensions: it has no SOF (start-of-frame) "
                "marker",
            )
        ]
    if sof_width <= 0 or sof_height <= 0:
        return [
            _finding(
                name,
                "bad-dimensions",
                "the JPEG declares a zero or negative width or height in its "
                "SOF marker",
            )
        ]
    return []


def _gif_findings(name: str, data: bytes) -> list[Finding]:
    """Require a GIF whose logical screen has a size and whose file is whole.

    The width and height in the logical screen descriptor must both be non-zero
    and the file must end with the 0x3B trailer byte.
    """
    if len(data) < 10:
        return [
            _finding(
                name,
                "bad-dimensions",
                "the GIF declares no dimensions: it ends before its width and "
                "height fields",
            )
        ]
    width = int.from_bytes(data[6:8], "little")
    height = int.from_bytes(data[8:10], "little")
    if width == 0 or height == 0:
        return [
            _finding(name, "bad-dimensions", "the GIF declares a zero width or height")
        ]
    if not data.endswith(b"\x3b"):
        return [
            _finding(
                name,
                "truncated",
                "the GIF is truncated: it does not end with the trailer byte",
            )
        ]
    return []


def _bmp_findings(name: str, data: bytes) -> list[Finding]:
    """Read the BMP's DIB header and require dimensions and pixel data to follow.

    The DIB header size must be one of the known sizes and the header must fit
    the file; the width must be positive and the height non-zero (a negative
    height means a top-down bitmap); and the file must be at least as long as the
    pixel-data offset it declares.
    """
    if len(data) < 18:
        return [
            _finding(
                name,
                "bad-dimensions",
                "the BMP declares no dimensions: it ends before its DIB header size",
            )
        ]
    dib = int.from_bytes(data[14:18], "little")
    if dib not in (12, 40, 52, 56, 64, 108, 124):
        return [
            _finding(
                name,
                "bad-dimensions",
                "the BMP declares an unknown DIB header size, so its dimensions "
                "cannot be read",
            )
        ]
    if len(data) < 14 + dib:
        return [
            _finding(
                name,
                "truncated",
                "the BMP is truncated: it ends before its DIB header completes",
            )
        ]
    if dib == 12:
        width = int.from_bytes(data[18:20], "little")
        height = int.from_bytes(data[20:22], "little")
        invalid = width == 0 or height == 0
    else:
        width = int.from_bytes(data[18:22], "little", signed=True)
        height = int.from_bytes(data[22:26], "little", signed=True)
        invalid = width <= 0 or height == 0
    if invalid:
        return [
            _finding(
                name,
                "bad-dimensions",
                "the BMP declares a zero or negative width, or a zero height",
            )
        ]
    pixel_offset = int.from_bytes(data[10:14], "little")
    if len(data) < pixel_offset:
        return [
            _finding(
                name,
                "truncated",
                "the BMP is truncated: it is shorter than its pixel-data offset",
            )
        ]
    return []


def _webp_findings(name: str, data: bytes) -> list[Finding]:
    """Require a WEBP whose RIFF size matches and whose first chunk has a size.

    The RIFF size must equal the file length, and the first chunk must be VP8,
    VP8L or VP8X with a header long enough to read a width and height from
    (bit-packed for lossy and lossless, 24-bit little-endian for extended), which
    must not be zero.
    """
    riff_size = int.from_bytes(data[4:8], "little")
    if riff_size + 8 != len(data):
        return [
            _finding(
                name,
                "truncated",
                "the WEBP is truncated: its RIFF size does not match the file length",
            )
        ]
    fourcc = data[12:16]
    if fourcc == b"VP8 ":
        if len(data) < 30:
            return [
                _finding(
                    name,
                    "truncated",
                    "the WEBP is truncated: its VP8 frame header is cut short",
                )
            ]
        width = 1 + (int.from_bytes(data[26:28], "little") & 0x3FFF)
        height = 1 + (int.from_bytes(data[28:30], "little") & 0x3FFF)
        if width == 0 or height == 0:
            return [
                _finding(
                    name, "bad-dimensions", "the WEBP declares a zero width or height"
                )
            ]
        return []
    if fourcc == b"VP8L":
        if len(data) < 25:
            return [
                _finding(
                    name,
                    "truncated",
                    "the WEBP is truncated: its VP8L header is cut short",
                )
            ]
        bits = data[20:25]
        if bits[0] != 0x2F:
            return [
                _finding(
                    name,
                    "bad-dimensions",
                    "the WEBP declares no dimensions: its VP8L header is malformed",
                )
            ]
        width = 1 + (bits[1] | ((bits[2] & 0x3F) << 8))
        height = 1 + ((bits[2] >> 6) | (bits[3] << 2) | ((bits[4] & 0x0F) << 10))
        if width <= 0 or height <= 0:
            return [
                _finding(
                    name, "bad-dimensions", "the WEBP declares a zero width or height"
                )
            ]
        return []
    if fourcc == b"VP8X":
        if len(data) < 30:
            return [
                _finding(
                    name,
                    "truncated",
                    "the WEBP is truncated: its VP8X header is cut short",
                )
            ]
        width = 1 + int.from_bytes(data[24:27], "little")
        height = 1 + int.from_bytes(data[27:30], "little")
        if width <= 0 or height <= 0:
            return [
                _finding(
                    name, "bad-dimensions", "the WEBP declares a zero width or height"
                )
            ]
        return []
    return [
        _finding(
            name,
            "bad-dimensions",
            "the WEBP declares no dimensions: its first chunk is not VP8, VP8L or VP8X",
        )
    ]


def _wav_findings(name: str, data: bytes) -> list[Finding]:
    """Require a WAV whose RIFF size matches, with a usable fmt and data chunk.

    The chunk walk must find a `fmt ` chunk of at least 16 bytes and a non-empty
    `data` chunk without overrunning the file, and the format's sample rate and
    byte rate must both be non-zero: those are the figures a duration is
    computed from.
    """
    riff_size = int.from_bytes(data[4:8], "little")
    if riff_size + 8 != len(data):
        return [
            _finding(
                name,
                "truncated",
                "the WAV is truncated: its RIFF size does not match the file length",
            )
        ]
    fmt = b""
    data_size = -1
    offset = 12
    while offset + 8 <= len(data):
        chunk_size = int.from_bytes(data[offset + 4 : offset + 8], "little")
        payload_end = offset + 8 + chunk_size
        if payload_end > len(data):
            return [
                _finding(
                    name,
                    "truncated",
                    "the WAV is truncated: a chunk overruns the end of the file",
                )
            ]
        fourcc = data[offset : offset + 4]
        if fourcc == b"fmt ":
            fmt = data[offset + 8 : payload_end]
        elif fourcc == b"data":
            data_size = chunk_size
        offset = payload_end + (chunk_size % 2)
    if not fmt or data_size < 0 or len(fmt) < 16 or data_size == 0:
        return [
            _finding(
                name,
                "bad-duration",
                "the WAV declares no duration: its fmt or data chunk is missing, "
                "short, or empty",
            )
        ]
    sample_rate = int.from_bytes(fmt[4:8], "little")
    byte_rate = int.from_bytes(fmt[8:12], "little")
    if sample_rate == 0 or byte_rate == 0:
        return [
            _finding(
                name,
                "bad-duration",
                "the WAV declares no duration: its sample rate or byte rate is zero",
            )
        ]
    return []


def _flac_findings(name: str, data: bytes) -> list[Finding]:
    """Require a FLAC whose first metadata block is a complete STREAMINFO.

    The first block must be of type 0 and exactly 34 bytes, and the sample rate
    and total sample count packed into it must be non-zero, so a duration follows
    from the stream's own figures.
    """
    if len(data) < 8:
        return [
            _finding(
                name,
                "truncated",
                "the FLAC is truncated: its first metadata block header runs "
                "off the end of the file",
            )
        ]
    block_type = data[4] & 0x7F
    length = int.from_bytes(data[5:8], "big")
    payload_end = 8 + length
    if payload_end > len(data):
        return [
            _finding(
                name,
                "truncated",
                "the FLAC is truncated: its STREAMINFO block overruns the end "
                "of the file",
            )
        ]
    if block_type != 0:
        return [
            _finding(
                name,
                "bad-duration",
                "the FLAC declares no duration: its first metadata block is "
                "not STREAMINFO",
            )
        ]
    if length != 34:
        return [
            _finding(
                name,
                "bad-duration",
                "the FLAC declares no duration: its STREAMINFO block is not 34 bytes",
            )
        ]
    value = int.from_bytes(data[18:26], "big")
    sample_rate = (value >> 44) & 0xFFFFF
    total_samples = value & 0xFFFFFFFFF
    if sample_rate == 0 or total_samples == 0:
        return [
            _finding(
                name,
                "bad-duration",
                "the FLAC declares no duration: its sample rate or total "
                "samples is zero",
            )
        ]
    return []


def _mp3_findings(name: str, data: bytes) -> list[Finding]:
    """Scan past any ID3v2 tag for a valid MPEG audio frame header.

    A leading ID3v2 tag is skipped by its declared size so it cannot hide the
    audio; the first frame sync must then parse as a header the MPEG version,
    layer, bitrate and sample-rate tables accept, and the frame body its bitrate
    implies must fit the file. A reserved or invalid header, or a frame body that
    overruns the file, is refused.
    """
    audio_start = 0
    if data.startswith(b"ID3"):
        if len(data) < 10:
            return [
                _finding(
                    name,
                    "bad-duration",
                    "the MP3 declares no duration: its ID3v2 header is cut short",
                )
            ]
        # ID3v2.2 holds the tag size as a plain 3-byte big-endian number; later
        # versions use a 4-byte syncsafe integer with each high bit clear.
        if data[3] == 2:
            tag_size = int.from_bytes(data[6:9], "big")
        else:
            tag_size = (
                (data[6] & 0x7F) << 21
                | (data[7] & 0x7F) << 14
                | (data[8] & 0x7F) << 7
                | (data[9] & 0x7F)
            )
        audio_start = 10 + tag_size
    for i in range(audio_start, len(data) - 2):
        if data[i] == 0xFF and (data[i + 1] & 0xE0) == 0xE0:
            b1 = data[i + 1]
            b2 = data[i + 2]
            version = (b1 >> 3) & 0x03
            layer = (b1 >> 1) & 0x03
            bitrate_index = (b2 >> 4) & 0x0F
            samplerate_index = (b2 >> 2) & 0x03
            if (
                version == 1
                or layer == 0
                or bitrate_index in (0, 15)
                or samplerate_index == 3
            ):
                return [
                    _finding(
                        name,
                        "bad-duration",
                        "the MP3 declares no duration: its first frame header "
                        "is reserved or invalid",
                    )
                ]
            padding = (b2 >> 1) & 0x01
            sample_rates = {
                3: [44100, 48000, 32000],
                2: [22050, 24000, 16000],
                0: [11025, 12000, 8000],
            }
            sample_rate = sample_rates[version][samplerate_index]
            version_group = "mpeg1" if version == 3 else "mpeg2"
            bitrates = {
                ("mpeg1", 3): [
                    32,
                    64,
                    96,
                    128,
                    160,
                    192,
                    224,
                    256,
                    288,
                    320,
                    352,
                    384,
                    416,
                    448,
                ],
                ("mpeg1", 2): [
                    32,
                    48,
                    56,
                    64,
                    80,
                    96,
                    112,
                    128,
                    160,
                    192,
                    224,
                    256,
                    320,
                    384,
                ],
                ("mpeg1", 1): [
                    32,
                    40,
                    48,
                    56,
                    64,
                    80,
                    96,
                    112,
                    128,
                    160,
                    192,
                    224,
                    256,
                    320,
                ],
                ("mpeg2", 3): [
                    32,
                    48,
                    56,
                    64,
                    80,
                    96,
                    112,
                    128,
                    144,
                    160,
                    176,
                    192,
                    224,
                    256,
                ],
                ("mpeg2", 2): [
                    8,
                    16,
                    24,
                    32,
                    40,
                    48,
                    56,
                    64,
                    80,
                    96,
                    112,
                    128,
                    144,
                    160,
                ],
                ("mpeg2", 1): [
                    8,
                    16,
                    24,
                    32,
                    40,
                    48,
                    56,
                    64,
                    80,
                    96,
                    112,
                    128,
                    144,
                    160,
                ],
            }
            bitrate_kbps = bitrates[(version_group, layer)][bitrate_index - 1]
            samples = 384 if layer == 3 else 1152
            frame_len = (samples * bitrate_kbps * 1000) // (8 * sample_rate) + padding
            if i + frame_len > len(data):
                return [
                    _finding(
                        name,
                        "truncated",
                        "the MP3 is truncated: its first frame body overruns "
                        "the end of the file",
                    )
                ]
            return []
    return [
        _finding(
            name,
            "bad-duration",
            "the MP3 declares no duration: it has no MPEG audio frame header",
        )
    ]


def _ogg_findings(name: str, data: bytes) -> list[Finding]:
    """Require a first OGG page whose header and segment table fit the file.

    The 27-byte page header must be present, declare version 0, and be followed
    by the lacing bytes its segment count promises. Only that structure is
    checked: OGG has no duration in its page headers, so nothing past the first
    page is read.
    """
    if len(data) < 27:
        return [
            _finding(
                name,
                "truncated",
                "the OGG is truncated: its first page header is cut short",
            )
        ]
    if data[4] != 0:
        return [
            _finding(
                name,
                "truncated",
                "the OGG is truncated: its first page declares a non-zero version",
            )
        ]
    page_segments = data[26]
    if len(data) < 27 + page_segments:
        return [
            _finding(
                name,
                "truncated",
                "the OGG is truncated: its first page's segment table runs off "
                "the end of the file",
            )
        ]
    return []


# The tool-backed checks, and the helpers that read what a tool wrote.


def _word_error_rate(hypothesis: str, reference: str) -> float:
    """Return the word error rate of `hypothesis` against `reference`.

    Words are whitespace-separated: the numerator is the Levenshtein distance
    between the two word lists and the denominator the number of reference words,
    guarded so an empty reference divides by one rather than zero.
    """
    hyp_words = hypothesis.split()
    ref_words = reference.split()
    previous = list(range(len(hyp_words) + 1))
    for i, ref_word in enumerate(ref_words, start=1):
        current = [i] + [0] * len(hyp_words)
        for j, hyp_word in enumerate(hyp_words, start=1):
            current[j] = min(
                previous[j] + 1,
                current[j - 1] + 1,
                previous[j - 1] + (ref_word != hyp_word),
            )
        previous = current
    return previous[len(hyp_words)] / max(1, len(ref_words))


def _first_line(stderr: str | bytes) -> str:
    """Return the first non-blank line of a tool's stderr, capped at 200 chars.

    Bytes are decoded as UTF-8 with replacement so a tool writing raw bytes still
    yields readable text, and an empty or blank stderr yields the empty string.
    """
    text = stderr.decode("utf-8", "replace") if isinstance(stderr, bytes) else stderr
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:200]
    return ""


def safety_pass(path: Path, label: str = "") -> list[Finding]:
    """Run the safety classifier over `path` and report an unsafe verdict.

    An empty list means the classifier exited 0. Exit 1 is its unsafe verdict and
    becomes an `unsafe` finding. A missing binary raises `ToolUnavailableError`
    and any other exit code raises `ToolFailedError` carrying the first line of
    stderr, so a broken classifier is never read as clean.
    """
    if shutil.which("safety-classifier") is None:
        raise ToolUnavailableError("safety-classifier")
    proc = subprocess.run(["safety-classifier", str(path)], capture_output=True)
    if proc.returncode == 0:
        return []
    if proc.returncode == 1:
        return [
            Finding(
                check=SAFETY_PASS,
                path=label or str(path),
                code="unsafe",
                message="the output was classified unsafe by the safety classifier",
            )
        ]
    raise ToolFailedError(
        "safety-classifier", proc.returncode, detail=_first_line(proc.stderr)
    )


def asr_wer(
    path: Path,
    transcript: str,
    wer_threshold: float,
    label: str = "",
) -> list[Finding]:
    """Transcribe `path` with whisper and report a word error rate over the cap.

    Whisper's stdout is the hypothesis and `transcript` the reference; when the
    two differ by more than `wer_threshold` (a share from 0 to 1) the result is a
    `wer-exceeded` finding. A missing binary raises `ToolUnavailableError` and a
    failing run raises `ToolFailedError` with the first line of stderr.
    """
    if shutil.which("whisper") is None:
        raise ToolUnavailableError("whisper")
    proc = subprocess.run(["whisper", str(path)], capture_output=True, text=True)
    if proc.returncode != 0:
        raise ToolFailedError(
            "whisper", proc.returncode, detail=_first_line(proc.stderr)
        )
    hypothesis = proc.stdout.strip()
    wer = _word_error_rate(hypothesis, transcript)
    if wer > wer_threshold:
        return [
            Finding(
                check=ASR_WER,
                path=label or str(path),
                code="wer-exceeded",
                message=(
                    f"the transcription's word error rate {wer:.3f} exceeds "
                    f"the threshold {wer_threshold}"
                ),
            )
        ]
    return []


# The report one pass of the checks hands to the gate, and the rung running it.


@dataclass(frozen=True)
class OutputReport:
    """What one pass of the output checks produced.

    `findings` are the checks' verdicts, `environment_issues` the rendered text of
    each inconclusive rung, and `inconclusive` the rungs themselves, so the gate
    can tell a check that ran and passed from one that never ran.
    """

    findings: tuple[Finding, ...] = ()
    environment_issues: tuple[str, ...] = ()
    inconclusive: tuple[InconclusiveRung, ...] = ()


class OutputChecks:
    """The output checks a contract declares, run over one artifact.

    `checks` are the evidence names to run (`media_valid`, `safety_pass`,
    `asr_wer` in the order given), `target` is the artifact's path relative to
    `workspace`, and `media_kind`, `transcript` and `wer_threshold` are the
    contract settings those checks need.
    """

    def __init__(
        self,
        *,
        checks: Sequence[str],
        workspace: Path,
        target: str = "",
        media_kind: str = "",
        transcript: str = "",
        wer_threshold: float | None = None,
    ) -> None:
        self.checks = tuple(checks)
        self.workspace = workspace
        self.target = target
        self.media_kind = media_kind
        self.transcript = transcript
        self.wer_threshold = wer_threshold

    def run(self) -> OutputReport:
        """Run every declared check and collect findings, issues and rungs.

        A validator that raises `ToolUnavailableError` or `ToolFailedError` does not
        fail the run: it becomes an inconclusive rung whose rendered text is also
        recorded as an environment issue. Any other exception propagates.
        """
        findings: list[Finding] = []
        issues: list[str] = []
        inconclusive: list[InconclusiveRung] = []
        path = self.workspace / self.target
        for name in self.checks:
            try:
                findings.extend(_run_one(name, self, path))
            except (ToolUnavailableError, ToolFailedError) as exc:
                # A missing or failing tool is not a pass, so the rung is kept as
                # inconclusive; the import is local because runner imports this module.
                from mcgyvr.gate.runner import InconclusiveRung

                if isinstance(exc, ToolUnavailableError):
                    rung = InconclusiveRung(adapter="output", rung=name, tool=exc.tool)
                else:
                    rung = InconclusiveRung(
                        adapter="output",
                        rung=name,
                        tool=exc.tool,
                        exit_code=exc.exit_code,
                        detail=exc.detail,
                    )
                inconclusive.append(rung)
                issues.append(str(rung))
        return OutputReport(
            findings=tuple(findings),
            environment_issues=tuple(issues),
            inconclusive=tuple(inconclusive),
        )


def _run_one(name: str, checks: OutputChecks, path: Path) -> list[Finding]:
    """Run one named check with the settings `checks` carries.

    An unknown name, or `asr_wer` with no `wer_threshold`, is a fault in the
    contract wiring and raises `ValueError` rather than passing silently.
    """
    if name == MEDIA_VALID:
        return media_valid(path, checks.media_kind, checks.target)
    if name == SAFETY_PASS:
        return safety_pass(path, checks.target)
    if name == ASR_WER:
        if checks.wer_threshold is None:
            raise ValueError("asr_wer: wer_threshold is not set")
        return asr_wer(path, checks.transcript, checks.wer_threshold, checks.target)
    raise ValueError(f"unknown output check {name!r}")
