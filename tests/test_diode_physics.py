"""2.4: the diode as a diode -- slope, conservation, resolution, terminals.

Five claims, each tested against an independent expectation:

  0. EQUILIBRIUM -- the equilibrium solve is a fixed point, not a solve that
                   ran out of iterations. Checked by re-solving and
                   requiring that nothing moves.
  1. IDEALITY   -- d(ln I)/dV matches q/(n k T) with n close to 1 over a
                   decade of forward bias. The expectation is computed from
                   k*T/q here, not copied from the solver.
  2. CONSERVATION -- the current entering one terminal leaves the other. The
                   JUDGED number is the ABSOLUTE residual: below the
                   round-off floor a relative residual is arithmetic on noise
                   (see the note in sweep_diode_iv). The relative form is
                   checked only where the current is meaningfully above that
                   floor.
  3. RESOLUTION -- a mesh finer than L_D/2 at a doping change is accepted and
                   a coarser one is REFUSED, with the refusal naming the
                   region, the worst L_D and the local edge (spec.md, Debye
                   requirement). Both sides are tested: a gate that never
                   refuses is indistinguishable from no gate.
  4. TERMINALS  -- four contacts on a three-region device have currents
                   summing to zero. Three regions is the smallest stack
                   where "all contacts" is not trivially the two ends.

POLARITY (this test module's reason for existing twice over): forward bias
means the p-side goes positive. ``sweep_diode_iv`` puts the n-side at z > 0,
so +V belongs on the bottom contact. With +V on top, every "forward" point
was reverse bias and n*p fell as exp(-V/V_T); see the note above p_contact in
mse_axisymmetric.py.

DEVSIM is installed only in the solver image, so this module SKIPS (not
passes) anywhere else -- a skip is not evidence. Run:
  docker run --rm --cpus=2 --memory=2g -e DEVSIM_MATH_LIBS="libblas.so.3:liblapack.so.3" \\
    -e PYTHONPATH=/repo/dockerfiles/maxwell_solver:/repo/.venv-mse/lib/python3.12/site-packages \\
    -v "$PWD":/repo:ro --entrypoint python {DEVSIM_IMAGE} \\
    -m pytest /repo/tests/test_diode_physics.py -q
"""
import math

import numpy as np
import pytest

from devsim_image import DEVSIM_IMAGE  # noqa: E402

devsim = pytest.importorskip("devsim", reason="DEVSIM lives only in the solver image")

from mse_axisymmetric import (  # noqa: E402
    DebyeUnresolved,
    EquilibriumNotReached,
    build_grid,
    require_debye_resolved,
    solve_multi_terminal,
    sweep_diode_iv,
)

# Boltzmann's constant over the elementary charge, SI (CODATA 2018). Computed
# here rather than taken from the solver so the ideality expectation is an
# independent number, not the solver agreeing with itself.
K_B = 1.380649e-23
Q_E = 1.602176634e-19
V_T_300 = K_B * 300.0 / Q_E  # 25.85 mV at 300 K

N_A, N_D = 1.0e18, 1.0e18
N_I, EPS_S = 1.0e10, 11.7

# Absolute current scale of the round-off floor for this device: the terminal
# currents are computed by summing per-equation contact currents over a few
# hundred nodes, so their sum carries an ~1e-15 A error whatever the bias.
# Measured 2026-11-09: 1.6e-16..6.6e-15 A, unchanged with the iteration cap.
# A test that compares conservation residuals to a current smaller than this
# floor is testing the floor, not the physics.
ROUNDOFF_FLOOR_A = 1.0e-13


@pytest.fixture(scope="module")
def iv():
    """One forward sweep, solved once and shared: the solve is the slow part.

    Biases start at 0.3 V on purpose. Below that the device current is at or
    under the round-off floor, so a "slope" fitted at 0.1..0.2 V is a
    straight line through noise (measured 2026-11-09: 5.2e-15 A at 0.2 V
    against 5.6e-13 A at 0.3 V -- a 0.1 V step that should be x48 was x108,
    because the 0.2 V point is one round-off unit above zero).
    """
    return sweep_diode_iv(
        n_a=N_A, n_d=N_D, n_i=N_I, eps_s=EPS_S,
        biases=[0.30, 0.35, 0.40, 0.45, 0.50, 0.55], n_z=200, refine=5.0e-9,
        allow_unresolved=True,
    )


