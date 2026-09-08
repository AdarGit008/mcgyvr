"""A source that declares its window is emitted at that window, not at the run's.

`mcgyvr emit --ctx-per-slot N` takes one number for the whole fleet, and a
config declares `context_window` per source. On the live ladder those two
disagree by construction: srv1 serves 8192 per slot and srv2's vLLM pair serves
4096, both read back off the running units and written down. The consequence is
that **the fleet cannot be checked in one command** — at 4096 `emit --check`
reports srv1 as drifted, at 8192 it reports srv2, and neither is true.

That is the same defect `--sandbox` and the sleep/wake switch are argued
against elsewhere: a number that reaches a rig from a flag is a number
`Config.digest` cannot see, so two runs can share a digest and serve different
windows. The declaration is the fact; the flag is what a run says when nobody
has written the fact down yet.

So the precedence is: **a declared window wins, a flag fills a gap, and a flag
that contradicts a declaration is refused by name** rather than silently
preferred in either direction. Refused, because both numbers are in hand at one
moment and that is exactly where `Capacity.of` names a width disagreement
instead of correcting it — an operator who typed 4096 at a ladder that serves
8192 has said two things, and which one they meant is not this module's to
guess.
"""

from __future__ import annotations

import pytest

from mcgyvr.config import parse
from mcgyvr.scan import Scan
from mcgyvr.serving import Unit, UnitError, units_for

HF_CACHE = "/home/someone/.cache/huggingface"
SEVEN_B = "Qwen/Qwen2.5-Coder-7B-Instruct-AWQ"
BIG = "Qwen3.6-35B-A3B-UD-IQ3_XXS"


def rig(host: str, *, vram_mib: int, ram_gb: float) -> Scan:
    return Scan.of(
        host=host,
        vram_mib=vram_mib,
        ram_gb=ram_gb,
        disk_free_gb=900.0,
        cores=6,
        threads=6,
        bandwidth_gbps=40.3,
    )


SCANS = {
    "srv1": rig("srv1", vram_mib=6144, ram_gb=48.0),
    "srv2": rig("srv2", vram_mib=12288, ram_gb=45.0),
}


def config_text(*, srv1_window: str = "", srv2_window: str = "") -> str:
    """The live fleet's shape: llama.cpp on srv1, one vLLM unit on srv2."""
    return f"""
version: 1
sources:
  srv1_llamacpp:
    base_url: "http://srv1:8080"
    api: openai
{srv1_window}  srv2_vllm_7b:
    base_url: "http://srv2:8002"
    api: openai
    engine: vllm
{srv2_window}models:
  "{BIG}":
    vram_gb: 3.0
    disk_gb: 12.31
  "{SEVEN_B}":
    vram_gb: 7.12
    disk_gb: 4.93
    hf_cache: "{HF_CACHE}"
ladder:
  tiers:
    - name: local_big
      source: srv1_llamacpp
      model: "{BIG}"
      max_parallel: 2
    - name: local_7b
      source: srv2_vllm_7b
      model: "{SEVEN_B}"
      max_parallel: 8
"""


def units(text: str, *, ctx_per_slot: int | None) -> dict[str, Unit]:
    return {
        unit.host: unit
        for unit in units_for(parse(text), SCANS, specs=(), ctx_per_slot=ctx_per_slot)
    }


def test_two_hosts_two_declared_windows_and_no_flag_at_all() -> None:
    """The live fleet, emitted from its own declarations.

    srv1's `-c` is the window times the slots it was sized for; srv2's vLLM
    unit states the window directly. Neither number came from the command line,
    which is what makes one `emit --check` true of the whole fleet.
    """
    emitted = units(
        config_text(
            srv1_window="    context_window: 8192\n",
            srv2_window="    context_window: 4096\n",
        ),
        ctx_per_slot=None,
    )

    assert emitted["srv1"].args["-c"] == str(8192 * 2)
    assert emitted["srv2"].args["--max-model-len"] == "4096"


def test_a_flag_that_contradicts_a_declaration_is_refused_by_name() -> None:
    """Both numbers are in hand at one moment, so the disagreement is named.

    Preferring the flag would serve a window the config denies; preferring the
    declaration would ignore what the operator typed. The refusal says which
    source disagrees and both figures, so the fix is one edit either way.
    """
    with pytest.raises(UnitError) as raised:
        units(
            config_text(srv1_window="    context_window: 8192\n"),
            ctx_per_slot=4096,
        )
    why = str(raised.value)
    assert "srv1_llamacpp" in why, why
    assert "8192" in why and "4096" in why, why


def test_a_flag_still_sizes_a_source_that_declares_nothing() -> None:
    """The flag is not removed — it is what a run says when the config has not
    been told yet, and a fleet that declares nothing behaves exactly as before."""
    emitted = units(config_text(), ctx_per_slot=4096)

    assert emitted["srv1"].args["-c"] == str(4096 * 2)
    assert emitted["srv2"].args["--max-model-len"] == "4096"


def test_a_declared_window_and_a_matching_flag_agree_silently() -> None:
    """Saying the same thing twice is not a disagreement."""
    emitted = units(
        config_text(
            srv1_window="    context_window: 4096\n",
            srv2_window="    context_window: 4096\n",
        ),
        ctx_per_slot=4096,
    )

    assert emitted["srv1"].args["-c"] == str(4096 * 2)


def test_neither_a_declaration_nor_a_flag_is_still_refused() -> None:
    """The refusal that existed before this precedence survives it, and it must:
    a window nobody stated is a cache priced against a number nobody measured.
    What changes is only *where* the answer may come from, never that there has
    to be one."""
    with pytest.raises(UnitError) as raised:
        units(config_text(), ctx_per_slot=None)
    assert "context window" in str(raised.value).lower()


def test_one_unit_behind_two_sources_that_disagree_is_refused() -> None:
    """Two sources naming one URL and two windows are two claims about one
    process. The unit is the same key — same host, model, engine and port — so
    one of the two windows would silently lose, and the rung pointing at the
    loser would be served a window its contracts were never priced against."""
    text = f"""
version: 1
sources:
  srv1_a:
    base_url: "http://srv1:8080"
    api: openai
    context_window: 8192
  srv1_b:
    base_url: "http://srv1:8080"
    api: openai
    context_window: 4096
models:
  "{BIG}":
    vram_gb: 3.0
    disk_gb: 12.31
  "{SEVEN_B}":
    vram_gb: 7.12
    disk_gb: 4.93
    hf_cache: "{HF_CACHE}"
ladder:
  tiers:
    - name: local_a
      source: srv1_a
      model: "{BIG}"
      max_parallel: 2
    - name: local_b
      source: srv1_b
      model: "{BIG}"
      max_parallel: 2
"""
    with pytest.raises(UnitError) as raised:
        units(text, ctx_per_slot=None)
    why = str(raised.value)
    assert "8192" in why and "4096" in why, why
