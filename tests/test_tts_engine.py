"""The TTS engine is sized and rendered for real, from stated numbers.

A TTS unit prices no context window, no KV cache, no offload knob and no load
mode. Its card peak is the stated working set — no VAE spike, which is the
image engine's — and a ``cpu_only`` unit (a Piper-class rung) claims no card at
all. Its host claim is the stated ``ram_gb``, charged directly against
MemAvailable. The launch spec carries only what was stated: the weights
directory, the port, and the operator's ``serve_args``. mcgyvr ships no TTS
server image or shell binary, so the compose file names the operator's image,
mounts the weights directory at its own absolute path, and a cpu_only unit
carries no GPU reservation.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from mcgyvr.emit import EmitError, argv, render_command, render_compose
from mcgyvr.scan import Scan
from mcgyvr.serving import (
    ModelSpec,
    Unit,
    UnitError,
    alternate,
    fit,
    hold_together,
    unit_for,
)

MODEL = "rhasspy/piper-voices"


def scan(*, vram: bool = True) -> Scan:
    return Scan.of(
        host="localhost",
        vram_mib=6144 if vram else None,
        ram_gb=16.0,
        disk_free_gb=40.0,
        cores=4,
        threads=8,
        bandwidth_gbps=41.2,
    )


def spec(*, serve_args: tuple[str, ...] = (), cpu_only: bool = False) -> ModelSpec:
    return ModelSpec(
        name=MODEL,
        vram_gb=0.0 if cpu_only else 0.6,
        ram_gb=0.4,
        disk_gb=0.1,
        hf_cache="/srv/weights/piper",
        cpu_only=cpu_only,
        serve_args=serve_args,
    )


def tts_unit(
    *,
    image: str | None = None,
    serve_args: tuple[str, ...] = (),
    cpu_only: bool = False,
) -> Unit:
    unit = unit_for(
        scan(vram=not cpu_only),
        spec(serve_args=serve_args, cpu_only=cpu_only),
        engine="tts",
        port=8080,
        ctx_per_slot=4096,
    )
    return unit if image is None else replace(unit, image=image)


def test_a_tts_fit_charges_the_working_set_with_no_vae_spike() -> None:
    sized = fit(
        scan(), replace(spec(), vae_decode_gb=9.0), engine="tts", ctx_per_slot=4096
    )
    assert sized.fits is True
    assert sized.vram_gb == pytest.approx(0.6)


def test_a_tts_fit_charges_the_stated_ram() -> None:
    sized = fit(scan(), spec(), engine="tts", ctx_per_slot=4096)
    assert sized.fits is True
    assert sized.ram_gb == pytest.approx(0.4)


def test_a_tts_ram_past_the_host_is_refused_naming_ram_and_gb() -> None:
    sized = fit(scan(), replace(spec(), ram_gb=17.0), engine="tts", ctx_per_slot=4096)
    assert sized.fits is False
    assert "RAM" in sized.why
    assert "GB" in sized.why


def test_a_tts_peak_past_the_card_is_refused_naming_the_model_and_gb() -> None:
    sized = fit(scan(), replace(spec(), vram_gb=6.0), engine="tts", ctx_per_slot=4096)
    assert sized.fits is False
    assert MODEL in sized.why
    assert "GB" in sized.why


def test_a_tts_unit_without_a_weights_dir_is_refused_by_name() -> None:
    with pytest.raises(UnitError, match="hf_cache"):
        unit_for(scan(), replace(spec(), hf_cache=""), engine="tts", ctx_per_slot=4096)


def test_a_tts_unit_has_width_one_and_a_stated_only_argv() -> None:
    unit = tts_unit()
    assert unit.engine == "tts"
    assert unit.width.value == 1
    assert argv(unit) == ("--model", "/srv/weights/piper", "--port", "8080")


def test_tts_serve_args_are_appended_to_the_argv() -> None:
    unit = tts_unit(serve_args=("--voice", "en_US-amy"))
    assert argv(unit)[-2:] == ("--voice", "en_US-amy")


def test_a_tts_unit_ignores_width_and_context() -> None:
    unit = unit_for(scan(), spec(), engine="tts", width=99, ctx_per_slot=12345)
    assert unit.width.value == 1


def test_a_tts_unit_without_an_image_cannot_be_rendered() -> None:
    with pytest.raises(EmitError, match="image"):
        render_compose(tts_unit())


def test_a_tts_compose_names_the_operators_image_and_weights_mount() -> None:
    rendered = render_compose(tts_unit(image="ghcr.io/example/tts-server:latest"))
    assert "ghcr.io/example/tts-server:latest" in rendered
    assert "/srv/weights/piper:/srv/weights/piper:ro" in rendered


def test_a_tts_unit_has_no_shell_command() -> None:
    with pytest.raises(EmitError, match="no shell command"):
        render_command(tts_unit(image="ghcr.io/example/tts-server:latest"))


def test_a_cpu_only_tts_unit_fits_a_machine_with_no_card() -> None:
    sized = fit(scan(vram=False), spec(cpu_only=True), engine="tts", ctx_per_slot=4096)
    assert sized.fits is True
    assert sized.vram_gb == 0.0


def test_a_cpu_only_tts_unit_renders_without_a_gpu_reservation() -> None:
    rendered = render_compose(
        tts_unit(cpu_only=True, image="ghcr.io/example/tts-server:latest")
    )
    assert "deploy" not in rendered
    assert "device_ids" not in rendered


def test_a_cpu_only_tts_unit_never_contends_for_a_card() -> None:
    cpu = tts_unit(cpu_only=True)
    gpu = unit_for(scan(), spec(), engine="tts", port=8081, ctx_per_slot=4096)
    assert alternate(cpu, gpu) is False
    assert alternate(gpu, cpu) is False


def test_two_cpu_only_tts_units_sum_host_memory_with_no_text_margin() -> None:
    """A media engine's host memory is its stated ram_gb, summed directly with
    no text-engine refusal margin: two cpu_only rungs asking for 14.0 GB of a
    15.0 GB host fit together."""
    host = Scan.of(host="localhost", ram_gb=15.0, disk_free_gb=40.0, cores=4, threads=8)
    stated = replace(spec(), ram_gb=7.0, cpu_only=True)
    one = unit_for(host, stated, engine="tts", port=8080, ctx_per_slot=4096)
    two = unit_for(host, stated, engine="tts", port=8081, ctx_per_slot=4096)
    assert hold_together((one, two), {"localhost": host}) == ()


def test_two_cpu_only_tts_units_still_refuse_a_short_host() -> None:
    """The sum still fires, with no margin: 16.0 GB of a 15.0 GB host."""
    host = Scan.of(host="localhost", ram_gb=15.0, disk_free_gb=40.0, cores=4, threads=8)
    stated = replace(spec(), ram_gb=8.0, cpu_only=True)
    one = unit_for(host, stated, engine="tts", port=8080, ctx_per_slot=4096)
    two = unit_for(host, stated, engine="tts", port=8081, ctx_per_slot=4096)
    with pytest.raises(UnitError):
        hold_together((one, two), {"localhost": host})
