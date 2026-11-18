"""The endpoint, API key and model a custom provider points at.

At the end of a successful `mcgyvr setup` (and at the end of a `serve up`), the
endpoint, key and model of the unit the ladder serves first are written to
``provider.env``, so the user can ``source`` it into a custom provider (Pi,
Hermes, VLM, …), and printed. The key is the one mcgyvr already keeps for the
unit (:mod:`mcgyvr.unitkey`), read the way `mcgyvr fleet key <unit>` reads it;
nothing here mints a second key. The key itself is never printed: the screen
names the `mcgyvr fleet key` command that prints it (:func:`key_command`), and
the file it is exported in.
"""

from __future__ import annotations

import os
import shlex
from dataclasses import dataclass
from pathlib import Path

from mcgyvr import atomic, unitkey
from mcgyvr.config import EXPOSE_LAN, Config, Unit, named_config_path

#: The environment variables a custom provider reads, written by :func:`write`.
ENDPOINT_ENV = "MCGYVR_ENDPOINT"
API_KEY_ENV = "MCGYVR_API_KEY"
MODEL_ENV = "MCGYVR_MODEL"

#: The file :func:`write` writes, meant to be `source`d into a provider.
PROVIDER_FILENAME = "provider.env"


class HandoffError(Exception):
    "A ``provider.env`` that cannot be written privately, named with what to do."


@dataclass(frozen=True)
class Provider:
    """One unit's handoff: where it answers, its key (None when it asks none),
    the model it serves, and the unit's name as `fleet.yaml` writes it (None
    when the caller does not know it)."""

    endpoint: str
    api_key: str | None
    model: str
    unit: str | None = None


def endpoint_of(address: str) -> str:
    """The OpenAI-shaped endpoint of a unit address: ``…/v1``, added once.

    A unit's `address` is a base URL with scheme and port; llama-server and
    vLLM both answer the OpenAI wire under the `/v1` path. An address that
    already names `/v1` (as setup's staged detection writes it) is kept whole.
    """
    base = address.rstrip("/")
    if base.endswith("/v1"):
        return base
    return f"{base}/v1"


def for_unit(name: str, unit: Unit) -> Provider:
    """The handoff of one declared unit: its endpoint, its key and its model."""
    key: str | None = None
    try:
        key = unitkey.for_address(unit.address)
    except unitkey.UnitKeyError:
        # A key file that cannot be trusted is named nowhere here: the unit
        # still answers, and a provider that needs a key is refused later.
        key = None
    return Provider(
        endpoint=endpoint_of(unit.address),
        api_key=key,
        model=unit.model,
        unit=name,
    )


def from_config(config: Config) -> Provider | None:
    """The handoff of the first unit the ladder serves, or None when it has none.

    The first ladder rung is the unit a custom provider points at: the one the
    use case serves first. A setup with no ladder (nothing to serve) has no
    handoff.
    """
    if not config.ladder.names:
        return None
    name = config.ladder.names[0]
    unit = config.units.get(name)
    if unit is None or not unit.address:
        return None
    return for_unit(name, unit)


def _line(variable: str, value: str) -> str:
    # Quoted for the shell that sources the file: the model can be a server's
    # `/v1/models` answer. A value that is already shell-safe is left as it is,
    # and an empty one stays bare (`shlex.quote` would write `''`).
    return f"export {variable}={shlex.quote(value) if value else ''}"


def render(provider: Provider) -> str:
    """The three `export` lines a custom provider sources, one per line."""
    return (
        "\n".join(
            (
                _line(ENDPOINT_ENV, provider.endpoint),
                _line(API_KEY_ENV, provider.api_key or ""),
                _line(MODEL_ENV, provider.model),
            )
        )
        + "\n"
    )


def write(directory: Path, provider: Provider) -> Path:
    """Write ``provider.env`` under `directory` and answer its path.

    The file holds the unit's key, so it is kept the way the key's own file is
    (:func:`mcgyvr.atomic.write_private`): at 0600, in one step, and a link in
    its place raises HandoffError rather than being written through.
    """
    path = directory / PROVIDER_FILENAME
    try:
        return atomic.write_private(path, render(provider))
    except atomic.PrivateFileError as exc:
        raise HandoffError(str(exc)) from exc


def _passed_as(setup: Path) -> Path | None:
    """The `--config` that names `setup` to `mcgyvr fleet key`, or None.

    None when the bare command reads `setup`: no `MCGYVR_CONFIG` is set and
    `setup` is the live fleet's folder. A setup `MCGYVR_CONFIG` names is still
    passed, as an absolute path, so the command reads it from another shell or
    folder too.
    """
    from mcgyvr.fleet import roots

    if named_config_path() is None:
        try:
            live = roots.live_fleet_dir()
        except roots.LiveFleetError:
            # A live pointer that cannot be read names no folder the bare
            # command reads, so the setup is passed.
            live = None
        if live is not None and os.path.realpath(live) == os.path.realpath(setup):
            return None
    return setup.absolute()


def key_command(
    config: Config, unit: str | None, key: str | None, setup: Path
) -> str | None:
    """The `mcgyvr fleet key` command that prints `key`, or None when none does.

    `config` is the setup loaded from `setup`, and `unit` the name it gives the
    unit. The command is answered only when `mcgyvr fleet key` would print that
    very key: the unit is one of the fleet's own (not a hitchhike or crew
    unit), it is `expose: lan`, and its key file holds `key`. A unit that asks
    no key, and one that command refuses, have no command.
    """
    from mcgyvr.serving import exposure

    if key is None or unit is None:
        return None
    declared = config.units.get(unit)
    if declared is None or declared.hitchhike or declared.crew:
        return None
    exposed = exposure(
        declared.expose, address=declared.address, launcher=declared.launcher
    )
    if exposed != EXPOSE_LAN:
        return None
    try:
        if unitkey.for_address(declared.address) != key:
            return None
    except unitkey.UnitKeyError:
        return None
    argv = ["mcgyvr", "fleet", "key", unit]
    passed = _passed_as(setup)
    if passed is not None:
        argv += ["--config", str(passed)]
    return shlex.join(argv)


def _key_shown(key: str | None, command: str | None) -> str:
    if key is None:
        return "(none — the unit asks for no key)"
    if command is None:
        return "(not printed here)"
    return f"`{command}` prints it"


def print_provider(
    provider: Provider, exported: Path, command: str | None = None
) -> None:
    """Print the handoff on stdout, aligned the way a provider reads it.

    The three lines line up their values in one column, and the api-key line
    also names the file the three are exported in. The key is never printed:
    the api-key line names `command`, the one that prints it
    (:func:`key_command`), or says it is not printed when no command would.
    """
    note = f"        (also exported in {exported})"
    print(f"endpoint: {provider.endpoint}")
    print(f"api-key:  {_key_shown(provider.api_key, command)}{note}")
    print(f"model:    {provider.model}")
