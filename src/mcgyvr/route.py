"""Routing: which rung a contract is tried on, and when a family is spent (#24).

The ladder is ordered cheapest to dearest in two nested ways. *Families* —
deterministic tools, then local models, then API models (ADR-0001 boundary 3) —
are the coarse order, and they are declared in the catalog with a rank. *Rungs*
are the fine order inside a family, and they are whatever the operator wrote in
the config. This module walks the fine order. It does not walk the coarse one.

**That split is the acceptance criterion, not a stylistic preference.** #24 owns
climbing rungs within one family and naming the moment that family is spent;
#43 owns what happens next, because crossing from local to API is a spend
decision with its own rules — ascent is monotonic, a global ceiling bounds the
task, and a contract that declared no verification is upgraded the moment it
leaves the deterministic family. Splitting those two rules across two modules
would mean neither module could be read on its own, so the boundary here is
hard: nothing in this file ever looks at a family other than the one it was
asked about, and :func:`plan` returns an empty plan naming its reason rather
than quietly reaching for a dearer rung. #43's task-wide ceiling reaches in as
a *predicate* (:func:`climb`'s ``permit``) for the same reason the attempt
function is one — a budget that spans families cannot be computed here, and a
module that took the number instead of the question would be holding half of a
rule it cannot see the other half of.

**A plan is inspectable before anything is spent.** :func:`plan` answers "which
rungs, in what order, with how many attempts each" without dispatching, which is
what makes routing reproducible rather than merely deterministic: the decision
can be printed, diffed and asserted on. :func:`climb` then executes a plan
against an attempt function the caller supplies. Nothing here assembles a
prompt, applies a diff or runs a gate — those are #25's, #43's and E5's, and a
routing module that did them could not be tested without a model.

**Attempts are policy, and the default is to escalate rather than retry.** Two
numbers meet: the rung's own ``attempts`` (``config.ladder.tiers[].attempts``,
default 1) and the contract's ``limits.attempts``, whose schema calls it a hard
ceiling on one execution. The lower wins, so an operator lowering a rung's
budget is obeyed and a contract lowering its own is obeyed, and neither can
raise the other. The default of 1 means a failed attempt escalates: a retry
re-runs the same model on the same input, and the figure this rule was
inherited with — worker-tier remediation rescued 2 of 35 failures — says that is
usually spend without a result. **That figure is inherited from local-ai and has
not been re-verified here** (ADR-0004, and #152 is where it gets settled), which
is why it argues for a default rather than being quoted as a measurement of
mcgyvr.

**The deterministic family gets exactly one attempt, and it is not on the
ladder.** A tool fails identically on retry, so a second attempt is spend with a
known-in-advance result; :func:`attempts_for` returns 1 for it whatever the
config says. But no configuration can put a rung in that family: a rung's family
comes from whether its *source* needs a credential
(:meth:`~mcgyvr.catalog.Catalog.family_of`), and the deterministic tier binds no
source because it is a program, not a model. So :func:`plan` for that family
answers from the task type instead (#81, :mod:`mcgyvr.deterministic`), and what
it returns is a program — which is why a plan's steps are two types and why
:attr:`Plan.climbable` exists. A caller that read ``bool(plan)`` as "there is
something to climb" was right only while the floor was empty; it holds work and
nothing climbable now, and :func:`climb` refuses the difference by name.

**Declining is not failing.** An attempt may answer that this rung cannot do
this contract at all — #81's rule, and the reason it exists is that a
deterministic tool emitting a plausible-but-wrong edit is far more expensive
than one that steps aside. A decline moves to the next rung without spending an
attempt and without being recorded as a failure, which is why
:class:`Exhaustion` distinguishes a family whose rungs all declined from one
whose attempts were spent.

**Fan-out chooses where a climb starts; it never reorders the ladder.**
``ladder.fanout`` is the knob and ``none`` is its default, which is this
module as it was: a batch of contracts sharing a task type shares a floor
family, so every one of them takes the cheapest rung and queues there while a
peer serving the same model sits idle — and raising ``max_parallel`` does not
fix that, it widens the rig that was already the only one being used. Under
``full`` and under ``idle`` alike, :func:`climb` starts on the cheapest rung of
its plan that has a free slot rather than on the cheapest rung outright.

**Fan-out is a scheduling decision — which rung goes first — and it is not a
spend decision.** That is the invariant of the whole knob, and it is the one
this module had wrong. A rung the climb started *above* is not dropped: it stays
on the walk and is tried like any other, so a fan-out climb spends the same
attempts on the same rungs as ``none`` and ends in the same exhaustion, with the
same history and the same escalation arithmetic. Dropping them was arithmetic
rather than routing — :func:`mcgyvr.escalate.permit` charges an escalation per
rung actually *spent*, so a family whose cheap rungs had been discarded ran out
of ladder while still holding a move nothing had paid for, and that leftover move
funded a dispatch into a *priced* family: ``full`` bought an api call that
``none`` refused at the escalation ceiling. ``full`` is a throughput knob and
must never be able to do that; only ``idle`` may reach a priced rung, and only
deliberately. "Start higher" and "discard what is below" are different things,
and only the first of them is scheduling.

Free slots — ``width - load`` — and not the smallest load, because the question
a fan-out asks is "which of these can take this dispatch now", and an absolute
load cannot answer it: a four-wide rig with two dispatches on it carries twice
the work of a single-slot rig that is full, and it is the only one of the two
with anywhere to put the work. Sending the climb to the emptier-looking rung
parks it in :meth:`~mcgyvr.capacity.Capacity.hold` on a saturated machine while
slots stand free next door — the funnel the knob exists to end, arrived at
through the knob. It is the same rule
:attr:`mcgyvr.escalate.Ascent.next_free_rung` states as ``load < width``, and
one question answered two ways at two seams would be worse than either answer.

**And it chooses once.** The start rung is read from load; from there the walk
is the plan's own price order, over every rung the start did not take. Asking
again after each failure would order the whole *walk* by load, and a walk
ordered by load is a walk with no ladder in it at all — the rung a failure
escalates to would be whichever machine happened to be quiet, which inverts the
one thing a ladder asserts, each rung being measurably better than the one
below it, and which ``docs/config-reference.md`` calls actively harmful.

**A start can also be handed in, already paid for.** :func:`climb`'s ``claimed``
takes the name of a rung whose reservation the caller holds, and that rung goes
first without being reserved again. It exists because the *entry* decision —
which family an ``idle`` ladder enters, which is #43's — is priced across
families and must commit to what it prices: naming a rung reserves nothing, so
without this every member of a batch reads the same one free api slot and each
pays for it. It changes nothing else. The claimed rung is popped out of the
middle of the walk and every other rung stays where it was, because a start is a
scheduling decision and a deletion is a spend one — the same rule, stated the
same way, for a start chosen by load.

That walk does pass back through the rungs the start skipped over, because they
are the cheap end of the price order, and that is deliberate. Trying a rung a
dearer one has already failed at looks like a descent, and the alternative was
measured and is worse: a climb that skipped them would spend less of its family
than ``none`` would and hand the leftover escalation budget to a dearer family —
the defect above. Every rung ``none`` would have tried is tried, exactly once,
for exactly its own attempts; only the order differs, and only in the family
fan-out was asked about.

:func:`plan` still orders by price and nothing may make it do otherwise, because
price order is what a ladder means and a plan that put a busy rung last would be
deciding, from inside one family, that load outranks price. Load breaks a tie —
between rungs that will all admit the work, the cheapest wins, so on an idle
ladder every mode starts where ``none`` starts however the widths differ — and
load never reorders the ladder, which is what preferring a roomier rung over a
cheaper free one would have been.

``idle`` is honoured here for the half of it that is #24's. Its choice is the
cheapest rung *at or above the floor* with a free slot, and that question has
two halves at two seams: which rung *within* one family, which is choosing among
the rungs of a plan and so is this module's under any mode, and which *family*
to enter, which may reach a priced api rung and so is #43's — nothing here looks
at a family other than the one it was asked about, and
:func:`mcgyvr.escalate.ascent` already holds the view that half needs. So
:func:`climb` under ``idle`` starts on the cheapest rung of its plan with a free
slot, and when no rung of the plan has one it starts on the cheapest and queues
there, exactly as ``none`` does; the spill into the next family up is
:attr:`mcgyvr.escalate.Ascent.next_free_rung`'s answer and is applied by
:func:`mcgyvr.escalate.escalate` choosing which family this module is asked
about. Leaving both halves out of this file was the earlier reading of the
boundary and it made the mode a switch wired to nothing: entering a family whose
cheapest rung was full still picked that full rung.

**``idle`` and ``full`` are one rule here and differ only in reach.** Inside a
family both take the cheapest rung that will admit work — see
:func:`_next_index` — and that identity is deliberate rather than an oversight:
within one family there is exactly one useful question, "which of these will
take this dispatch now", and answering it two ways would be two rules to keep
true where one is enough. What differs is how far each may look: ``idle`` may
raise the family a climb *enters*, which is a spend decision and is
:func:`mcgyvr.escalate.escalate`'s, while ``full`` never leaves the family it
was handed. And busy is never a verdict under either: passing a rung over
records nothing about it, so a climb that succeeds where it started leaves the
rung below unjudged — and what load can no longer do is change the *count*, the
rungs a family spends being the same rungs under all three modes.

**What is deliberately not here.** Risk floors raising where work may start are
#16's; this module reads the type's floor from the catalog and applies nothing
on top of it. Draws per rung — trying a rung twice at temperature and taking the
first candidate the gate accepts — are #119's and ADR-0008's, and are a
different axis from attempts: a draw is a fresh sample, an attempt is a retry
after a verdict. Grouping the ladder by family discards the operator's
cross-family ordering, which is only visible in a ladder that interleaves
families (a local rung written below an API one); nothing depends on that today
because nothing here crosses families, and #153 records it against #43, which is
where it first becomes observable.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from mcgyvr.catalog import Family, catalog

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.capacity import Capacity
    from mcgyvr.config import Config
    from mcgyvr.contract import Contract
    from mcgyvr.deterministic import ToolStep
    from mcgyvr.pool import Rung, SourceMap


class RouteError(Exception):
    """A route could not be planned from the inputs given."""


class Verdict(StrEnum):
    """What one attempt on one rung came to.

    Three outcomes, and the third is the one that carries information the other
    two cannot. ``FAILED`` means the rung tried and did not produce an
    acceptable change; ``DECLINED`` means it did not try, because the contract
    is not work of a kind it can do. A caller that collapsed the two would spend
    a rung's budget on rungs that never ran.
    """

    PASSED = "passed"
    FAILED = "failed"
    DECLINED = "declined"


class Exhaustion(StrEnum):
    """Why a family ended without an accepted result.

    Machine-readable because #24 requires family exhaustion to be
    distinguishable from every other failure, and because the cases want
    different responses: spent attempts are a real signal that this family is
    not up to the work, universal declines say nothing about the family's
    ability at all, and no rung at all is a configuration fact.

    ``WITHHELD`` is the fourth and is not about the family: a caller's budget
    guard refused to fund the next attempt, so the family says nothing about
    itself because it was not allowed to finish. It is kept distinct for the
    same reason the other three are — a family stopped by someone else's
    ceiling must not read like one that was tried and could not.
    """

    RUNGS_SPENT = "rungs_spent"
    ALL_DECLINED = "all_declined"
    NO_RUNG = "no_rung"
    WITHHELD = "withheld"


class Fanout(StrEnum):
    """How a batch of contracts spreads over the rungs it may run on.

    The three modes of ``ladder.fanout``, mirrored here as an enum so that a
    plan carries a decided value rather than a string a caller has to remember
    the spellings of. It is a knob and not a behaviour because the right answer
    is a property of the machines: two interchangeable rigs should share a
    batch, and a throughput rig feeding an intelligence rig must not, since the
    second is sized to drain the first's failure tail.

    ``FULL`` and ``IDLE`` both change which rung of a plan a climb starts on,
    and inside a family they choose the same way: the cheapest rung with a slot
    to spare. That they are identical here is the decision and not an
    oversight — one family admits one useful question, "which of these will take
    this dispatch now" — and what separates them is reach. ``IDLE`` may also
    raise the *family* a climb enters, which can land on a priced api rung and
    is therefore #43's to make and not #24's, so it is carried here and acted on
    in :func:`mcgyvr.escalate.escalate`; ``FULL`` never leaves the family it was
    handed, which is what keeps a throughput knob from buying an api call. See
    the module docstring.
    """

    NONE = "none"
    IDLE = "idle"
    FULL = "full"


class Machine:
    """What a rung runs on, as a question rather than as a name (#20).

    Load is a property of the machine and of nothing else: two rungs bound to
    one source are two names for one queue, so a fan-out that compared rungs
    would "spread" a batch across a single box. But a plan is a thing that gets
    printed, and #20's rule is that nothing above the execution seam learns
    where work runs — a :class:`~mcgyvr.pool.Rung` says a name and a model and
    deliberately nothing else, which is what lets a rung be re-pointed at
    another machine without anything above noticing.

    Both hold if the plan carries the *question* instead of the answer, which is
    the same move :func:`climb` makes with ``permit`` and with its attempt
    function. The source name stays private, this renders as ``<machine>``
    wherever a plan is printed, and the only thing anyone above can do with one
    is ask how busy it is. Rungs sharing a source share an instance, so "same
    box" is answerable without anyone being told which box.

    That grouping is what load-aware routing needs today and is observable
    upstream; it is not a boundary this module has settled. A fleet holds rigs,
    a rig holds containers, and a rung may come to bind at any of those levels,
    so how rungs group is a question the ladder/rungs/rigs/models composition is
    still working out. What is decided is that a machine stays an opaque handle
    that answers "how busy" and names nothing — which is exactly what leaves the
    grouping free to change.
    """

    __slots__ = ("_source",)

    def __init__(self, source: str) -> None:
        self._source = source

    def __repr__(self) -> str:
        return "<machine>"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Machine):
            return NotImplemented
        return self._source == other._source

    def __hash__(self) -> int:
        return hash(self._source)

    def load(self, capacity: Capacity) -> int | None:
        """How busy this machine is, or ``None`` if this capacity cannot say.

        :meth:`~mcgyvr.capacity.Capacity.load` is the answer, which is the
        slots that capacity has granted *plus* the attempts reserved against it
        — neither alone is the load, because granted under-reports a batch that
        is mid-choice, which is exactly when this gets asked, and reserved
        misses every dispatch that was never routed through a caller that
        reserves. A reserved attempt that has since been admitted is counted
        once and not twice: :meth:`~mcgyvr.capacity.Capacity.hold` consumes the
        reserving thread's reservation for the length of the slot.

        **This process, this capacity, and only the choices it was told about.**
        Another mcgyvr process contending for the same host-wide slot files
        (#185) is not counted here and never was: the *bound* is the flock and is
        shared, while this number exists to spread the choices one batch is
        making. Cross-process load sensing would mean a ``LOCK_NB`` sweep of
        every slot file on every routing decision — a syscall per rung per
        choice, to fix a case that only bites multi-process runs — so if it is
        ever wanted it belongs in :class:`~mcgyvr.capacity.Capacity`, beside the
        files it would have to read, and not here.

        ``None`` when the capacity does not bound this source at all, which is a
        capacity and a plan built from different configs; it is an ordinary
        answer here rather than an error, because the caller's response is to
        keep price order rather than to fail a climb over a number nobody asked
        for. A caller about to *act* on the answer reads it inside
        :meth:`~mcgyvr.capacity.Capacity.deciding`, as :func:`_claim_next` does,
        because choosing and claiming have to be one decision.
        """
        if self._source not in capacity.limits:
            return None
        return capacity.load(self._source)

    def free(self, capacity: Capacity) -> int | None:
        """How many more dispatches this machine would admit, or ``None``.

        ``width - load``, and the number a fan-out actually needs: a load on its
        own says how much work a machine is doing and not whether it has
        anywhere to put more, and those are different questions the moment two
        machines are different sizes. Zero means saturated — a dispatch sent
        here queues — and the value can go below zero when more attempts have
        chosen a machine than it has slots, which is a truthful reading of a rung
        that is oversubscribed rather than merely full.

        ``None`` for a source this capacity does not bound, for the same reason
        and with the same consequence as :meth:`load`: an unknown width is not a
        free slot, and the two must not be made to look alike.
        """
        width = capacity.limits.get(self._source)
        if width is None:
            return None
        return width - capacity.load(self._source)

    def claim(self, capacity: Capacity) -> None:
        """Count one more attempt as headed here, before it holds anything.

        Called inside :meth:`~mcgyvr.capacity.Capacity.deciding`, so that the
        loads a choice was read from cannot have moved before the choice is
        counted. A source ``capacity`` does not bound is not counted rather than
        refused, because a plan from another config is something this module
        answers ``None`` to everywhere else and a climb over it still has to run.
        """
        if self._source in capacity.limits:
            capacity.reserve(self._source)

    def release(self, capacity: Capacity) -> None:
        """Stop counting one attempt. Never raises, so a ``finally`` is safe.

        A leaked reservation is forever, and it would show this machine as busy
        to every later choice the batch makes — so the release has to be
        callable on the path where something has already gone wrong.
        """
        capacity.release(self._source)


@dataclass(frozen=True)
class Step:
    """One rung of a plan, with the number of attempts it is allowed.

    ``machine`` is what the rung runs on, as a :class:`Machine` — a thing that
    answers "how busy" and names nothing. ``None`` for a step nobody bound to a
    machine, which is a step no load can be read for and which is therefore
    taken in price order whatever the fan-out mode says.

    **And it is out of the comparison.** A :class:`Machine` names nothing, so it
    has no value equality to offer and falls back to identity — which made
    ``plan(config, pool, contract)`` unequal to itself called twice, and with it
    every :class:`mcgyvr.escalate.Ascent`, directly contradicting that class's
    own claim that two ascents differing only in the capacity they were handed
    are the same ascent. Giving ``Machine`` an ``__eq__`` keyed by its source
    would cure the symptom by asserting something this project has not decided:
    a fleet holds rigs, a rig holds containers, and a rung may come to bind at
    any of those levels, so "machine identity is the source name" is a
    commitment the composition work is likely to contradict. A plan describes
    the same route whichever handle answers "how busy" for it, so the field
    stays and the comparison does not use it.
    """

    rung: Rung
    attempts: int
    machine: Machine | None = field(default=None, compare=False)


class Planned:
    """Reading a tuple of steps as rungs and as programs, in one place.

    Two types carry ``tuple[Step | ToolStep, ...]`` — :class:`Plan`, which is one
    family's answer, and :class:`~mcgyvr.deterministic.Routed`, which is the
    floor router's — and every question worth asking about that tuple is the
    same question for both. It is stated here once because the alternative was
    tried: ``Plan`` gained :attr:`climbable` when #81 bound the floor, ``Routed``
    did not, and a caller holding the second had truthiness and nothing else —
    which is precisely the misreading :attr:`climbable` was added to end.

    A plain base rather than a dataclass one: it holds no field, only the four
    readings of the field its subclasses declare, and a dataclass base would put
    ``steps`` in both constructors' signatures from a class that cannot supply
    one.
    """

    steps: tuple[Step | ToolStep, ...]

    @property
    def climbable(self) -> tuple[Step, ...]:
        """The steps :func:`climb` can run: rungs, never programs.

        The question every reader of a plan actually has, asked once here rather
        than by each of them. ``bool(plan)`` answers "is there anything here",
        which was the same question only while the floor was empty by
        construction; since #81 bound it, a family can hold work and hold
        nothing to climb, and a caller that kept using truthiness would enter a
        family whose only step :func:`climb` refuses.
        """
        return tuple(step for step in self.steps if isinstance(step, Step))

    @property
    def programs(self) -> tuple[ToolStep, ...]:
        """The steps that are a program rather than a rung.

        The complement of :attr:`climbable`, and named so that a caller refusing
        one can say which program it was holding rather than only that the plan
        was the wrong shape.
        """
        return tuple(step for step in self.steps if not isinstance(step, Step))

    @property
    def budget(self) -> int:
        """The most attempts these steps could spend between them."""
        return sum(step.attempts for step in self.steps)

    @property
    def climb_budget(self) -> int:
        """The most attempts :func:`climb` could spend on these steps.

        Distinct from :attr:`budget` because a program's single attempt is spent
        by :mod:`mcgyvr.deterministic` and never by the ladder. A caller
        budgeting a climb wants this one; a caller reporting what the family
        costs in total wants :attr:`budget`. Collapsing them would hand the
        climb an attempt of headroom the operator's ladder does not offer.
        """
        return sum(step.attempts for step in self.climbable)


@dataclass(frozen=True)
class Plan(Planned):
    """What one family would run for a contract, cheapest first.

    Empty is an ordinary answer rather than an error: a keyless install
    planning an ``api`` family has no rungs. ``reason`` says which, in words, so
    that a caller reporting "nothing ran" can say why without inspecting the
    config itself.

    A step is a :class:`Step` — a rung a runner dispatches against — or, on the
    deterministic floor, a :class:`~mcgyvr.deterministic.ToolStep`, which is a
    program and has no rung to name. The two are deliberately different types
    rather than one with an optional field: fitting a tool into ``Step`` would
    mean inventing a rung name :meth:`~mcgyvr.pool.SourceMap.bind` cannot
    honour, and every caller that reads ``rung`` would have to learn that it
    sometimes means nothing.

    ``fanout`` is the mode the ladder was configured with, carried on the plan
    so that :func:`climb` can honour it without being handed a
    :class:`~mcgyvr.config.Config`. It says nothing about the order of
    ``steps``, which is price order under every mode — only about which of them
    a climb starts on.
    """

    family: Family
    steps: tuple[Step | ToolStep, ...]
    reason: str = ""
    fanout: Fanout = Fanout.NONE

    def __bool__(self) -> bool:
        return bool(self.steps)

    def __len__(self) -> int:
        return len(self.steps)

    @property
    def rungs(self) -> tuple[str, ...]:
        """The rung names in the order they would be tried.

        A deterministic step contributes nothing here rather than a placeholder:
        it has no rung, and a name invented for it would be a name no source map
        could bind and no ladder entry could configure.
        """
        return tuple(step.rung.name for step in self.steps if isinstance(step, Step))


@dataclass(frozen=True)
class Try:
    """What an attempt function is handed: a rung, its place in the budget, and
    the capacity it must dispatch under.

    ``capacity`` is passed through to every attempt rather than captured once by
    the caller because :func:`~mcgyvr.runner.dispatch` is unbounded by default —
    a ladder walk that threaded a capacity into the first rung and not the rest
    would enforce a source's limit on some of its dispatches, which is the same
    as not enforcing it. ``None`` is a legitimate value for a single task
    running alone; :func:`~mcgyvr.capacity.run_batch` is where it stops being.
    """

    rung: Rung
    attempt: int
    of: int
    capacity: Capacity | None = None


@dataclass(frozen=True)
class Result:
    """What an attempt function reports back.

    Built through :meth:`passed`, :meth:`failed` or :meth:`declined` rather than
    by hand, so that a verdict is always chosen deliberately — a positional
    boolean is exactly how "cannot approve" comes to mean approved.
    """

    verdict: Verdict
    detail: str = ""

    @classmethod
    def passed(cls, detail: str = "") -> Result:
        return cls(verdict=Verdict.PASSED, detail=detail)

    @classmethod
    def failed(cls, detail: str = "") -> Result:
        return cls(verdict=Verdict.FAILED, detail=detail)

    @classmethod
    def declined(cls, detail: str = "") -> Result:
        return cls(verdict=Verdict.DECLINED, detail=detail)


@dataclass(frozen=True)
class Attempted:
    """One entry in the record of what a climb actually did.

    Kept for every rung touched, including the ones that declined, because a
    climb that reported only its failures would make a family that was never
    tried look like one that was tried and could not.
    """

    rung: str
    attempt: int
    verdict: Verdict
    detail: str = ""


@dataclass(frozen=True)
class Accepted:
    """A climb that ended with a rung producing an acceptable result.

    Names which rung and what it took to get there, and carries nothing the
    attempt produced. It used to carry a ``value`` this module never inspected,
    which is what kept routing testable without a model — the testability came
    from not inspecting it, not from holding it, and the caller that needs the
    accepted bytes reads them off the :class:`~mcgyvr.escalate.Judgement` that
    bound them to a tree.
    """

    family: Family
    rung: str
    history: tuple[Attempted, ...]

    @property
    def ok(self) -> bool:
        return True


@dataclass(frozen=True)
class Exhausted:
    """A climb that ended with the family spent, and why.

    This is the named outcome #24 asks for. It is a distinct type rather than a
    flag on a shared one so that a caller cannot reach for a result that was
    never produced, and so that escalation (#43) reads as a match on the answer
    rather than as a boolean it has to remember the polarity of.
    """

    family: Family
    reason: Exhaustion
    history: tuple[Attempted, ...]
    detail: str = ""

    @property
    def ok(self) -> bool:
        return False

    @property
    def attempts_spent(self) -> int:
        """How many attempts were actually consumed — declines are not attempts."""
        return sum(1 for a in self.history if a.verdict is not Verdict.DECLINED)


# --- the family view of a configured ladder --------------------------------


def family_of(config: Config, rung: str) -> Family:
    """Which family the rung named ``rung`` belongs to.

    Resolved through the config's tier binding and the catalog's one rule, so
    this module never restates what a family *is*. Raises rather than guessing
    for an unknown rung: a caller asking about a name the ladder does not offer
    has a bug, not a routing question.
    """
    tier = config.ladder.get(rung)
    if tier is None:
        offered = ", ".join(t.name for t in config.ladder.tiers) or "none"
        raise RouteError(f"no rung named {rung!r} in the ladder. Offered: {offered}")
    return catalog().family_of(config.sources[tier.source])


def by_family(config: Config, pool: SourceMap) -> Mapping[Family, tuple[Rung, ...]]:
    """The usable rungs grouped by family, cheapest family first.

    Every declared family is a key, including the ones with no rungs — an empty
    tuple is the answer to "what can this install run locally", and it is a
    different answer from the family not existing. Within a family the rungs
    keep the order the operator wrote them in, because that is the ladder.

    Only rungs the pool is offering appear: a rung skipped for a missing
    credential or an unreachable source is not something to route work to, and
    :class:`~mcgyvr.pool.SourceMap` has already recorded why it is absent.
    """
    known = catalog()
    grouped: dict[Family, list[Rung]] = {f: [] for f in known.families}
    for rung in pool.rungs:
        grouped[family_of(config, rung.name)].append(rung)
    return {family: tuple(rungs) for family, rungs in grouped.items()}


def attempts_for(family: Family, configured: int, contract: Contract) -> int:
    """How many attempts one rung of ``family`` gets for ``contract``.

    The lower of the rung's configured budget and the contract's declared
    ceiling, except in the deterministic family, which gets exactly one whatever
    either says. That exception is not a special case being carved out — a tool
    is a program, so its second attempt is its first attempt again, and a budget
    that permitted it would be describing spend nobody could benefit from.
    """
    if family.rank == 0:
        return 1
    return min(configured, contract.limits.attempts)


def plan(
    config: Config,
    pool: SourceMap,
    contract: Contract,
    *,
    family: Family | None = None,
    capacity: Capacity | None = None,
) -> Plan:
    """The rungs of one family this contract may be tried on, in order.

    ``family`` defaults to the contract's type floor from the catalog — where
    work of this type may *begin*. It is deliberately not adjusted here when the
    floor's family has no rungs: satisfying a floor with a dearer family is an
    ascent, ascent is #43's, and doing it quietly here would put half of "each
    family is entered at most once" in a module that cannot see the other half.
    An install whose floor family is empty gets an empty plan that names the
    situation, which is the input #43 acts on.

    ``capacity`` is accepted and changes nothing, which is the point of its
    being accepted at all. A caller holding one reaches for this seam first, and
    the guarantee worth being able to state at it is that the ladder it gets
    back is the same ladder: load may break a tie between rungs, and it may
    never rewrite the order they are written in. The load-aware choice is
    :func:`climb`'s instead, for a reason beyond tidiness — load read here would
    be a reading from before the batch started, and the only moment it is true
    is the moment an attempt is about to be made. What this function does carry
    is the *mode*, so that a climb can honour ``ladder.fanout`` without being
    handed a whole config.
    """
    chosen = family if family is not None else contract.type.starts_on
    rungs = by_family(config, pool).get(chosen)
    if rungs is None:  # a Family from another catalog than the one loaded here
        raise RouteError(f"{chosen.name!r} is not a family of the loaded catalog")

    mode = fanout_of(config)

    if chosen.rank == 0:
        # The deterministic floor is planned from the task type, not from the
        # ladder: it binds no rung because its executor is a program, and until
        # this branch existed every `starts_on: deterministic` type planned
        # nothing at all — a model call for work a tool does for free. Imported
        # here rather than at module scope because `mcgyvr.deterministic` reads
        # `attempts_for` from this module; at module scope that is a cycle.
        from mcgyvr.deterministic import tool_steps

        tools = tool_steps(contract)
        if tools:
            return Plan(family=chosen, steps=tools)

    if not rungs:
        return Plan(
            family=chosen,
            steps=(),
            reason=_why_empty(config, chosen, pool),
            fanout=mode,
        )

    machines = _machines(config, rungs)
    steps = tuple(
        Step(
            rung=rung,
            attempts=attempts_for(
                chosen, _configured_attempts(config, rung.name), contract
            ),
            machine=machines[rung.name],
        )
        for rung in rungs
    )
    return Plan(family=chosen, steps=steps, fanout=mode)


def fanout_of(config: Config) -> Fanout:
    """The configured fan-out mode, as a decided value rather than a string.

    Raises rather than falling back to the default for a mode nobody declared:
    the schema's ``choices`` already refuse an unknown one at parse, so reaching
    this means a config was assembled by hand, and quietly routing it as ``none``
    would answer a question about spreading a batch by not spreading it.
    """
    declared = config.ladder.fanout
    try:
        return Fanout(declared)
    except ValueError as exc:
        offered = ", ".join(m.value for m in Fanout)
        raise RouteError(
            f"{declared!r} is not a fan-out mode. Offered: {offered}"
        ) from exc


def _configured_attempts(config: Config, rung: str) -> int:
    tier = config.ladder.get(rung)
    if tier is None:  # unreachable: the rung came from the pool, which came from here
        raise RouteError(f"no rung named {rung!r} in the ladder")
    return tier.attempts


def _machines(config: Config, rungs: tuple[Rung, ...]) -> Mapping[str, Machine]:
    """One :class:`Machine` per source, shared by every rung bound to it.

    Shared on purpose: a ladder with two rungs on one box is one queue, and
    handing each rung its own machine would let a fan-out "spread" a batch
    across a box it never left.
    """
    made: dict[str, Machine] = {}
    by_rung: dict[str, Machine] = {}
    for rung in rungs:
        tier = config.ladder.get(rung.name)
        if tier is None:  # unreachable: the rung came from the pool, from here
            raise RouteError(f"no rung named {rung.name!r} in the ladder")
        by_rung[rung.name] = made.setdefault(tier.source, Machine(tier.source))
    return by_rung


def _why_empty(config: Config, family: Family, pool: SourceMap) -> str:
    """Why a family offers nothing, in the terms that make it actionable.

    The deterministic family is empty for a reason no config edit will change,
    so saying "no rung is bound to it" would send an operator to the wrong file.
    It is also, since the floor was bound, a much narrower case than it was:
    :func:`plan` reaches this branch only when no program is bound for the
    contract's type on its target, not merely because the family holds no rung.
    Every other family is empty either because nothing was bound to it or
    because what was bound could not be offered, and the pool already holds the
    reason for the second case.

    Only *this family's* skipped rungs are quoted. A local rung that was skipped
    says nothing about why the api family is empty, and offering it as the
    explanation would send someone to fix a source that was never the problem.
    """
    if family.rank == 0:
        return (
            "the deterministic family runs tools, not a model on a source, and no "
            "tool is bound for this contract's task type on this target. It binds "
            "no rung either, so there is no ladder entry to configure: what is "
            "missing is a program for the type, not a source for a rung."
        )
    mine = [s for s in pool.skipped if family_of(config, s.name) == family]
    if mine:
        why = "; ".join(f"{s.name}: {s.reason}" for s in mine)
        return (
            f"every rung of the {family.name!r} family was skipped ({why}), so "
            f"this is a configuration or availability problem rather than an "
            f"empty ladder."
        )
    return (
        f"no configured rung is in the {family.name!r} family — bind one to a "
        f"source that "
        + ("declares an api_key_env" if family.name == "api" else "needs no credential")
        + "."
    )


# --- which rung a climb takes next -----------------------------------------


def _next_index(remaining: list[Step], mode: Fanout, capacity: Capacity) -> int:
    """Which of the rungs still untried to take, under each of the three modes.

    Under ``none`` this is ``0`` — the cheapest rung still standing, byte for
    byte the order this module has always walked.

    Under ``full`` and ``idle`` it is the *cheapest rung with at least one free
    slot*: the walk goes up the price order and stops at the first rung that
    will admit this dispatch now. One rule for the two modes, because within a
    family there is one question worth asking and both modes are asking it;
    they part company over *reach*, not over rungs, and that half of ``idle``
    is :func:`mcgyvr.escalate.escalate`'s. ``full`` once took the *roomiest*
    rung instead, which read load as an ordering rather than as a threshold and
    so let a wide dear rung outrank a free cheap one — a price ladder reordered
    by capacity, and on an idle ladder it cost a lone task its cheapest rung for
    no contention at all.

    When no rung has a free slot the answer is ``0``, which queues on the
    cheapest exactly as ``none`` does: within one family there is nowhere
    cheaper to wait, and the rung a queue would spill into is in another family
    and so is :attr:`mcgyvr.escalate.Ascent.next_free_rung`'s to name.

    Free slots — ``width - load`` — and not the smallest load. The two only
    agree when every rung is the same width, and where they disagree the load is
    wrong: a four-wide rig with two dispatches on it has two slots free, a
    single-slot rig holding one dispatch has none, and it is the
    *emptier-looking* second one that a climb ordered by load would queue on.
    See the module docstring; and :attr:`mcgyvr.escalate.Ascent.next_free_rung`,
    which states the same rule as ``load < width`` for the half of ``idle`` that
    crosses families.

    :func:`climb` asks this once, for the rung it starts on. Asking again after
    a failure would order the whole walk by load, and a walk ordered by load has
    no ladder left in it: the rung a failure escalated to would be whichever
    machine happened to be quiet.

    Falls back to price order when a load cannot be read — a step bound to no
    machine, or a machine this capacity does not bound. An unreadable rung stops
    the walk where it stands rather than being stepped over, so what falls back
    is every rung *cheaper than any rung that could have been chosen*: "cheapest
    free" is only knowable if every cheaper rung could be priced, and an unknown
    belongs on the cheap side, never on the side that spends. That is the rule
    ``next_free_rung`` states in the same words, and one question answered two
    ways at two seams would be worse than either answer. A climb with no
    capacity at all never gets here; :func:`_claim_next` answers that one, and
    answers it the same way.
    """
    if mode is Fanout.NONE:
        return 0
    for index, step in enumerate(remaining):
        slots = None if step.machine is None else step.machine.free(capacity)
        if slots is None:
            return 0
        if slots > 0:
            return index
    return 0


def _standing(remaining: list[Step], claimed: str | None) -> int | None:
    """Where ``claimed`` sits in ``remaining``, or ``None`` if it is not there.

    A name rather than a step, because the caller holding the reservation is one
    module up and holds a rung name — a :class:`Step` is built by :func:`plan`
    and a caller that had to hand one back would be handing back a thing it did
    not make. ``None`` for a name this plan does not offer is an ordinary
    answer and :func:`_claim_next` treats it as one; see :func:`climb` for whose
    reservation that leaves and why it cannot be given back from here.
    """
    if claimed is None:
        return None
    for index, step in enumerate(remaining):
        if step.rung.name == claimed:
            return index
    return None


def _claim_next(
    remaining: list[Step],
    mode: Fanout,
    capacity: Capacity | None,
    claimed: str | None = None,
) -> Step:
    """Take the next step off ``remaining`` and count it as chosen.

    Choosing and counting are one decision and so happen inside one
    :meth:`~mcgyvr.capacity.Capacity.deciding` section: a climb that read the
    loads, left the section and only then said which rung it had taken would
    leave a window in which every member of a batch reads the same zeroes — the
    funnel again, narrowed to microseconds but not closed. Nothing slow may run
    in there, which is why this reserves a rung and never holds a slot: the
    section borrows the very lock :meth:`~mcgyvr.capacity.Capacity.hold` keeps
    its counters under.

    **The chosen rung is taken out and no other rung is.** The rungs *cheaper*
    than it stay on ``remaining``, in price order, and later iterations take
    them like any other rung. Dropping them was the earlier decision and it was
    wrong: passing a rung over is a statement about a queue at one instant, and
    deleting it is a statement about what this family is worth — which is spend,
    and fan-out does not make spend decisions. It showed up as one:
    :func:`mcgyvr.escalate.permit` charges an escalation per rung actually
    spent, so a family short of the rungs it was dropped ran out early with
    escalation budget unspent, and that budget bought a priced api rung that the
    same ladder under ``none`` was refused. What survives of the old rule is the
    part that was really about ladders — the *start* is chosen once, and the
    walk after it is price order rather than a fresh load reading.

    **``claimed`` is a rung the caller already reserved, and it is taken as it
    stands.** It is popped out of wherever it sits and *not* claimed again —
    the reservation exists — so the pairing over the whole climb stays one
    reserve and one release, :func:`climb`'s ``finally`` giving back the
    caller's. It is how a decision made one module up, inside its own
    ``deciding`` section, arrives here intact: :func:`mcgyvr.escalate._idle_entry`
    prices the families against one another and reserves what it names in the
    same breath, and without a way to hand that reservation down the two would
    be a read and then a separate commitment, with every member of a batch free
    to read the same one free api slot in between and each pay for it.

    **And it drops nothing.** The rungs cheaper than the claimed one stay on
    ``remaining`` exactly as they do for a rung chosen by load, for exactly the
    same reason: a start is a scheduling decision and a deletion is a spend one.
    An earlier note in ``escalate`` proposed ``del remaining[:index]`` here and
    it was wrong in the way ``869bf2a1`` was wrong — a shortened walk leaves
    escalation budget unspent, and leftover budget funds a move into a dearer
    family. Popping the claimed rung out of the middle honours the invariant;
    deleting what is below it does not.

    A ``claimed`` name this plan does not offer selects normally, as though
    nothing had been claimed — see :func:`climb` for why that leaves the
    reservation with the caller.

    Without a capacity there is nothing to read and nothing to count, so the
    walk is the plan's own order and ``climb(capacity=None)`` counts nothing —
    which is intended: the reservations exist to spread one batch across rigs,
    and a climb with no capacity is not in a batch. A ``claimed`` name is
    ignored there too, and can only be a mistake: a reservation is a claim
    against a capacity, so a caller without one has nothing to hand over.
    """
    if capacity is None:
        return remaining.pop(0)
    with capacity.deciding():
        held = _standing(remaining, claimed)
        if held is not None:
            return remaining.pop(held)
        step = remaining.pop(_next_index(remaining, mode, capacity))
        if step.machine is not None:
            step.machine.claim(capacity)
    return step


def _release(machine: Machine | None, capacity: Capacity | None) -> None:
    """Stop counting an attempt that has ended, however it ended."""
    if machine is None or capacity is None:
        return
    machine.release(capacity)


# --- executing a plan ------------------------------------------------------


def climb(
    plan: Plan,
    attempt: Callable[[Try], Result],
    *,
    capacity: Capacity | None = None,
    permit: Callable[[Step, int], bool] | None = None,
    claimed: str | None = None,
) -> Accepted | Exhausted:
    """Try each rung of ``plan`` in turn until one passes or the family is spent.

    ``attempt`` is the caller's — it is what actually assembles a prompt,
    dispatches, applies and gates, none of which is routing. Keeping it a
    parameter is what lets every rule in this module be asserted without a
    model, a backend or a sandbox, and it is the same move
    :func:`~mcgyvr.capacity.run_batch` makes with a job.

    ``permit`` is the caller's too, and for the same reason. It is asked before
    each attempt is funded and ends the climb when it answers no. A task-wide
    ceiling spans families, so it cannot be computed from a plan — but neither
    may it live here, because #24's boundary is that nothing in this module
    looks past the family it was asked about. A predicate keeps both true: the
    caller knows what its budget means and this module never does, exactly as
    it never knows what an attempt does. The refusal is reported as
    :attr:`Exhaustion.WITHHELD`, which says the family did not finish rather
    than that it failed; naming *whose* ceiling stopped it is the caller's, and
    :mod:`mcgyvr.escalate` is where that happens.

    An attempt that raises is not caught. A verdict is a judgement the attempt
    function made; an exception is one it could not make, and swallowing it into
    an exhaustion would report "this family cannot do the work" when what
    happened was a bug or a dead socket. :func:`~mcgyvr.capacity.run_batch`
    already turns a raising job into a named failure beside its neighbours,
    which is the right place for that to happen.

    ``capacity`` is also what makes load-aware fan-out possible, and this is the
    only place in the module load is read. Under :attr:`Fanout.FULL` and
    :attr:`Fanout.IDLE` alike the rung the climb *starts* on is the cheapest
    rung of the plan with a free slot — which is the top of the plan whenever
    the top has one, and is the top again when no rung does. Under
    :attr:`Fanout.NONE` the start is the top of the plan, unchanged. In every
    case each rung keeps its own budget and ``permit`` is asked before each
    attempt: fan-out decides where a climb begins, never how many attempts it
    may make.

    **And never which rungs it makes them on.** Every rung of the plan is
    walked under every mode — the start rung first, then the rest in the plan's
    price order, which passes back down through the rungs the start skipped
    before going on up. So a fan-out climb and a ``none`` climb of the same plan
    spend the same attempts on the same rungs and reach the same
    :class:`Exhausted`; only the order differs. Dropping the skipped rungs
    instead would make a busy ladder cost *less* than a quiet one, and the
    difference is not a saving — it is escalation budget left over for a dearer
    family to spend, which is how ``full`` came to buy an api call that ``none``
    refused. Being passed over is still not a verdict: a rung the climb never
    reaches, because something below it passed, has no history entry and cannot
    fund anything.

    ``claimed`` names a rung whose reservation the caller **already holds**, and
    it is what lets a choice made across families be one decision rather than
    two. :func:`mcgyvr.escalate.escalate` prices every family's rungs against
    one another inside a single :meth:`~mcgyvr.capacity.Capacity.deciding`
    section and reserves the rung it lands on before leaving it; handing the
    name down here is how that reservation becomes the one this climb walks on,
    instead of being read by one member of a batch and paid for by all of them.
    The rung goes first, whatever the mode and whatever the loads now say — the
    caller decided, under a lock, and re-deciding here would reopen the window
    the reservation closed — and it is taken *without being claimed again*, so
    the caller's reservation and this climb's ``finally`` release pair off
    exactly once. Every other rung of the plan is walked after it in the plan's
    own price order, the claimed rung being popped out of the middle and nothing
    else moved: the budget, the history and the exhaustion are the plan's, and a
    handed-down start is a start like any other.

    **Only for the first step.** ``claimed`` is consumed by the rung it names
    and every later rung claims its own, which is the same shape as the fan-out
    mode being asked once: a caller holds one reservation, so there is exactly
    one to hand over.

    **A ``claimed`` name this plan does not offer** — an ascent rebuilt
    differently, a stale name — selects normally, as though none had been given.
    The reservation behind it then stays the *caller's* to release, and that is
    not a division of labour this function could choose otherwise: a
    :class:`Machine` is built by :func:`plan` from the rungs of one family, so a
    name that is not in the plan has no machine here to release, and #20's rule
    means nothing above the execution seam holds the source name that would be
    the alternative. The same applies to an empty plan, which returns
    :attr:`Exhaustion.NO_RUNG` before any step is taken. So a caller that
    reserves must be able to give it back on every path that does not reach a
    climb that can take it, which is what
    :func:`mcgyvr.escalate.escalate` does in a ``finally``; a leaked reservation
    narrows a source for the life of the process.
    """
    history: list[Attempted] = []
    if not plan.steps:
        return Exhausted(
            family=plan.family,
            reason=Exhaustion.NO_RUNG,
            history=(),
            detail=plan.reason,
        )

    # A tool is not climbed. Every shape this loop hands out — `Try`, `permit`'s
    # argument, an `Attempted` row — is named after a rung, and a deterministic
    # step has none: it is a program, executed by :mod:`mcgyvr.deterministic`.
    # Refusing here rather than skipping keeps that a visible routing error
    # instead of a plan that reports having run and spent nothing.
    #
    # The refusal is for a caller that reached for the wrong function, so it is
    # not something a walk of the ascent should ever meet: `Plan.climbable` is
    # what a caller asks before handing a plan over, and #43 asks it.
    steps = plan.climbable
    if plan.programs:
        named = ", ".join(sorted({step.tool.task_type for step in plan.programs}))
        raise RouteError(
            f"the {plan.family.name!r} plan is a program, not a rung, so it is "
            f"not climbed: run it through `mcgyvr.deterministic` instead "
            f"({named})."
        )

    remaining = list(steps)
    # Fan-out is asked once, for the rung this climb starts on; from there the
    # walk is the plan's own price order over everything still standing. Re-asking
    # it per rung would order the whole walk by load, and a walk ordered by load
    # has no ladder left in it — see :func:`_next_index`.
    choosing = plan.fanout
    # The caller's reservation is handed over once, to the rung it was taken
    # for, and every rung after it claims its own — one reservation, one
    # hand-over, one release.
    holding = claimed
    while remaining:
        step = _claim_next(remaining, choosing, capacity, holding)
        choosing = Fanout.NONE
        holding = None
        try:
            for number in range(1, step.attempts + 1):
                if permit is not None and not permit(step, number):
                    return Exhausted(
                        family=plan.family,
                        reason=Exhaustion.WITHHELD,
                        history=tuple(history),
                        detail=(
                            f"the climb stopped at {step.rung.name!r} attempt "
                            f"{number}: the caller's budget did not fund it."
                        ),
                    )
                result = attempt(
                    Try(
                        rung=step.rung,
                        attempt=number,
                        of=step.attempts,
                        capacity=capacity,
                    )
                )
                history.append(
                    Attempted(
                        rung=step.rung.name,
                        attempt=number,
                        verdict=result.verdict,
                        detail=result.detail,
                    )
                )
                if result.verdict is Verdict.PASSED:
                    return Accepted(
                        family=plan.family,
                        rung=step.rung.name,
                        history=tuple(history),
                    )
                if result.verdict is Verdict.DECLINED:
                    # A decline is about the contract, not about this attempt,
                    # so trying the same rung again would ask a question already
                    # answered. It costs the rung's remaining budget nothing.
                    break
        finally:
            # However this rung ended — passed, declined, withheld, spent or
            # raised — it is no longer in flight, and a reservation that leaked
            # would make the machine look busy to every later choice made under
            # this capacity.
            _release(step.machine, capacity)

    declined_only = all(a.verdict is Verdict.DECLINED for a in history)
    return Exhausted(
        family=plan.family,
        reason=Exhaustion.ALL_DECLINED if declined_only else Exhaustion.RUNGS_SPENT,
        history=tuple(history),
        detail=_exhausted_detail(plan, history, declined_only),
    )


def _exhausted_detail(plan: Plan, history: list[Attempted], declined_only: bool) -> str:
    """One sentence saying what was tried, for a caller reporting upward.

    The rungs named are the ones actually attempted, in the order they were
    attempted — which under fan-out is the start rung first and the rungs it
    began above after it, and which is every rung of the plan under all three
    modes, because :func:`climb` exhausts ``remaining`` before it gets here.

    This once carried an aside naming the rungs a climb had *skipped* and
    blaming "no free slot when this climb chose where to start". The clause went
    when the skipping did — :func:`_claim_next` no longer drops the rungs below
    its start, so under every mode a family reaches an exhaustion having tried
    all of its rungs, and the aside had become a fixed reason printed for an
    empty set. It had also been printing that reason for rungs that were merely
    narrower, which is a fabricated cause: an exhaustion that invents why a rung
    went untried is worse than one that says nothing, because a caller acts on
    it. Nothing replaces it. A plan whose steps were handed a budget of zero is
    the one remaining way a rung can go unattempted, and it is not reachable
    from :func:`plan` — both ``attempts`` schemas floor at 1 — so such a rung is
    simply absent from the list of what was tried, which is true.
    """
    tried = tuple(dict.fromkeys(a.rung for a in history))
    rungs = ", ".join(tried)
    if declined_only:
        return (
            f"every rung of the {plan.family.name!r} family declined this "
            f"contract ({rungs}); no attempt was spent."
        )
    spent = sum(1 for a in history if a.verdict is not Verdict.DECLINED)
    return (
        f"the {plan.family.name!r} family is spent: {spent} attempt(s) across "
        f"{rungs} and none produced an acceptable result."
    )
