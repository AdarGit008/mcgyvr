"""What a config resolves into: the sources work may be dispatched to.

`source_map` reads a `Config` and answers what it can actually use: which
ladder rungs survive the key they name, which are dropped and why, the
`Endpoint` each name is dispatched at, and which unit each role runs on. A
`SourceProbe` may be handed in to drop sources that are not answering, or that
answer while holding weights other than the model their rung names.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Protocol as TypingProtocol

from mcgyvr.config import Config, Unit

_ROLES = ("orchestrator", "verifier", "jev")


class SourceProbe(TypingProtocol):
    """What a caller may ask about endpoints before any work is dispatched.

    `source_map` asks `unavailable`, and asks `not_serving` only when the probe
    has it, so a probe may answer liveness alone.
    """

    def unavailable(self, endpoints: Sequence[Endpoint]) -> Mapping[str, str]:
        """The sources among `endpoints` that are not live, each mapped to why.

        A source the mapping leaves out is taken as live.
        """
        ...

    # `source_map` is the only caller that asks a probe: it is how a caller
    # that has already looked at the machines says which of them to drop.
    # The second question a probe may answer, `not_serving`, is not declared
    # here because answering it is optional. It takes `(endpoint, model)`
    # pairs and returns why each model is not held, keyed by
    # `(source, model)`. It is asked because a source can be live and still
    # hold other weights: llama.cpp answers a request naming weights it is
    # not serving from the weights it is, so such a reply is another
    # model's and nothing in it says so.
    # A probe is asked about ladder rungs and role endpoints, never relief
    # rungs: a lent rung is reached through a hub, not probed here.


class PoolError(Exception):
    """Base class for what goes wrong resolving or using the source map."""


class UnknownRungError(PoolError):
    """A name was asked for that the config lists nowhere, as rung or role."""


class SourceUnavailableError(PoolError):
    """A source the config declares cannot be used: it was skipped, or the
    environment variable holding its key is unset."""


class Protocol(StrEnum):
    """The request shape an endpoint answers.

    `OPENAI` is the OpenAI-compatible one every backend behind a unit serves,
    and the one that states where liveness is read: `GET /v1/models` on the
    endpoint's base URL.
    """

    OPENAI = "openai"


@dataclass(frozen=True)
class Endpoint:
    """One address work is dispatched at, with the limits it is sent within.

    Built from the `Unit` a rung or role names. It is the pool's unit of
    dispatch: its `source` is the unit's name, which is what a probe reports on
    and what a refusal names.
    """

    source: str
    base_url: str
    protocol: Protocol
    max_parallel: int
    credential_env: str | None
    #: NAME of the environment variable holding this endpoint's key. `None`
    #: means no key is sent, which is how a local backend that checks nothing
    #: is asked. The value never lives here: a key that is needed and missing
    #: raises rather than sending an unauthenticated request.
    #: `requires_credential` says whether a key is needed; `credential`
    #: resolves it.
    context_window: int | None = None
    #: Tokens this endpoint serves in one request, as the unit states them,
    #: prompt and reply together; `None` means the unit says nothing. Every
    #: reply is clamped to what this window leaves once the prompt is paid
    #: for, and a `code` contract with neither this nor `output_tokens`
    #: behind it is refused rather than guessed at. It limits the whole
    #: request, where `output_tokens` limits the reply alone.
    output_tokens: int | None = None
    #: Room a reply on this endpoint is given, hidden reasoning included, as
    #: the unit states it: the reply cap every request to it is sent, clamped
    #: to the room the window leaves the prompt. `None` means the unit states
    #: no room, and the cap is then whatever the window leaves.
    #: It is kept apart from `context_window` because one is room one reply is
    #: given and the other is room the whole request is served in, and where
    #: both are stated the smaller one holds.
    output_ceiling: int | None = None
    #: The reply room of the rung this one stands in for, set on relief
    #: rungs alone by `source_map`: a lent rung answers as one of yours
    #: would, so its reply cap is held to this ceiling too.
    request_timeout_s: float | None = None
    #: Seconds one dispatched request to this endpoint may take before the
    #: transport gives up. `None` means nothing is stated here and the
    #: caller's default holds, which differs between a hosted and a local
    #: endpoint. It is kept unresolved rather than filled in, so that an
    #: unstated timeout and a stated one stay different facts and a caller
    #: can tell which one applies.
    engine: str | None = None
    #: The server program behind the address, as the unit declares it;
    #: `None` means llama.cpp. Read where a request or a status poll has to
    #: speak the engine's own API rather than the one path they share.
    relief: bool = False
    #: Whether this endpoint is a rung lent through a hub rather than one
    #: of your own. A relief rung is a step of the ladder only where the
    #: ladder names it.
    served_model: str | None = None
    #: What the host says its unit runs, for people to read; it is not what
    #: is asked for. On a relief rung it is what a reply's own model is
    #: checked against, and a mismatch passes the rung over as full.
    busy_answers: frozenset[tuple[int, str]] | None = None
    #: The (status, code) answers that say this endpoint cannot take a
    #: request now. On a relief rung one of them raises
    #: `ReliefUnavailableError`, which is what makes a full lent rung cost
    #: nothing to pass over; elsewhere an answer is read as any other.
    sampling: str = "request"
    use_case: str | None = None
    #: The setup's use case, which every chat request names in the
    #: `mcgyvr.hubwire.USE_CASE_HEADER` header so a hub can refuse one its pool
    #: does not serve; `None` sends no header.
    scope: str | None = None
    #: Whose rigs may serve this endpoint's requests, the unit's `scope`, which
    #: every chat request names in the `mcgyvr.hubwire.SCOPE_HEADER` header so a
    #: hub serves it from that scope's pool; `None` sends no header.

    @property
    def requires_credential(self) -> bool:
        """Whether a key must be resolved before this endpoint is called."""
        return self.credential_env is not None

    def credential(self) -> str | None:
        """The key read from the environment variable `credential_env` names.

        `None` when the endpoint names no variable, meaning nothing is sent.
        Raises `SourceUnavailableError` when the variable is unset or empty:
        the value is never written into a config file.
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
    """One step of the ladder: the unit's name, and the model sent to it."""

    name: str
    model: str


