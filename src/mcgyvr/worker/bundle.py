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

**The JS/TS bundle has now been measured, and it found nothing.** CLM-0004's
confidence note barred generalising its percentages to another language until
re-measured, and #144 re-measured: the same four-condition ladder over a JS/TS
task set, same model, same quant, produced 45/55/50/45% first-pass acceptance
across c0-c3. Every delta is inside the ±1-task noise floor the design declared
in advance, and the deltas are built from flips in both directions rather than
from a consistent gain. So ``prompts/javascript.md`` ships with
:data:`BundleStanding.MEASURED_NO_EFFECT` — the prediction it shipped on in #25
was not confirmed.

**Why the Python effect did not transfer is legible in the token column, and it
is the more useful half of the result.** CLM-0004's speed-up came from output
rules stopping a small model rambling: 403 completion tokens at c0 against ~124
at c2. The JS/TS run measured 167/167/169/177 — flat. The 3b was never rambling
on this task set, so the mechanism the bundle works through had nothing to act
on. That predicts where a bundle *will* pay: workers that over-produce without
one, not languages as such.

**#167 ran the control that says why, and it is not the language.** CLM-0012
could not separate "the device does not work in JS/TS" from "the device does not
work on this serving stack", because CLM-0004's Python task set had been left in
another repository. It was recovered, and both readings are wrong. Re-run
unchanged against Ollama, CLM-0004's own instrument reproduces its effect
(35/50/55/65% across c0-c3, and its never-passing set exactly) — so the stack is
not it. The same twenty tasks through *this* module's prompt assembly measure
+1 task at p = 1.00 — so the language is not it either.

What differs is the harness. :func:`~mcgyvr.worker.prompt.render_user_message`
already ends every user message by demanding the whole file as one fenced block
and nothing else, which *is* the device. Through it the 3b emits 111.8
completion tokens at c0, where local-ai's markerless contract draws 427.4;
appending that one sentence to the original contracts under the original
harness moved c0 from 7/20 to 11/20 at 121.5 tokens, matching the entire
1 972-byte bundle. So ``prompts/python.md`` ships with
:data:`BundleStanding.MEASURED_REDUNDANT`: its effect is real, and this project
had already built it. The remaining ~1 500 bytes of standards, checklists and
pitfalls bought nothing measurable on either task set.

The file still ships. Measuring no benefit is not measuring harm, and c0 is not
a better-evidenced choice than c2 — the run cannot separate them either. What
changed is that "probably better than nothing" is no longer available as a
reason. The marker stating all this is stripped by :func:`strip_provenance`,
which is what keeps a file's standing sayable in the file without spending the
worker's prompt on it; ``tools/bundle/`` is the instrument that settled it.

One bundle per language adapter, selected by asking the gate's adapters which
one owns the contract's target. That reuses the ownership rules the gate
already applies (:meth:`~mcgyvr.gate.adapter.LanguageAdapter.owns`) instead of
growing a second, driftable table of file extensions.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from importlib import resources

from mcgyvr.gate.adapter import LanguageAdapter
from mcgyvr.gate.adapters import JavaScriptAdapter, PythonAdapter

# The measured ceiling, in bytes of UTF-8. 2 KiB: the c2 condition (1972 bytes)
# is the best of the four measured, and c3 at 8342 bytes measured *worse* than
# c2 on the small worker while buying nothing on the large one. So this is not
# a budget guess — it is the point past which the evidence says quality falls.
# Raising it is a claim about quality and needs a measurement, not an edit.
#
# It stays ONE constant across languages, and #144 is why that is now a finding
# rather than a gap. The same ladder was run on a JS/TS task set (CLM-0012) and
# no rung separated from c0 — so there is no JS/TS peak to place a different
# ceiling at. A per-language ceiling would need a language whose curve has a
# peak; JS/TS measured flat, which is not the same as measuring 2 KB.
MAX_BUNDLE_BYTES = 2048

# Which bundle serves which adapter, keyed by `LanguageAdapter.name`. A language
# with no entry gets no bundle rather than another language's: the standards and
# pitfalls sections are language-specific, and handing a Go worker the Python
# rules would be worse than handing it nothing.
_BUNDLE_FILES: dict[str, str] = {
    "python": "python.md",
    "js/ts": "javascript.md",
}


