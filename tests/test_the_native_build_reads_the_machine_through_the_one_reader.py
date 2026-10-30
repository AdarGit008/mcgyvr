"""The native build reads the machine through the one reader, in the wire's names.

The architecture a native build is picked for is the reader's (``host.arch``
of :func:`mcgyvr.serving.rigscan.host`, the machine's, not the interpreter's),
and the ``nvidia-smi`` it asks for the driver is the one the reader runs
(:func:`mcgyvr.serving.rigscan.nvidia_smi`: on Windows by its full path only,
never from the working folder). The systems, architectures and backends the
build table names are the wire's (:mod:`mcgyvr.hubwire`), as is the figure a
Metal working set is filed under.
"""

from __future__ import annotations

import subprocess
from typing import Any

import pytest

from mcgyvr import hostos, hubwire
from mcgyvr.serving import llamacpp, native, rigscan
from tests.machine_shapes import host_shape


def test_the_build_tables_names_are_the_wires() -> None:
    assert (hostos.LINUX, hostos.DARWIN, hostos.WINDOWS) == hubwire.HOST_OS
    assert (hostos.LINUX, hostos.DARWIN, hostos.WINDOWS) == (
        "linux",
        "darwin",
        "windows",
    )
    assert (
        (llamacpp.X86_64, llamacpp.ARM64)
        == hubwire.HOST_ARCH
        == (
            "x86_64",
            "arm64",
        )
    )
    assert (llamacpp.CUDA, llamacpp.METAL, llamacpp.VULKAN, llamacpp.CPU) == (
        "cuda",
        "metal",
        "vulkan",
        "cpu",
    )
    assert set(llamacpp.BACKENDS) <= set(hubwire.RESOURCE_BACKENDS)
    for build in llamacpp.BUILDS:
        assert build.os in hubwire.HOST_OS and build.arch in hubwire.HOST_ARCH
        assert build.backend in hubwire.RESOURCE_BACKENDS
    assert not hasattr(native, "ARCH_NAMES")
    assert not hasattr(native, "machine_arch")


@pytest.mark.parametrize("label", ["unified-laptop", "windows-one-card"])
def test_the_build_is_picked_for_the_readers_host(
    label: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    machine = host_shape(label)
    asked: list[Any] = []

    def host(**kwargs: Any) -> dict[str, Any]:
        return {"os": machine.system, "arch": "arm64", "version": machine.version}

    monkeypatch.setattr(rigscan, "host", host)
    monkeypatch.setattr(native, "nvidia_driver", lambda: None)
    monkeypatch.setattr(native, "vulkan_loader", lambda: False)
    monkeypatch.delenv(native.BACKEND_ENV, raising=False)

    def build_for(os_name: str, arch: str, backend: str, **kw: Any) -> Any:
        asked.append((os_name, arch, backend))
        return llamacpp.BUILDS[0]

    monkeypatch.setattr(llamacpp, "build_for", build_for)
    native.pick()
    want = llamacpp.METAL if machine.system == hostos.DARWIN else llamacpp.CPU
    assert asked == [(machine.system, llamacpp.ARM64, want)]


def test_a_host_whose_arch_the_reader_does_not_name_has_no_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        rigscan, "host", lambda **kw: {"os": "linux", "arch": None, "version": "1"}
    )
    with pytest.raises(native.NativeError, match="arch"):
        native.pick()


def test_the_driver_is_asked_of_the_readers_nvidia_smi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ran: list[list[str]] = []

    class Done:
        returncode = 0
        stdout = "580.95.05\n"

    def run(argv: list[str], **kwargs: Any) -> Done:
        ran.append(argv)
        return Done()

    monkeypatch.setattr(rigscan, "nvidia_smi", lambda system=None: "/opt/tool/smi")
    monkeypatch.setattr(subprocess, "run", run)
    assert native.nvidia_driver() == "580.95.05"
    assert ran[0][0] == "/opt/tool/smi"
    monkeypatch.setattr(rigscan, "nvidia_smi", lambda system=None: None)
    assert native.nvidia_driver() is None


def test_on_windows_the_readers_tool_is_never_the_working_folders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(rigscan, "_windows_nvidia_smi", lambda: None)
    assert rigscan.nvidia_smi(system="windows") is None
    monkeypatch.setattr(rigscan, "_windows_nvidia_smi", lambda: r"C:\Tools\smi.exe")
    assert rigscan.nvidia_smi(system="windows") == r"C:\Tools\smi.exe"
