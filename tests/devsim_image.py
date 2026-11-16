"""The solver image every DEVSIM run instruction in this repo names.

It lives ONLY at the Harbor tag. The local build (`mse-solver:devsim-2.1`)
was removed from this host for disk (2026-11-13), so a bare local name pulls
nothing, the container never starts, and any test guarded by
`pytest.importorskip("devsim")` reports SKIPPED. A skip is not evidence, so
the tag is defined here once and spelled out nowhere else.

Import it, do not copy it:

    from devsim_image import DEVSIM_IMAGE
    _RUN = f\"\"\"docker run --rm --cpus=2 --memory=2g ... \\
        --entrypoint python {DEVSIM_IMAGE} -m pytest ...\"\"\"

For a shell script under scripts/ (which cannot import this module) paste the
full Harbor path; tests/test_devsim_image_refs.py checks the whole tree for a
bare local tag, so a stale copy fails at once, by file and line.
"""

#: Full registry path. `docker manifest inspect` on it succeeds; the bare
#: local name does not exist on this host.
DEVSIM_IMAGE = (
    "registry.example/mode-search-engine/mse-solver:devsim-2.1"
)
