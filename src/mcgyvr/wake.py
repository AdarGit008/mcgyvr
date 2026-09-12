"""A card that is down and has a launch spec is asleep, and asleep is not a decline.

Three neighbours already answer liveness questions and none of them answers
this one.

* :mod:`mcgyvr.cooldown` is failure-driven and its outcome is a **decline**:
  three consecutive dispatch failures take a source out for sixty seconds, and
  ``drive`` turns the resulting ``SlotUnavailableError`` into
  ``Verdict.DECLINED`` — "Nothing was asked and nothing answered". A sleeping
  card must queue and wake, not step aside.
* :mod:`mcgyvr.availability` is liveness-driven and reads a sleeping rig as
  **down**, correctly on its own terms — nothing is listening — and with the
  wrong consequence.
* :mod:`mcgyvr.capacity` bounds a wait for a *slot* on a server that exists.

So ``asleep`` is not a fourth state to store. It is ``down`` plus one more fact
mcgyvr already holds: **a launch spec it wrote for that card**::

    up      the unit answers                          -> dispatch, unchanged
    asleep  it does not answer, and this config's
            serving.compose_dir holds a file for it   -> wake, then dispatch
    down    it does not answer, and there is no
            such file                                 -> availability's DOWN

There is no state machine, no field to keep in sync with a rig and no third
liveness module. The distinction that matters to a caller — *can mcgyvr bring
this back?* — is answered by *does mcgyvr have the file?*, which is answerable
without touching the network. It degrades honestly by construction: an api
source has no compose file and is never asleep, a rig somebody else runs has no
compose file and is never asleep, and a config with no ``serving.compose_dir``
has no sleeping cards at all.

**Fail-first, never probe-first.** A card that is up must cost nothing extra, so
this module does not ask whether a rig is awake before sending work. It sends
the work. A sleeping rig has nothing listening, so the connection is refused in
under a millisecond and **that instant refusal is the wake signal**. A
probe-first design would pay a round trip on every dispatch to learn something
the dispatch itself reports for free, which is the cost
:mod:`mcgyvr.availability` exists to avoid, re-added per request.

**One door and nothing else.** A wake is
``python -m mcgyvr.serving.run serve up --host H --compose FILE --suffix S``,
spawned as a subprocess, and a sleep is the same with ``down``. Nothing here
runs ``docker`` or ``ssh``: under the door those two names resolve to shims that
"admit exactly the host the door was opened for and refuse any process the door
did not start" (:mod:`mcgyvr.serving.run`), and ``tests/test_one_door.py`` bans
the way round it. :func:`spawn_door` is therefore the whole of this module's
contact with a machine, which is what lets a test own all of it.

The design is ``records/plans/sleep-wake.md``, approved; the budget argument is
``records/plans/wake-timeout.md``.
"""

from __future__ import annotations

import json
import math
import os
import stat
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from mcgyvr.config import Config
from mcgyvr.runner import TransportError
from mcgyvr.serving import Card, cards

# The module the door is spelled as -- an ``-m`` and never a path, because the
# door mints its own ``RUN_*`` vocabulary, refuses to start under an inherited
# one and files write-once evidence under ``records/evidence/``, so a wake that
# reached a rig any other way would be the second way in that
# ``src/mcgyvr/serving/run.py`` says the seal is against.
#
# Imported rather than restated. It stood here as its own literal until the
# four-lenses check named it (ADR-0026 lens 3): two spellings of one door is a
# door that can be half-renamed, and the half nobody edits is the one that
# quietly stops being the door. `gatelib` is where the gates already read it
# from, so it is the definition and this is the reader.
from mcgyvr.serving.gatelib import DOOR_MODULE

#: What one dispatch answers with. Named so that :meth:`Waker.dispatching`
#: hands back exactly what the call it wrapped would have, which is what lets it
#: sit inside `drive` without `drive` learning anything about wakes.
Answer = TypeVar("Answer")


class WakeError(Exception):
    """A card could not be woken or slept, and the reason is worth reading."""


