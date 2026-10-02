"""The ComfyUI engine is sized and rendered for real, from stated numbers.

A ComfyUI unit prices no context window, no KV cache, no offload knob and no
load mode. Its card peak is the stated working set — ComfyUI tiles its decode
(c-04), so there is no VAE spike — and its host claim is the stated ``ram_gb``,
charged directly against MemAvailable. The launch spec carries only what was
stated: the weights directory, the port, and the operator's ``serve_args``.
mcgyvr ships no ComfyUI server image or shell binary, so the compose file names
the operator's image and mounts the weights directory at its own absolute path.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from mcgyvr.emit import EmitError, argv, render_command, render_compose
from mcgyvr.scan import Scan
from mcgyvr.serving import ModelSpec, Unit, UnitError, fit, unit_for

MODEL = "Lightricks/LTX-Video"


def scan() -> Scan:
    return Scan.of(
        host="localhost",
        vram_mib=12288,
        ram_gb=32.0,
        disk_free_gb=120.0,
        cores=8,
        threads=16,
        bandwidth_gbps=41.2,
    )


def spec(*, serve_args: tuple[str, ...] = ()) -> ModelSpec:
    return ModelSpec(
        name=MODEL,
        vram_gb=6.0,
        ram_gb=1.0,
        disk_gb=4.1,
        hf_cache="/srv/weights/comfyui",
        serve_args=serve_args,
    )


def comfyui_unit(*, image: str | None = None, serve_args: tuple[str, ...] = ()) -> Unit:
    unit = unit_for(
        scan(),
        spec(serve_args=serve_args),
        engine="comfyui",
        port=8080,
        ctx_per_slot=4096,
    )
    return unit if image is None else replace(unit, image=image)


def test_a_comfyui_fit_charges_the_working_set_with_no_vae_spike() -> None:
    sized = fit(
        scan(), replace(spec(), vae_decode_gb=9.0), engine="comfyui", ctx_per_slot=4096
    )
    assert sized.fits is True
    assert sized.vram_gb == pytest.approx(6.0)


def test_a_comfyui_fit_charges_the_stated_ram() -> None:
    sized = fit(scan(), spec(), engine="comfyui", ctx_per_slot=4096)
    assert sized.fits is True
    assert sized.ram_gb == pytest.approx(1.0)


def test_a_comfyui_ram_past_the_host_is_refused_naming_ram_and_gb() -> None:
    sized = fit(
        scan(), replace(spec(), ram_gb=33.0), engine="comfyui", ctx_per_slot=4096
    )
    assert sized.fits is False
    assert "RAM" in sized.why
    assert "GB" in sized.why


def test_a_comfyui_peak_past_the_card_is_refused_naming_the_model_and_gb() -> None:
    sized = fit(
        scan(), replace(spec(), vram_gb=11.0), engine="comfyui", ctx_per_slot=4096
    )
    assert sized.fits is False
    assert MODEL in sized.why
    assert "GB" in sized.why


def test_a_comfyui_unit_without_a_weights_dir_is_refused_by_name() -> None:
    with pytest.raises(UnitError, match="hf_cache"):
        unit_for(
            scan(), replace(spec(), hf_cache=""), engine="comfyui", ctx_per_slot=4096
        )


def test_a_comfyui_unit_has_width_one_and_a_stated_only_argv() -> None:
    unit = comfyui_unit()
    assert unit.engine == "comfyui"
    assert unit.width.value == 1
    assert argv(unit) == ("--model", "/srv/weights/comfyui", "--port", "8080")


def test_comfyui_serve_args_are_appended_to_the_argv() -> None:
    unit = comfyui_unit(
        serve_args=("--extra-model-paths-config", "/srv/comfyui-extra.yaml")
    )
    assert argv(unit)[-2:] == (
        "--extra-model-paths-config",
        "/srv/comfyui-extra.yaml",
    )


def test_a_comfyui_unit_ignores_width_and_context() -> None:
    unit = unit_for(scan(), spec(), engine="comfyui", width=99, ctx_per_slot=12345)
    assert unit.width.value == 1


def test_a_comfyui_unit_without_an_image_cannot_be_rendered() -> None:
    with pytest.raises(EmitError, match="image"):
        render_compose(comfyui_unit())


def test_a_comfyui_compose_names_the_operators_image_and_weights_mount() -> None:
    rendered = render_compose(comfyui_unit(image="ghcr.io/example/comfyui:latest"))
    assert "ghcr.io/example/comfyui:latest" in rendered
    assert "/srv/weights/comfyui:/srv/weights/comfyui:ro" in rendered


def test_a_comfyui_unit_has_no_shell_command() -> None:
    with pytest.raises(EmitError, match="no shell command"):
        render_command(comfyui_unit(image="ghcr.io/example/comfyui:latest"))