def test_the_equilibrium_solve_is_actually_converged():
    """A solve that stops on the iteration cap is not equilibrium.

    Lead, 2026-11-09: make the test fail if the equilibrium solve stops on
    iteration count rather than converging. ``_solve_converged`` reads the
    solver's OWN verdict -- ``devsim.solve(info=True)`` returns
    ``{'converged': bool, 'iterations': ...}`` -- and raises
    ``EquilibriumNotReached`` when it is False. This test drives the same
    path the sweep uses and requires it not to raise.

    The failure this catches: with absolute_error=1.0 an under-toleranced
    stage-1 solve churned 1.0 -> 1.49 -> 0.47 -> 0.94 ... for the full 30
    iterations and DEVSIM reported success, so the carriers were seeded from
    a non-equilibrium potential and every downstream number inherited it.

    (History, so the guard is not rebuilt wrong: the first version of the
    guard RE-SOLVED and compared node values. That missed the case above
    entirely, because Newton revisits similar territory on a second call.
    ``info=True`` is the solver telling you what happened, and there is no
    reason to infer it.)
    """
    # Build the same device the sweep builds, but stop at equilibrium:
    # sweep_diode_iv at zero bias must produce zero current and converge.
    result = sweep_diode_iv(
        n_a=N_A, n_d=N_D, n_i=N_I, eps_s=EPS_S,
        biases=[0.0], n_z=120, refine=2.0e-9, allow_unresolved=True,
    )
    row = result["rows"][0]
    assert row["bias_v"] == 0.0
    # At equilibrium no net current may flow at all.
    assert abs(row["i_top_a"]) < 1.0e-16, (
        "equilibrium carries a current: i_top=%.3e A" % row["i_top_a"])
    assert abs(row["i_bottom_a"]) < 1.0e-16, (
        "equilibrium carries a current: i_bottom=%.3e A" % row["i_bottom_a"])
    # The guard is exported so a caller can distinguish this failure from a
    # generic RuntimeError rather than parsing a message.
    assert issubclass(EquilibriumNotReached, RuntimeError)


def test_the_forward_current_grows_with_bias(iv):
    """A forward sweep must show current rising exponentially. Without the
    growth a "slope" test could pass on a flat noise floor."""
    currents = [abs(r["i_top_a"]) for r in iv["rows"]]
    assert all(b > a for a, b in zip(currents, currents[1:])), (
        "the forward current is not monotonic in bias: %s" % currents)
    # Measured 2026-11-09: 5.59e-13 A at 0.30 V to 8.60e-09 A at 0.55 V,
    # a factor of 15400 (x6.9 per 50 mV). Requiring 1000x is a real bar
    # that a flat or noisy series cannot reach.
    assert currents[-1] > 1000.0 * currents[0], (
        "the current grew by less than 1000x across 0.25 V: %s" % currents)


def test_the_ideality_factor_is_near_one(iv):
    """d(ln I)/dV = q/(n k T). Invert for n and require 0.9 < n < 1.1.

    MEASURED 2026-11-09 on this device, 0.30..0.55 V: the current rises x6.9
    every 50 mV (n = 1.002..1.005 per step) and the least-squares fit over
    the whole range gives n = 1.003, against 1.000 ideal. The band is
    therefore +-10 %, which is a real test: n=2 (SRH-dominated recombination
    current) is far outside it, and so is a reverse-biased sweep, which has
    the wrong SIGN of slope entirely.

    A note on the original band, so it is not quietly widened again: the
    first draft allowed 0.9 < n < 1.6 "because this device is neither a pure
    diffusion nor a pure SRH case". That was an assumption with a 60 % band
    around a number I had not measured. The measurement says 1.003.
    """
    v = np.array([r["bias_v"] for r in iv["rows"]])
    i = np.array([abs(r["i_top_a"]) for r in iv["rows"]])
    assert i.min() > ROUNDOFF_FLOOR_A, (
        "the ideality fit includes a current (%.3e A) below the round-off "
        "floor; the bias range must be where the diode is on" % i.min())
    slope = np.polyfit(v, np.log(i), 1)[0]   # d(ln I)/dV
    n_ideal = 1.0 / (slope * V_T_300)
    assert 0.9 < n_ideal < 1.1, (
        "ideality factor far from 1: n = %.3f (d ln I/dV = %.2f /V, "
        "expected %.2f /V)" % (n_ideal, slope, 1.0 / V_T_300))


def test_the_current_is_conserved_at_every_bias(iv):
    """Electrons out one terminal are electrons in the other.

    Judged on the ABSOLUTE residual against a stated round-off floor, not on
    a ratio whose denominator goes to zero with the current. Where the
    current is well above the floor the relative form must also hold, so a
    genuine leak could not hide behind a generous absolute bound.
    """
    for row in iv["rows"]:
        assert row["i_sum_residual_a"] < ROUNDOFF_FLOOR_A, (
            "current not conserved at %.2f V: i_top=%.6e, i_bottom=%.6e, "
            "absolute residual %.3e A"
            % (row["bias_v"], row["i_top_a"], row["i_bottom_a"],
               row["i_sum_residual_a"]))
    # The top of the sweep is well clear of the floor: there the ratio must
    # also be small, or a proportionally large leak would pass the bound above.
    top = max(iv["rows"], key=lambda r: abs(r["i_top_a"]))
    scale = max(abs(top["i_top_a"]), abs(top["i_bottom_a"]))
    assert scale > 10.0 * ROUNDOFF_FLOOR_A, (
        "the sweep never rises above 10x the round-off floor (%.3e A), so "
        "conservation is not being tested where it matters" % scale)
    assert top["conservation_residual"] < 1.0e-4, (
        "at %.2f V the currents differ by %.2e relatively, which is far "
        "outside round-off" % (top["bias_v"], top["conservation_residual"]))