def spawn_door(argv: Sequence[str], **kwargs: object) -> int:
    """Run the door to completion and return its exit code.

    The one seam. It is a module-level function rather than a method so that a
    test can substitute it with one ``monkeypatch.setattr`` and thereby own
    every path from this module to a machine — which is the property D3 buys by
    refusing to let anything here run ``docker`` or ``ssh`` directly.

    Output is inherited rather than captured: the door writes its own evidence
    envelope and its refusals are worth reading verbatim, and a wake that
    swallowed "no run root, refusing before gate 1" would silently decline a
    rung on an install that simply cannot wake a card.
    """
    done = subprocess.run(list(argv), check=False, **kwargs)  # type: ignore[call-overload]
    code: int = done.returncode
    return code


def door_argv(
    *, direction: str, host: str, compose: Path, suffix: str
) -> tuple[str, ...]:
    """The one command a wake or a sleep is.

    ``--suffix`` is not optional and is not cosmetic. Gate 5 claims the
    ``RUN_ID`` with ``O_CREAT | O_EXCL`` and refuses a second run that mints the
    same one, so without a suffix two wakes on one day collide with each other
    and with an operator's hand-run ``serve up``. It is derived from the waker's
    pid and clock, so every wake gets an envelope of its own.
    """
    return (
        sys.executable,
        "-m",
        DOOR_MODULE,
        "serve",
        direction,
        "--host",
        host,
        "--compose",
        str(compose),
        "--suffix",
        suffix,
    )


def _suffix() -> str:
    """A RUN_ID suffix no other wake on this host will mint.

    Only ``[A-Za-z0-9_.-]`` — gate 5 requires it because the id prefixes
    container names, and two arms of the 2026-09-09 campaign were lost to a
    ``+`` in a label.
    """
    return f"wake-{os.getpid()}-{int(time.monotonic() * 1000) % 1_000_000}"


@dataclass(frozen=True)
class Wake:
    """What one door run cost, and whether that is what was expected.

    Kept as a value rather than printed and forgotten because the owner's ruling
    of 2026-09-09 is that **every wake records predicted against actual** and
    warns on a deviation in *both* directions. The prediction is advisory and
    the warning is the whole of what it is allowed to do — see
    :func:`predicted_wake_s`.
    """

    host: str
    compose_file: Path
    direction: str
    seconds: float
    predicted_s: float | None
    code: int

    @property
    def ok(self) -> bool:
        return self.code == 0

    @property
    def deviation(self) -> str | None:
        """The sentence an operator is owed, or ``None`` when there is nothing.

        The wake limit now comes from the fleet lock's validated wake plus its
        tolerance, not a ratio written in code, so the ratio-based warning has
        no number to stand on here. Judgement moves to the lock's alert path.
        """
        return None


def _clock_dir() -> Path:
    """Where this host keeps what it has learned about its own wakes.

    Beside the capacity rendezvous directory and keyed by uid for the same
    reason D7 gives: twenty ``mcgyvr run`` processes have twenty memories and
    one filesystem, and a record that lived in memory would be a record the
    next run could not read. Nothing here is a lock and nothing here is
    authoritative — it is one number per card, and a missing or unreadable file
    means the card has no history, which is the ordinary state on the first
    wake after an install.
    """
    return Path(tempfile.gettempdir()) / f"mcgyvr-wake-{os.getuid()}"


def _ours(where: Path) -> bool:
    """Whether this directory is one only this user can have put anything in.

    ``/tmp/mcgyvr-wake-<uid>/`` is a predictable path in a world-writable
    directory, so the first process to create it wins the name — and
    ``mkdir(exist_ok=True)`` adopts whatever is there, including a directory
    another local user made, and including a symlink pointing somewhere else
    entirely.

    Nothing in this cache is secret. What is at stake is that the number in it
    is read back and printed to an operator as what the card did last time, and
    that a wake writes into the directory afterwards. So it is used only when it
    is a real directory, owned by this user, and writable by nobody else — the
    conditions ``mkdir(mode=0o700)`` establishes when we are the one who made
    it. Anything else degrades to no history, which is free: it is the ordinary
    state of the first wake after an install.

    ``lstat`` and not ``stat``, because a symlink is precisely the case a
    ``stat`` would follow into and approve.
    """
    try:
        found = os.lstat(where)
    except OSError:
        return False
    if not stat.S_ISDIR(found.st_mode):
        return False
    if found.st_uid != os.getuid():
        return False
    return not found.st_mode & (stat.S_IWGRP | stat.S_IWOTH)


def _history(card: Card) -> Path:
    return _clock_dir() / f"{_safe(card.host)}.wake.json"


