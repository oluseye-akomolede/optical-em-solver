"""Task 2.12: the potential-only junction converges, and V_bi agrees with DD.

The task as written asks for two agreements: V_bi AND depletion width. Only
the first is achievable, and the reason is physics rather than an unfinished
fix -- these tests record the difference so a future reader does not try to
"finish" the width.

WHAT WAS ACTUALLY WRONG (measured 2026-11-11)
=============================================
The failure was not a tolerance or scheduling problem. With the function's own
defaults the solve stalled at AbsError 4.09097e-01 -- exactly V_bi/2 -- for
every one of its 800 iterations, and a bias ramp in 0.05 V steps stalled at the
same place. A staging fix therefore cannot work.

The cause was the units of the fixed space charge. ``SpaceCharge`` was
``q * NetDoping * 1e6`` under a comment claiming the geometry is SI; the
``1e6`` inflated the charge by a million. Dropping it converges in ~9 Newton
steps to RelError 5e-14. The sweep that established this, other things equal:

    Permittivity=F/m,  charge=q*N      -> converged, span 0.8334 V   <-- taken
    Permittivity=F/m,  charge=q*N*1e6  -> FAIL
    Permittivity=F/cm, charge=q*N      -> converged, span 36.98 V  (wrong)
    Permittivity=F/cm, charge=q*N*1e6  -> FAIL

Only (F/m, q*N) both converges and lands on the analytic V_bi. Note this means
the potential-only builder and the coupled ``_build_dd_device`` (which sets
Permittivity from ``EPS0_CM``) are not on one unit system; unifying them was
left alone deliberately, because ``EPS0_CM`` is what the validated 2.3 numbers
were calibrated with and changing it needs that suite's numbers re-derived.

WHY THE WIDTH IS NOT A RESULT
=============================
Without electron/hole continuity there are no mobile carriers, so nothing
screens the field: the potential ramps across the whole domain instead of
flattening past the depletion edges. The far-field slope measured 3.0e5 V/m
where the coupled solve plateaus, and w_measured reads 1.82e-6 m against the
coupled 8.77e-8 m on the identical domain. The number is returned (a memory
gate uses it as a cheap fixture) but it is not physics.
"""

from __future__ import annotations

import pytest

from mse_axisymmetric import (
    analytic_v_bi,
    solve_abrupt_junction,
    solve_abrupt_junction_dd,
)

# The defaults the task names as failing. Explicit here so the regression is
# pinned to the input that actually reproduced.
_NA, _ND, _NI = 1.0e17, 1.0e17, 1.0e10


@pytest.fixture(scope="module")
def po_result():
    return solve_abrupt_junction(n_a=_NA, n_d=_ND, n_i=_NI)


def test_the_potential_only_solve_converges_with_its_own_defaults(po_result):
    """The 2.12 regression itself.

    Before the fix this raised ConvergenceError after 800 stalled iterations.
    The assertion is deliberately on a RESULT rather than on "does not raise":
    a solve that silently returned a half-converged profile would satisfy
    "does not raise" while being exactly the bug.
    """
    assert po_result["v_bi_measured"] == pytest.approx(
        analytic_v_bi(_NA, _ND, _NI), rel=1e-6), (
        "V_bi is not the value the contact condition implies -- the solve did "
        "not actually reach equilibrium")


def test_v_bi_agrees_with_the_coupled_dd_solve(po_result):
    """The agreement the task asks for that IS achievable.

    V_bi is set entirely by the contact boundary condition and is therefore a
    stage-1 quantity that the extra carrier equations cannot change. The
    tolerance is 0.5 % because the coupled solve carries the same contact
    condition on a slightly different mesh (2272 nodes vs 1120).
    """
    dd = solve_abrupt_junction_dd(n_a=_NA, n_d=_ND, n_i=_NI)
    a, b = po_result["v_bi_measured"], dd["v_bi_measured"]
    rel = abs(a - b) / abs(b)
    assert rel < 5e-3, (
        f"V_bi disagrees between the equilibrium solve ({a:.6f} V) and the "
        f"coupled solve ({b:.6f} V): {rel:.2e} relative")


def test_the_width_is_reported_but_is_not_a_depletion_width(po_result):
    """The half of the task that is not achievable, asserted as such.

    This is not a tolerance left loose -- it asserts the measured failure of
    the width criterion and says why. If someone later adds carriers to this
    path and the width becomes real, this test SHOULD fail, and the docstring
    is the instruction for what to change.
    """
    dd = solve_abrupt_junction_dd(n_a=_NA, n_d=_ND, n_i=_NI)
    ratio = po_result["w_measured"] / dd["w_measured"]
    assert ratio > 5.0, (
        "the equilibrium solve's transition width is now comparable to the "
        f"coupled solve's (ratio {ratio:.2f}). That would mean the "
        "potential-only path has carrier screening it should not have -- "
        "re-read this module's docstring before relaxing this assertion")


def test_the_solve_still_reports_the_profile_for_comparison(po_result):
    """A result without the profile cannot be compared sample-by-sample.

    ``solve_abrupt_junction_dd`` returns ``z`` (metres) and ``phi`` (volts);
    the equilibrium solver used to return neither, so the V_bi agreement above
    could only be checked through a summary number.
    """
    z, phi = po_result["z"], po_result["phi"]
    assert len(z) == len(phi) > 100
    # The domain is ±1 µm. The outermost NODE sits just inside it (measured
    # 9.83e-7 m), so this asserts the ORDER OF MAGNITUDE, not the endpoint: a
    # solver that leaked the mesh's cm axis through would report ~1e-4, which
    # is what this is here to catch. Pinning it to exactly 1e-6 would be a
    # test about where the mesher puts its last node, not about units.
    assert 5.0e-7 < max(abs(z[0]), abs(z[-1])) < 2.0e-6, (
        f"z spans ±{abs(z[-1]):.3g} m, which is not a micrometre-scale "
        "domain -- the metres conversion is wrong")
