"""Is there ANY charge measurement on this device that converges?

Lead's order (qitem-20261112041525): compute the electrode charge
INDEPENDENTLY -- `eps*E.n*A` at the contact, and the volume charge on each side
of the junction -- and compare all of them with `get_contact_charge` across the
same z sweep. Record which converges. Do NOT touch the transient balance until
this is settled.

This is a measuring instrument, not a model. It prints numbers and comments;
the record in openspec/changes/electrical-simulation/tasks.md says which of
them may be quoted.

WHAT IS COMPARED, at one bias, one n_z per process:

  q_contact   devsim.get_contact_charge(top)      -- the suspect
  epsEA       -eps_cm * (dV/dz) * A_disk          -- Gauss's law at the plane
                dV/dz is taken from the SOLVED Potential on the two z-planes
                nearest the contact, not from any contact edge model: the
                question is whether the contact charge agrees with the field
                the solution actually has there.
  q_half_top  -q * sum((p-n)*CylNodeVol) over z > 0
  q_half_bot  -q * sum((p-n)*CylNodeVol) over z < 0
  q_full      -q * sum((p-n)*CylNodeVol) over the whole region
  q_dop_net   q * sum((p-n-NetDoping)*CylNodeVol) over the whole region
                (the full Poisson right-hand side -- carries the dopant,
                unlike the solvers' mobile-only sum)
  flux_edges  sum(contactcharge_edge * EdgeLength) over ALL silicon edges --
                DEVSIM's own per-edge quantity, summed the way a Gauss
                integral would be. NOTE the weight is EdgeLength, not an
                area: CylindricalEdgeCouple does not exist at edge scope in
                this build (2026-11-12). So this is a SCALE CHECK on
                contactcharge_edge, not an independent electrode charge.
  edge_unity  the same sum with eps_cm*E in place of contactcharge_edge.

The half-space sums are the independent check: they are a VOLUME integral and
touch the contact assembly not at all. In equilibrium each side balances the
ionised dopant there; in forward bias it grows by the stored minority charge.

WHY ONE PROCESS PER n_z: DEVSIM's mesh registry is PROCESS-GLOBAL. A second
device build in one process dies with `A mesh already exists with name ...`.
A sweep is therefore a loop over n_z in the shell, one process each. There is
no committed sweep script; an earlier draft of this docstring cited
`elec28_electrode_charge_sweep.sh`, which never existed. Run each point by
hand as below, at each n_z in 84 336 1344 5376, and at BOTH biases (0.35 and
0.15) -- a capacitance needs the same mesh at two biases, never two meshes at
one bias.

Run one point (from the repo root, DEVSIM_MATH_LIBS set if the wheel cannot
find a system BLAS):

    (ulimit -v 4194304; nice -n 19 /tmp/devsim-probe/bin/python -I \
        scripts/elec28_electrode_charge_probe.py 400)

Optional second argument: bias in volts (default 0.35).
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
    EPS0_CM, Q, _build_dd_device, _solve_at_bias, build_grid)

# The same device the record and elec28_capacitance_fixture.py use. Kept in
# step by hand; if these drift the probe is measuring a different diode.
N_A = N_D = 1.0e17
N_I = 1.0e10
EPS_S = 11.7
JUNCTION_Z = 0.0
R_MAX_M = 4.0e-8
Z_LO_M = -3.0e-7
Z_HI_M = 3.0e-7
REFINE_M = 1.0e-9
REFINE_HALFWIDTH_M = 5.0e-8
RAMP_STEP = 0.01

EPS_CM = EPS_S * EPS0_CM  # F/cm, the units _build_dd_device solves in


def build(n_z, n_r=2):
    grid = build_grid(JUNCTION_Z, r_max=R_MAX_M, z_min=Z_LO_M, z_max=Z_HI_M,
                      n_r=n_r, n_z=n_z, refine=REFINE_M,
                      refine_halfwidth=REFINE_HALFWIDTH_M)
    _build_dd_device(grid, net_doping_cm3=lambda z_m: (N_D if z_m > 0 else -N_A),
                     eps_s=EPS_S, mesh_name="dd", n_i_cm3=N_I)
    return "dd"


def solve_to(v):
    """Ramp to v through _solve_at_bias, which raises on non-convergence."""
    n = max(1, int(round(v / RAMP_STEP)))
    for i in range(1, n + 1):
        bias = round(i * (v / n), 10)
        _solve_at_bias(devsim, ("top", "bottom"),
                       {"top": bias, "bottom": 0.0})


def nodes(name):
    return list(devsim.get_node_model_values(device="dd", region="silicon",
                                             name=name))


def plane_values(zc, vals, target, tol=1e-13):
    """Values on the z-plane at `target`, asserting the plane is single-valued.

    An isopotential contact plane with NON-single-valued Potential would mean
    the plane has more than one node stack and averaging across it is wrong.
    On THIS axisymmetric mesh x is constant along z, so each z-plane is a
    single value. The assertion makes that a checked property, not a guess.
    """
    hits = [vals[i] for i, zz in enumerate(zc) if abs(zz - target) < tol]
    assert hits, f"no nodes on the z-plane {target!r}"
    assert max(hits) - min(hits) < 1e-9, (
        f"the z-plane {target!r} is not single-valued "
        f"(spread {max(hits) - min(hits):.3e}) -- read the mesh, not the "
        "field")
    return hits[0]


def contact_field_and_area():
    """Field at the last node plane AND at the contact boundary, plus area."""
    # The transport (graded) axis is DEVSIM's "y": build_grid feeds z_lines to
    # dir="y". "z" is a 2-D leftover in this mesh and is constant. Measured
    # 2026-11-12: reading "z" here gave 338 nodes all at 0.0 and a bogus
    # one-plane mesh -- the instrument, not the device.
    zc = nodes("y")
    pot = nodes("Potential")
    xc = nodes("x")
    z_max = max(zc)
    dzs = sorted({zz for zz in zc if zz < z_max})  # nearest plane below
    dz_plane = dzs[-1]
    dz = z_max - dz_plane
    p_top = plane_values(zc, pot, z_max)
    p_next = plane_values(zc, pot, dz_plane)
    # Field points from the positive-potential plane towards the negative
    # one: for the top contact at +V with the bottom at 0, it points +z.
    e_z = (p_top - p_next) / dz  # V/cm, signed
    r_cm = max(xc)
    area = math.pi * r_cm ** 2  # full disk: the half-disk is swept through 2*pi
    # The contact EQUATION is assembled on the mesh boundary, so the field it
    # sees is the one-sided finite-volume average over the control volume
    # between the boundary edge and the first node plane: (V_contact -
    # V_first_node) / (h/2), h = the first-plane spacing. e_z above measures
    # one plane INTERIOR of that. Both are reported; the difference is not
    # assumed away (measured 2026-11-12: interior 2.4e-3 V/cm against
    # 1.29e5 V/cm at the junction -- 1000x, and it moves with n_z).
    h = dz  # uniform first spacing here: the refinement is at the junction
    e_boundary = (p_top - p_next) / (0.5 * h)
    return e_z, e_boundary, area, dz, r_cm


def volume_sums():
    n = nodes("Electrons")
    h = nodes("Holes")
    dop = nodes("NetDoping")
    vol = nodes("CylindricalNodeVolume")
    zc = nodes("y")
    tot = lambda sel: sum((h[i] - n[i]) * vol[i]
                          for i in range(len(zc)) if sel(zc[i]))
    q_half_top = -Q * tot(lambda zz: zz > 0)
    q_half_bot = -Q * tot(lambda zz: zz < 0)
    q_full = -Q * tot(lambda zz: True)
    q_dop_net = Q * sum((h[i] - n[i] - dop[i]) * vol[i]
                        for i in range(len(zc)))
    return q_half_top, q_half_bot, q_full, q_dop_net


def main():
    n_z = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    v = float(sys.argv[2]) if len(sys.argv) > 2 else 0.35
    build(n_z)
    solve_to(v)

    q_contact = devsim.get_contact_charge(device="dd", contact="top",
                                          equation="PotentialEquation")
    e_int, e_bnd, area, dz, r_cm = contact_field_and_area()

    q_ht, q_hb, q_full, q_dop = volume_sums()

    # Per-edge sums. E per edge must come from the node potentials the solve
    # left, so define the edge models after the solve. CylindricalEdgeCouple
    # DOES NOT EXIST at edge scope in this build (2026-11-12: querying it
    # raised and took the whole probe down with it) -- the axisymmetric
    # weight is applied to the contact equation's assembly, not exposed as an
    # edge model. `edge_unity` therefore uses EdgeLength as the weight and is
    # only a scale check on contactcharge_edge, NOT a plane area. Do not read
    # it as one.
    devsim.edge_model(device="dd", region="silicon", name="ProbeEFieldSigned",
                      equation="(Potential@n0 - Potential@n1) * EdgeInverseLength")
    ef = devsim.get_edge_model_values(device="dd", region="silicon",
                                      name="ProbeEFieldSigned")
    ce = devsim.get_edge_model_values(device="dd", region="silicon",
                                      name="EdgeLength")
    cc = devsim.get_edge_model_values(device="dd", region="silicon",
                                      name="contactcharge_edge")
    flux_edges = sum(a * c for a, c in zip(cc, ce))
    edge_unity = sum(EPS_CM * a * c for a, c in zip(ef, ce))

    eps_ea_int = EPS_CM * e_int * area
    eps_ea = EPS_CM * e_bnd * area

    print(f"# n_z={n_z} V={v}  r_max={r_cm:.6e} cm  "
          f"A_disk={area:.6e} cm^2  dz_to_next_plane={dz:.6e} cm")
    print(f"# E interior (last plane pair)     {e_int:+.6e} V/cm")
    print(f"# E boundary (contact, one-sided)   {e_bnd:+.6e} V/cm")
    print("MEASURE            WHAT                          VALUE (C)")
    print(f"q_contact   get_contact_charge(top)          {q_contact:+.6e}")
    print(f"epsEA_bnd   eps*E_boundary*A_disk            {eps_ea:+.6e}")
    print(f"epsEA_int   eps*E_interior*A_disk            {eps_ea_int:+.6e}")
    print(f"q_half_top  mobile, z>0                      {q_ht:+.6e}")
    print(f"q_half_bot  mobile, z<0                      {q_hb:+.6e}")
    print(f"q_full      mobile, all                      {q_full:+.6e}")
    print(f"q_dop_net   mobile+dopant, all               {q_dop:+.6e}")
    print(f"flux_edges  sum(cc_edge*EdgeLength)          {flux_edges:+.6e}")
    print(f"edge_unity  sum(eps*E*EdgeLength)            {edge_unity:+.6e}")


if __name__ == "__main__":
    main()