def _safe(host: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in host)


def predicted_wake_s(card: Card) -> float | None:
    """How long this card took to wake last time, or ``None`` the first time.

    **The last actual is the prediction, and that is a deliberate refusal to
    fit a curve.** ``records/plans/wake-timeout.md`` §3 derives a per-unit form
    — ``blob x r(host, engine) x clearance penalty``, summed over the units a
    launch spec sequences — and §4 then says how weak every coefficient in it
    is: ``r(srv1)`` is two points, one of them n=1, and the only line through
    them has an unphysical negative intercept; ``r(srv2)`` is a single point,
    which cannot tell a rate from a constant; ``k`` spans 1.44x across three
    points, over-predicts its one out-of-sample check by 27% and *under*-
    predicts the refusal-gate cliff by 2.4x. §4.3 prices the campaign that
    would fix that at about 56 arms, roughly a week of rig time. A figure
    derived from coefficients that wrong, shipped as though it were knowledge,
    is worse than no figure — so this module ships none, and ships instead the
    one number every fleet has for free.

    **It may never shorten or abort a wake** (owner's ruling, 2026-09-09). It
    warns, and it informs scheduling, and ``budgets.wake_timeout_s`` remains the
    sole authority that gives up. That is not a limitation of *this* predictor
    but of any of them: a derived budget that could abort would abandon a wake
    that was about to land, and what it would leave behind is a card half-up,
    which is the one lifecycle state D2 says the reading cannot name.

    What it is good for is exactly what a repeated measurement is good for. A
    card that took 133 s and now takes 385 s has lost the RAM clearance its blob
    needs (measured, srv1's Qwen3.6 over a 0.97 GB shortfall). A card that took
    103 s and now takes 4 s did not load what you think it did. Neither of those
    needs a coefficient to notice.

    **Every way of not being a number is no prediction, and none of them is an
    exception.** The ruling above is not only about the figure being wrong; it
    is about this function being unable to stop a wake, and a raise stops one —
    :func:`_run_door` calls this *before* it spawns the door, so an
    ``AttributeError`` here is a card that never comes back for a rung that is
    queued on it. What is on the other end is a file in a temporary directory
    written by a process that may have been killed halfway through it, so JSON
    ``null``, a list, a number, a string, half a document and a file of bytes
    that are not text are all things that have to arrive as ``None``. The read
    catches ``ValueError`` as well as ``OSError`` because a file that is not
    UTF-8 raises ``UnicodeDecodeError`` out of ``read_text``, which is neither
    an ``OSError`` nor something ``json`` ever sees.

    A boolean is not a number of seconds either, however much
    ``isinstance(True, int)`` says otherwise: ``{"seconds": true}`` predicted a
    1.0 s wake, which is not a time anything on this fleet has taken and would
    have warned about every real wake that followed it.
    """
    where = _clock_dir()
    if not _ours(where):
        return None
    try:
        raw = _history(card).read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None
    try:
        said = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(said, dict):
        return None
    seconds = said.get("seconds")
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
        return None
    # `NaN` and `inf` are JSON that `json` accepts and arithmetic that no
    # comparison in `Wake.deviation` is true of, so they would be a prediction
    # that silently warns about nothing.
    number = float(seconds)
    return number if math.isfinite(number) else None


def _remember(made: Wake) -> None:
    """Write down what this wake actually cost, for the next one to be read against.

    Best-effort and silent on failure: a wake that landed must not be reported
    as failed because a temporary directory was not writable, and the only thing
    lost is the next wake's warning.

    ``mode=0o700`` on the directory, and :func:`_ours` before writing into one
    that already exists. ``mkdir(exist_ok=True)`` on a predictable path under
    ``/tmp`` adopts whatever another local user put there first, symlink
    included, and this is the write that would then land in it.
    """
    if not made.ok or made.direction != "up":
        return
    try:
        where = _clock_dir()
        where.mkdir(parents=True, mode=0o700, exist_ok=True)
        if not _ours(where):
            return
        (where / f"{_safe(made.host)}.wake.json").write_text(
            json.dumps({"host": made.host, "seconds": round(made.seconds, 3)}),
            encoding="utf-8",
        )
    except OSError:
        return


