"""The output checks — the evidence kinds a structural check makes itself.

Four evidence kinds are declared structural in the catalog
(``needs_commands: false``): ``media_valid``, ``safety_pass``, ``asr_wer`` and
``grounded``. A structural check is one the gate produces itself, so no
contract command is emitted for it; this module is where those checks are
produced. It is the seam the media-gen and agent verticals hang their
validators on (gate seam 3, P1 generalize-the-core).

``media_valid`` is the one check with a real validator in this build: it reads
the output file's own header and answers whether the bytes are a file of the
declared media kind. A worker cannot fake a header, and a wrong-kind or empty
output is refused by name. The other three name validators that land with P2;
their check names are pinned here so a contract declaring one never reads as
clean while no bar was applied.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from mcgyvr.gate.adapter import ToolUnavailableError
from mcgyvr.gate.findings import Finding

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
#: us". Deliberately the header only: the honest claim ``media_valid`` can make
#: without a decoder is "these bytes are a file of this kind", and dimensions,
#: duration or decode validity are the P2 validators' job.
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


def media_valid(path: Path, kind: str) -> list[Finding]:
    """One finding unless ``path`` holds a valid file of the declared ``kind``.

    ``kind`` is one of :data:`MEDIA_KINDS`, validated by the contract schema
    before it reaches here; an unknown kind is still refused rather than
    guessed at, because a check that judges a kind it does not know is one that
    reports clean over no bar.
    """
    if kind not in MEDIA_KINDS:
        raise ValueError(f"media_valid: unknown media kind {kind!r}")
    try:
        data = path.read_bytes()
    except OSError:
        return [
            Finding(
                check=MEDIA_VALID,
                path=str(path),
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
                path=str(path),
                code="empty",
                message=f"the output is empty and is not a valid {kind}",
            )
        ]
    if _is_kind(data, kind):
        return []
    return [
        Finding(
            check=MEDIA_VALID,
            path=str(path),
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
        return True
    if data[:4] == b"RIFF" and len(data) >= 12 and _RIFF_FORMS.get(data[8:12]) == kind:
        return True
    return any(data.startswith(prefix) for prefix in _PREFIXES[kind])


# --- the P2 validators, declared but not yet wired -------------------------


def safety_pass() -> list[Finding]:
    """The deterministic safety classifier's verdict — P2, not wired in this build.

    A safety check that reported clean while no classifier ran would be the one
    failure a gate must not have, so this raises rather than returning no
    findings. P2 lands the classifier and its input (the output artifact); a
    *missing* classifier must then read as inconclusive — a rejection — never
    as a skipped environment issue that accepts.
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

    ``findings`` reject the change; ``environment_issues`` record a check whose
    validator is not available, so a degraded run is never mistaken for a
    passing one. Mirrors :class:`~mcgyvr.gate.acceptance.AcceptanceReport`.
    """

    findings: tuple[Finding, ...] = ()
    environment_issues: tuple[str, ...] = ()


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
        for name in self.checks:
            try:
                findings.extend(_run_one(name, self))
            except ToolUnavailableError as exc:
                issues.append(f"{name}: {exc.tool} not available — skipped")
        return OutputReport(findings=tuple(findings), environment_issues=tuple(issues))


def _run_one(name: str, checks: OutputChecks) -> list[Finding]:
    """Dispatch one declared evidence kind to its check function."""
    if name == MEDIA_VALID:
        return media_valid(checks.workspace / checks.target, checks.media_kind)
    if name == SAFETY_PASS:
        return safety_pass()
    if name == ASR_WER:
        return asr_wer()
    if name == GROUNDED:
        return grounded()
    raise ValueError(f"unknown output check {name!r}")
