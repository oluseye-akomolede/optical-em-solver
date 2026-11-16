"""Reproduce the absolute terminal charge and junction capacitance of the 2.8
axisymmetric pin diode, so the reviewer can check the numbers in
openspec/changes/electrical-simulation/tasks.md section 2.8 rather than trust
them.

If the numbers below disagree with that text, THE TEXT IS WRONG, not this
script.

Run (from the repo root, DEVSIM_MATH_LIBS set if the wheel cannot find a
system BLAS):

    (ulimit -v 4194304; nice -n 19 .venv-mse/bin/python -I \
        scripts/elec28_capacitance_fixture.py)

Optional first argument: n_z (default 400). Optional second: n_r (default 2).

WHY A SEPARATE PROCESS PER n_z MATTERS: DEVSIM's mesh registry is
PROCESS-GLOBAL. Building a second device in one process dies with
`A mesh already exists with name "..."` and that traceback reads like an
output row if you are grepping. For the n_z sweep use
running the script once per n_z from the shell, one process per point (there
is no committed sweep script; an earlier draft cited
`elec28_capacitance_sweep.sh`, which never existed).

WHY THE RAMP IS FINE (this has bitten every probe on this row): a 0 -> 0.05 V
first step raises EquilibriumNotReached on a fresh device, and an unguarded
devsim.solve returns a number anyway (RelError 1.0, stopped at the iteration
limit) -- a FALSE GREEN. The ramp below walks 0.01 V at a time through
_solve_converged, which raises rather than returning a bad state.

WHY THE REFERENCE AREA IS THE FULL DISK: the mesh is a half-disk
(r_lines = linspace(0, r_max, n_r)) swept through 2*pi by
cylindrical_edge_couple, so the electrode is a full disk pi*r^2. Halving it
for the half-disk is a cancellation error, not a correction.
"""
import math
import os
import sys

import devsim

_HERE = os.path.dirname(os.path.abspath(__file__))
_SOLVER_DIR = os.path.join(os.path.dirname(_HERE), "dockerfiles", "maxwell_solver")
if _SOLVER_DIR not in sys.path:
    sys.path.insert(0, _SOLVER_DIR)

from mse_axisymmetric import (  # noqa: E402
    _build_dd_device, _solve_at_bias, build_grid)

# Fixture: symmetric 1e17 pin diode, the same device the record uses.
N_A = N_D = 1.0e17
N_I = 1.0e10
EPS_S = 11.7
JUNCTION_Z = 0.0
R_MAX_M = 4.0e-8
Z_LO_M = -3.0e-7
Z_HI_M = 3.0e-7
# The junction refinement MATTERS and was missing from the first draft of
# this script: without it the charges differ by ~3x from the record, which is
# how a "fixture" silently becomes a different device.
REFINE_M = 1.0e-9
REFINE_HALFWIDTH_M = 5.0e-8
V_BIAS = (0.15, 0.25, 0.35, 0.45)
RAMP_STEP = 0.01


def build(n_r, n_z):
    grid = build_grid(JUNCTION_Z, r_max=R_MAX_M, z_min=Z_LO_M, z_max=Z_HI_M,
                      n_r=n_r, n_z=n_z, refine=REFINE_M,
                      refine_halfwidth=REFINE_HALFWIDTH_M)
    # net_doping_cm3 is a CALLABLE taking position in METRES (see
    # _set_net_doping), not a value: abrupt pin junction at z=0, p below.
    _build_dd_device(grid, net_doping_cm3=lambda z_m: (N_D if z_m > 0 else -N_A),
                     eps_s=EPS_S, mesh_name="dd", n_i_cm3=N_I)
    return "dd"


def solve_to(device, v):
    """Walk to v in RAMP_STEP increments via _solve_at_bias.

    _solve_at_bias sets EVERY terminal explicitly (including the reference at
    0 V) and solves with the module's own convergence settings. Setting only
    top_bias by hand leaves the other contact stale and does not converge on
    a fresh device.
    """
    n = max(1, int(round(v / RAMP_STEP)))
    for i in range(1, n + 1):
        bias = round(i * (v / n), 10)
        _solve_at_bias(devsim, ("top", "bottom"),
                       {"top": bias, "bottom": 0.0})
    return None


def contact_q(device):
    return devsim.get_contact_charge(device=device, contact="top",
                                     equation="PotentialEquation")


def main():
    n_z = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    n_r = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    device = build(n_r, n_z)

    # Geometric reference. The mesh is in CM (M_TO_CM inside build_grid), so
    # read back the actual max radius rather than converting by hand -- that
    # unit slip has caused two wrong baselines on this row already.
    xs = devsim.get_node_model_values(device=device, region="silicon",
                                      name="x")
    r_cm = max(xs)
    area_cm2 = math.pi * r_cm ** 2
    length_cm = (Z_HI_M - Z_LO_M) * 100.0
    eps_cm = EPS_S * 8.854e-14
    c_pp = eps_cm * area_cm2 / length_cm

    print(f"# n_r={n_r} n_z={n_z}  r_max={r_cm:.6e} cm  "
          f"area(disk)={area_cm2:.6e} cm^2  L={length_cm:.6e} cm")
    # CHECKED 2026-11-12 (lead step 1): length_cm is CORRECT. The box is
    # 600 nm = 6e-7 m = 6e-5 cm; (Z_HI_M - Z_LO_M)*100.0 evaluates to
    # 5.9999999999999995e-05, which is 6e-5 cm to float noise. A reviewer and
    # I both read this as a 10x bug by converting nm->cm twice. It is not.
    # What IS wrong is using it as the reference: a 600 nm BOX parallel plate
    # is not the capacitance of a junction whose depletion width is ~80-95 nm.
    # Kept as a labelled geometric constant of the mesh ONLY. The physically
    # meaningful reference is C_dep = eps_s*A/W(V); see 2.8-charge-probe.md.
    print(f"# box parallel-plate constant C_pp = {c_pp:.6e} F "
          f"(NOT a junction capacitance -- see C_dep)")

    prev_q, prev_v = None, None
    for v in V_BIAS:
        solve_to(device, v)
        q = contact_q(device)
        line = f"Q_top({v:.2f} V) = {q:+.6e} C"
        if prev_q is not None:
            c = (q - prev_q) / (v - prev_v)
            line += f"   C = {c:.6e} F   ratio_to_pp = {c / c_pp:.4e}"
        print(line)
        prev_q, prev_v = q, v


if __name__ == "__main__":
    main()
