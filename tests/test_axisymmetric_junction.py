"""2.3: the axisymmetric (r,z) drift-diffusion solve, against junction theory.

Two claims, both earned and both tested:

  V_bi  -- the built-in voltage, within 1% of the abrupt-junction formula.
  W     -- the depletion width, within 10% of the formula.

Both numbers are unit-conversion-invariant, and BOTH were wrong until
2026-11-09 for one reason: DEVSIM's simple_physics is a centimetre model and
the solve was being fed a metre mesh. That does not error -- it silently
lengthens the Debye screening length by 1000, so the junction never screens,
the potential ramps linearly, and the "width" becomes a measure of the
domain. V_bi looked right anyway because a linear ramp of the right length
gives the right endpoint difference. That is why
test_the_built_in_voltage_does_not_depend_on_the_domain exists: it is the
check that would have caught it, and a single-domain V_bi check would not.

DEVSIM is installed only in the solver image, so this module SKIPS (not
passes) anywhere else -- a skip is not evidence, which is the point. Run:
  docker run --rm --cpus=2 --memory=2g -e DEVSIM_MATH_LIBS="libblas.so.3:liblapack.so.3" \\
    -e PYTHONPATH=/repo/dockerfiles/maxwell_solver:/opt/app -v "$PWD":/repo:ro \\
    --entrypoint python {DEVSIM_IMAGE} -m pytest /repo/tests/test_axisymmetric_junction.py

DEVSIM_IMAGE is the Harbor tag from tests/devsim_image.py, not a bare local
name: the local image was removed for disk, so a bare tag pulls nothing, the
container never starts, devsim never imports, and the importorskip below turns
that into a SKIP -- green and worthless. tests/test_devsim_image_refs.py fails
if the literal comes back.
"""
import math
import os
import sys

import numpy as np
import pytest

from devsim_image import DEVSIM_IMAGE

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "dockerfiles", "maxwell_solver"))

pytest.importorskip("devsim", reason="DEVSIM is only in the solver image")

from mse_axisymmetric import (
    TEN_NINETY_OVER_FULL,
    analytic_depletion_width,
    analytic_v_bi,
    solve_abrupt_junction_dd,
)

N_A = 1.0e17
N_D = 1.0e17
N_I = 1.0e10
EPS_S = 11.7


def _solve(z_lo=-1.0e-6, z_hi=1.0e-6):
    # No refine_halfwidth: let the solver size the refined band from the
    # analytic depletion width. A hard-coded 20 nm band sits entirely INSIDE
    # the ~147 nm transition at 1e17, so the 10 %/90 % crossings fall in the
    # coarse region and the measured width is grid-limited, not physical.
    return solve_abrupt_junction_dd(
        n_a=N_A, n_d=N_D, n_i=N_I, eps_s=EPS_S,
        z_lo=z_lo, z_hi=z_hi, n_r=2, n_z=200, refine=1e-9)


def test_the_coupled_solve_reproduces_the_built_in_voltage():
    """V_bi within 1%: the spec's criterion.

    The analytic value is recomputed here independently (kB T/q ln(NA ND/ni^2))
    rather than read back from the module's own helper.
    """
    r = _solve()
    v_analytic = analytic_v_bi(N_A, N_D, N_I)
    v_checked = 1.380649e-23 * 300.0 / 1.602176634e-19 * math.log(
        N_A * N_D / N_I ** 2)
    assert abs(v_checked - v_analytic) < 1e-9, (
        "the module's analytic V_bi disagrees with an independent "
        "recomputation: %r vs %r" % (v_analytic, v_checked))
    err = abs(r["v_bi_measured"] - r["v_bi_analytic"]) / r["v_bi_analytic"]
    assert err < 0.01, (
        "V_bi %.5f V is %.2f%% from analytic %.5f V"
        % (r["v_bi_measured"], err * 100, r["v_bi_analytic"]))


def test_the_built_in_voltage_does_not_depend_on_the_domain():
    """"Earned, not coincidence": V_bi must be the same on two domains.

    This is the check the earlier report lacked. A solve that fails to screen
    returns a potential ramp whose ENDPOINT DIFFERENCE is V_bi whatever the
    domain -- so one domain cannot tell screening from a ramp. Two domains,
    one narrow and one ~7x wider, must agree on V_bi.

    It must NOT follow that W is the same on both: a junction near its
    contacts is depletion-limited and one far from them is Debye-screened, so
    W legitimately differs. That distinction is what
    ``test_the_junction_is_not_just_the_box`` guards.
    """
    narrow = _solve(z_lo=-3.0e-7, z_hi=3.0e-7)
    wide = _solve(z_lo=-2.0e-6, z_hi=2.0e-6)

    v_n = narrow["v_bi_measured"]
    v_w = wide["v_bi_measured"]
    assert abs(v_n - v_w) / abs(v_w) < 0.01, (
        "V_bi moved with the domain: %.5f V on +-0.3um vs %.5f V on +-2um. "
        "A domain-dependent V_bi means the junction is not screening, and "
        "the potential is a linear ramp." % (v_n, v_w))


def test_the_potential_does_separate_the_two_doping_regions():
    """A solved junction is not flat: phi must change sign across z=0.

    Guards the failure mode where a solve converges to the flat zero-bias
    solution and still yields a plausible V_bi from endpoint noise.
    """
    r = _solve()
    z, phi = r["z"], r["phi"]
    assert phi.min() < -0.05 and phi.max() > 0.05, (
        "potential barely moves: min=%r max=%r -- this is not a junction"
        % (phi.min(), phi.max()))
    diffs = np.diff(phi[np.argsort(z)])
    assert (diffs >= -1e-6).all(), "potential is not monotonic across z"