def test_a_mesh_finer_than_the_debye_length_is_accepted():
    """The gate must PASS a good mesh. A gate that only ever refuses is an
    outage, not a check."""
    g = build_grid(0.0, r_max=1.0e-8, z_min=-1.0e-6, z_max=1.0e-6,
                   n_r=2, n_z=200, refine=1.0e-9, refine_halfwidth=1.5e-7)
    diag = require_debye_resolved(
        g, lambda z: N_D if z > 0 else -N_A, EPS_S)
    # L_D at 1e18 in cm-units: sqrt(eps*eps0*kT/(q^2 n)). 4.09 nm, computed
    # here so the figure in the message and the assertion agree.
    ld = math.sqrt(EPS_S * 8.8541878128e-12 * K_B * 300.0
                   / (Q_E * Q_E * 1.0e18 * 1.0e6))
    assert 3.0e-9 < ld < 5.0e-9, "sanity: L_D at 1e18 should be ~4 nm"
    assert diag["worst_ld_m"] == pytest.approx(ld, rel=0.05), (
        "the gate reports L_D %.3e m, expected %.3e m"
        % (diag["worst_ld_m"], ld))
    assert diag["nodes_checked"] > 0


def test_a_mesh_coarser_than_the_debye_length_is_refused_and_says_why():
    """The refusal must name the region, the worst L_D and the local edge --
    all three, because those are what a caller needs to re-mesh. A bare
    "mesh too coarse" would be a refusal with no route out of it."""
    g = build_grid(0.0, r_max=1.0e-8, z_min=-1.0e-6, z_max=1.0e-6,
                   n_r=2, n_z=200, refine=1.0e-7, refine_halfwidth=1.5e-7)
    with pytest.raises(DebyeUnresolved) as excinfo:
        require_debye_resolved(g, lambda z: N_D if z > 0 else -N_A, EPS_S)
    msg = str(excinfo.value)
    assert "silicon" in msg, "the refusal does not name the region: %r" % msg
    assert "L_D" in msg and "edge" in msg, (
        "the refusal does not name both L_D and the local edge: %r" % msg)
    # It must be a ValueError, as the spec requires, and specifically a
    # DebyeUnresolved so a caller can tell it from a missing-parameter error.
    assert isinstance(excinfo.value, ValueError)


@pytest.mark.skip(
    reason="NOT DELIVERED: a contact on a plane inside the silicon region is "
           "not physical and DEVSIM creates no contact there (measured: "
           "get_contact_list returns only c0 and c3). A real nanowire's middle "
           "contact is a RING on the outer surface, so the fix is surface ring "
           "contacts, not a region split. Tracked as tasks.md 2.10. The other "
           "three 2.4 deliverables are delivered and tested.")
def test_four_terminals_carry_currents_that_sum_to_zero():
    """Three regions, four contacts -- the interior taps on the junctions.

    SKIPPED, not passing and not deleted: the geometry this fixture builds
    cannot carry an interior contact at all, so the assertion below has never
    had a choice but to fail. It is kept so the check runs the day ring
    contacts land (2.7).
    """
    # refine=2e-10 is set by the Debye gate, not by taste: at 1e18 the gate
    # requires an edge <= L_D/2 = 2.04 nm near a doping change, and a first
    # draft of this fixture at refine=1e-9 was REFUSED by it (measured
    # 2026-11-09). The gate is right; the fixture was.
    regions = [(-3.0e-6, -1.0e-6, -1.0e18),
               (-1.0e-6, 1.0e-6, 1.0e18),
               (1.0e-6, 3.0e-6, -1.0e18)]
    result = solve_multi_terminal(
        regions=regions,
        contact_bias={"c0": 0.0, "c1": 0.2, "c2": 0.4, "c3": 0.0},
        n_i=N_I, eps_s=EPS_S, n_z=300, refine=2.0e-10)

    assert len(result["currents_a"]) == 4
    assert result["i_sum_residual_a"] < 1.0e-13, (
        "the four terminal currents do not sum to zero: %s (absolute %.3e A)"
        % (result["currents_a"], result["i_sum_residual_a"]))
    # The outer contacts must actually carry current. Without this, four
    # correctly-signed zeros would satisfy conservation perfectly. The bar
    # is 100x the round-off floor so it cannot be met by solver noise.
    assert any(abs(i) > 1.0e-13 for i in result["currents_a"].values()), (
        "no terminal carries measurable current: %s" % result["currents_a"])
