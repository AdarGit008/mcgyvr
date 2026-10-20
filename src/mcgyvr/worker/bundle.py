"""The skill bundles a worker is sent as its system prompt.

A bundle is a prompt file under `mcgyvr/prompts/` loaded whole, minus a leading
provenance comment, and shipped with the standing its own sweep found. For the
`coding` use case the contract's target picks the language bundle through the
gate adapter that owns it; the other use cases carry one bundle each. `chat` and
any unregistered or unowned target get `None`, because another language's
standards are worse than no system prompt at all.

Nothing here runs a sweep — it only carries what a sweep said. `BundleStanding`
keeps never-swept, swept-and-flat and swept-and-redundant-with-this-harness
apart, and `load_bundle` refuses an artifact over `MAX_BUNDLE_BYTES` rather than
sending it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from importlib import resources

from mcgyvr.config import CHAT
from mcgyvr.gate.adapter import LanguageAdapter
from mcgyvr.gate.adapters import JavaScriptAdapter, PythonAdapter

# The measured ceiling on one bundle, in bytes of UTF-8 text after provenance is
# stripped — the number `load_bundle` enforces and the marker never spends.
# It is evidence, not a budget: the 8 KB condition measured worse than this one,
# so an oversized artifact is refused at load with instructions to re-measure
# rather than truncated to fit. One constant covers every language because a
# per-language ceiling needs a curve with a peak, and JS/TS measured flat, so
# there is no peak here to place one at.
MAX_BUNDLE_BYTES = 2048


class BundleStanding(StrEnum):
    """What a bundle's own measurement licenses a reader to say about it.

    It travels with the artifact from the registry through `Bundle` to whatever
    reports on a run, because no other field records it."""

    UNMEASURED = "unmeasured"
    """No sweep has been run on this artifact."""

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


# Language bundles, keyed by the gate adapter's `name` rather than by a second
# table of extensions: `bundle_for` asks the adapters which one owns the target
# and looks that name up here, so a language the gate knows but this registry
# does not gets no bundle. Each entry carries the standing its own sweep found;
# `python.md` is measured redundant with this harness, `javascript.md` flat.
_LANGUAGE_BUNDLES: dict[str, tuple[str, BundleStanding]] = {
    "python": ("python.md", BundleStanding.MEASURED_REDUNDANT),
    "js/ts": ("javascript.md", BundleStanding.MEASURED_NO_EFFECT),
}

#: Use-case bundles, keyed by the contract's use case. The file has not been
#: swept, so it ships `UNMEASURED`; `chat` has no entry because it is a raw
#: pass-through and a system prompt would bias it.
_USE_CASE_BUNDLES: dict[str, tuple[str, BundleStanding]] = {
    "agent": ("agent.md", BundleStanding.UNMEASURED),
}

#: Both key kinds in one registry. The namespaces do not collide today, and
#: `load_bundle` names the whole sorted set when a key is missing.
_BUNDLES: dict[str, tuple[str, BundleStanding]] = {
    **_LANGUAGE_BUNDLES,
    **_USE_CASE_BUNDLES,
}

#: The use case whose bundle is chosen by the target's language; every other use
#: case carries a single bundle.
CODING = "coding"

_DEFAULT_ADAPTERS: tuple[LanguageAdapter, ...] = (PythonAdapter(), JavaScriptAdapter())


class BundleError(Exception):
    """Base for bundle load failures: an unregistered key, an absent file, or an
    artifact over the ceiling."""


class BundleTooLargeError(BundleError):
    """A bundle's stripped text exceeds `MAX_BUNDLE_BYTES`, so it is refused at
    load. Keeps `name` and `size` so a caller can report what to re-measure."""

    def __init__(self, name: str, size: int) -> None:
        super().__init__(
            f"bundle {name!r} is {size} bytes, over the measured ceiling of "
            f"{MAX_BUNDLE_BYTES} (the limit is evidence, not a budget). "
            f"Re-measure before raising it."
        )
        self.name = name
        self.size = size


class BundleMissingError(BundleError):
    """No bundle is registered for the key, or its file is not present in this
    installation."""


@dataclass(frozen=True)
class Bundle:
    """One loaded prompt file: its text, the size the ceiling was checked
    against, and what its own sweep found."""

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
        """Whether any sweep has been run on this artifact, whatever it found.
        Says nothing about benefit; `standing` is what names the outcome."""
        return self.standing is not BundleStanding.UNMEASURED


def _read(filename: str) -> str | None:
    resource = resources.files("mcgyvr") / "prompts" / filename
    if not resource.is_file():
        return None
    return resource.read_text(encoding="utf-8")


def strip_provenance(text: str) -> str:
    """Drop a leading `<!-- ... -->` provenance comment and return the rest.

    The marker stays in the file so the caveat cannot be lost by reading the
    artifact alone, but it must not open the worker's system prompt or be
    charged against `MAX_BUNDLE_BYTES`. Text that does not start with a comment,
    or whose comment is never closed, is returned unchanged."""
    if not text.startswith("<!--"):
        return text
    _, separator, rest = text.partition("-->\n")
    return rest if separator else text


def load_bundle(key: str) -> Bundle:
    """Load the bundle registered under `key`, stripped of provenance.

    Raises `BundleMissingError` for an unregistered key or a file absent from
    this installation, and `BundleTooLargeError` when the stripped text is over
    `MAX_BUNDLE_BYTES`. The size recorded and checked is the UTF-8 length of
    what a worker would actually be sent."""
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
    """The bundle for a contract's use case, or `None` when it should get none.

    `chat` is refused: it is a raw, un-gated endpoint where a system prompt
    would bias the reply. A use-case bundle is returned as-is; for `coding`, the
    adapter that owns `target` names the language, and no owning adapter — or
    one whose name has no registered bundle — yields `None`. `adapters` defaults
    to the Python and JavaScript adapters and exists so a caller can restrict
    the languages in play."""
    if use_case == CHAT:
        return None
    if use_case in _USE_CASE_BUNDLES:
        return load_bundle(use_case)
    if use_case == CODING:
        for adapter in adapters if adapters is not None else _DEFAULT_ADAPTERS:
            if adapter.owns(target) and adapter.name in _LANGUAGE_BUNDLES:
                return load_bundle(adapter.name)
    return None
