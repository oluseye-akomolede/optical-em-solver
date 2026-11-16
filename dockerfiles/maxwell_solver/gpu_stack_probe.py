"""Build-time check that a GPU solver image can actually factorise, without a GPU.

Runs inside ``Dockerfile.gpu`` after the requirements are installed. Exit 0 means
the image has the stack a GPU solve needs; any other exit fails the BUILD, so a
broken image cannot reach Harbor and cannot be deployed to the A4000.

Why this file exists rather than two ``python -c`` lines in the Dockerfile: the
permission string is long enough to be unreadable when backslash-continued, and
Docker's line continuation cannot carry a multi-line Python literal. As a
checked-in script it is also runnable outside a build (the lead's red-path check is in tasks.md).

Why an import check is not enough
---------------------------------
The solver imports cupy, cupyx.scipy.sparse and nvmath on its GPU path, and
``mse_backend._missing_gpu_package()`` names the first of those that is absent.
All three import cleanly WITHOUT cuDSS. cuDSS arrives only because
nvmath-python declares it under ``extra == "cu12"``:

    nvidia-cudss-cu12==0.7.*; extra == "cu12"

so ``nvmath-python==0.9.0`` on its own installs no cuDSS at all, and the first
``nvmath.sparse.advanced.DirectSolver`` factorisation is where that surfaces --
on the A4000, after build, push and deploy. That is the failure this probe
closes: it loads the cuDSS shared object itself.

``dlopen`` needs no GPU (it is the loader, not a kernel), so this still fails at
build time. Only a real factorisation needs the card, and that is the lead's
bounded-Job smoke on one A4000.

Why importing, and even loading cuDSS, is STILL not enough
---------------------------------------------------------
A third failure reached production on 2026-11-12 (td proof job 69e3152c, image
``mse-maxwell-solver-gpu:a24e9f7``): the solve died in ``fdtd.simulate`` at

    xp.all(eps > 0)

because CuPy JIT-compiles that elementwise kernel with NVRTC, and NVRTC could
not find the CUDA headers:

    RuntimeError: Failed to find CUDA headers. Please install CUDA toolkit
    headers (e.g., pip install cupy-cuda12x[ctk]) or specify CUDA_PATH ...

The image imported cupy fine and loaded cuDSS fine. Both checks passed and the
image could not run a single kernel. ``// Dockerfile.gpu`` had already written
the lesson down ("import cupy ... went green on an image whose first real kernel
died") and the probe had not acted on it.

``nvrtc_probe`` closes it the only way that would have caught this: it COMPILES,
by NVRTC, with no GPU. NVRTC needs two things this base image lacked -- the
CUDA headers (``cuda_runtime.h``) and the ``libnvrtc.so`` that ``cupy-cuda12x``
finds through ``cuda-pathfinder`` -- and the probe fails the build if either is
missing.

The source deliberately ``#include``s ``<cuda_runtime.h>``. A bare elementwise
kernel compiles against the headers NVRTC carries BUILT IN, so a headerless
image would pass that probe -- tried, and it false-greened. Including a real
header is what makes the check ask the question the GPU solve asks.

Measured on 2026-11-12 in a scratch venv, both directions:

* headers + libnvrtc present  -> ``NVRTC COMPILED OK`` (635 bytes of PTX)
* the same source with no ``-I`` -> ``could not open source file
  "cuda_runtime.h" (no directories in search list)``
"""

from __future__ import annotations

import ctypes
import importlib
import importlib.metadata
import sys
from pathlib import Path

_CUDSS_DIST = "nvidia-cudss-cu12"

_NO_PKG = (
    "no " + _CUDSS_DIST + " distribution: nvmath-python does not install cuDSS "
    "on its own (it is declared only under the cu12 extra). Pin it in "
    "requirements-gpu.txt."
)


