"""The worker's system prompt: a small, measured skill bundle.

A system-prompt bundle is a worker-tier device: it pays where a small worker
over-produces without output rules, and only there. Figures and method are in
``mcgyvr-lab/records/measurements/python-bundle-2026-08-07/README.md`` and
``mcgyvr-lab/records/measurements/jsts-bundle-2026-08-04/README.md``;
``tools/bundle/`` is the instrument.

**The ceiling is enforced here, not documented.** :data:`MAX_BUNDLE_BYTES` is a
load-time refusal, because a size limit that lives in a comment is a size limit
that a helpful edit walks straight through. The failure is loud and at
import-adjacent time rather than a quiet quality regression nobody attributes.

**The shipped Python bundle is the measured artifact, byte for byte.**
``prompts/python.md`` is a copy of the experiment's ``c2.md`` condition, and a
test holds the two files equal. Rewording it — even improving it — would mean
the measurement describes a file that is not the one being shipped. If the
bundle should change, the change has to be measured first.

**Standing.** ``prompts/javascript.md`` is
:data:`BundleStanding.MEASURED_NO_EFFECT`: no bundle-size condition (c1-c3)
separated from no bundle at all. ``prompts/python.md`` is
:data:`BundleStanding.MEASURED_REDUNDANT`: its effect is real, and
:func:`~mcgyvr.worker.prompt.render_user_message` already produces it by ending
every user message with a demand for the whole file as one fenced block and
nothing else. Both files still ship — measuring no benefit is not measuring
harm. The marker stating a file's standing is stripped by
:func:`strip_provenance`, which keeps the standing sayable in the file without
spending the worker's prompt on it.

One bundle per use case; only the coding use case splits by language, selected
by asking the gate's adapters which one owns the contract's target. Chat gets
no bundle — it is a raw un-gated endpoint, and a system prompt would bias a
pass-through. Agent and media-gen each carry one bundle, unmeasured until a
sweep is run on them (``BundleStanding.UNMEASURED``).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from importlib import resources

from mcgyvr.config import CHAT
from mcgyvr.gate.adapter import LanguageAdapter
from mcgyvr.gate.adapters import JavaScriptAdapter, PythonAdapter

# The ceiling, in bytes of UTF-8. 2 KiB holds the shipped c2 condition; the
# original sweep measured the 8 KB condition below it on the small worker.
# Raising it is a claim about quality and needs a measurement, not an edit.
#
# It stays ONE constant across languages: on the JS/TS task set no rung
# separated from c0, so there is no JS/TS peak to place a different ceiling
# at.
MAX_BUNDLE_BYTES = 2048


class BundleStanding(StrEnum):
    """What a measurement says about a bundle — not merely whether one ran.

    A bare "measured" boolean is not enough. Both shipped bundles are the
    artifact a sweep was taken on, so a boolean would read the same for a
    bundle measured at +25 pp and one measured at nothing — and "measured" is a
    word a reader takes as endorsement. The outcome is the part worth carrying,
    so it is the part the type names.
    """

    UNMEASURED = "unmeasured"
    """No sweep has been run on this artifact."""

    MEASURED_BENEFIT = "measured-benefit"
    """A sweep ran and the bundle beat its absence."""

    MEASURED_NO_EFFECT = "measured-no-effect"
    """A sweep ran and no rung separated from no-bundle-at-all (`javascript.md`).
    The file still ships because measuring no benefit is not measuring harm —
    but nothing here licenses citing a gain."""

    MEASURED_REDUNDANT = "measured-redundant"
    """The bundle's effect is real, and this project's own prompt already has it.

    `python.md`: the gain was measured against a user message with no output
    rule in it. :func:`~mcgyvr.worker.prompt.render_user_message` ends every
    message by requiring the complete file as one fenced block and nothing
    else, which is the device the bundle's gain runs through. Figures:
    ``mcgyvr-lab/records/measurements/python-bundle-2026-08-07/README.md``.

    Distinct from :data:`MEASURED_NO_EFFECT`, and the distinction is
    load-bearing in both directions. A reader must not cite a gain here — on
    mcgyvr's path there is none. A reader must also not conclude the artifact
    is inert: a harness whose prompt lacks output discipline gains from it.
    What is redundant is redundant *with something*, and naming that is the
    difference between a fact and a shrug."""


# The coding use case keeps per-language bundles, keyed by
# ``LanguageAdapter.name``. A language with no entry gets no bundle rather
# than another language's: the standards and pitfalls sections are
# language-specific, and handing a Go worker the Python rules would be worse
# than handing it nothing.
_LANGUAGE_BUNDLES: dict[str, tuple[str, BundleStanding]] = {
    "python": ("python.md", BundleStanding.MEASURED_REDUNDANT),
    "js/ts": ("javascript.md", BundleStanding.MEASURED_NO_EFFECT),
}

#: The use-case bundles, keyed by use-case name. Chat is deliberately absent:
#: it is a raw endpoint and gets no system prompt. Agent and media-gen are
#: unmeasured — no sweep has been run on either artifact yet.
_USE_CASE_BUNDLES: dict[str, tuple[str, BundleStanding]] = {
    "agent": ("agent.md", BundleStanding.UNMEASURED),
    "media-gen": ("media-gen.md", BundleStanding.UNMEASURED),
}

#: The one registry ``load_bundle`` reads, so a key names exactly one artifact
#: and its standing, whatever axis (language or use case) it came from.
_BUNDLES: dict[str, tuple[str, BundleStanding]] = {
    **_LANGUAGE_BUNDLES,
    **_USE_CASE_BUNDLES,
}

#: The use case whose worker edits files, and so keeps per-language bundles.
CODING = "coding"

_DEFAULT_ADAPTERS: tuple[LanguageAdapter, ...] = (PythonAdapter(), JavaScriptAdapter())


class BundleError(Exception):
    """A bundle could not be supplied as the shipped, measured artifact."""


class BundleTooLargeError(BundleError):
    """A bundle exceeds the measured ceiling.

    Carries both sizes so the message says how far over it is, rather than
    only that it is over.
    """

    def __init__(self, name: str, size: int) -> None:
        super().__init__(
            f"bundle {name!r} is {size} bytes, over the measured ceiling of "
            f"{MAX_BUNDLE_BYTES} (the limit is evidence, not a budget). "
            f"Re-measure before raising it."
        )
        self.name = name
        self.size = size


class BundleMissingError(BundleError):
    """A bundle named in the registry is not present in the installation."""


@dataclass(frozen=True)
class Bundle:
    """One bundle's system prompt, with what is known about its standing."""

    key: str
    """The registry key this bundle was loaded under — a language for the
    coding use case, a use-case name for the others."""

    text: str
    size_bytes: int
    standing: BundleStanding
    """What *this* artifact's own sweep found.

    Not "was one run" — what it said. A bundle whose sweep found nothing and a
    bundle that has never been swept are both un-citable as a gain, and they are
    un-citable for different reasons; collapsing them loses the one that is
    settled. Anything reporting on a run should carry this through.
    """

    @property
    def measured(self) -> bool:
        """Whether this bundle is the artifact a measurement was taken on.

        Provenance only, and deliberately says nothing about the outcome — read
        :attr:`standing` for that. True here means a sweep covers *this file*
        rather than a file that inspired it.
        """
        return self.standing is not BundleStanding.UNMEASURED