class BundleStanding(StrEnum):
    """What a measurement says about a bundle — not merely whether one ran.

    A bare "measured" boolean stopped being enough the moment #144 reported.
    Both shipped bundles are now the artifact a sweep was taken on, so a
    boolean would read the same for a bundle measured at +25 pp and one
    measured at nothing — and "measured" is a word a reader takes as
    endorsement. The outcome is the part worth carrying, so it is the part
    the type names.
    """

    UNMEASURED = "unmeasured"
    """No sweep has been run on this artifact. The standing python.md had
    before CLM-0004 and javascript.md had before CLM-0012."""

    MEASURED_BENEFIT = "measured-benefit"
    """A sweep ran and the bundle beat its absence. `python.md`: 45% to 70%
    first-pass acceptance at ~2.5x the speed (CLM-0004)."""

    MEASURED_NO_EFFECT = "measured-no-effect"
    """A sweep ran and no rung separated from no-bundle-at-all. `javascript.md`:
    45/55/50/45% across c0-c3, every delta inside the stated ±1-task noise floor
    (CLM-0012). The file still ships because measuring no benefit is not
    measuring harm — but nothing here licenses citing a gain."""

    MEASURED_REDUNDANT = "measured-redundant"
    """The bundle's effect is real, and this project's own prompt already has it.

    `python.md`: CLM-0004's 45%-to-70% is not withdrawn and reproduces on the
    serving stack mcgyvr dispatches on (#167 arm B: 35/50/55/65% across c0-c3
    through the same instrument on Ollama). What it was measured against is a
    user message with no output rule in it. Through
    :func:`~mcgyvr.worker.prompt.render_user_message`, over the same twenty
    tasks on the same endpoint, the same bundle measures +1 task at p = 1.00.

    The cause is isolated rather than inferred: `render_user_message` ends every
    message by requiring the complete file as one fenced block and nothing else,
    which is the device the bundle's gain runs through. Appending that one
    sentence to the *original* contracts under the *original* harness — nothing
    else changed — took c0 from 7/20 at 427.4 completion tokens to 11/20 at
    121.5, matching the whole 1 972-byte bundle's 11/20 and beating it on
    tokens.

    Distinct from :data:`MEASURED_NO_EFFECT`, and the distinction is load-bearing
    in both directions. A reader must not cite a gain here — on mcgyvr's path
    there is none. A reader must also not conclude the artifact is inert: give
    it to a harness whose prompt lacks output discipline and it is worth about
    four tasks in twenty. What is redundant is redundant *with something*, and
    naming that is the difference between a fact and a shrug."""


# What each shipped bundle's own measurement found. A language absent from this
# table has had no sweep; `js/ts` is here with a null result rather than absent,
# because "measured, and it did nothing" is a different fact from "unmeasured"
# and only one of them is settled.
_STANDING: dict[str, BundleStanding] = {
    "python": BundleStanding.MEASURED_REDUNDANT,
    "js/ts": BundleStanding.MEASURED_NO_EFFECT,
}

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
        :attr:`standing` for that. True here means CLM-0004 or CLM-0012 covers
        *this file* rather than a file that inspired it, which is the property
        #144 asked to be able to assert.
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
    it is none. That is a note to a reader of the repository, and #144 found it
    being sent to the model: ``javascript.md``'s two-line marker was 162 bytes
    of the 2039 the loader handed a worker, and it opened the system prompt by
    telling the model its own instructions were an unmeasured port whose figures
    should not be cited. Both are defects. It spent the ceiling that
    :data:`MAX_BUNDLE_BYTES` exists to enforce on text that is not instructions,
    and it put meta-commentary where a small model expects its role.

    Stripping here makes the marker provenance rather than prompt, and that is
    what lets #144's two acceptance conditions hold at once: a bundle can carry
    an UNMEASURED marker *and* be byte-identical to the condition a sweep
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


def load_bundle(language: str) -> Bundle:
    """Load one language's bundle, refusing it if it broke the ceiling.

    The bundle is the file's body: a leading provenance marker is stripped by
    :func:`strip_provenance` before anything else, so neither the ceiling nor
    the worker ever sees it.

    Raises :class:`BundleMissingError` for a language with no bundle file and
    :class:`BundleTooLargeError` for one that outgrew the measurement.
    """
    filename = _BUNDLE_FILES.get(language)
    if filename is None:
        raise BundleMissingError(
            f"no bundle is registered for language {language!r} "
            f"(registered: {', '.join(sorted(_BUNDLE_FILES))})"
        )
    raw = _read(filename)
    if raw is None:
        raise BundleMissingError(
            f"bundle file {filename!r} for language {language!r} is not present "
            f"in this installation"
        )
    text = strip_provenance(raw)
    size = len(text.encode("utf-8"))
    if size > MAX_BUNDLE_BYTES:
        raise BundleTooLargeError(filename, size)
    return Bundle(
        language=language,
        text=text,
        size_bytes=size,
        standing=_STANDING.get(language, BundleStanding.UNMEASURED),
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