def import_probe() -> str:
    """Import each GPU package the solver needs. Returns what it checked.

    This deliberately does NOT go through ``mse_backend._missing_gpu_package()``.
    That helper returns ``"the CUDA stack"`` as a LABEL for an error message when
    nothing is missing, so a caller cannot tell "all present" from "the stack is
    missing" -- a first version of this probe read the label as a failure and
    refused a correct image. The packages are imported here, one name at a time,
    from the same tuple the solver uses, so the two cannot drift.
    """
    sys.path.insert(0, "/opt/app")
    import mse_backend  # noqa: PLC0415 -- needs the path insert above

    for module, name in mse_backend._GPU_PACKAGES:
        try:
            importlib.import_module(module)
        except ImportError as exc:
            raise AssertionError(
                f"this GPU image cannot run a GPU solve: {name!r} is not "
                f"importable ({exc})"
            ) from exc
    return ", ".join(name for _, name in mse_backend._GPU_PACKAGES)


def cudss_probe() -> str:
    """Load the cuDSS shared object, no GPU required. Returns the library name.

    Located through the ``nvidia-cudss-cu12`` DISTRIBUTION, not by importing a
    module: that wheel is data-only. Measured on 0.7.1.6, it installs

        nvidia/cu12/lib/libcudss.so.0        (no importable nvidia.cudss package)

    so ``importlib.util.find_spec("nvidia.cudss")`` fails on a correct image.
    An earlier version of this probe did exactly that and refused a good
    install -- a check whose constants were assumed rather than read off the
    thing it checks.
    """
    try:
        dist = importlib.metadata.distribution(_CUDSS_DIST)
    except importlib.metadata.PackageNotFoundError:
        raise AssertionError(_NO_PKG) from None
    lib_root = Path(dist.locate_file("nvidia")) / "cu12" / "lib"
    libs = sorted(lib_root.glob("*cudss*.so*"))
    if not libs:
        raise AssertionError(f"{_CUDSS_DIST} is installed but ships no cuDSS library under {lib_root}")
    # Load the SONAME-pinned file (libcudss.so.0); loading raises OSError if a
    # dependency it needs is missing, which is the other half of the check.
    ctypes.CDLL(str(libs[0]))
    return libs[0].name


def _cuda_include_dirs() -> list[str]:
    """The CUDA header directories the pip CUDA wheels install, if any.

    CuPy carries no CUDA headers of its own; the ``nvidia-*-cu12`` wheels put
    them under ``nvidia/<piece>/include`` inside site-packages, and CuPy finds
    them through ``cuda-pathfinder`` -- which is why no fixed path is correct
    for every install. Each ``include/crt`` is added beside its parent because
    the headers ``#include <crt/host_defines.h>`` by that relative path.
    """
    dirs: list[str] = []
    # Walk site-packages for the nvidia/*/include layout rather than guessing a
    # distribution name per header: nvcc ships crt/, runtime ships cuda.h, and
    # a future wheel may split them differently.
    for dist in importlib.metadata.distributions():
        try:
            root = Path(dist.locate_file("nvidia"))
        except Exception:
            continue
        if not root.is_dir():
            continue
        for inc in sorted(root.glob("*/include")):
            dirs.append(str(inc))
            if (inc / "crt").is_dir():
                dirs.append(str(inc / "crt"))
    return dirs


def _preload_nvrtc() -> str | None:
    """Load ``libnvrtc.so.12`` from the pip wheel by absolute path.

    Returns the path loaded, or ``None`` if no such file is installed (which is
    the image's problem, not this function's -- the caller reports it). Uses
    ``ctypes`` rather than an environment variable because the dynamic loader
    caches its search path at process start; see ``nvrtc_probe``.
    """
    for lib_dir in _cuda_library_dirs():
        for name in ("libnvrtc.so.12", "libnvrtc.so"):
            path = Path(lib_dir) / name
            if path.is_file():
                try:
                    ctypes.CDLL(str(path), mode=ctypes.RTLD_GLOBAL)
                except OSError:
                    continue
                return str(path)
    return None


def _cuda_library_dirs() -> list[str]:
    """The ``nvidia/<piece>/lib`` dirs holding libnvrtc.so / libcudart.so.

    The include dirs above make NVRTC able to RESOLVE ``#include
    <cuda_runtime.h>``; this one makes the ``libnvrtc.so.12`` shared object
    findable at all. They are separate lookups and separate wheels (nvrtc's
    own include is empty -- it ships only ``nvrtc.h``), and a probe that only
    sets ``-I`` fails with "Failure finding libnvrtc.so.13 or libnvrtc.so.12".
    """
    dirs: list[str] = []
    for dist in importlib.metadata.distributions():
        try:
            root = Path(dist.locate_file("nvidia"))
        except Exception:
            continue
        if not root.is_dir():
            continue
        for lib in sorted(root.glob("*/lib")):
            if lib.is_dir():
                dirs.append(str(lib))
    return dirs


