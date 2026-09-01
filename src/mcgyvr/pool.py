"""The source map — where work runs, and the seam that keeps it a secret.

A source is an endpoint with a capacity and a wire protocol. This module is the
one place that knows which source serves which rung, and it exists so that
nothing above it has to. Above the seam a caller sees a *ladder of rungs*: named
steps, cheapest first, each with a model. Below it, a rung resolves to an
:class:`Endpoint` a runner can dispatch against. The resolution happens here and
nowhere else.

That division is the whole point, and it is what #20 asks for:

* **A tier moves between sources with a config edit and no code change.** Rungs
  bind to sources *by name*, resolved at call time. Nothing is compiled against
  a host, so re-pointing a rung at a different machine — or at a hosted API — is
  a line in the config file, not a patch.
* **Nothing outside the seam reads a source or a backend.** :class:`Rung`
  carries a name and a model and deliberately nothing else: no URL, no protocol,
  no source name. A caller cannot accidentally depend on where work ran, because
  the type it holds does not say. Only :meth:`SourceMap.bind` produces an
  ``Endpoint``, and only a runner should be calling it.
* **Backend support is a protocol question, not a per-vendor integration.**
  There are exactly two wire protocols, :class:`Protocol`. ``openai`` covers
  vLLM, llama-server, LM Studio, TGI and the hosted providers; adding a backend
  that speaks one of them is a config entry, not code.
* **An unusable source degrades the ladder rather than raising.** A rung whose
  source cannot serve it is dropped from :attr:`SourceMap.rungs` and recorded in
  :attr:`SourceMap.skipped` with a reason in words. A pool with nothing usable
  is an empty ladder that says why, not an exception — the caller decides what
  an empty ladder means, because for a keyless install it may be expected.

**What is deliberately not here.** A tier naming a source that was never
declared is a typo, and E1's loader already refuses it at load time; that is the
right place for it, and this module does not re-litigate it. Live reachability —
is the endpoint actually answering — is #22's, and it enters through
:class:`SourceProbe`: a caller passes something that can say which sources are
down, and its answers become ordinary :class:`Skipped` entries. The narrowness of
that interface is the point. This module still knows nothing about HTTP,
timeouts, caching or retries; it knows only that a source may turn out to be
unusable for a reason it did not compute itself. Capacity is *carried* here
(:attr:`Endpoint.max_parallel`) and enforced in :mod:`mcgyvr.capacity` (#23),
which keys its semaphores by the source name this module resolves to and holds
one for the length of a single dispatch — so a task escalating across sources
accounts correctly without this module learning what a thread is. So the
degradation this module performs is structural only: a source
whose credential is named but absent from the environment cannot serve anything,
and that is knowable without touching the network.

**On credentials.** An ``Endpoint`` carries the environment variable's *name*,
never its value. The value is read at dispatch through :meth:`Endpoint.credential`
so that a secret never sits in a dataclass, never lands in a repr, and never
reaches a log through one. Presence is checked when the map is built — that is
what lets an unusable rung be skipped early — and the value is resolved later,
which means a variable exported mid-run is picked up and one unset mid-run fails
loudly at the point of use. That gap is deliberate: the alternative is holding
the secret for the lifetime of the process.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol as TypingProtocol

from mcgyvr.config import Config, Source

_ROLES = ("orchestrator", "verifier")


class SourceProbe(TypingProtocol):
    """Anything that can say which sources cannot currently serve, and why.

    The whole of #22's surface as this module sees it. It is a structural type
    rather than an import so that resolving a ladder never drags in a network
    stack: :class:`~mcgyvr.availability.Availability` satisfies it, and so does a
    dict-backed stub in a test, and neither is named here.

    Implementations must not raise. A source that cannot be probed is a source
    that is down, and it is reported as such with a reason — the same rule that
    keeps :func:`source_map` from raising on a missing credential.
    """

    def unavailable(self, endpoints: Sequence[Endpoint]) -> Mapping[str, str]:
        """Source name → why it cannot serve, holding only the ones that cannot."""
        ...


class PoolError(Exception):
    """A dispatch could not be resolved to somewhere to run."""


class UnknownRungError(PoolError):
    """A rung was asked for by a name the ladder does not offer."""


class SourceUnavailableError(PoolError):
    """A rung's source exists but cannot currently serve it."""


