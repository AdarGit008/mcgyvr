"""One llama.cpp build is pinned, and each system gets its archive of it.

The table (pin K5): Metal on Apple silicon, the CPU on an Intel Mac; on Linux
and Windows CUDA when ``nvidia-smi``'s driver runs one of the pinned CUDA
builds (the newest it runs), else Vulkan, else the CPU. A CUDA build comes
with its runtime archive. Every archive named is pinned with a size and a
sha256, the container image is the same build, and the archives hold both
programs the native launch runs.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from mcgyvr import emit
from mcgyvr.serving import llamacpp

CASES = [
    # system, arch, driver, backend, archive
    ("darwin", "arm64", None, "metal", "llama-b11960-bin-macos-arm64.tar.gz"),
    ("darwin", "x86_64", None, "cpu", "llama-b11960-bin-macos-x64.tar.gz"),
    ("windows", "x86_64", "591.44", "cuda", "llama-b11960-bin-win-cuda-13.4-x64.zip"),
    ("windows", "x86_64", "560.94", "cuda", "llama-b11960-bin-win-cuda-12.4-x64.zip"),
    ("windows", "x86_64", "511.65", "vulkan", "llama-b11960-bin-win-vulkan-x64.zip"),
    ("windows", "x86_64", None, "vulkan", "llama-b11960-bin-win-vulkan-x64.zip"),
    ("windows", "arm64", None, "vulkan", "llama-b11960-bin-win-vulkan-arm64.zip"),
    (
        "linux",
        "x86_64",
        "580.95.05",
        "cuda",
        "llama-b11960-bin-ubuntu-cuda-13.4-x64.tar.gz",
    ),
    (
        "linux",
        "x86_64",
        "535.183.01",
        "cuda",
        "llama-b11960-bin-ubuntu-cuda-12.8-x64.tar.gz",
    ),
    ("linux", "x86_64", None, "vulkan", "llama-b11960-bin-ubuntu-vulkan-x64.tar.gz"),
    (
        "linux",
        "arm64",
        "535.1",
        "vulkan",
        "llama-b11960-bin-ubuntu-vulkan-arm64.tar.gz",
    ),
]


@pytest.mark.parametrize(("system", "arch", "driver", "backend", "archive"), CASES)
def test_each_system_gets_its_backend_and_archive(
    system: str, arch: str, driver: str | None, backend: str, archive: str
) -> None:
    picked = llamacpp.backend_for(system, arch, nvidia_driver=driver)
    assert picked == backend
    build = llamacpp.build_for(system, arch, picked, nvidia_driver=driver)
    assert build.assets[0] == archive


@pytest.mark.parametrize("system", ["windows", "linux"])
def test_no_vulkan_loader_is_the_cpu(system: str) -> None:
    assert (
        llamacpp.backend_for(system, "x86_64", nvidia_driver=None, vulkan=False)
        == "cpu"
    )


def test_a_cuda_build_comes_with_its_runtime_archive() -> None:
    build = llamacpp.build_for("windows", "x86_64", "cuda", nvidia_driver="591.44")
    assert build.assets == (
        "llama-b11960-bin-win-cuda-13.4-x64.zip",
        "cudart-llama-bin-win-cuda-13.4-x64.zip",
    )


def test_the_cpu_is_named_where_it_is_asked_for() -> None:
    build = llamacpp.build_for("windows", "x86_64", "cpu")
    assert build.assets == ("llama-b11960-bin-win-cpu-x64.zip",)


def test_a_backend_no_build_runs_is_refused_naming_what_there_is() -> None:
    with pytest.raises(llamacpp.NoBuildError, match="metal on linux") as caught:
        llamacpp.build_for("linux", "x86_64", "metal")
    assert "cpu, cuda, vulkan" in str(caught.value)
    with pytest.raises(llamacpp.NoBuildError, match="driver 470"):
        llamacpp.build_for("linux", "x86_64", "cuda", nvidia_driver="470.256.02")


def test_every_archive_a_build_names_is_pinned_with_a_size_and_a_sha256() -> None:
    pinned = {asset.name: asset for asset in llamacpp.RELEASE.assets}
    named = {name for build in llamacpp.BUILDS for name in build.assets}
    assert named == set(pinned)
    for asset in pinned.values():
        assert asset.bytes > 0
        assert re.fullmatch(r"[0-9a-f]{64}", asset.sha256)
        if asset.name.startswith("llama-"):
            assert asset.name.startswith(f"llama-{llamacpp.TAG}-bin-")


def test_the_container_image_is_the_same_build() -> None:
    assert llamacpp.IMAGE.endswith(f":server-cuda-{llamacpp.TAG}")
    assert emit.ENGINE_IMAGES["llama.cpp"] == llamacpp.IMAGE


def test_both_programs_are_the_ones_the_native_launch_runs() -> None:
    assert llamacpp.EXECUTABLES == ("llama-server", "ggml-rpc-server")


def test_a_planted_nvidia_smi_in_the_working_folder_is_never_run_on_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.serving import native
    from tests.hostos_fakes import as_system

    here = tmp_path / "cwd"
    here.mkdir()
    for planted in ("nvidia-smi.exe", "nvidia-smi.bat", "nvidia-smi"):
        (here / planted).write_text("planted")
    elsewhere = tmp_path / "nowhere"
    monkeypatch.chdir(here)
    monkeypatch.setenv("PATH", os.pathsep.join(["", ".", "relative/bin"]))
    for variable in ("SYSTEMROOT", "PROGRAMW6432", "PROGRAMFILES"):
        monkeypatch.setenv(variable, str(elsewhere))
    as_system(monkeypatch, "windows")
    assert native.nvidia_smi() is None

    real = tmp_path / "Program Files" / "NVIDIA Corporation" / "NVSMI"
    real.mkdir(parents=True)
    (real / "nvidia-smi.exe").write_text("driver's")
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path / "Program Files"))
    assert native.nvidia_smi() == os.path.join(str(real), "nvidia-smi.exe")
