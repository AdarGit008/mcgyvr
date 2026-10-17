""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from importlib import resources

from mcgyvr.config import CHAT
from mcgyvr.gate.adapter import LanguageAdapter
from mcgyvr.gate.adapters import JavaScriptAdapter, PythonAdapter

#
#
#
#
#
#
#
MAX_BUNDLE_BYTES = 2048


class BundleStanding(StrEnum):
    ""

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
    else, which is the device the bundle's gain runs through. Figures: the
    lab's python-bundle measurement.

    Distinct from :data:`MEASURED_NO_EFFECT`, and the distinction is
    load-bearing in both directions. A reader must not cite a gain here — on
    mcgyvr's path there is none. A reader must also not conclude the artifact
    is inert: a harness whose prompt lacks output discipline gains from it.
    What is redundant is redundant *with something*, and naming that is the
    difference between a fact and a shrug."""


#
#
#
#
#
_LANGUAGE_BUNDLES: dict[str, tuple[str, BundleStanding]] = {
    "python": ("python.md", BundleStanding.MEASURED_REDUNDANT),
    "js/ts": ("javascript.md", BundleStanding.MEASURED_NO_EFFECT),
}

#
#
#t.
_USE_CASE_BUNDLES: dict[str, tuple[str, BundleStanding]] = {
    "agent": ("agent.md", BundleStanding.UNMEASURED),
    "media-gen": ("media-gen.md", BundleStanding.UNMEASURED),
}

#
#
_BUNDLES: dict[str, tuple[str, BundleStanding]] = {
    **_LANGUAGE_BUNDLES,
    **_USE_CASE_BUNDLES,
}

#
CODING = "coding"

_DEFAULT_ADAPTERS: tuple[LanguageAdapter, ...] = (PythonAdapter(), JavaScriptAdapter())


class BundleError(Exception):
    ""


class BundleTooLargeError(BundleError):
    ""

    def __init__(self, name: str, size: int) -> None:
        super().__init__(
            f"bundle {name!r} is {size} bytes, over the measured ceiling of "
            f"{MAX_BUNDLE_BYTES} (the limit is evidence, not a budget). "
            f"Re-measure before raising it."
        )
        self.name = name
        self.size = size


class BundleMissingError(BundleError):
    ""


@dataclass(frozen=True)
class Bundle:
    ""

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
        ""
        return self.standing is not BundleStanding.UNMEASURED


def _read(filename: str) -> str | None:
    resource = resources.files("mcgyvr") / "prompts" / filename
    if not resource.is_file():
        return None
    return resource.read_text(encoding="utf-8")


def strip_provenance(text: str) -> str:
    ""
    if not text.startswith("<!--"):
        return text
    _, separator, rest = text.partition("-->\n")
    return rest if separator else text


def load_bundle(key: str) -> Bundle:
    ""
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
    ""
    if use_case == CHAT:
        return None
    if use_case in _USE_CASE_BUNDLES:
        return load_bundle(use_case)
    if use_case == CODING:
        for adapter in adapters if adapters is not None else _DEFAULT_ADAPTERS:
            if adapter.owns(target) and adapter.name in _LANGUAGE_BUNDLES:
                return load_bundle(adapter.name)
    return None
