"""The skill bundles a worker is sent as its system prompt.

A bundle is a prompt file under `mcgyvr/prompts/` loaded whole, minus a leading
provenance comment, and shipped with the standing its own sweep found. For the
`coding` use case the contract's target picks the language bundle through the
gate adapter that owns it. Any other use case, and any unregistered or unowned
target, gets `None`, because another language's standards are worse than no
system prompt at all.

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

from mcgyvr.gate.adapter import LanguageAdapter
from mcgyvr.gate.adapters import JavaScriptAdapter, PythonAdapter

# The measured ceiling on one bundle, in bytes of UTF-8 text after provenance is
# stripped. `load_bundle` refuses an artifact over it rather than truncating it
# to fit; one constant covers every language.
MAX_BUNDLE_BYTES = 2048


class BundleStanding(StrEnum):
    """What a bundle's own measurement licenses a reader to say about it.

    It travels with the artifact from the registry through `Bundle`."""

    UNMEASURED = "unmeasured"
    """No sweep has been run on this artifact."""

    MEASURED_NO_EFFECT = "measured-no-effect"
    """A sweep ran and found no effect against no bundle at all
    (`javascript.md`), so no gain may be cited."""

    MEASURED_REDUNDANT = "measured-redundant"
    """The bundle's effect is real, and this project's own prompt already has it
    (`python.md`): :func:`~mcgyvr.worker.prompt.render_user_message` ends every
    message by requiring the complete file as one fenced block. No gain may be
    cited on mcgyvr's path; unlike :data:`MEASURED_NO_EFFECT`, the artifact is
    not inert in a harness without that rule."""


# Language bundles, keyed by the gate adapter's `name` rather than by a second
# table of extensions: `bundle_for` asks the adapters which one owns the target
# and looks that name up here, so a language the gate knows but this registry
# does not gets no bundle. Each entry carries its file and its standing.
_LANGUAGE_BUNDLES: dict[str, tuple[str, BundleStanding]] = {
    "python": ("python.md", BundleStanding.MEASURED_REDUNDANT),
    "js/ts": ("javascript.md", BundleStanding.MEASURED_NO_EFFECT),
}

#: The registry `load_bundle` reads; it names the whole sorted set when a key is
#: missing.
_BUNDLES: dict[str, tuple[str, BundleStanding]] = dict(_LANGUAGE_BUNDLES)

#: The use case whose bundle is chosen by the target's language; no other use
#: case carries a bundle.
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
    """The registry key this bundle was loaded under: a language of the coding
    use case."""

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

    Only `coding` carries one: the adapter that owns `target` names the
    language, and no owning adapter — or one whose name has no registered
    bundle — yields `None`. `adapters` defaults to the Python and JavaScript
    adapters and exists so a caller can restrict the languages in play."""
    if use_case == CODING:
        for adapter in adapters if adapters is not None else _DEFAULT_ADAPTERS:
            if adapter.owns(target) and adapter.name in _LANGUAGE_BUNDLES:
                return load_bundle(adapter.name)
    return None
