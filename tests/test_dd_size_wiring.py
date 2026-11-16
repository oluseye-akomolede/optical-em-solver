"""The size check is wired into the SOLVE PATHS, not only the helper (task 2.5).

``tests/test_dd_size.py`` proves the estimator and the refusal; it deliberately
runs no solve. That left a hole the reviewer found at 095c50f: one of the three
solve paths called ``require_job_memory(g)`` with a name that was never bound,
raising ``NameError`` instead of refusing -- and no test could see it, because
every test called the helper directly. A check that is correct in isolation and
broken where it is used does not gate real runs, and the commit claimed it did.

These tests drive the real entry points. Each one is cheap: the refusal must
happen BEFORE the device is built, so the too-big case does no DEVSIM work at
all, and the admitted case uses the smallest grid the solver accepts.

Run them the way the solver image is run (DEVSIM lives only there):

    DOCKER_CONFIG=~/.docker-mse docker run --rm --cpus=2 --memory=2g \\
    -e DEVSIM_MATH_LIBS="libblas.so.3:liblapack.so.3" \\
    -v "$PWD":/repo:ro --entrypoint python {DEVSIM_IMAGE} \\
    -m pytest /repo/tests/test_dd_size_wiring.py -q

{DEVSIM_IMAGE} is the Harbor tag; see tests/devsim_image.py for why a bare
local name is not usable here.
"""

import math

import pytest

from devsim_image import DEVSIM_IMAGE

devsim = pytest.importorskip("devsim", reason="DEVSIM lives only in the solver image")

from mse_axisymmetric import (  # noqa: E402
    TooBigForJob,
    solve_abrupt_junction,
)

# The coupled DD path, which converges and is covered by
# tests/test_axisymmetric_junction.py. The n_r=2 / n_z=200 grid is the one that
# suite already solves at, so this adds no new numerical risk.
_TINY = dict(n_a=1e17, n_d=1e17, n_i=1.0e10, eps_s=11.7,
             z_lo=-1.0e-6, z_hi=1.0e-6, n_r=2, n_z=60, refine=2e-9)


def test_the_potential_only_path_reaches_its_size_check_without_a_nameerror():
    """Regression for the 095c50f typo, on the function that HAD the typo.

    At 095c50f ``solve_abrupt_junction`` called ``require_job_memory(g)`` with
    no ``g`` in scope, so it raised ``NameError`` -- neither refusing nor
    solving. This must call THAT function: an earlier version of this test
    drove ``solve_abrupt_junction_dd`` instead, and a mutation restoring the
    typo still passed, which is the false green the test exists to prevent.

    The claim is precise: no ``NameError``. Until 2.12 was fixed this path did
    not converge on its own defaults, so the test tolerated a ``Convergence``
    failure rather than pretending the solve worked. It converges now, so the
    success branch is the one that runs -- and it asserts the key this solver
    actually returns, ``v_bi_measured``. The earlier ``"v_bi" in result`` was
    never executed (the else branch was dead while the solve raised), so it
    would have failed the moment 2.12 was fixed. That is the same shape of
    false green this test exists to prevent: an assertion no run ever reached.
    """
    try:
        result = solve_abrupt_junction(**_TINY)
    except NameError as exc:              # the defect under test
        pytest.fail(f"the size check is unbound again: {exc}")
    except Exception as exc:
        # 2.12 is fixed, so a non-convergence here is a NEW regression, not the
        # long-standing one this test used to tolerate.
        pytest.fail(f"the potential-only solve no longer converges: {exc!r}")
    assert "v_bi_measured" in result


def test_a_solve_path_refuses_a_too_big_run_before_it_solves(monkeypatch):
    """The gate is on the path a real run takes, and it refuses, not crashes.

    Shrinking the implemented limit to a byte makes the refusal certain for any
    real grid, so this proves the refusal is reachable through the solve path
    without needing a genuinely huge mesh. If the call is missing or passes the
    wrong object, the failure is a NameError or a solve running anyway, and
    both show up here.
    """
    import mse_axisymmetric as ax

    # The limit is resolved INSIDE require_job_memory, so there is no module
    # attribute to shrink. Replace the function itself -- which also proves the
    # solve path calls the module-level name, rather than a local copy of it.
    seen = {}

    def _refuse(grid, **kwargs):
        seen["nodes"] = grid.n_nodes
        raise TooBigForJob(2 ** 40, 2 ** 30, grid.n_nodes, 0)

    def _counting_build(*a, **k):
        raise AssertionError("the device was built despite the refusal")

    monkeypatch.setattr(ax, "require_job_memory", _refuse)
    monkeypatch.setattr(ax, "_build_device", _counting_build)

    with pytest.raises(TooBigForJob):
        solve_abrupt_junction(**_TINY)
    # Reached the gate with the grid the solve would have used, and stopped
    # BEFORE the device existed: that is the whole point of pricing. The count
    # is NOT n_r*n_z -- build_grid refines the junction band, so the real grid
    # has more nodes. Assert it is a real grid the gate was handed, not that
    # it matches a formula build_grid does not use.
    assert seen["nodes"] > _TINY["n_r"] * _TINY["n_z"]
