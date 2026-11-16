"""The 3-D form against the axisymmetric one (task 2.7): solve-level tests.

These need devsim, so they run in the image (see the module docstring in
tests/test_dd_3d.py for the pure-Python mesh tests).

TWO QUANTITIES ARE COMPARED, and they test different things. V_bi (below) is
set by the contact boundary condition and n_i; it agrees between the forms to
six digits and, as the reviewer showed, survives a 5 % permittivity error
unchanged. It therefore proves the two forms are wired to the same junction,
not that the 3-D Poisson solve is right. The depletion WIDTH is the quantity
that comes out of the Poisson solve, and it is compared in
``test_the_two_forms_agree_on_the_depletion_width``.

Width was originally NOT compared here, on the grounds that the tet edges are
coarser through the junction than the axisymmetric form's refined band, so the
comparison would measure mesh resolution. That reasoning is correct -- but only
up to a threshold. MEASURED 2026-11-10 (1e16, eps_s=11.7), 3-D 10-90 % width
against the axisymmetric 2.603206e-07 m:

    edge_m     3-D width       difference from axisymmetric
    2.5e-7     1.9257e-07      26.0 %
    1.6e-7     1.8802e-07      27.8 %
    1.0e-7     2.5160e-07       3.35 %
    7.0e-8     2.5708e-07       1.24 %

There is a CLIFF, not a gradual approach: at 1.6e-7 and coarser the 3-D width
is SHORTER than the axisymmetric one (1.9e-7 against 2.6e-7), which is not
discretisation noise -- the depletion region is not being resolved at all, and
the mesher's thin sub-slabs set the answer. From 1e-7 down the difference is
shrinking (3.35 % -> 1.24 %) and heading for the axisymmetric answer, but two
points do not establish an order, so do not read a convergence rate into it.

So a width comparison measures physics only at edge_m <= 1e-7; above that it
is a mesh artefact. It is NOT, however, a sharp test even there: at 1e-7 the
3-D width still carries ~3.35 % of discretisation error, and that is larger
than most mutations one would want to catch (see the width test's docstring
for the measured margins). The test below runs at 1e-7.

Every tolerance below is stated with its reason at the assertion, because a
tolerance chosen to make two numbers match is not a test.
"""

import pytest

devsim = pytest.importorskip("devsim", reason="devsim lives in the image")

import mse_axisymmetric as ax  # noqa: E402

# A doping both forms resolve comfortably: the Debye length is well inside the
# device at 1e16, so neither solve is grid-starved.
N_A = 1.0e16
N_D = 1.0e16
N_I = 1.0e10
EPS_S = 11.7


def test_the_3d_form_measures_the_analytic_builtin_voltage():
    """The 3-D form must reproduce V_bi, which no mesh choice can fake.

    V_bi is an EQUILIBRIUM quantity: stage 1 fixes it and no later stage can
    move it. So this solves equilibrium-only and deliberately does not depend
    on stage 3, which on a coarse tet mesh is a separate open problem
    (tasks.md 2.7). Gating V_bi behind stage 3 would report a convergence
    failure as a physics failure.

    The 1 % tolerance is NOT tuned to a measurement. V_bi is a thermodynamic
    quantity fixed by the doping and n_i; any error beyond 1 % is a physics
    error, not a discretisation one.
    """
    r = ax.solve_layered_dd_3d(
        n_a=N_A, n_d=N_D, n_i=N_I, eps_s=EPS_S,
        radius_m=1.0e-6, z_lo=-1.0e-6, z_hi=1.0e-6, junction_z=0.0,
        edge_m=1.0e-7, equilibrium_only=True)
    ratio = r["v_bi_measured"] / r["v_bi_analytic"]
    assert abs(ratio - 1.0) < 0.01, (
        "3-D V_bi %.6f against analytic %.6f (ratio %.5f): beyond 1 %% is a "
        "physics error, not a mesh one"
        % (r["v_bi_measured"], r["v_bi_analytic"], ratio))


def test_both_forms_agree_on_the_builtin_voltage():
    """The agreement deliverable: two forms, one junction, same V_bi.

    The 3 % band is NOT measured -- it is a placeholder justified only by the
    argument that two 1 %-accurate forms cannot legitimately differ by more.
    An earlier version of this docstring claimed it was the sum of measured
    mesh-resolution differences; that was never measured. The test above
    holds each form to 1 % of analytic independently, so this one can only
    fail if they disagree with EACH OTHER.

    Both sides are read from EQUILIBRIUM. The 3-D form is asked for
    equilibrium only, because V_bi is fixed at stage 1 and the axisymmetric
    side's own stage 3 (which converges) is not what V_bi measures.
    """
    ax_r = ax.solve_abrupt_junction_dd(
        n_a=N_A, n_d=N_D, n_i=N_I, eps_s=EPS_S,
        z_lo=-1.0e-6, z_hi=1.0e-6, junction_z=0.0)
    d3_r = ax.solve_layered_dd_3d(
        n_a=N_A, n_d=N_D, n_i=N_I, eps_s=EPS_S,
        radius_m=1.0e-6, z_lo=-1.0e-6, z_hi=1.0e-6, junction_z=0.0,
        edge_m=1.0e-7, equilibrium_only=True)
    a = ax_r["v_bi_measured"]
    b = d3_r["v_bi_measured"]
    rel = abs(a - b) / abs(a)
    assert rel < 0.03, (
        "axisymmetric %.6f vs 3-D %.6f differ by %.2f %%, beyond the 3 %% "
        "placeholder band" % (a, b, 100 * rel))


