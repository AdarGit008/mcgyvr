""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Protocol as TypingProtocol

from mcgyvr.config import Config, Unit

_ROLES = ("orchestrator", "verifier", "jev")


class SourceProbe(TypingProtocol):
    ""

    def unavailable(self, endpoints: Sequence[Endpoint]) -> Mapping[str, str]:
        ""
        ...

    #el
    #is
    #
    #
    #
    #
    #
    #
    #
    #
    #


class PoolError(Exception):
    ""


class UnknownRungError(PoolError):
    ""


class SourceUnavailableError(PoolError):
    ""


class Protocol(StrEnum):
    ""

    OPENAI = "openai"


@dataclass(frozen=True)
class Endpoint:
    ""

    source: str
    base_url: str
    protocol: Protocol
    max_parallel: int
    credential_env: str | None
    #
    #
    #
    #
    #ee
    #
    context_window: int | None = None
    #
    #
    #s,
    #
    #
    #
    #
    output_tokens: int | None = None
    #
    #
    #
    #
    #
    #
    #
    #
    output_ceiling: int | None = None
    #
    #
    #
    request_timeout_s: float | None = None
    #€”
    #
    #
    #
    #
    #
    engine: str | None = None
    #
    #
    #
    relief: bool = False
    #
    #
    served_model: str | None = None
    #
    #
    #
    busy_answers: frozenset[tuple[int, str]] | None = None
    #
    #
    #
    #
    sampling: str = "request"

    @property
    def requires_credential(self) -> bool:
        ""
        return self.credential_env is not None

    def credential(self) -> str | None:
        ""
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
    ""

    name: str
    model: str


@dataclass(frozen=True)
class Skipped:
    ""

    name: str
    model: str
    reason: str


@dataclass(frozen=True)
class RoleBinding:
    ""

    role: str
    model: str
    endpoint: Endpoint


class SourceMap:
    ""

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
        ""
        return self._rungs

    @property
    def skipped(self) -> tuple[Skipped, ...]:
        ""
        return self._skipped

    @property
    def relief(self) -> tuple[Rung, ...]:
        ""
        return self._relief

    @property
    def relief_skipped(self) -> tuple[Skipped, ...]:
        ""
        return self._relief_skipped

    def __bool__(self) -> bool:
        ""
        return bool(self._rungs)

    def __len__(self) -> int:
        return len(self._rungs)

    def get(self, name: str) -> Rung | None:
        ""
        return next(
            (rung for rung in (*self._rungs, *self._relief) if rung.name == name),
            None,
        )

    def bind(self, name: str) -> Endpoint:
        ""
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
        ""
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
        ""
        binding = self.role(role)
        return None if binding is None else binding.model


def source_map(config: Config, probe: SourceProbe | None = None) -> SourceMap:
    ""
    usable: list[Rung] = []
    skipped: list[Skipped] = []
    endpoints: dict[str, Endpoint] = {}

    def _served(unit: Unit, name: str) -> int:
        #
        #
        #
        #e.
        #
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
        endpoints[name] = _endpoint(unit, width=_served(unit, name))

    relief: list[Rung] = []
    relief_skipped: list[Skipped] = []
    for name, unit in config.relief.items():
        reason = _unusable(unit)
        if reason is not None:
            relief_skipped.append(Skipped(name=name, model=unit.model, reason=reason))
            continue
        relief.append(Rung(name=name, model=unit.model))
        endpoints[name] = _endpoint(unit)

    roles: dict[str, RoleBinding] = {}
    role_skips: dict[str, str] = {}
    for role in _ROLES:
        block = config.get(role) or {}
        bound, model = block.get("unit"), block.get("model")
        if bound is None:
            continue
        unit = config.units[bound]
        if model is None:
            #
            #
            #
            #
            #
            #
            model = unit.model
        reason = _unusable(unit)
        if reason is not None:
            role_skips[role] = reason
            continue
        roles[role] = RoleBinding(
            role=role,
            model=model,
            endpoint=_endpoint(unit, width=_served(unit, bound)),
        )

    if probe is not None:
        #
        #
        #
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
        #
        #
        #
        #€”
        #
        #
        #
        #
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

    #
    #
    #
    #
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
    ""
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
        if rung is None:  #
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
    ""
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
        if rung is None:  #
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


#


def _endpoint(unit: Unit, *, width: int | None = None) -> Endpoint:
    ""
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
    )


def _unusable(unit: Unit) -> str | None:
    ""
    if unit.api_key_env and not os.environ.get(unit.api_key_env):
        return (
            f"unit {unit.name!r} needs ${unit.api_key_env}, which is not "
            f"set in the environment"
        )
    return None
