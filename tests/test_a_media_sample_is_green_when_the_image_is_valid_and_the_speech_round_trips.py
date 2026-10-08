"""A media sample is green when the image is valid and the speech round-trips.

Plan section 8.2, P11; owner, Round 10. The media-gen sample runs one image
contract and one spoken line: green when ``media_valid`` passes on the image
and the spoken line, transcribed by Whisper, stays within the ASR-WER gate's
threshold (``asr_wer``). Media units answer no token-speed probe, so they are
held to their restarts and their card reads only, and the lock takes their
evidence without a warm decode or a prefill figure.

No rig is reached: the rig is invented and its reads are canned.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.fleet.promote import LOCK_DIR
from tests import sample_fleet as fx

FLEET = "media-gen-rig-a"
IMAGE = "rig-a-flux-8081"
VOICE = "rig-a-kokoro-8082"
IMAGE_CONTAINER = "mcgyvr-rig-a-flux-8081"
VOICE_CONTAINER = "mcgyvr-rig-a-kokoro-8082"
IMAGE_ID = "c0ffee0000a1"
VOICE_ID = "c0ffee0000a2"


def _fleet() -> dict[str, Any]:
    image = fx.unit(IMAGE, "unt-" + "c" * 64, 8081, IMAGE_CONTAINER, room_mib=9000)
    image.update(engine="comfyui", model="black-forest-labs/FLUX.1-schnell")
    voice = fx.unit(VOICE, "unt-" + "d" * 64, 8082, VOICE_CONTAINER, room_mib=0)
    voice.update(engine="tts", model="hexgrad/Kokoro-82M", launch={"cpu_only": True})
    for one in (image, voice):
        for key in ("width", "window", "output_tokens", "request_timeout_s"):
            del one[key]
    return {
        "profile": "dev",
        "units": {IMAGE: image, VOICE: voice},
        "rigs": {fx.RIG: {"rig_id": fx.rig_id()}},
        "fleets": {
            FLEET: {
                "layout": {fx.RIG: [[IMAGE, "awake"], [VOICE, "awake"]]},
                "next": [],
            }
        },
    }


def _policy(tmp_path: Path) -> dict[str, Any]:
    doc = fx.policy_doc(tmp_path, "media-gen")
    doc["ladder"] = [IMAGE, VOICE]
    return doc


def _reader(*, restarts: str = "0") -> str:
    lines = "".join(f"{key}={value}\n" for key, value in fx.SNAPSHOT.items())
    lines += f"container={IMAGE_CONTAINER},{IMAGE_ID},mcgyvr,{restarts}\n"
    lines += f"gpu_app=4243,8100,{IMAGE_ID},python3\n"
    lines += f"container={VOICE_CONTAINER},{VOICE_ID},mcgyvr,0\n"
    return lines


def _read(setup: Path, run_id: str, text: str) -> Any:
    from mcgyvr.fleet import read as door_read

    return door_read.record(
        fx.RIG,
        text,
        run_id=run_id,
        profile="live",
        probe=(),
        load=None,
        fleet_name=FLEET,
        setup=setup,
    )


def _setup(tmp_path: Path, **reader: Any) -> Path:
    setup = fx.staged(tmp_path, fleet=_fleet(), policy=_policy(tmp_path))
    fx.rig_file()
    for run_id in fx.READS:
        _read(setup, run_id, _reader(**reader))
    return setup


def _sample(setup: Path, *outcomes: tuple[str, str, bool, str]) -> Any:
    from mcgyvr.fleet import sample

    if not outcomes:
        outcomes = (
            ("media_valid", IMAGE, True, "a PNG of the asked size"),
            ("asr_wer", VOICE, True, "word error rate 0.04"),
        )
    return sample.Sample(
        setup=setup,
        fleet=FLEET,
        reads=fx.READS,
        outcomes=tuple(
            sample.Outcome(check, unit=unit, passed=passed, why=why)
            for check, unit, passed, why in outcomes
        ),
    )


@pytest.fixture
def no_lab(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "no-lab-root"
    root.mkdir()
    monkeypatch.setenv("MCGYVR_RUN_ROOT", str(root))
    return root


def test_a_valid_image_and_a_round_tripped_line_are_green_with_no_speed_probe(
    tmp_path: Path, no_lab: Path
) -> None:
    from mcgyvr.fleet import sample

    verdict = sample.judge(_sample(_setup(tmp_path)))

    assert verdict.green, verdict.why
    assert verdict.evidence is not None
    (comb,) = verdict.evidence["combinations"]
    assert comb["warm_decode_tok_s"] == {} and comb["prefill_tok_s"] == {}
    assert comb["restarts"] == {IMAGE: 0, VOICE: 0}
    assert comb["card_peak_mib"][IMAGE] == 8100


def test_the_lock_takes_a_media_fleets_evidence_and_it_is_stamped(
    tmp_path: Path, no_lab: Path
) -> None:
    from mcgyvr.fleet import stamp

    done = stamp.stamp(_sample(_setup(tmp_path)), run_id="sample-media")

    assert done.green, done.why
    assert (done.folder / LOCK_DIR / f"{FLEET}.json").is_file()
    evidence = json.loads((done.folder / "evidence.json").read_text("utf-8"))
    assert evidence["combinations"][0]["passed"] is True


@pytest.mark.parametrize(
    ("outcomes", "words"),
    [
        (
            (("media_valid", IMAGE, True, ""),),
            ("asr_wer", "did not run"),
        ),
        (
            (("asr_wer", VOICE, True, ""),),
            ("media_valid", "did not run"),
        ),
        (
            (
                ("media_valid", IMAGE, True, ""),
                ("asr_wer", VOICE, False, "word error rate 0.41 over 0.2"),
            ),
            ("asr_wer", VOICE, "0.41"),
        ),
        (
            (
                ("media_valid", IMAGE, False, "the file is not a PNG"),
                ("asr_wer", VOICE, True, ""),
            ),
            ("media_valid", IMAGE, "not a PNG"),
        ),
    ],
)
def test_an_image_or_a_line_that_did_not_pass_is_red_and_says_which(
    tmp_path: Path,
    no_lab: Path,
    outcomes: tuple[tuple[str, str, bool, str], ...],
    words: tuple[str, ...],
) -> None:
    from mcgyvr.fleet import sample

    verdict = sample.judge(_sample(_setup(tmp_path), *outcomes))

    assert not verdict.green
    said = "\n".join(verdict.why)
    for word in words:
        assert word in said, said
    assert "P11" not in said


def test_a_media_unit_is_still_held_to_its_restarts(
    tmp_path: Path, no_lab: Path
) -> None:
    from mcgyvr.fleet import sample

    restarted = sample.judge(_sample(_setup(tmp_path, restarts="2")))

    assert not restarted.green
    assert any(IMAGE in why and "restarted" in why for why in restarted.why)
    assert not any(VOICE in why for why in restarted.why), "the voice did not restart"


def test_a_text_unit_beside_them_is_still_probed(
    tmp_path: Path, no_lab: Path
) -> None:
    from mcgyvr.fleet import sample

    fleet = _fleet()
    fleet["units"][fx.UNIT] = copy.deepcopy(fx.unit())
    fleet["fleets"][FLEET]["layout"][fx.RIG].append([fx.UNIT, "awake"])
    setup = fx.staged(tmp_path, fleet=fleet, policy=_policy(tmp_path))
    fx.rig_file()
    for run_id in fx.READS:
        _read(setup, run_id, _reader())

    verdict = sample.judge(_sample(setup))

    assert not verdict.green
    assert any(fx.UNIT in why and "warm_decode_tok_s" in why for why in verdict.why)
