"""The Vulkan runtime image carries what the NVIDIA ICD needs to load.

Diagnosed on srv2, 2026-09-02, inside ``llamacpp:b10644-A3`` with
``--gpus all -e NVIDIA_DRIVER_CAPABILITIES=all``: the toolkit injected
``/etc/vulkan/icd.d/nvidia_icd.json`` and ``libGLX_nvidia.so.0`` correctly,
and the Vulkan loader then said

    Failed loading library associated with ICD JSON libGLX_nvidia.so.0
    libXext.so.6: cannot open shared object file
    vkCreateInstance: Found no drivers!

``libGLX_nvidia.so.0`` links ``libX11.so.6``, ``libXext.so.6`` and
``libGLdispatch.so.0``; the runtime stage installed ``libvulkan1`` and
``vulkan-tools`` under ``--no-install-recommends`` and none of the three. So no
device, so ggml fell back to the CPU, so A3's numbers were the i5-9600K.

With those three the ICD loads and then fails one step later, on
2026-09-03: ``Could not get 'vkCreateInstance' via 'vk_icdGetInstanceProcAddr'``.
``strace`` inside the image showed the ICD's init opening ``libEGL.so.1`` and
finding nothing; upstream's Vulkan image has it as a mesa dependency, ours
had no reason to. With ``libegl1`` our own ``llama-bench --list-devices``
lists ``Vulkan0: NVIDIA GeForce RTX 3060`` on srv2.

The fix is four packages on the runtime apt line and a build-time check that
they resolved, so an image that would silently bench the CPU fails to build.
And the arm's spec names the fix (``icd_deps=x11-egl``) so ``image_matches``
refuses to reuse an image that lacks it: the ladder rebuilds A3 rather than
re-measuring the CPU under the same tag.
"""

from __future__ import annotations

import re

from tests import onedoor

LADDER_SH = onedoor.KERNEL_ARMS / "1-build-ladder.sh"
ICD_LIBS = ("libglvnd0", "libegl1", "libx11-6", "libxext6")
ICD_SONAMES = ("libX11.so.6", "libXext.so.6", "libGLdispatch.so.0", "libEGL.so.1")


def _vulkan_dockerfile() -> str:
    text = LADDER_SH.read_text(encoding="utf-8")
    start = text.index("write_dockerfile_vulkan() {")
    body = text[start:]
    end = body.index("\nDOCKERFILE\n")
    return body[:end]


def _runtime_stage(dockerfile: str) -> str:
    stages = dockerfile.split("\nFROM ")
    assert len(stages) >= 3, "the vulkan Dockerfile is not a two-stage build"
    return stages[-1]


def test_the_runtime_stage_installs_what_the_nvidia_icd_links() -> None:
    runtime = _runtime_stage(_vulkan_dockerfile())
    apt = re.search(r"apt-get install[^&]*", runtime, re.S)
    assert apt, runtime
    for pkg in ICD_LIBS:
        assert re.search(rf"\b{re.escape(pkg)}\b", apt.group(0)), (
            f"{pkg} is not on the vulkan runtime apt line; libGLX_nvidia.so.0 "
            "will not load and ggml will bench the CPU"
        )


def test_the_build_fails_if_those_libraries_did_not_resolve() -> None:
    runtime = _runtime_stage(_vulkan_dockerfile())
    for soname in ICD_SONAMES:
        assert soname in runtime, (
            f"the runtime stage never checks that {soname} resolved; a missing "
            "library would be found on the rig, after the model loaded"
        )
    assert "ldconfig" in runtime, "the check should ask the loader, not apt"


def test_the_a3_spec_names_the_fix_so_the_old_image_is_not_reused() -> None:
    text = LADDER_SH.read_text(encoding="utf-8")
    spec = re.search(r"A3\)\s*printf\s*'([^']*)'", text)
    assert spec, "arm_spec has no A3 line"
    assert "icd_deps=x11-egl" in spec.group(1), spec.group(1)
    matches = text[text.index("image_matches() {") :]
    matches = matches[: matches.index("\n}\n")]
    assert "icd_deps" in matches, (
        "image_matches does not compare icd_deps, so the A3 image that benched "
        "the CPU would be reused under the same tag"
    )