def test_the_two_forms_agree_on_the_depletion_width():
    """The 3-D Poisson solve must put the junction in the right place (2.7).

    WHY THIS TEST EXISTS, in the lead's words: V_bi agreeing to six digits does
    not test the 3-D solve. V_bi is fixed by the contact boundary condition and
    n_i, and the reviewer showed that a 5 % permittivity error leaves it
    unchanged. The depletion width is the first quantity that has to come out
    of the Poisson solve itself, so it is the one that CAN in principle catch a
    wrong permittivity or a wrong doping. What it actually catches at this mesh
    is narrower than that, and the table below says which -- do not read the
    "can" as a claim that it does.

    THE TOLERANCE IS 5 %, AND IT IS A MESH-RESOLUTION BOUND, NOT A PHYSICS
    CLAIM. Measured at edge_m = 1e-7 (see the module docstring for the full
    sweep): the 3-D form gives 2.515978e-07 m against the axisymmetric
    2.603206e-07 m, a 3.35 % difference. The whole of that 3.35 % is
    discretisation -- refining to 7e-8 halves it to 1.24 %, straight
    convergence toward the axisymmetric answer. The window is 5 % so it stays
    ~1.5x above the measured discretisation error at the mesh this test runs
    at, and it would have to be widened if the mesh were coarsened.

    WHAT THIS CATCHES -- AND IT IS MUCH LESS THAN I FIRST CLAIMED. The margin
    is measured on the SAME quantity this test asserts, rel(w_3d, w_ax), not on
    the 3-D width's own shift (an earlier version of this docstring quoted the
    self-shift, which is a different and larger number):

        mutation                rel(3d, ax)   vs the 5 % window
        (none)                     3.35 %     passes
        eps_s +5 %                 2.08 %     passes -- see WHY below
        n_d  +5 %                  6.22 %     fails
        n_d  x2                    5.32 %     fails, by 0.32 points
        n_d  x0.1                  1.02 %     passes
        na, nd both x0.8           1.76 %     passes
        na, nd both x1.2           2.98 %     passes

    So the only mutation this reliably catches is a large UPWARD error in n_d.
    A downward doping error, scaled doping, and a permittivity error all slide
    under the band. At this fixture n_a == n_d, so swapping them is a no-op and
    the test could never catch that either.

    WHY THE PERMITTIVITY MUTATION IS NOT CAUGHT: CANCELLATION, NOT DROWNING.
    A 5 % eps_s error raises the 3-D width from 2.515978e-07 to 2.611917e-07,
    i.e. TOWARD the axisymmetric 2.603206e-07, so the ratio FALLS from 3.35 %
    to 2.08 %. The discretisation error and the permittivity error point the
    same way and partly cancel. No window can catch it: catching it would need
    < 2.08 %, which the clean 3.35 % already fails. This is a coincidence of
    sign at this mesh, not a general property -- if a mesh change flips it, the
    mutant becomes catchable and the window was never chosen for that.

    Permittivity stays covered by the axisymmetric width test, which pins a
    0.5 % window on a mesh where the signal is resolvable. Do not treat this
    test as a permittivity check, and do not rest anything on its doping
    coverage beyond a gross upward n_d error.
    """
    ax_r = ax.solve_abrupt_junction_dd(
        n_a=N_A, n_d=N_D, n_i=N_I, eps_s=EPS_S,
        z_lo=-1.0e-6, z_hi=1.0e-6, junction_z=0.0)
    d3_r = ax.solve_layered_dd_3d(
        n_a=N_A, n_d=N_D, n_i=N_I, eps_s=EPS_S,
        radius_m=1.0e-6, z_lo=-1.0e-6, z_hi=1.0e-6, junction_z=0.0,
        edge_m=1.0e-7, equilibrium_only=True)
    w_ax = ax_r["w_measured"]
    w_3d = d3_r["w_measured"]
    rel = abs(w_ax - w_3d) / w_ax
    assert rel < 0.05, (
        "axisymmetric 10-90%% width %.6e m vs 3-D %.6e m differ by %.2f %%, "
        "beyond the 5 %% mesh-resolution band (measured 3.35 %% at this mesh). "
        "See the docstring for exactly which mutations this catches (a large "
        "upward n_d error) and which it cannot (permittivity, which CANCELS "
        "into agreement here, and any downward doping error)."
        % (w_ax, w_3d, 100 * rel))


def test_the_3d_form_refuses_an_oversize_mesh_before_solving():
    """2.5's refusal must stay live on the 3-D path.

    A limit of one byte makes every real mesh too big, which is the cheapest
    way to prove the check runs BEFORE the device is built: if it ran after,
    the solve would raise EquilibriumNotReached (or take minutes) instead of
    TooBigForJob.
    """
    with pytest.raises(ax.TooBigForJob):
        ax.solve_layered_dd_3d(
            n_a=N_A, n_d=N_D, n_i=N_I, eps_s=EPS_S,
            radius_m=1.0e-6, z_lo=-1.0e-6, z_hi=1.0e-6, junction_z=0.0,
            edge_m=1.0e-7, limit_bytes=1)