def _read(filename: str) -> str | None:
    resource = resources.files("mcgyvr") / "prompts" / filename
    if not resource.is_file():
        return None
    return resource.read_text(encoding="utf-8")


def strip_provenance(text: str) -> str:
    """A bundle without its leading HTML-comment marker.

    A marker says what standing the file has — which measurement it is, or that
    it is none. That is a note to a reader of the repository; sent to the model
    it would spend the ceiling :data:`MAX_BUNDLE_BYTES` enforces on text that is
    not instructions, and put meta-commentary where a small model expects its
    role.

    Stripping here makes the marker provenance rather than prompt: a bundle can
    carry a standing marker *and* be byte-identical to the condition a sweep
    measured, because the marker is not in the bytes either one sends. Without
    this, marking a file and measuring it are mutually exclusive.

    Only a marker at the very start is removed, and only through the first
    ``-->``. A comment further down is content — the file is Markdown, and this
    is not a comment stripper.
    """
    if not text.startswith("<!--"):
        return text
    _, separator, rest = text.partition("-->\n")
    return rest if separator else text


def load_bundle(key: str) -> Bundle:
    """Load one bundle by registry key, refusing it if it broke the ceiling.

    A key is a language (the coding use case) or a use-case name (agent,
    media-gen). The bundle is the file's body: a leading provenance marker is
    stripped by :func:`strip_provenance` before anything else, so neither the
    ceiling nor the worker ever sees it.

    Raises :class:`BundleMissingError` for a key with no bundle file and
    :class:`BundleTooLargeError` for one that outgrew the measurement.
    """
    entry = _BUNDLES.get(key)
    if entry is None:
        raise BundleMissingError(
            f"no bundle is registered for {key!r} "
            f"(registered: {', '.join(sorted(_BUNDLES))})"
        )
    filename, standing = entry
    raw = _read(filename)
    if raw is None:
        raise BundleMissingError(
            f"bundle file {filename!r} for {key!r} is not present in this installation"
        )
    text = strip_provenance(raw)
    size = len(text.encode("utf-8"))
    if size > MAX_BUNDLE_BYTES:
        raise BundleTooLargeError(filename, size)
    return Bundle(
        key=key,
        text=text,
        size_bytes=size,
        standing=standing,
    )


def bundle_for(
    use_case: str,
    target: str = "",
    adapters: Sequence[LanguageAdapter] | None = None,
) -> Bundle | None:
    """The bundle for ``use_case``, or ``None``.

    Chat is a raw endpoint and gets none; coding picks the language bundle
    whose adapter owns ``target`` (or none, when no adapter does); agent and
    media-gen each get their one bundle. ``None`` is a real answer: a coding
    target no adapter owns has no language-specific standards to state, and
    inventing some would put unmeasured instructions in front of a worker. A
    caller that gets ``None`` dispatches with no system prompt — the c0
    condition — and should say so rather than silently substituting another
    bundle.
    """
    if use_case == CHAT:
        return None
    if use_case in _USE_CASE_BUNDLES:
        return load_bundle(use_case)
    if use_case == CODING:
        for adapter in adapters if adapters is not None else _DEFAULT_ADAPTERS:
            if adapter.owns(target) and adapter.name in _LANGUAGE_BUNDLES:
                return load_bundle(adapter.name)
    return None
