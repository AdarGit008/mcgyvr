"""A CPU-only voice runs in Kokoro-FastAPI's CPU image when it names no image.

Owner, Round 10: the voice is Kokoro, served by the Kokoro-FastAPI CPU image,
so the cards stay free. That image carries its model and starts its own
server from its own start script, which reads the port from ``PORT`` and takes
no arguments. So a CPU-only TTS unit that names no image renders that image
by its version tag (the convention of the text engines' default images), with
no command, its port in ``PORT``, and no card reservation. A unit that names
its own image keeps the operator's contract (the argv is the command), a TTS
unit on a card names its image, and the default image refuses arguments it
would never read.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
import yaml

from mcgyvr.emit import MEDIA_IMAGES, EmitError, render_command, render_compose
from mcgyvr.scan import Scan
from mcgyvr.serving import ModelSpec, Unit, unit_for


def _voice(*, cpu_only: bool = True, serve_args: tuple[str, ...] = ()) -> Unit:
    return unit_for(
        Scan.of(
            host="localhost",
            vram_mib=None if cpu_only else 6144,
            ram_gb=16.0,
            disk_free_gb=40.0,
            cores=4,
            threads=8,
            bandwidth_gbps=41.2,
        ),
        ModelSpec(
            name="hexgrad/Kokoro-82M",
            vram_gb=0.0 if cpu_only else 0.6,
            ram_gb=1.8,
            disk_gb=0.0,
            hf_cache="/srv/weights",
            cpu_only=cpu_only,
            serve_args=serve_args,
        ),
        engine="tts",
        port=8082,
        ctx_per_slot=0,
    )


def _service(unit: Unit) -> dict[str, object]:
    (service,) = yaml.safe_load(render_compose(unit))["services"].values()
    assert isinstance(service, dict)
    return service


def test_the_default_voice_image_is_kokoro_fastapis_cpu_image_by_version_tag() -> (
    None
):
    image = MEDIA_IMAGES["tts"]
    assert image.startswith("ghcr.io/remsky/kokoro-fastapi-cpu:v")
    assert "latest" not in image


def test_a_cpu_only_voice_with_no_image_renders_kokoro_with_its_port_and_no_command() -> (
    None
):
    service = _service(_voice())
    assert service["image"] == MEDIA_IMAGES["tts"]
    assert "command" not in service
    assert service["environment"] == {"PORT": "8082"}
    assert "deploy" not in service


def test_a_voice_that_names_its_own_image_keeps_the_operators_argv() -> None:
    service = _service(replace(_voice(), image="ghcr.io/example/tts-server:1.0"))
    assert service["image"] == "ghcr.io/example/tts-server:1.0"
    assert service["command"] == ["--model", "/srv/weights", "--port", "8082"]
    assert "environment" not in service


def test_the_default_image_refuses_arguments_it_would_never_read() -> None:
    with pytest.raises(EmitError, match="takes no arguments"):
        render_compose(_voice(serve_args=("--voice", "af_heart")))


def test_a_voice_on_a_card_still_names_its_image() -> None:
    with pytest.raises(EmitError, match="image"):
        render_compose(_voice(cpu_only=False))


def test_the_default_voice_still_has_no_shell_command() -> None:
    with pytest.raises(EmitError, match="no shell command"):
        render_command(_voice())
