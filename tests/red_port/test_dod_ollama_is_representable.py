"""A config can say a source is served by Ollama, and the serving side believes it.

Ollama is asked natively and dispatched to compatibly — deliberately, and
measured: the native path enumerates pulled models, and the OpenAI-compatible
path is the one CAV-01 measured at 84.1% (#164). So ``detect`` writes
``api: openai`` for a detected Ollama daemon (``binds_as_for``), and that is
correct for dispatch.

It is wrong for everything else, because ``api`` is then the *only* thing a
config records about the backend, and two places on the serving side ask ``api``
a question it cannot answer:

- ``mcgyvr emit``'s port-contention refusal exempts Ollama, which swaps models
  behind one endpoint by design. The exemption reads ``source.api == "ollama"``,
  which is never true of a config `init` wrote — so two rungs behind one Ollama
  endpoint are refused as contending for a port they are meant to share.
- ``units_for`` has no ``ollama`` engine to choose (``sources.*.engine`` offers
  none), so it builds a llama-server unit: a compose file binding port 11434,
  which the Ollama daemon already holds, launching a ``.gguf`` under
  ``~/.cache/mcgyvr/weights`` that was never downloaded.

Neither bites the owner's ladder of 2026-09-05, which is vLLM and llama.cpp
throughout. Both bite the first person who runs ``mcgyvr init`` on a machine with
Ollama running, which is the onboarding path.

What must be observably true: a source an Ollama daemon serves is distinguishable
from one llama.cpp serves, by something other than the protocol it is dispatched
on — and the serving side reads that, not ``api``.
"""

from __future__ import annotations

from typing import Any

from tests.red_port.conftest import required

CONFIG = """
version: 1
sources:
  box_ollama:
    base_url: "http://box:11434"
    api: openai
    max_parallel: 1
ladder:
  tiers:
    - name: small
      source: box_ollama
      model: "qwen2.5-coder:3b"
    - name: big
      source: box_ollama
      model: "qwen2.5-coder:7b"
"""


def _config() -> Any:
    from mcgyvr.config import parse

    return parse(CONFIG)


def test_a_source_says_which_daemon_serves_it() -> None:
    """The fact `api` cannot carry.

    Asserted on the resolved source rather than on a spelling, because whether
    it is a new ``engine`` choice, a ``kind``, or something else is the port's
    to choose. That a caller can ask "is this Ollama?" and be told the truth is
    the requirement.
    """
    config = _config()
    source = config.sources["box_ollama"]
    served_by = required(
        "read which daemon serves a source, separately from the protocol work "
        "is dispatched to it on",
        lambda: source.served_by,
    )
    assert served_by == "ollama", (
        f"a source on :11434 written by `mcgyvr init` is served by Ollama and "
        f"dispatched as openai; got served_by={served_by!r}"
    )
    assert source.api == "openai", (
        "and the dispatch protocol must not change — asking natively and "
        "dispatching compatibly is the measured choice (#164)"
    )


def _units() -> Any:
    """The units a ladder on one Ollama endpoint implies — none, when this works.

    ``units_for`` is handed no scans on purpose. An Ollama daemon is already
    running and already holds its weights; a source it serves needs no
    measurement of the card to decide what to launch, because nothing is
    launched. Demanding a scan for such a host is itself the defect.
    """
    import pytest

    from mcgyvr.serving import UnitError, units_for

    try:
        return units_for(_config(), {}, specs=())
    except UnitError as refused:
        pytest.fail(
            "mcgyvr must be able to: emit a ladder whose rungs are served by "
            "an already-running Ollama daemon, without scanning a rig for a "
            f"process it will never launch\n  refused: {refused}",
            pytrace=False,
        )


def test_two_rungs_behind_one_ollama_endpoint_are_not_refused() -> None:
    """The exemption `emit` means to grant and never does.

    One llama-server serves one model, so two units on one port is a refusal.
    Ollama swaps models behind one endpoint, so the same shape is correct.
    """
    ports = [getattr(unit, "port", None) for unit in _units()]
    assert len(ports) == len(set(ports)), (
        f"two units bound the same port: {ports}. An Ollama endpoint serves "
        "both rungs from one process and needs no second unit"
    )


def test_no_compose_unit_is_written_for_a_daemon_that_is_already_running() -> None:
    """The file that would fail on the rig.

    Ollama is a daemon the machine already runs. A compose unit for it launches
    a second server on a held port, pointed at weights nothing downloaded.
    """
    units = _units()
    assert units == (), (
        f"emit wrote {len(units)} unit(s) for an Ollama-served source; the "
        "daemon is already serving them"
    )