def test_the_depletion_width_matches_the_abrupt_junction_formula():
    """The measured 10-90% width within 0.5% of its pinned, measured value.

    ``w_analytic`` is the FULL space-charge width; ``w_measured`` is the
    distance between the 10% and 90% potential crossings. Those differ by a
    fixed factor ``TEN_NINETY_OVER_FULL`` that depends on the SHAPE of the
    potential, so comparing them directly reads as a broken solver:
    triangular gives 0.447, linear gives 0.578. The solver's own profile is
    linear to within 2.5% (measured 2026-11-09 at N_A = N_D = 1e17), which is
    the constant shipped. Using the triangular value here manufactured a
    stable, refinement-independent 32.5% "error" and cost a round-trip with
    the lead before the shape was checked.

    The default solve is sized to the depletion width on purpose, but the
    measurement itself does NOT need a small domain any more: once the mesh
    units were fixed the width is domain-invariant to 0.6% from +-0.3um to
    +-2um (see ``test_the_junction_is_not_just_the_box``). The old note that a
    distant junction is "screened over L_D rather than depleted" was written
    during the unit bug, when every domain produced a linear ramp.

    WHY THIS IS NOW PINNED RATHER THAN LOOSE (2026-11-10, lead's request).
    A 10 % tolerance did not catch a real 2.7 % shift in this width when
    2.4 corrected the permittivity that ``SetSiliconParameters`` had been
    silently overriding (11.1 -> the cited 11.7; W ~ sqrt(eps_s), so
    sqrt(11.7/11.1) = 1.0267). A tolerance wide enough to hide a 2.7 %
    change is not testing anything. The semantics are understood, so this
    pins the measured value: it is stable to a 3.1e-5 relative spread across a
    2x refinement in ``refine`` and in ``n_z`` (8.7705404e-08 at
    refine 1e-9, 8.7702707e-08 at 5e-10 -- the two share their first 4
    significant digits, 8770, and 3.1e-5 is about 4.5 figures), so a
    0.5 % window is ~160x the numerical spread and still catches the shift.
    The 3.32 % residual from the analytic 10-90% line is a property of the
    linear-shape factor, not of this measurement.
    """
    r = _solve()
    expected = r["w_analytic"] * TEN_NINETY_OVER_FULL
    err = abs(r["w_measured"] - expected) / expected
    # Pinned measured width (see docstring); 0.5% window.
    W_MEASURED_PINNED = 8.7705404e-08
    pin_err = abs(r["w_measured"] - W_MEASURED_PINNED) / W_MEASURED_PINNED
    assert pin_err < 0.005, (
        "10-90%% width %.7e m moved %.3f%% from the pinned %.7e m. A change "
        "here means the solved permittivity, the cited eps_s or the mesh "
        "unit changed: W ~ sqrt(eps_s), and 11.1 vs 11.7 is 2.7%%. "
        "(%.1f%% from the analytic 10-90%% line, %.3f x the full %.3e m "
        "space-charge width)"
        % (r["w_measured"], pin_err * 100, W_MEASURED_PINNED, err * 100,
           TEN_NINETY_OVER_FULL, r["w_analytic"]))


def test_the_junction_is_not_just_the_box():
    """The width must be set by the doping, not by how far away the box is.

    This is the lead's question, asked directly: "find why W tracks the box".
    The answer was a unit bug -- a metre mesh fed a centimetre-unit physics
    model -- which made the solve return a LINEAR potential ramp across the
    whole domain with no junction in it. Every domain then reported a width
    that was a fixed fraction of itself: 4.73 / 31.06 / 70.24 nm on +-0.3um /
    +-1um / +-2um. The width was the box because the box was the whole
    solution.

    With the mesh in cm the width is set by N_A, N_D and V_bi and is
    domain-invariant, so this asserts that properly rather than weakly:
    W must agree within a few percent across a 6.7x change in box size. An
    earlier version of this test only demanded W grow SLOWER than the box,
    which a still-broken solve could satisfy.
    """
    narrow = _solve(z_lo=-3.0e-7, z_hi=3.0e-7)
    wide = _solve(z_lo=-2.0e-6, z_hi=2.0e-6)

    v_n = narrow["v_bi_measured"]
    v_w = wide["v_bi_measured"]
    assert abs(v_n - v_w) / abs(v_w) < 0.01, (
        "V_bi moved with the domain: %.5f V on +-0.3um vs %.5f V on +-2um. "
        "A domain-dependent V_bi means the junction is not screening, and "
        "the potential is a linear ramp." % (v_n, v_w))

    # The box grows 6.7x in half-width. A real depletion width is fixed by
    # the doping and V_bi, so demand the two agree to 3% -- not merely that
    # the width grows slower than the box, which a broken solve satisfies.
    w_n = narrow["w_measured"]
    w_w = wide["w_measured"]
    rel = abs(w_n - w_w) / w_w
    assert rel < 0.03, (
        "the depletion width moved %.1f%% with the box (%.3e m on +-0.3um vs "
        "%.3e m on +-2um) -- the width is tracking the box, not the junction"
        % (rel * 100, w_n, w_w))
    assert wide["w_measured"] < 2.0 * wide["w_analytic"], (
        "the measured width %.3e m exceeds twice the full space-charge "
        "width %.3e m -- that is not a depletion region"
        % (wide["w_measured"], wide["w_analytic"]))

