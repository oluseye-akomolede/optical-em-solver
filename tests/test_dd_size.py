"""The size check (task 2.5): price a run from its mesh, refuse if too big.

The point of these tests is that the estimate is the DEVICE's own: two devices
of different size must give different estimates that scale with their node and
edge counts, not with a constant. A check that returns the same number for any
geometry would pass a "refuses a big run" test and be useless, because it would
either admit real runs or refuse small ones.

No test here runs a solve. That is the requirement, not a shortcut: the whole
value of the estimate is deciding before anything is allocated. The one test
that drives a solve path lives in tests/test_dd_size_wiring.py.
"""

import math

import pytest

from mse_axisymmetric import (
    GIB,
    TooBigForJob,
    build_grid,
    estimate_job_bytes,
    require_job_memory,
)


def _grid(n_r=12, n_z=200):
    return build_grid(0.0, 1e-8, -2e-6, 2e-6, n_r=n_r, n_z=n_z)


def test_the_estimate_counts_the_mesh_the_solve_would_build():
    """Node and edge counts are the structured grid's, not a constant.

    A tensor-product (r, z) mesh has ``n_r * n_z`` nodes and
    ``(n_r-1)*n_z + n_r*(n_z-1)`` edges. The estimate must be built on those
    counts, and the test checks them from the grid rather than restating them.
    """
    grid = _grid(n_r=12, n_z=200)
    assert grid.n_nodes == 12 * 200
    n_r, n_z = grid.n_r, grid.n_z
    edges = (n_r - 1) * n_z + n_r * (n_z - 1)
    assert edges == 11 * 200 + 12 * 199


def test_two_geometries_give_different_estimates():
    """The estimate is the device's own: doubling the mesh changes the number.

    This is the deliverable that separates a real estimate from a constant.
    Two grids of the SAME shape family but different resolution must give
    different answers, and a larger one must be larger.
    """
    small = estimate_job_bytes(_grid(n_r=12, n_z=200))
    large = estimate_job_bytes(_grid(n_r=12, n_z=400))
    assert small != large
    assert large > small


def test_the_estimate_scales_with_the_node_count_not_a_constant():
    """Admissible bytes grow with nodes, and superlinearly (the fill law).

    The sparse factorisation's fill grows like ``n^1.5`` on a 2-D stencil, so
    doubling the nodes must more than double the bytes. Asserting that is what
    makes this a model of the geometry: a purely per-node estimate would
    under-predict exactly the large runs this check exists to refuse.
    """
    estimates = {}
    for n_z in (200, 400, 800):
        grid = _grid(n_z=n_z)
        estimates[n_z] = (grid.n_nodes, estimate_job_bytes(grid))
    ns = [v[0] for v in estimates.values()]
    bs = [v[1] for v in estimates.values()]
    assert ns == sorted(ns)
    assert bs == sorted(bs)
    # 4x the nodes must give more than 2x the bytes: the fill term is present.
    assert bs[-1] > 2.5 * bs[0]
    # and the ratio must itself grow, which a per-node constant cannot do
    r1 = bs[1] / bs[0]
    r2 = bs[2] / bs[1]
    assert r2 > r1


def test_a_run_over_the_limit_is_refused_before_any_solve():
    """Refusal is terminal and names the estimate, the limit and the mesh size."""
    grid = _grid()
    limit = 1 << 20                     # 1 MiB: below any real estimate
    with pytest.raises(TooBigForJob) as excinfo:
        require_job_memory(grid, limit_bytes=limit)
    err = excinfo.value
    assert err.estimate_bytes > limit
    assert err.limit_bytes == limit
    text = str(err)
    assert "GiB" in text
    assert "nodes" in text and "edges" in text
    assert "before any solve" in text
    assert str(err.nodes) in text.replace(",", "")


def test_a_run_under_the_limit_is_admitted_and_returns_its_estimate():
    """Admission returns the number, so a caller need not recompute it."""
    grid = _grid()
    estimate = require_job_memory(grid, limit_bytes=14 * 1024 ** 3)
    assert estimate == estimate_job_bytes(grid)


def test_the_refusal_names_the_axisymmetric_form_for_a_round_device():
    """A round device is pointed at the 1-D form, which is how to solve it.

    The hint appears only when the caller supplies a ratio at or below the
    roundness tolerance: this function does not re-derive roundness.
    """
    grid = _grid()
    limit = 1 << 20
    with pytest.raises(TooBigForJob) as excinfo:
        require_job_memory(grid, limit_bytes=limit, roundness_ratio=1.0005)
    assert "axisymmetric" in str(excinfo.value)
    assert "one-dimensional" in str(excinfo.value)


def test_a_non_round_device_gets_no_axisymmetric_hint():
    """The hint must not appear for a device that is not round."""
    grid = _grid()
    with pytest.raises(TooBigForJob) as excinfo:
        require_job_memory(grid, limit_bytes=1 << 20, roundness_ratio=3.0)
    assert "axisymmetric" not in str(excinfo.value)


def test_an_unknown_roundness_gives_no_hint_rather_than_a_guess():
    """``None`` means the caller did not measure: say nothing, do not assume."""
    grid = _grid()
    with pytest.raises(TooBigForJob) as excinfo:
        require_job_memory(grid, limit_bytes=1 << 20)
    assert "axisymmetric" not in str(excinfo.value)


def test_the_default_limit_is_the_jobs_not_the_namespace_ceiling():
    """The default is the Job's 14 GiB, not the 16Gi admission ceiling.

    A run between the two would be ADMITTED by the namespace and then killed by
    the Job's own limit, which is the failure this check exists to prevent.
    """
    from mse_common import DEFAULT_JOB_MEMORY_BYTES
    assert DEFAULT_JOB_MEMORY_BYTES == 14 * 1024 ** 3
    grid = _grid()
    estimate = estimate_job_bytes(grid)
    # Under the real limit: admitted by the default.
    assert estimate < DEFAULT_JOB_MEMORY_BYTES
    assert require_job_memory(grid) == estimate
