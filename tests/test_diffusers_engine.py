"""The diffusers image engine is sized and rendered for real, from stated numbers.

A diffusers image unit prices no context window, no KV cache, no offload knob
and no load mode. Its card peak is the denoiser's resident working set plus the
one-shot VAE decode spike, and its host claim is the once-per-run components the
spec offloads to RAM. The launch spec carries only what was stated: the weights
directory, the port, and the operator's ``serve_args``. mcgyvr ships no diffusers
server image or shell binary, so the compose file names the operator's image and
mounts the weights directory at its own absolute path.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from mcgyvr.emit import EmitError, argv, render_command, render_compose
from mcgyvr.scan import Scan
from mcgyvr.serving import ModelSpec, Unit, UnitError, fit, unit_for

MODEL = "stabilityai/stable-diffusion-xl-base-1.0"


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
        vram_gb=7.0,
        ram_gb=1.0,
        disk_gb=6.9,
        hf_cache="/srv/weights/sdxl",
        vae_decode_gb=1.2,
        serve_args=serve_args,
    )


def diffusers_unit(
    *, image: str | None = None, serve_args: tuple[str, ...] = ()
) -> Unit:
    unit = unit_for(
        scan(),
        spec(serve_args=serve_args),
        engine="diffusers",
        port=8080,
        ctx_per_slot=4096,
    )
    return unit if image is None else replace(unit, image=image)


def test_a_diffusers_fit_charges_the_working_set_plus_the_vae_spike() -> None:
    sized = fit(scan(), spec(), engine="diffusers", ctx_per_slot=4096)
    assert sized.fits is True
    assert sized.vram_gb == pytest.approx(8.2)


def test_a_diffusers_fit_charges_the_stated_ram() -> None:
    sized = fit(scan(), spec(), engine="diffusers", ctx_per_slot=4096)
    assert sized.fits is True
    assert sized.ram_gb == pytest.approx(1.0)


def test_a_diffusers_ram_past_the_host_is_refused_naming_ram_and_gb() -> None:
    sized = fit(
        scan(),
        replace(spec(), ram_gb=33.0),
        engine="diffusers",
        ctx_per_slot=4096,
    )
    assert sized.fits is False
    assert "RAM" in sized.why
    assert "GB" in sized.why


def test_a_diffusers_success_omits_the_ram_clause_when_none_is_stated() -> None:
    sized = fit(
        scan(),
        replace(spec(), ram_gb=0.0),
        engine="diffusers",
        ctx_per_slot=4096,
    )
    assert sized.fits is True
    assert "RAM" not in sized.why


def test_a_diffusers_peak_past_the_card_is_refused_naming_the_model_and_gb() -> None:
    sized = fit(
        scan(),
        replace(spec(), vram_gb=11.0, vae_decode_gb=2.0),
        engine="diffusers",
        ctx_per_slot=4096,
    )
    assert sized.fits is False
    assert MODEL in sized.why
    assert "GB" in sized.why


def test_a_diffusers_unit_without_a_cache_is_refused_by_name() -> None:
    with pytest.raises(UnitError, match="hf_cache"):
        unit_for(
            scan(),
            replace(spec(), hf_cache=""),
            engine="diffusers",
            ctx_per_slot=4096,
        )


def test_a_diffusers_unit_has_width_one_and_a_stated_only_argv() -> None:
    unit = diffusers_unit()
    assert unit.engine == "diffusers"
    assert unit.width.value == 1
    assert argv(unit) == ("--model", "/srv/weights/sdxl", "--port", "8080")


def test_diffusers_serve_args_are_appended_to_the_argv() -> None:
    unit = diffusers_unit(serve_args=("--resolution", "1024"))
    assert argv(unit)[-2:] == ("--resolution", "1024")


def test_a_diffusers_unit_ignores_width_and_context() -> None:
    unit = unit_for(
        scan(),
        spec(),
        engine="diffusers",
        width=99,
        ctx_per_slot=12345,
    )
    assert unit.width.value == 1


def test_a_diffusers_unit_without_an_image_cannot_be_rendered() -> None:
    with pytest.raises(EmitError, match="image"):
        render_compose(diffusers_unit())


def test_a_diffusers_compose_names_the_operators_image_and_weights_mount() -> None:
    rendered = render_compose(
        diffusers_unit(image="ghcr.io/example/diffusers-server:latest")
    )
    assert "ghcr.io/example/diffusers-server:latest" in rendered
    assert "/srv/weights/sdxl:/srv/weights/sdxl:ro" in rendered


def test_a_diffusers_unit_has_no_shell_command() -> None:
    with pytest.raises(EmitError, match="no shell command"):
        render_command(diffusers_unit(image="ghcr.io/example/diffusers-server:latest"))


def test_an_engine_outside_known_engines_is_refused_by_name() -> None:
    sized = fit(scan(), spec(), engine="whisper", ctx_per_slot=4096)
    assert sized.fits is False
    assert "not wired" in sized.why
    with pytest.raises(UnitError, match="whisper"):
        unit_for(scan(), spec(), engine="whisper", ctx_per_slot=4096)
