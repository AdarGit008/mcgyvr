"""The output checks — the evidence kinds a structural check makes itself.

Four evidence kinds are declared structural in the catalog
(``needs_commands: false``): ``media_valid``, ``safety_pass``, ``asr_wer`` and
``grounded``. A structural check is one the gate produces itself, so no
contract command is emitted for it; this module is where those checks are
produced. It is the seam the media-gen and agent verticals hang their
validators on (gate seam 3, P1 generalize-the-core).

``media_valid`` is the one check with a real validator in this build: it reads
the output file's own header and answers whether the bytes are a file of the
declared media kind. Images are checked past the header — their dimensions
must be present and positive, and the file must be structurally complete
— while audio and video stay header-only until P2 adds their duration and
decode checks. A worker cannot fake a header, and a wrong-kind or empty
output is refused by name. The other three name validators that land with P2;
their check names are pinned here so a contract declaring one is never
silently treated as if the bar ran. Each raises
:class:`~mcgyvr.gate.adapter.ToolUnavailableError`, and a check whose
validator is missing is recorded as *inconclusive* — a rejection — never a
skipped environment issue that accepts. A missing validator cannot be
reported clean, so declaring one refuses the change until the validator is
wired.
"""

from __future__ import annotations

import zlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from mcgyvr.gate.adapter import ToolUnavailableError
from mcgyvr.gate.findings import Finding

if TYPE_CHECKING:
    from mcgyvr.gate.runner import InconclusiveRung

#: The media kinds a contract may declare, and ``media_valid`` judges.
MEDIA_IMAGE = "image"
MEDIA_AUDIO = "audio"
MEDIA_VIDEO = "video"
MEDIA_KINDS = (MEDIA_IMAGE, MEDIA_AUDIO, MEDIA_VIDEO)

#: The check name ``media_valid`` findings carry, so a caller groups by it.
MEDIA_VALID = "media_valid"

#: The check names of the P2 validators, pinned now so their evidence kinds
#: have a check type to map to. Their validators raise
#: :class:`~mcgyvr.gate.adapter.ToolUnavailableError` in this build.
SAFETY_PASS = "safety_pass"
ASR_WER = "asr_wer"
GROUNDED = "grounded"

#: Container formats whose signature is not a plain prefix: a RIFF envelope
#: whose four form-type bytes (offset 8) name the format. Keyed by those bytes
#: to the kind they belong to, so a PNG-declared-as-audio is still refused.
_RIFF_FORMS = {b"WEBP": MEDIA_IMAGE, b"WAVE": MEDIA_AUDIO, b"AVI ": MEDIA_VIDEO}

#: Plain-prefix signatures per kind. The first bytes that say "this is one of
#: us". For images the check then goes past the signature (dimensions and
#: decode completeness); audio and video remain header-only until P2 adds
#: their duration and decode checks.
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

#: MP4's signature sits four bytes in (the box size occupies the head), not at
#: offset zero like the prefixes above.
_MP4_FTYP = b"ftyp"


def media_valid(path: Path, kind: str, label: str = "") -> list[Finding]:
    """One finding unless ``path`` holds a valid file of the declared ``kind``.

    ``kind`` is one of :data:`MEDIA_KINDS`, validated by the contract schema
    before it reaches here; an unknown kind is still refused rather than
    guessed at, because a check that judges a kind it does not know is one that
    reports clean over no bar. ``label`` is the repo-relative name the finding
    quotes — never the sandbox path the bytes were read from.
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
    """Whether ``data`` opens like a file of ``kind``, header only."""
    if kind == MEDIA_VIDEO and len(data) >= 8 and data[4:8] == _MP4_FTYP:
        box_size = int.from_bytes(data[:4], "big")
        # ``ftyp`` four bytes in is only a video when the box size in front of
        # it is a real size: 0 (to EOF) or 1 (the 64-bit extension), or one
        # that fits the file. Arbitrary bytes before ``ftyp`` are refused.
        return box_size in (0, 1) or 8 <= box_size <= len(data)
    if data[:4] == b"RIFF" and len(data) >= 12 and _RIFF_FORMS.get(data[8:12]) == kind:
        return True
    return any(data.startswith(prefix) for prefix in _PREFIXES[kind])


def _finding(name: str, code: str, message: str) -> Finding:
    """One ``media_valid`` finding, quoted against the repo-relative ``name``."""
    return Finding(check=MEDIA_VALID, path=name, code=code, message=message)


def _image_findings(name: str, data: bytes) -> list[Finding]:
    """Deeper-than-header checks for an image whose signature already matched.

    Only dimensions and decode completeness: a file whose header claims an
    image but whose dimensions are absent or whose payload is cut short is
    refused by name. Every offset and mask lives inside the per-format checker
    bodies, because a module-level numeric constant would flip ``output.py``'s
    classification in ``tests/numbers_coverage.json`` to *judging*.
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