class Protocol(StrEnum):
    """A wire protocol, which is the only thing a runner needs to know.

    ``OPENAI`` is the OpenAI-compatible chat-completions shape, which vLLM,
    llama-server, LM Studio, TGI and the hosted providers all speak. Supporting
    a new backend is therefore a config entry naming one of these, not a new
    integration — which is why this enum has two members and is expected to keep
    having two.
    """

    OLLAMA = "ollama"
    OPENAI = "openai"


@dataclass(frozen=True)
class Endpoint:
    """Everything needed to dispatch, and nothing about who asked. Below the seam.

    ``max_parallel`` is the source's declared capacity, carried so #23 can bound
    concurrency at this seam; this module does not enforce it. ``source`` is the
    declared source name, kept for capacity accounting and telemetry — both of
    which live below the seam.

    ``credential_env`` is the *name* of the variable holding the key, never the
    key. Use :meth:`credential` to resolve it at the moment of dispatch.
    """

    source: str
    base_url: str
    protocol: Protocol
    max_parallel: int
    credential_env: str | None

    @property
    def requires_credential(self) -> bool:
        """Whether this endpoint expects a key at all — local ones do not."""
        return self.credential_env is not None

    def credential(self) -> str | None:
        """The key for this endpoint, read from the environment at call time.

        ``None`` for a keyless endpoint, which is the ordinary case for a local
        backend. Raises :class:`SourceUnavailableError` when a key is expected and the
        variable is unset — the map checks presence when it is built, so reaching
        this means the environment changed underneath the run, and saying so is
        better than dispatching an unauthenticated request.
        """
        if self.credential_env is None:
            return None
        value = os.environ.get(self.credential_env)
        if not value:
            raise SourceUnavailableError(
                f"source {self.source!r} needs a credential, but "
                f"${self.credential_env} is not set. Export it in your shell or "
                f"put it in a git-ignored .env; never write the value into the "
                f"config file."
            )
        return value


@dataclass(frozen=True)
class Rung:
    """One usable step of the ladder, as seen from above the seam.

    A name and a model, and by construction nothing else. There is no endpoint,
    protocol or source here, so a caller holding a ``Rung`` cannot come to depend
    on where its work runs — which is the property that lets a rung be re-pointed
    at a different machine without anything above noticing.
    """

    name: str
    model: str


@dataclass(frozen=True)
class Skipped:
    """A rung the pool cannot offer, with the reason stated in words.

    Kept beside the usable rungs rather than discarded, because a ladder that
    quietly got shorter is indistinguishable from one that was always that
    length — and the difference is usually the thing worth knowing.
    """

    name: str
    model: str
    reason: str


@dataclass(frozen=True)
class RoleBinding:
    """A non-ladder role (orchestrator, verifier) resolved to somewhere to run."""

    role: str
    model: str
    endpoint: Endpoint


