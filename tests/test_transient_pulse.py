"""Task 2.8: the transient solver's recombination sign, and the honest record.

WHAT THIS FILE DOES AND DOES NOT ESTABLISH
==========================================
It establishes the SIGN of the recombination rate, which was inverted on the
first pass and is cheap to keep right. It does NOT establish a charge balance:
the identity ``int I dt = dQ + q int R dt`` does not close on this device, and
no test here pretends otherwise. See the 2.8 entry in tasks.md for the measured
state and for what remains unsolved.

THE SIGN (fixed 2026-11-11)
===========================
``simple_physics.CreateSRH`` line 257 is ``USRH = (np - n_i^2) / (...)``, so a
POSITIVE value means the device has excess pairs and they are RECOMBINING. The
first implementation returned ``-sum(USRH*volume)`` and its docstring claimed
positive USRH meant generation, so both the doc and the code were inverted and
the solver reported generation on a device that was recombining.

The trap is the model name: DEVSIM calls it ``ElectronGeneration``, but that
model is ``-q*USRH`` -- the sign belongs to the continuity term, not to USRH.
Anchor any future edit at the formula, never at the name.

MUTATION-PROVED: flipping the return back to ``-float(np.sum(...))`` in
``_recombination_per_second`` fails ``test_recombination_is_positive_at_forward_bias``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dockerfiles" / "maxwell_solver"))

devsim = pytest.importorskip("devsim")
mx = pytest.importorskip("mse_axisymmetric")

# A coarse mesh and one short run: this is a SIGN test, not a physics
# validation, so it must stay cheap enough for the VM tier.
_DEVICE = dict(n_a=1e17, n_d=1e17, n_i=1e10, z_lo=-3.0e-7, z_hi=3.0e-7,
               n_r=2, n_z=120, refine=1.0e-9, refine_halfwidth=5.0e-8)
_V_FWD = 0.30


def _run_isolated(body: str) -> str:
    """Run ``body`` in a fresh interpreter and return its combined output.

    DEVSIM's mesh registry is process-global: a second ``transient_pulse``
    call in one process dies with ``A mesh already exists with name "axtr"``.
    That is not a solver defect, but it means two solver tests in one pytest
    process cannot both pass -- the first leaves the mesh behind and the
    second raises the wrong exception class, which reads as a product bug.
    It also cost a real measurement once: a dt sweep printed those tracebacks
    and they were read as result rows, producing a false "the integral is
    constant across dt" claim.

    ``pytest-forked`` is not installed in the solver image, so isolation is
    explicit. Failing loudly here is better than order-dependent greens.
    """
    import os
    import subprocess
    import sys as _sys

    prelude = (
        "import sys\n"
        f"sys.path.insert(0, {str(ROOT / 'dockerfiles' / 'maxwell_solver')!r})\n"
        "import devsim\n"
        "import mse_axisymmetric as mx\n"
        "DEVICE = dict(n_a=1e17, n_d=1e17, n_i=1e10, z_lo=-3e-7, z_hi=3e-7,\n"
        "              n_r=2, n_z=120, refine=1e-9, refine_halfwidth=5e-8)\n"
        "V_FWD = 0.30\n"
    )
    proc = subprocess.run([_sys.executable, "-c", prelude + body],
                          capture_output=True, text=True, timeout=600,
                          env=dict(os.environ))
    return proc.stdout + proc.stderr


def test_recombination_is_positive_at_forward_bias():
    """At forward bias the device recombines, so the returned rate is > 0.

    A forward-biased junction has ``np > n_i^2`` -- measured 40.6x on this
    device -- so the net pair rate is recombination and must come back
    POSITIVE. If a future edit re-inverts the sign this fails, which is the
    whole point: the sign is not inferable from the function's name or from
    DEVSIM's ``ElectronGeneration`` model name.
    """
    out = _run_isolated(
        "r = mx.transient_pulse(waveform=lambda t: V_FWD, dt=2e-12,\n"
        "                       t_end=3e-12, v_initial=V_FWD, **DEVICE)\n"
        "rate = r['recombination']\n"
        "assert len(rate) > 0, 'empty recombination series'\n"
        "print('FIRST', repr(float(rate[0])))\n")
    marker = [ln for ln in out.splitlines() if ln.startswith("FIRST ")]
    assert marker, f"isolated run produced no result:\n{out[-2000:]}"
    first = float(marker[0].split()[1])
    assert first > 0.0, (
        "recombination came back NEGATIVE at forward bias. The device has "
        f"np/n_i^2 = 40.6 at {_V_FWD} V, so it is recombining; a negative "
        "value means the sign is flipped again. USRH = (np - n_i^2)/(...) in "
        "simple_physics.CreateSRH:257, so positive USRH IS recombination -- "
        "do not anchor on the model name ElectronGeneration, which is -q*USRH."
    )


def test_charge_error_default_is_tighter_than_accept_anything():
    """The transient ships a charge tolerance; it must not be a rubber stamp.

    DEVSIM keeps a separate acceptance test on the projected-vs-solved charge
    and prints ``Charge Relative Error`` per step. This function shipped with
    ``charge_error=1.0``, and on a driven step that error starts at 1.08e-01
    and the iteration does not drive it down -- so 1.0 accepted the FIRST
    iteration and every step carried ~1e-1 charge error. The default is now
    0.2: still loose, because the solver cannot do better without a different
    time-integration setup (see tasks.md 2.8), but no longer a value that
    cannot fail.
    """
    import inspect

    sig = inspect.signature(mx.transient_pulse)
    assert "charge_error" in sig.parameters, (
        "charge_error is hard-coded again; a caller must be able to see and "
        "set the tolerance the solver is held to")
    default = sig.parameters["charge_error"].default
    assert default < 1.0, (
        f"charge_error defaults to {default!r}; on a driven step DEVSIM's "
        "charge error starts at 1.08e-01, so any value >= 1.0 accepts the "
        "first iteration and the tolerance can never fail")


def test_a_charge_tolerance_the_solver_cannot_meet_is_refused_not_ignored():
    """A tolerance tighter than achievable must RAISE, not silently pass.

    Measured: the projected-vs-solved charge error starts at 1.08e-01 on a
    stepped bias and does not fall, so ``charge_error=1e-3`` cannot converge.
    That is the correct outcome -- it turns "the number is wrong" into "the
    solve did not converge", which a caller cannot mistake for success. What
    must never happen is a tight tolerance being accepted while the returned
    series carries 1e-1 charge error.
    """
    out = _run_isolated(
        "try:\n"
        "    mx.transient_pulse(waveform=lambda t: 0.32 if t > 0 else V_FWD,\n"
        "                       dt=2e-12, t_end=4e-12, v_initial=V_FWD,\n"
        "                       charge_error=1e-3, **DEVICE)\n"
        "    print('RESULT converged-anyway')\n"
        "except mx.EquilibriumNotReached:\n"
        "    print('RESULT raised')\n")
    assert "RESULT raised" in out, (
        "a charge tolerance the solver cannot meet was ACCEPTED, so the "
        f"returned series carries ~1e-1 charge error:\n{out[-2000:]}")


_SKIP_28 = pytest.mark.skip(
    "UNFIXED 2.8: the transient step's stored charge does not match the "
    "series current (dQ is ~6 orders below 0.5*(I_prev+I)*dt at dt=2e-12); "
    "see tasks.md 2.8. Un-skip when the balance is closed.")


@_SKIP_28
def test_a_transient_step_conserves_charge_against_its_series_current():
    """TASK 2.8 IS NOT DONE. This test PINS the defect so it cannot be lost.

    THE FIRST VERSION OF THIS TEST WAS WRONG and is recorded so it is not
    rebuilt. It compared I(top) with I(bottom) and reported an 11 % mismatch
    at dt=2e-12. Both of those numbers are the DC answer for 0.32 V
    (1.798112e-03 / -1.672860e-03, identical to a standalone DC solve), and
    the two legs of this fixture do not carry equal current in DC either --
    the contacts have different areas. Comparing the legs was never a
    conservation test, in transient or in DC.

    The real check is the SERIES current against the change in stored
    charge, I=0.5*(I_top-I_bottom) against `_contact_charge_coulombs`:
        step  0.5*(I_prev+I)*dt      actual dQ
          1      1.7355e-15          4.203e-21
          2      2.2421e-15         -2.521e-21
          3      6.5943e-16         -1.130e-21
    ~6 orders apart, and dQ changes sign after step 1. The current is the
    dielectric-relaxation current of a bias jump (1.7e-03 A decaying to
    4.3e-06 A over six steps), so the open question is whether that decay
    is physical or an artefact of half-step integration -- not whether the
    two contact legs agree.

    ``i_contact`` carries only the p contact, so the body runs
    ``transient_pulse`` and prints what the solver reports. ``t_end`` is
    4e-12: ``transient_pulse`` refuses ``t_end <= dt`` before solving, and
    with t_end==dt the run raises ValueError and never reaches the balance.

    The assertion is written so that it FAILS the moment the balance is
    fixed, on purpose: closing 2.8 means flipping it to assert balance and
    deleting this docstring's first line. It deliberately does NOT assert a
    tolerance that passes today, because a test that passes while the
    defect is present is the false green this file exists to prevent.

    A re-seeded start does NOT help (tasks.md 2.8, corrected): the seed does
    apply -- one Newton iteration shows the +/-0.02 V seeds differ by 0.04 V
    -- and the solve then walks away from it, because the time term in the
    Jacobian is tiny at dt=2e-12. Any future check must still require a
    NON-ZERO current before it looks at the balance.
    """
    out = _run_isolated(
        "r = mx.transient_pulse(waveform=lambda t: 0.32 if t > 0 else V_FWD,\n"
        "                       dt=2e-12, t_end=4e-12, v_initial=V_FWD, **DEVICE)\n"
        "print('FIRST', repr(float(r['i_contact'][1])))\n")
    marker = [ln for ln in out.splitlines() if ln.startswith("FIRST ")]
    assert marker, f"isolated run produced no result:\n{out[-2000:]}"
    first = abs(float(marker[0].split()[1]))
    assert first > 1e-6, (
        "the step produced no current (%.3e A), so the balance below would "
        "be vacuous -- that is the shape of the re-seeded no-op, not a "
        "conserving solve" % first)
    # When un-skipped, this is where the real assertion goes: the
    # trapezoid 0.5*(I_prev+I)*dt against the change in
    # _contact_charge_coulombs. NOT I(top) against I(bottom).
    raise AssertionError("UNFIXED 2.8: see docstring")


def test_transient_pulse_runs_in_a_fresh_process():
    """DEVSIM's mesh registry is PROCESS-GLOBAL, so this file needs care.

    A second ``transient_pulse`` call in one process dies with
    ``A mesh already exists with name "axtr"``. That is not a solver bug --
    DEVSIM owns the mesh registry, not this module -- but it silently corrupts
    any test that calls the solver twice in a session, and it corrupted a
    measurement once: a dt sweep printed tracebacks that were read as result
    rows, producing a "the integral is constant" claim that was false.

    The tests above therefore each get their own process via ``pytest-forked``
    or run one-per-invocation. This test states the constraint so nobody
    "simplifies" the file by merging them.
    """
    import os
    import subprocess
    import sys as _sys

    program = (
        "import sys; sys.path.insert(0, %r);"
        "import devsim;"  # imported for the side effect of being available
        "import mse_axisymmetric as mx;"
        "d=dict(n_a=1e17,n_d=1e17,n_i=1e10,z_lo=-3e-7,z_hi=3e-7,n_r=2,"
        "n_z=120,refine=1e-9,refine_halfwidth=5e-8);"
        "mx.transient_pulse(waveform=lambda t: 0.30, dt=2e-12, t_end=3e-12,"
        "v_initial=0.30, **d);"
        "mx.transient_pulse(waveform=lambda t: 0.30, dt=2e-12, t_end=3e-12,"
        "v_initial=0.30, **d)"
    ) % str(ROOT / "dockerfiles" / "maxwell_solver")
    proc = subprocess.run([_sys.executable, "-c", program],
                          capture_output=True, text=True, timeout=300,
                          env=dict(os.environ))
    assert "mesh already exists" in (proc.stderr + proc.stdout), (
        "two transient_pulse calls in one process no longer collide. Good "
        "news if intended -- but check WHY before deleting this test: the "
        "collision is what made a dt sweep look like a constant integral, "
        "so the per-process isolation of the tests above is load-bearing.")


@pytest.mark.skip(reason=(
    "OPEN DEFECT 2.8: junction capacitance is bit-identical across n_r. "
    "Remove this skip when the contact assembly is fixed -- a passing run "
    "here IS the closing condition for that half of the task."))
def test_junction_capacitance_depends_on_radial_resolution():
    """C = dQ/dV must CHANGE when the electrode gains radial columns.

    Measured 2026-11-11: C is 3.90730e-20 F to six digits at n_r = 2, 4, 8
    and 16, even though the mesh genuinely gains radial columns (verified:
    the node ``x`` values take 2, 4, 8 and 16 distinct values). A resolved
    physical quantity cannot be independent of the radial discretisation, so
    this pins the defect rather than the physics.

    WHY IT IS WORTH PINNING AT ALL: it is the crispest evidence on the row.
    It does not depend on the n_z extrapolation (which is only asymptotic
    and whose 5-point refit moves Q_inf by 43 %), and it does not depend on
    any geometry reference I have to compute by hand -- the two things that
    have wrong-footed every previous attempt. It points at the CONTACT
    ASSEMBLY (which nodes the contact carries and how their edge charge is
    weighted), not at the silicon solution.

    TWO TRAPS THIS TEST EXISTS TO CATCH:
      * Comparing C at n_r=2 against a hand-computed area. That produced
        three separate false "1e4 / 1e6 factor" claims on this row; the
        half-disk areas only converge at large n_r.
      * Using an unguarded devsim.solve. It returns a number from a state
        with RelError 1.0, which made a diverged capacitance look converged.

    Each n_r needs its own process (DEVSIM's mesh registry is global), so
    this spawns one interpreter per point.
    """
    vals = {}
    for n_r in (2, 4):
        out = _run_isolated(
            "import devsim\n"
            "import mse_axisymmetric as mx\n"
            "mg = mx.build_grid(0.0, r_max=4e-8, z_min=-3e-7, z_max=3e-7,\n"
            f"                   n_r={n_r}, n_z=100, refine=1e-9,\n"
            "                   refine_halfwidth=5e-8)\n"
            "mx._build_dd_device(mg,\n"
            "    net_doping_cm3=lambda z: 1e17 if z > 0 else -1e17,\n"
            "    eps_s=11.7, mesh_name='cap%d', n_i_cm3=1e10)\n"
            # Guarded ramp to each bias: an unguarded solve returns a
            # number from a RelError-1.0 state (see the docstring).
            "def ramp(v):\n"
            "    n = max(1, int(round(v / 0.01)))\n"
            "    for i in range(1, n + 1):\n"
            "        b = round(i * (v / n), 10)\n"
            "        mx._solve_at_bias(devsim, ('top', 'bottom'),\n"
            "                         {'top': b, 'bottom': 0.0})\n"
            "def q_top():\n"
            "    return float(devsim.get_contact_charge(device='dd',\n"
            "        contact='top', equation='PotentialEquation'))\n"
            "ramp(0.24); q_lo = q_top()\n"
            "ramp(0.26); q_hi = q_top()\n"
            "print('NCOL', len(set(devsim.get_node_model_values(\n"
            "    device='dd', region='silicon', name='x'))))\n"
            "print('C', repr((q_hi - q_lo) / 0.02))\n"
            % (n_r,))
        nums = [ln.split()[-1] for ln in out.splitlines()
                if ln.startswith("C ")]
        assert nums, f"probe produced no capacitance at n_r={n_r}:\n{out}"
        vals[n_r] = float(nums[-1])

    c2, c4 = vals[2], vals[4]
    assert abs(c4 - c2) / c2 > 0.05, (
        "junction capacitance is unchanged by doubling the radial node "
        f"count (n_r=2 -> {c2:.6e} F, n_r=4 -> {c4:.6e} F). That is the "
        "open 2.8 defect: the contact charge is not seeing the radial "
        "discretisation, so C is not measuring the junction.")