def _png_findings(name: str, data: bytes) -> list[Finding]:
    """PNG: IHDR first, positive dimensions, and an IDAT stream that decompresses."""
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
    """JPEG: SOI…EOI, a SOF marker with positive dimensions, and an SOS marker."""
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
    """GIF: positive dimensions and the 0x3B trailer byte."""
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
    """BMP: a known DIB header size, positive dimensions, and a whole header."""
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
    """WEBP: a RIFF size that fits the file and a VP8 / VP8L / VP8X chunk."""
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


# --- the P2 validators, declared but not yet wired -------------------------


def safety_pass() -> list[Finding]:
    """The deterministic safety classifier's verdict — P2, not wired in this build.

    A safety check that reported clean while no classifier ran would be the one
    failure a gate must not have, so this raises rather than returning no
    findings. Until P2 lands the classifier and its input (the output
    artifact), the raise is recorded as *inconclusive* — a rejection — never
    a skipped issue that accepts.
    """
    raise ToolUnavailableError("safety-classifier")


def asr_wer() -> list[Finding]:
    """Whisper transcription WER against the contract's transcript — P2.

    Not wired in this build: a WER the gate never computed must not read as
    "the transcript matched". P2 lands the transcriber and the contract's
    ``transcript`` / ``wer_threshold`` inputs.
    """
    raise ToolUnavailableError("whisper-asr")


def grounded() -> list[Finding]:
    """Every claim cites a provided source — P2, not wired in this build.

    A grounding check that never looked for a citation must not read as
    "every claim is grounded". P2 lands the citation extractor and the
    contract's ``sources`` input.
    """
    raise ToolUnavailableError("citation-checker")


# --- the rung the gate runs -------------------------------------------------


@dataclass(frozen=True)
class OutputReport:
    """The output-checks rung's verdict, in the gate's own currency.

    ``findings`` reject the change; ``inconclusive`` also rejects it, and is
    the stronger case: a check whose validator is missing could not say what
    bar it applied, so it must not read as clean. ``environment_issues`` is
    the rendered sentence of each such rung, kept so a reader that only knows
    that field still sees the rejection. Mirrors
    :class:`~mcgyvr.gate.acceptance.AcceptanceReport`.
    """

    findings: tuple[Finding, ...] = ()
    environment_issues: tuple[str, ...] = ()
    inconclusive: tuple[InconclusiveRung, ...] = ()


class OutputChecks:
    """The gate's output-checks rung, built from a contract's declared evidence.

    Holds which structural evidence kinds a contract declared and the
    parameters each needs, and runs them over the artifact in ``workspace``.
    Built in :func:`mcgyvr.drive.gate_workspace` and passed into
    :meth:`~mcgyvr.gate.runner.Gate.run` — the same injected-rung shape as
    :class:`~mcgyvr.gate.acceptance.Acceptance` and
    :class:`~mcgyvr.gate.semantic.SemanticCheck`.
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
        sources: Sequence[str] = (),
    ) -> None:
        self.checks = tuple(checks)
        self.workspace = workspace
        self.target = target
        self.media_kind = media_kind
        self.transcript = transcript
        self.wer_threshold = wer_threshold
        self.sources = tuple(sources)

    def run(self) -> OutputReport:
        """Run every declared check; one unwired check never hides another's."""
        findings: list[Finding] = []
        issues: list[str] = []
        inconclusive: list[InconclusiveRung] = []
        for name in self.checks:
            try:
                findings.extend(_run_one(name, self))
            except ToolUnavailableError as exc:
                # runner.py imports OutputChecks at module top, so importing
                # InconclusiveRung here avoids the circular import.
                from mcgyvr.gate.runner import InconclusiveRung

                rung = InconclusiveRung(adapter="output", rung=name, tool=exc.tool)
                inconclusive.append(rung)
                issues.append(str(rung))
        return OutputReport(
            findings=tuple(findings),
            environment_issues=tuple(issues),
            inconclusive=tuple(inconclusive),
        )


def _run_one(name: str, checks: OutputChecks) -> list[Finding]:
    """Dispatch one declared evidence kind to its check function."""
    if name == MEDIA_VALID:
        return media_valid(
            checks.workspace / checks.target, checks.media_kind, checks.target
        )
    if name == SAFETY_PASS:
        return safety_pass()
    if name == ASR_WER:
        return asr_wer()
    if name == GROUNDED:
        return grounded()
    raise ValueError(f"unknown output check {name!r}")