class SourceMap:
    """The ladder, resolved against the declared sources.

    Built by :func:`source_map`. Holds the usable rungs in declared order —
    cheapest first, since that is how a ladder is written — the rungs that were
    skipped and why, and the single method that crosses the seam.
    """

    def __init__(
        self,
        rungs: tuple[Rung, ...],
        skipped: tuple[Skipped, ...],
        endpoints: dict[str, Endpoint],
        roles: dict[str, RoleBinding],
        role_skips: dict[str, str],
    ) -> None:
        self._rungs = rungs
        self._skipped = skipped
        self._endpoints = endpoints
        self._roles = roles
        self._role_skips = role_skips

    @property
    def rungs(self) -> tuple[Rung, ...]:
        """The usable rungs, cheapest first."""
        return self._rungs

    @property
    def skipped(self) -> tuple[Skipped, ...]:
        """The rungs that could not be offered, each with its reason."""
        return self._skipped

    def __bool__(self) -> bool:
        """True when at least one rung is usable."""
        return bool(self._rungs)

    def __len__(self) -> int:
        return len(self._rungs)

    def get(self, name: str) -> Rung | None:
        """The usable rung of this name, or ``None``."""
        return next((rung for rung in self._rungs if rung.name == name), None)

    def bind(self, name: str) -> Endpoint:
        """Resolve a rung to the endpoint that serves it — the seam crossing.

        This is the only way to obtain an :class:`Endpoint`, and it is meant for
        a runner about to dispatch. Everything above the seam should be working
        with :class:`Rung`, which cannot tell it where anything runs.

        Raises :class:`UnknownRungError` when no rung has this name, and
        :class:`SourceUnavailableError` when the rung exists but was skipped — the two
        are different mistakes and the messages keep them apart.
        """
        endpoint = self._endpoints.get(name)
        if endpoint is not None:
            return endpoint
        skipped = next((s for s in self._skipped if s.name == name), None)
        if skipped is not None:
            raise SourceUnavailableError(
                f"rung {name!r} is not available: {skipped.reason}"
            )
        offered = ", ".join(rung.name for rung in self._rungs) or "none"
        raise UnknownRungError(f"no rung named {name!r}. Offered: {offered}")

    def role(self, role: str) -> RoleBinding | None:
        """The binding for a non-ladder role, or ``None`` when it has no source.

        ``None`` is an ordinary answer, not a failure: a role is "unset until
        something needs it", and a keyless install runs with no verifier at all.
        A role whose source is declared but unusable raises
        :class:`SourceUnavailableError`, because that is a misconfiguration the caller
        asked about rather than a role it declined to use.
        """
        if role not in _ROLES:
            raise UnknownRungError(f"no such role {role!r}. Roles: {', '.join(_ROLES)}")
        binding = self._roles.get(role)
        if binding is not None:
            return binding
        reason = self._role_skips.get(role)
        if reason is not None:
            raise SourceUnavailableError(f"role {role!r} cannot run: {reason}")
        return None

    def role_model(self, role: str) -> str | None:
        """Which model ``role`` runs, or ``None`` when it has no source.

        What a caller *above* the seam may ask about a role, and the reason
        :meth:`role` is not that caller's method. A ``RoleBinding`` carries an
        :class:`Endpoint`, and an endpoint carries ``credential()`` — so a
        presence check written as ``source_map.role(VERIFIER_ROLE) is None``
        put a live credential in the hands of a module that only wanted to know
        whether a verifier existed. It imported neither forbidden name, which is
        how the import guard missed it: the object arrived through an accessor,
        not through an import.

        The two questions above the seam actually asks are "is this role bound"
        and "which model is it" — ``mcgyvr.cli`` prints the second, ``verify``
        asks the first — and both are answered here without anything to dispatch
        with. Raises the same :class:`SourceUnavailableError` as :meth:`role`
        for a role declared but unusable, because a caller that cannot see the
        endpoint still has to be able to tell "no verifier" from "the verifier
        is misconfigured".
        """
        binding = self.role(role)
        return None if binding is None else binding.model