@dataclass(frozen=True)
class Skipped:
    """A rung the pool will not offer, with the reason it was dropped.

    The reason is either structural, the key the unit names being unset, or
    what a probe said about the source.
    """

    name: str
    model: str
    reason: str


@dataclass(frozen=True)
class RoleBinding:
    """What a role runs on: its unit, the model it asks for, and where to
    dispatch."""

    role: str
    model: str
    endpoint: Endpoint


class SourceMap:
    """A config resolved into what can be dispatched, and what cannot.

    `rungs` are the ladder's usable steps in the ladder's own order, `relief`
    the usable lent rungs, and `skipped` and `relief_skipped` the rest with
    their reasons. `bind` turns a rung name into the `Endpoint` to call and
    `role` a role into its `RoleBinding`. `source_map` builds it.
    """

    def __init__(
        self,
        rungs: tuple[Rung, ...],
        skipped: tuple[Skipped, ...],
        endpoints: dict[str, Endpoint],
        roles: dict[str, RoleBinding],
        role_skips: dict[str, str],
        relief: tuple[Rung, ...] = (),
        relief_skipped: tuple[Skipped, ...] = (),
    ) -> None:
        self._rungs = rungs
        self._skipped = skipped
        self._endpoints = endpoints
        self._roles = roles
        self._role_skips = role_skips
        self._relief = relief
        self._relief_skipped = relief_skipped

    @property
    def rungs(self) -> tuple[Rung, ...]:
        """The usable ladder rungs, in the order the ladder lists them."""
        return self._rungs

    @property
    def skipped(self) -> tuple[Skipped, ...]:
        """The ladder rungs that cannot be dispatched, each with its reason."""
        return self._skipped

    @property
    def relief(self) -> tuple[Rung, ...]:
        """The usable relief rungs: lent units, never a step of the ladder."""
        return self._relief

    @property
    def relief_skipped(self) -> tuple[Skipped, ...]:
        """The relief rungs that cannot be dispatched, each with its reason."""
        return self._relief_skipped

    def __bool__(self) -> bool:
        """Whether any ladder rung is usable. Relief rungs alone are not."""
        return bool(self._rungs)

    def __len__(self) -> int:
        return len(self._rungs)

    def get(self, name: str) -> Rung | None:
        """The rung of that name on the ladder, else among the relief, or `None`."""
        return next(
            (rung for rung in (*self._rungs, *self._relief) if rung.name == name),
            None,
        )

    def bind(self, name: str) -> Endpoint:
        """The endpoint to dispatch at for the rung of that name.

        Raises `SourceUnavailableError` when the rung was skipped, carrying the
        reason, and `UnknownRungError` when no rung or relief rung is named so.
        """
        endpoint = self._endpoints.get(name)
        if endpoint is not None:
            return endpoint
        skipped = next(
            (s for s in (*self._skipped, *self._relief_skipped) if s.name == name),
            None,
        )
        if skipped is not None:
            raise SourceUnavailableError(
                f"rung {name!r} is not available: {skipped.reason}"
            )
        offered = ", ".join(rung.name for rung in self._rungs) or "none"
        raise UnknownRungError(f"no rung named {name!r}. Offered: {offered}")

    def role(self, role: str) -> RoleBinding | None:
        """The binding for a role, or `None` when the config binds none.

        The role must be one of `orchestrator`, `verifier` and `jev`. One bound
        to a unit that was skipped raises `SourceUnavailableError` rather than
        reading as unbound.
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
        """The model string of a role, or `None` when it is not bound.

        Raises what `role` raises.
        """
        binding = self.role(role)
        return None if binding is None else binding.model


def source_map(config: Config, probe: SourceProbe | None = None) -> SourceMap:
    """Resolve `config` into the `SourceMap` work is dispatched from.

    Each ladder unit is checked for the key it names and, when it passes, given
    an endpoint; relief rungs are taken the same way and kept off the ladder.
    Each role bound in the config becomes a `RoleBinding`, its model defaulting
    to its unit's own. With a `probe`, sources it reports unreachable are
    dropped, and so are rungs whose source is up but not holding their model.
    A relief rung ends up with `output_ceiling` set to the reply room of the
    cheapest usable rung, so a lent rung is held to what it stands in for.
    """
    usable: list[Rung] = []
    skipped: list[Skipped] = []
    endpoints: dict[str, Endpoint] = {}

    def _served(unit: Unit, name: str) -> int:
        # Requests this unit is asked to take at once: the width it states,
        # or one. The exception is a deployment that runs its orchestrator
        # locally: the unit bound to `orchestrator.unit` needs no credential
        # and takes one request per user, so where it states no width its
        # slot count is the configured `users` rather than one.
        if (
            config.provisions_local_orchestrator
            and name == config.get("orchestrator.unit")
            and not unit.requires_credential
        ):
            return unit.width or int(config.get("users", 1))
        return unit.width or 1

    for name in config.ladder.names:
        unit = config.units[name]
        reason = _unusable(unit)
        if reason is not None:
            skipped.append(Skipped(name=name, model=unit.model, reason=reason))
            continue
        usable.append(Rung(name=name, model=unit.model))
        endpoints[name] = _endpoint(
            unit, width=_served(unit, name), use_case=config.use_case
        )

    relief: list[Rung] = []
    relief_skipped: list[Skipped] = []
    for name, unit in config.relief.items():
        reason = _unusable(unit)
        if reason is not None:
            relief_skipped.append(Skipped(name=name, model=unit.model, reason=reason))
            continue
        relief.append(Rung(name=name, model=unit.model))
        endpoints[name] = _endpoint(unit, use_case=config.use_case)

    roles: dict[str, RoleBinding] = {}
    role_skips: dict[str, str] = {}
    for role in _ROLES:
        block = config.get(role) or {}
        bound, model = block.get("unit"), block.get("model")
        # A role switched off (`jev.enabled: false`) is read as one never bound.
        if bound is None or (role == "jev" and block.get("enabled") is False):
            continue
        unit = config.units[bound]
        if model is None:
            # A role may name a unit and no model: it then asks for the model
            # that unit names, so the string lives in one place and the role
            # follows the unit when the unit's own model is rewritten.
            # A model stated on the role wins instead: that is what a unit
            # serving more than one model is pointed at, and the string is
            # sent as stated.
            model = unit.model
        reason = _unusable(unit)
        if reason is not None:
            role_skips[role] = reason
            continue
        roles[role] = RoleBinding(
            role=role,
            model=model,
            endpoint=_endpoint(
                unit, width=_served(unit, bound), use_case=config.use_case
            ),
        )

    if probe is not None:
        # One endpoint per source, so each source is asked about once however
        # many rungs and roles sit on it. Relief rungs are left out, being
        # another person's machine reached through a hub.
        asking: dict[str, Endpoint] = {}
        for endpoint in (*endpoints.values(), *(b.endpoint for b in roles.values())):
            if endpoint.relief:
                continue
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
        # Then the question a probe need not answer: a source can be up and
        # still not hold the model its rung names. llama.cpp answers a
        # request naming weights it is not serving from the weights it is,
        # so such a reply is another model's with nothing saying so.
        # It is looked up with `getattr` rather than declared on the protocol,
        # so a probe answering only `unavailable` is still a `SourceProbe`;
        # one answering this too has its verdict applied to the ladder rungs
        # still standing.
        asks_models = getattr(probe, "not_serving", None)
        if asks_models is not None and usable:
            bound = tuple(
                (endpoints[rung.name], rung.model)
                for rung in usable
                if rung.name in endpoints
            )
            elsewhere = asks_models(bound)
            if elsewhere:
                usable, skipped, endpoints = _drop_wrong_model(
                    config, usable, skipped, endpoints, elsewhere
                )

    # A lent rung answers as one of yours would, so it is held to a ceiling
    # of yours: `output_ceiling` is the reply room of the cheapest usable
    # rung, and a reply on it is capped there as it would be on the rung the
    # lent one stands in for.
    if usable and relief:
        local = endpoints[usable[0].name].output_tokens
        for rung in relief:
            endpoints[rung.name] = replace(endpoints[rung.name], output_ceiling=local)

    return SourceMap(
        rungs=tuple(usable),
        skipped=tuple(skipped),
        endpoints=endpoints,
        roles=roles,
        role_skips=role_skips,
        relief=tuple(relief),
        relief_skipped=tuple(relief_skipped),
    )


def _drop_unreachable(
    config: Config,
    usable: list[Rung],
    skipped: list[Skipped],
    endpoints: dict[str, Endpoint],
    down: Mapping[str, str],
) -> tuple[list[Rung], list[Skipped], dict[str, Endpoint]]:
    """Drop the usable rungs whose source `down` reports unreachable.

    The ladder's order is walked, so the kept rungs stay in it. A rung already
    skipped keeps the reason it was skipped for; a rung dropped here is recorded
    with the probe's reason and loses its endpoint.
    """
    by_name = {rung.name: rung for rung in usable}
    already = {skip.name: skip for skip in skipped}
    kept: list[Rung] = []
    grew: list[Skipped] = []
    for name in config.ladder.names:
        structural = already.get(name)
        if structural is not None:
            grew.append(structural)
            continue
        rung = by_name.get(name)
        if rung is None:  # not one of this walk's usable rungs
            continue
        reason = down.get(endpoints[name].source)
        if reason is None:
            kept.append(rung)
            continue
        grew.append(Skipped(name=rung.name, model=rung.model, reason=reason))
        del endpoints[name]
    return kept, grew, endpoints


def _drop_wrong_model(
    config: Config,
    usable: list[Rung],
    skipped: list[Skipped],
    endpoints: dict[str, Endpoint],
    elsewhere: Mapping[tuple[str, str], str],
) -> tuple[list[Rung], list[Skipped], dict[str, Endpoint]]:
    """Drop the usable rungs whose source is up but not serving their model.

    `elsewhere` is keyed by `(source, model)`, so one endpoint serving several
    rungs loses only the rungs asking for the model it lacks. The ladder's order
    is walked, an earlier skip keeps its reason, and a rung dropped here is
    recorded with the probe's reason and loses its endpoint.
    """
    by_name = {rung.name: rung for rung in usable}
    already = {skip.name: skip for skip in skipped}
    kept: list[Rung] = []
    grew: list[Skipped] = []
    for name in config.ladder.names:
        structural = already.get(name)
        if structural is not None:
            grew.append(structural)
            continue
        rung = by_name.get(name)
        if rung is None:  # not one of this walk's usable rungs
            continue
        endpoint = endpoints.get(name)
        reason = (
            elsewhere.get((endpoint.source, rung.model))
            if endpoint is not None
            else None
        )
        if reason is None:
            kept.append(rung)
            continue
        grew.append(Skipped(name=rung.name, model=rung.model, reason=reason))
        del endpoints[name]
    return kept, grew, endpoints


# Turning a unit into an endpoint, and saying why a unit cannot be used.


def _endpoint(
    unit: Unit, *, width: int | None = None, use_case: str | None = None
) -> Endpoint:
    """Build the endpoint for `unit`, with the limits it is dispatched within.

    `width` replaces the slot count taken from the unit's own `width`, for a
    caller that knows how many requests the unit has to take at once.
    `use_case` is the setup's and the scope the unit's, which every request to
    it names.
    """
    return Endpoint(
        source=unit.name,
        base_url=unit.address,
        protocol=Protocol.OPENAI,
        max_parallel=(unit.width or 1) if width is None else width,
        credential_env=unit.api_key_env,
        context_window=unit.window,
        output_tokens=unit.output_tokens,
        request_timeout_s=unit.request_timeout_s,
        engine=unit.engine,
        relief=unit.relief,
        served_model=unit.served_model,
        busy_answers=(
            None if unit.busy_answers is None else frozenset(unit.busy_answers)
        ),
        sampling=unit.sampling,
        use_case=use_case,
        scope=unit.scope,
    )


def _unusable(unit: Unit) -> str | None:
    """Why `unit` cannot be used, or `None` when it can be.

    One thing stops a unit here: it names a key variable that is unset in the
    environment. A unit naming no variable is usable as it stands.
    """
    if unit.api_key_env and not os.environ.get(unit.api_key_env):
        return (
            f"unit {unit.name!r} needs ${unit.api_key_env}, which is not "
            f"set in the environment"
        )
    return None
