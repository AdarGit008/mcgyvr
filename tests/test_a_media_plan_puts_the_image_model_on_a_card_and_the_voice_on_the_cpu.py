"""A media plan puts the image model on a card and the voice on the CPU.

Plan section 10, P11; owner, Round 2 and Round 10. ``media-gen`` is image and
voice: a quantised image model served by ComfyUI on a card, a voice (Kokoro,
in Kokoro-FastAPI's CPU image) on the CPU so the cards stay free, and Whisper
as the ASR-WER gate's own tool on the machine mcgyvr runs on, listed in the
plan with its role and served on no rig. Media units are prompt-sized
(Round 4): one slot, no context priced.

Promises, from the shipped knowledge on invented machines:

* the image unit is the serving sizer's ComfyUI unit on a card, its card
  figure the bytes of the files its record holds on the card plus the judged
  margin, its RAM the files it holds in RAM; every file it downloads is
  pinned by repository, revision and sha256, and the plan's download total
  is those files;
* the voice is a CPU-only TTS unit with no card, in the default TTS image,
  which carries its model, so it downloads nothing; it sits on the image
  unit's machine when that machine's RAM holds both, else on another;
* Whisper is listed under ``local`` with role ``local-check`` and its board
  score, and no rig serves it;
* a card too small for the image model plans nothing, and says why;
* an opted-in Jev unit is sized first, and the image unit around it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import cli, emit, mediaplan, planner, recommend
from mcgyvr.knowledge import store
from mcgyvr.scan import Disk, Gpu, Machine, Memory, Scan, Vram

RIG = "192.0.2.30"
OTHER = "192.0.2.31"
GIB = 1 << 30


def _scan(
    host: str, free_mib: tuple[int, ...], *, ram_gb: float = 32.0
) -> Scan:
    return Scan(
        machine=Machine(id=f"machine-{host}", host=host, kernel="0.0.0-example"),
        gpus=tuple(
            Gpu(
                index=index,
                name="Example Card V",
                vram=Vram(
                    total_mib=free + 512, used_mib=512, free_mib=free, reserved_mib=0
                ),
            )
            for index, free in enumerate(free_mib)
        ),
        memory=Memory(total_gb=ram_gb + 4.0, available_gb=ram_gb),
        disk=Disk(path=Path("/weights"), free_gb=500.0),
    )


def _plan(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    scans: dict[str, Scan],
    *more: str,
) -> tuple[int, dict[str, Any] | None, str]:
    monkeypatch.setattr(recommend, "_scan_host", lambda host: scans[host])
    argv = ["recommend", "--use-case", "media-gen", "--users", "1", "--offline", *more]
    for rig in scans:
        argv += ["--host", rig]
    code = cli.main(argv)
    out = capsys.readouterr()
    return code, (json.loads(out.out) if code == 0 else None), out.err


def _record(part: str) -> Any:
    (one,) = [r for r in store.shipped() if r.is_media and r.part == part]
    return one


def _units(plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [u for laid in plan["rigs"].values() for u in laid["units"]]


def _part(plan: dict[str, Any], part: str) -> dict[str, Any]:
    (unit,) = [u for u in _units(plan) if u.get("part") == part]
    return unit


def test_the_image_model_is_a_comfyui_unit_on_a_card_sized_from_its_files(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, plan, err = _plan(monkeypatch, capsys, {RIG: _scan(RIG, (11800,))})
    assert code == 0, err
    assert plan is not None
    record = _record("image")
    held = {one.file: int(one.bytes.value) for one in record.files}
    assert record.working_set is not None
    card = sum(held[name] for name in record.working_set.card)
    ram = sum(held[name] for name in record.working_set.ram)

    image = _part(plan, "image")
    assert image["engine"] == "comfyui"
    assert image["role"] == planner.ROLE_ALWAYS_ON
    assert image["cards"] == [0]
    assert image["slots"] == 1
    assert image["ctx_per_slot"] is None
    assert image["context"] == mediaplan.PROMPT_SIZED
    assert image["model"]["id"] == record.model_id
    assert image["fit"]["vram_gib"] == pytest.approx(card / GIB + mediaplan.MARGIN_GIB)
    assert image["fit"]["ram_gib"] == pytest.approx(ram / GIB)
    files = image["download"]["files"]
    assert {f["file"] for f in files} == set(held)
    assert all(len(f["sha256"]) == 64 and len(f["revision"]) == 40 for f in files)
    assert image["download"]["bytes"] == record.total_bytes
    assert plan["downloads"]["total_bytes"] == record.total_bytes
    assert plan["use_case"] == "media-gen"
    assert plan["ladder"] == [image["name"], _part(plan, "tts")["name"]], (
        "a fleet's ladder names at least one unit: the image unit, then the voice"
    )


def test_the_voice_is_a_cpu_only_unit_in_the_default_tts_image_downloading_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, plan, err = _plan(monkeypatch, capsys, {RIG: _scan(RIG, (11800,))})
    assert code == 0, err
    assert plan is not None
    voice = _part(plan, "tts")
    assert voice["engine"] == "tts"
    assert voice["role"] == planner.ROLE_ALWAYS_ON
    assert voice["cpu_only"] is True
    assert voice["cards"] == []
    assert voice["fit"]["vram_gib"] == 0.0
    assert voice["image"] == emit.MEDIA_IMAGES["tts"]
    assert voice["download"]["bytes"] == 0
    assert voice["model"]["id"] == _record("tts").model_id
    image = _part(plan, "image")
    assert voice["port"] != image["port"]


def test_the_voice_moves_to_a_machine_whose_ram_holds_it(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    record = _record("image")
    assert record.working_set is not None
    held = {one.file: int(one.bytes.value) for one in record.files}
    encoders = sum(held[name] for name in record.working_set.ram) / GIB
    scans = {
        RIG: _scan(RIG, (11800,), ram_gb=encoders + 0.1),
        OTHER: _scan(OTHER, (), ram_gb=16.0),
    }
    code, plan, err = _plan(monkeypatch, capsys, scans)
    assert code == 0, err
    assert plan is not None
    assert [u["part"] for u in plan["rigs"][RIG]["units"]] == ["image"]
    assert [u["part"] for u in plan["rigs"][OTHER]["units"]] == ["tts"]


def test_whisper_is_listed_as_the_local_speech_check_and_served_on_no_rig(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, plan, err = _plan(monkeypatch, capsys, {RIG: _scan(RIG, (11800,))})
    assert code == 0, err
    assert plan is not None
    (check,) = plan["local"]
    record = _record("asr")
    assert check["role"] == mediaplan.ROLE_LOCAL_CHECK
    assert check["part"] == "asr"
    assert check["model"]["id"] == record.model_id
    assert check["gate"] == "asr_wer"
    assert [s["board"] for s in check["scores"]] == ["open-asr"]
    assert all(u.get("part") != "asr" for u in _units(plan))
    assert plan["sample"]["checks"] == ["media_valid", "asr_wer"]


def test_a_card_too_small_for_the_image_model_plans_nothing_and_says_why(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, plan, err = _plan(monkeypatch, capsys, {RIG: _scan(RIG, (4000,))})
    assert code != 0
    assert plan is None
    assert _record("image").model_id in err and "GB" in err, err


def test_an_opted_in_jev_unit_is_sized_first_and_the_image_unit_around_it(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, plan, err = _plan(
        monkeypatch, capsys, {RIG: _scan(RIG, (20000,))}, "--jev"
    )
    assert code == 0, err
    assert plan is not None
    units = plan["rigs"][RIG]["units"]
    assert units[0]["jev"] is True
    image = _part(plan, "image")
    assert image["cards"] == units[0]["cards"]
    together = units[0]["fit"]["vram_gib"] + image["fit"]["vram_gib"]
    assert together * 1024 <= 20000
    assert plan["decision"]["by"] == "deterministic"