def source_map(config: Config, probe: SourceProbe | None = None) -> SourceMap:
    """Resolve a config's ladder against its sources, degrading where it must.

    Every rung whose source can serve it becomes a :class:`Rung`, in declared
    order. A rung whose source cannot becomes a :class:`Skipped` with the reason.
    Nothing raises: an install with no usable rung at all yields an empty ladder
    that can say why, which the caller is better placed to interpret than this
    module is.

    Without ``probe`` the resolution is **structural** and touches no network: a
    source whose named credential is absent from the environment cannot
    authenticate, and that is knowable here. With one, live reachability is
    folded in afterwards on the same terms — an unreachable source's rungs move
    to :attr:`SourceMap.skipped` carrying the probe's own words, so nothing
    downstream has to distinguish "skipped because unconfigured" from "skipped
    because down" unless it wants to.

    The probe runs **once for the whole map**, over the distinct sources that
    survived the structural pass, which is what makes a dead source cost one
    timeout per run rather than one per rung or one per attempt. Sources already
    ruled out structurally are never probed: there is nothing to learn from
    asking whether a host we have no key for is awake.

    A tier naming an undeclared source cannot reach here; E1's loader rejects
    that at load time, where a typo belongs.
    """
    usable: list[Rung] = []
    skipped: list[Skipped] = []
    endpoints: dict[str, Endpoint] = {}

    for tier in config.ladder.tiers:
        source = config.sources[tier.source]
        reason = _unusable(source)
        if reason is not None:
            skipped.append(Skipped(name=tier.name, model=tier.model, reason=reason))
            continue
        usable.append(Rung(name=tier.name, model=tier.model))
        endpoints[tier.name] = _endpoint(source)

    roles: dict[str, RoleBinding] = {}
    role_skips: dict[str, str] = {}
    for role in _ROLES:
        block = config.get(role) or {}
        bound, model = block.get("source"), block.get("model")
        if bound is None or model is None:
            continue
        source = config.sources[bound]
        reason = _unusable(source)
        if reason is not None:
            role_skips[role] = reason
            continue
        roles[role] = RoleBinding(role=role, model=model, endpoint=_endpoint(source))

    if probe is not None:
        # One endpoint per *source*, not per rung. `endpoints` is keyed by rung
        # name, so a source serving four rungs appears four times, and handing
        # that to a probe would make correct behaviour depend on the probe
        # deduplicating for us. The seam should not ask for work it does not
        # need done.
        asking: dict[str, Endpoint] = {}
        for endpoint in (*endpoints.values(), *(b.endpoint for b in roles.values())):
            asking.setdefault(endpoint.source, endpoint)
        down = probe.unavailable(tuple(asking.values()))
        if down:
            usable, skipped, endpoints = _drop_unreachable(
                config, usable, skipped, endpoints, down
            )
            for role, binding in list(roles.items()):
                reason = down.get(binding.endpoint.source)
                if reason is not None:
                    role_skips[role] = reason
                    del roles[role]

    return SourceMap(
        rungs=tuple(usable),
        skipped=tuple(skipped),
        endpoints=endpoints,
        roles=roles,
        role_skips=role_skips,
    )


def _drop_unreachable(
    config: Config,
    usable: list[Rung],
    skipped: list[Skipped],
    endpoints: dict[str, Endpoint],
    down: Mapping[str, str],
) -> tuple[list[Rung], list[Skipped], dict[str, Endpoint]]:
    """Move the rungs on unreachable sources over to ``skipped``.

    Both lists are rebuilt in declared tier order rather than filtered in place.
    The ladder is written cheapest-first, so a report that reordered it while
    shortening it would be harder to read than one that simply got shorter — and
    that applies to the skipped list too, which would otherwise end up with the
    structurally-skipped rungs first and the unreachable ones bolted on the end,
    in an order matching neither the config nor anything else.
    """
    by_name = {rung.name: rung for rung in usable}
    already = {skip.name: skip for skip in skipped}
    kept: list[Rung] = []
    grew: list[Skipped] = []
    for tier in config.ladder.tiers:
        structural = already.get(tier.name)
        if structural is not None:
            grew.append(structural)
            continue
        rung = by_name.get(tier.name)
        if rung is None:  # not usable and not skipped: cannot happen
            continue
        reason = down.get(endpoints[tier.name].source)
        if reason is None:
            kept.append(rung)
            continue
        grew.append(Skipped(name=rung.name, model=rung.model, reason=reason))
        del endpoints[tier.name]
    return kept, grew, endpoints


# --- small deterministic helpers -------------------------------------------


def _endpoint(source: Source) -> Endpoint:
    """A declared source as the endpoint a runner dispatches against."""
    return Endpoint(
        source=source.name,
        base_url=source.base_url,
        protocol=Protocol(source.api),
        max_parallel=source.max_parallel,
        credential_env=source.api_key_env,
    )


def _unusable(source: Source) -> str | None:
    """Why this source cannot serve anything, or ``None`` when it can.

    Structural only, and knowable without the network: a source that names a
    credential the environment does not hold cannot authenticate, so every rung
    on it is unusable before a request is ever attempted. Whether a reachable
    source is actually *answering* is #22's question, and needs a probe.
    """
    if source.api_key_env and not os.environ.get(source.api_key_env):
        return (
            f"source {source.name!r} needs ${source.api_key_env}, which is not "
            f"set in the environment"
        )
    return None