def compose_for(card: Card) -> Path | None:
    """The launch spec that would bring this card back, if there is exactly one.

    **One, or none, and never a choice.** A card whose directory holds several
    of mcgyvr's launch specs is a card mcgyvr cannot bring back, because
    ``serve up`` starts one file and nothing in a config says which of them is
    the current one (D2, ``records/plans/sleep-wake.md``). Picking is not a
    tie-break to be got right later; it is the fleet-shape controller's question
    (``records/plans/fleet-shape/``) and no line of it is implemented.

    Declining is not conservatism for its own sake. The file a name-based choice
    picked was reliably the **wrong** one: ``emit`` deletes nothing, so the day
    a host's units stopped summing onto its card the alternatives were written
    beside a ``compose.<host>.yml`` that holds all of them at once — 11.83 GiB
    of a 6.00 GiB card on srv1's own figures — and that leftover is exactly what
    ``compose.<host>.yml`` names. A wake would have started the overcommit
    ``hold_together`` was written to refuse, on a rig, with ``emit --check``
    clean, because a check reads only the paths a config plans.

    :func:`mcgyvr.emit.unplanned` is the other half: it names the leftover so
    the operator can delete it, and one spec is left, and this answers again.
    """
    if len(card.specs) == 1:
        return card.specs[0]
    return None


def _why_not_one(card: Card) -> str:
    """The sentence a caller is owed when there is no single spec to start."""
    if not card.specs:
        return (
            f"{card.host}: this config holds no launch spec for that card. "
            f"`asleep` is `down` plus a file mcgyvr wrote, and there is no "
            f"file: set `serving.compose_dir` to where `mcgyvr emit --out` "
            f"wrote, and emit if it has not been emitted"
        )
    listed = ", ".join(path.name for path in card.specs)
    return (
        f"{card.host}: this config holds {len(card.specs)} launch specs for "
        f"that card — {listed} — and only one of them is ever up. Which one is "
        f"current is not a question the config answers, so mcgyvr will not "
        f"guess: name the file to `python -m {DOOR_MODULE} serve` yourself. If "
        f"one of these is an older cut of the rig, `mcgyvr emit --check` says "
        f"which, and deleting it leaves one"
    )


def _run_door(config: Config, card: Card, direction: str, compose: Path) -> Wake:
    predicted = predicted_wake_s(card)
    started = time.monotonic()
    code = spawn_door(
        door_argv(
            direction=direction,
            host=card.host,
            compose=compose,
            suffix=_suffix(),
        )
    )
    made = Wake(
        host=card.host,
        compose_file=compose,
        direction=direction,
        seconds=time.monotonic() - started,
        predicted_s=predicted,
        code=code,
    )
    _remember(made)
    said = made.deviation
    if said is not None:
        print(f"warning: {said}", file=sys.stderr)
    return made