_NVRTC_SRC = r"""
#include <cuda_runtime.h>
extern "C" __global__ void mse_probe_kernel(float *a) {
    a[threadIdx.x] = a[threadIdx.x] > 0.0f ? 1.0f : 0.0f;
}
"""


def nvrtc_probe() -> str:
    """JIT-compile a kernel to PTX with NVRTC, no GPU. Returns the PTX size.

    This is the failure that reached production (see the module docstring):
    CuPy's elementwise kernels are NVRTC-compiled, so ``import cupy`` and a
    loaded cuDSS prove nothing about whether a solve can actually start. NVRTC
    compilation needs no device -- it is a compiler, not a launcher -- so a bad
    image fails HERE, at build time, instead of on the A4000 after a deploy.

    ``compute_86``/``sm_86`` is the A4000 (GA104). Compiling for an explicit
    arch rather than ``compute_XX`` detected from a device matters: there is no
    device at build time, and a probe that needed one could not run here.
    """
    try:
        from cupy_backends.cuda.libs import nvrtc
    except Exception as exc:  # noqa: BLE001 -- any load failure is the finding
        raise AssertionError(
            "this GPU image cannot JIT-compile a CuPy kernel: the NVRTC library "
            f"is not loadable ({exc}). cupy-cuda12x needs a libnvrtc.so.12 on a "
            "machine with no CUDA toolkit; pin nvidia-cuda-nvrtc-cu12 in "
            "requirements-gpu.txt."
        ) from exc

    include_dirs = _cuda_include_dirs()
    if not include_dirs:
        raise AssertionError(
            "this GPU image cannot JIT-compile a CuPy kernel: no CUDA headers are "
            "installed (no nvidia/*/include under site-packages), and NVRTC needs "
            "cuda_runtime.h. Pin nvidia-cuda-runtime-cu12 and "
            "nvidia-cuda-nvcc-cu12 in requirements-gpu.txt."
        )

    # Headers are only half of it. libnvrtc.so.12 lives beside them under
    # site-packages/nvidia/cuda_nvrtc/lib, and cuda.pathfinder does NOT search
    # there: measured on this VM, with the headers present and findable, cupy
    # still failed with `Failure finding "libnvrtc.so.13 or libnvrtc.so.12"`.
    #
    # Setting LD_LIBRARY_PATH here does NOT work -- the dynamic loader reads it
    # once at process start, so assigning os.environ is inert (measured: the
    # same failure with the variable set in-process, success only when it was
    # exported BEFORE the interpreter started). Preloading the shared object by
    # absolute path with RTLD_GLOBAL does work, because the loader then finds
    # it already loaded: 695 bytes of PTX, no GPU. Done here so the probe tests
    # the wheels the image installs, not whatever the caller's shell exported.
    _preload_nvrtc()

    program = nvrtc.createProgram(_NVRTC_SRC, "mse_probe_kernel.cu", (), ())
    options = tuple("-I" + d for d in include_dirs) + ("-arch=compute_86",)
    try:
        nvrtc.compileProgram(program, options)
        ptx = nvrtc.getPTX(program)
    except Exception as exc:  # noqa: BLE001
        log = ""
        try:
            log = nvrtc.getProgramLog(program)
        except Exception:
            pass
        raise AssertionError(
            "this GPU image cannot JIT-compile a CuPy kernel -- NVRTC failed. "
            "This is the fdtd.simulate `xp.all(eps > 0)` failure, caught at "
            f"build time. ({exc})\nNVRTC log:\n{log}"
        ) from exc
    return f"{len(ptx)} bytes of PTX"


def main() -> int:
    import_probe()
    print("GPU STACK IMPORTS OK")
    print("cuDSS LOADS OK: " + cudss_probe())
    print("NVRTC COMPILES OK: " + nvrtc_probe())
    return 0


if __name__ == "__main__":
    sys.exit(main())
