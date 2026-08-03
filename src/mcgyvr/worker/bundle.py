"""The worker's system prompt: a small, measured skill bundle.

CLM-0004 is the whole reason this module exists. A ~2 KB skill bundle took
qwen2.5-coder:3b from 45% to 70% first-pass acceptance and made it ~2.5x
faster — the speed-up because output rules stop a small model rambling, and
completion tokens dominate wall time. An 8 KB bundle gave 10 points back. The
effect was specific to the small worker; a 30B MoE was at ceiling and
insensitive to bundle size, which is why this is a worker-tier device and not
a global system prompt.

**The ceiling is enforced here, not documented.** :data:`MAX_BUNDLE_BYTES` is
the measured falloff turned into a load-time refusal, because a size limit that
lives in a comment is a size limit that a helpful edit walks straight through —
and the measurement says the walk is *downhill*. The failure is loud and at
import-adjacent time rather than a quiet quality regression nobody attributes.

**The shipped Python bundle is the measured artifact, byte for byte.**
``prompts/python.md`` is a copy of the experiment's ``c2.md`` condition, and a
test holds the two files equal. Rewording it — even improving it — would mean
the numbers above describe a file that is no longer the one being shipped. If
the bundle should change, the change has to be measured first.

**The JS/TS bundle is not measured, and says so in its own first line.**
CLM-0004's confidence note bars generalising its percentages to another
language until re-measured, so ``prompts/javascript.md`` is an idiom port
carrying no evidentiary weight. It is shipped because a worker on a JS/TS
contract with no bundle at all is the c0 condition, which measured worst of the
four — but "probably better than nothing" is a prediction, and it is recorded
as one.

One bundle per language adapter, selected by asking the gate's adapters which
one owns the contract's target. That reuses the ownership rules the gate
already applies (:meth:`~mcgyvr.gate.adapter.LanguageAdapter.owns`) instead of
growing a second, driftable table of file extensions.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from importlib import resources

from mcgyvr.gate.adapter import LanguageAdapter
from mcgyvr.gate.adapters import JavaScriptAdapter, PythonAdapter

# The measured ceiling, in bytes of UTF-8. 2 KiB: the c2 condition (1972 bytes)
# is the best of the four measured, and c3 at 8342 bytes measured *worse* than
# c2 on the small worker while buying nothing on the large one. So this is not
# a budget guess — it is the point past which the evidence says quality falls.
# Raising it is a claim about quality and needs a measurement, not an edit.
MAX_BUNDLE_BYTES = 2048

# Which bundle serves which adapter, keyed by `LanguageAdapter.name`. A language
# with no entry gets no bundle rather than another language's: the standards and
# pitfalls sections are language-specific, and handing a Go worker the Python
# rules would be worse than handing it nothing.
_BUNDLE_FILES: dict[str, str] = {
    "python": "python.md",
    "js/ts": "javascript.md",
}

# The one language whose bundle is the artifact a measurement was taken on.
_MEASURED: frozenset[str] = frozenset({"python"})

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
            f"{MAX_BUNDLE_BYTES} (CLM-0004 measured 8 KB degrading the small "
            f"worker; the limit is evidence, not a budget). Re-measure before "
            f"raising it."
        )
        self.name = name
        self.size = size


class BundleMissingError(BundleError):
    """A bundle named in the registry is not present in the installation."""


@dataclass(frozen=True)
class Bundle:
    """One language's system prompt, with what is known about its standing."""

    language: str
    text: str
    size_bytes: int
    measured: bool
    """Whether *this* bundle is the artifact a measurement was taken on.

    False is not a defect to be fixed by asserting otherwise — it is the
    difference between CLM-0004 covering the file and CLM-0004 covering a file
    that inspired it. Anything reporting on a run should carry this through.
    """


def _read(filename: str) -> str | None:
    resource = resources.files("mcgyvr") / "prompts" / filename
    if not resource.is_file():
        return None
    return resource.read_text(encoding="utf-8")


def load_bundle(language: str) -> Bundle:
    """Load one language's bundle, refusing it if it broke the ceiling.

    Raises :class:`BundleMissingError` for a language with no bundle file and
    :class:`BundleTooLargeError` for one that outgrew the measurement.
    """
    filename = _BUNDLE_FILES.get(language)
    if filename is None:
        raise BundleMissingError(
            f"no bundle is registered for language {language!r} "
            f"(registered: {', '.join(sorted(_BUNDLE_FILES))})"
        )
    text = _read(filename)
    if text is None:
        raise BundleMissingError(
            f"bundle file {filename!r} for language {language!r} is not present "
            f"in this installation"
        )
    size = len(text.encode("utf-8"))
    if size > MAX_BUNDLE_BYTES:
        raise BundleTooLargeError(filename, size)
    return Bundle(
        language=language,
        text=text,
        size_bytes=size,
        measured=language in _MEASURED,
    )


def bundle_for(
    target: str,
    adapters: Sequence[LanguageAdapter] | None = None,
) -> Bundle | None:
    """The bundle for the language that owns ``target``, or ``None``.

    ``None`` is a real answer: a target no adapter owns has no language-specific
    standards to state, and inventing some would put unmeasured instructions in
    front of a worker. A caller that gets ``None`` dispatches with no system
    prompt — the c0 condition — and should say so rather than silently
    substituting another language's bundle.
    """
    for adapter in adapters if adapters is not None else _DEFAULT_ADAPTERS:
        if adapter.owns(target) and adapter.name in _BUNDLE_FILES:
            return load_bundle(adapter.name)
    return None