class Waker:
    """The dispatch-time half: a refused port becomes a wake and one retry.

    Built by :func:`for_config` and ``None`` for a config that did not ask, so
    that "the switch is off" and "the feature does not exist" are the same code
    path rather than a branch that could be got wrong. That equality is the
    design's safety property: mcgyvr must not be able to take a card down for an
    operator who did not ask, and a switch that gated only *some* of the
    behaviour would leave "asked" meaning nothing.
    """

    def __init__(self, config: Config) -> None:
        self._config = config
        self._cards = cards(config)
        #: Cards this run has already woken. One wake per card per run: a
        #: second refusal after a successful wake is a real fault of the rung —
        #: the card is up and something else is wrong — and re-running the door
        #: for it would spend minutes of rig time proving that twice.
        self._woken: set[str] = set()

    def dispatching(self, rung: str, send: Callable[[], Answer]) -> Answer:
        """Send, and on a refused port wake the card once and send again.

        The retry spends **no attempt**: nothing was asked and nothing answered,
        which is the rule ``drive`` already applies to a declined rung and the
        reason it has to hold here too — a refusal charged as a failure would
        exhaust a one-attempt rung on a card that was merely off.

        A wake that *fails* is a different thing and is a real verdict against
        the rung: the original refusal is re-raised with the door's exit code
        left where the operator can read it, and the run reports the transport
        fault it actually had.
        """
        try:
            return send()
        except TransportError as refused:
            if not self.wake_for(rung):
                raise refused
            return send()

    def wake_for(self, rung: str) -> bool:
        """Bring this rung's card back, or say why nothing was tried.

        ``False`` is not a failure. It is every one of the honest degradations
        D2 asks for — an api rung, a rig somebody else runs, a config that
        states no ``compose_dir``, a card mcgyvr never wrote a spec for, and a
        card this run has already woken once — and in each of them the caller's
        refusal stands exactly as it stands today.
        """
        card = self._cards.get(rung)
        if card is None or card.host in self._woken:
            return False
        # Live wakes only along a listed switch, and a switch exists only on a
        # locked fleet. With no committed lock naming this rig there is no
        # switch to be along, so the wake is refused before any door run.
        if self._config.get("profile") == "live":
            from mcgyvr.fleet.admit import host_is_locked

            if not host_is_locked(Path.cwd(), card.host):
                return False
        compose = compose_for(card)
        if compose is None:
            # `down`, not `asleep`. Waking a card mcgyvr never sized would be
            # sizing and starting in one act, which is exactly what
            # `mcgyvr.emit`'s boundary forbids: sizing is a judgement a person
            # reviews.
            #
            # A card with *several* specs is the same refusal for the opposite
            # reason, and it is the one worth a sentence: nothing is missing,
            # something is ambiguous, and the difference is a directory listing
            # an operator has not looked at. Said once per card per run — the
            # `_woken` set is what bounds it — because a rung that declines for
            # a reason only the filesystem holds is the silence this whole
            # module exists to stop.
            if card.specs:
                self._woken.add(card.host)
                print(f"warning: {_why_not_one(card)}", file=sys.stderr)
            return False
        self._woken.add(card.host)
        return _run_door(self._config, card, "up", compose).ok


def for_config(config: Config) -> Waker | None:
    """A waker for this run, or ``None`` where the config did not ask for one.

    Two keys and both of them have to be there. ``enable_sleep_wake`` is the
    permission and ``compose_dir`` is the means: a config that says yes and
    names no directory holds no launch spec for anything, so there is nothing
    to wake and nothing to be wrong about.
    """
    if not config.get("serving.enable_sleep_wake"):
        return None
    if not config.get("serving.compose_dir"):
        return None
    return Waker(config)


def card_named(config: Config, host: str) -> Card:
    """The card an operator named by host, refused by name where there is none."""
    for card in cards(config).values():
        if card.host == host:
            return card
    known = sorted({card.host for card in cards(config).values()})
    raise WakeError(
        f"no rung of this ladder is served by {host!r}"
        + (f" — this config's rigs are {', '.join(known)}" if known else "")
    )


def sleep(config: Config, host: str) -> Wake:
    """Take the whole card down, after draining every slot it serves.

    **Whole-card eviction is not a behaviour to build; it is the behaviour
    ``serve down`` already has**, because the down step tears down every service
    in the file it is given. On a host of co-residents that file is the host's
    and the sentence is exact — srv2's two rungs go down together, in one door
    run, and the operator never spells a container name.

    **The drain is the caller's and is not optional in practice.** An eviction
    takes all of the card's slots before it takes the card down, never
    interrupts a dispatch already in flight, and is best-effort against
    processes the flock cannot see (D8) — and the thing that owns those slots is
    a :class:`~mcgyvr.capacity.Capacity`, which is built from a config by the
    caller and is not this module's to construct. So the drain is spelled where
    the capacity is, as ``capacity.drain(card.sources)`` around this call, and
    :func:`mcgyvr.cli._serve` is the worked example. Calling this without one is
    correct only where there is no capacity at all; with one and unused, it is
    killing containers out from under requests that were already admitted.
    """
    card = card_named(config, host)
    compose = compose_for(card)
    if compose is None:
        raise WakeError(_why_not_one(card))
    return _run_door(config, card, "down", compose)


def wake(config: Config, host: str) -> Wake:
    """Bring the whole card back, through the door and through nothing else."""
    card = card_named(config, host)
    compose = compose_for(card)
    if compose is None:
        # Two refusals in one sentence, and `_why_not_one` tells them apart. No
        # spec at all is emit's boundary — waking a card mcgyvr never sized
        # would be sizing and starting in one act. Several specs is D2's gap:
        # mcgyvr holds the files and not the answer to which.
        raise WakeError(_why_not_one(card))
    return _run_door(config, card, "up", compose)
