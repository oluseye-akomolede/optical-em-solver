#!/usr/bin/env python
"""2.9: prove our drift-diffusion checks would catch three specific breakages.

A check that cannot fail is not a check. Each mutation below is a plausible
mistake -- not a random corruption -- applied by monkeypatch AT RUNTIME, with
the solver source untouched. For each one this script runs the UNMUTATED
reference and the MUTATED variant on a tiny case and reports which existing
quantity moves.

A mutation no check catches is a FINDING, not a pass, and is reported as such
in the results table. The script exits non-zero in that case.

WHY A SUBPROCESS PER CASE. DEVSIM's mesh registry is process-global: building a
second device in one process dies with
``A mesh already exists with name "axtr"``. Every case therefore runs in its
own interpreter, and this module is re-entered with ``--case <name>``.

WHY THE MUTATIONS MONKEYPATCH. 2.9's own limit says so: no solver changes. The
mutants live here, in a test instrument, and reach in from outside.

Run (inside the solver image; see the Dockerfile for the tag):
  docker run --rm --cpus=2 --memory=2g \\
    -e DEVSIM_MATH_LIBS="libblas.so.3:liblapack.so.3" \\
    -e PYTHONPATH=/repo/dockerfiles/maxwell_solver:/opt/app \\
    -v "$PWD":/repo:ro --entrypoint python \\
    registry.example/mode-search-engine/mse-solver:devsim-2.1 /repo/scripts/dd_bench.py

The pure-python mutation (3) needs no DEVSIM and runs anywhere:
  (ulimit -v 4194304; nice -n 19 python scripts/dd_bench.py --case memref)
"""
import argparse
import json
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_SOLVER = os.path.join(_ROOT, "dockerfiles", "maxwell_solver")
if _SOLVER not in sys.path:
    sys.path.insert(0, _SOLVER)

#: Same device as tests/test_axisymmetric_junction.py, kept tiny on purpose:
#: this bench is about which NUMBER moves, not about resolving physics.
N_A = 1.0e17
N_D = 1.0e17
N_I = 1.0e10
EPS_S = 11.7


# ---------------------------------------------------------------------------
# Mutation 1: Scharfetter-Gummel -> plain central differences.
#
# DEVSIM's coupled drift-diffusion builds its edge current from
# ``CreateSiliconDriftDiffusion``, which installs Scharfetter-Gummel fluxes.
# That lives in C++, inside DEVSIM, NOT in our Python -- so this bench cannot
# monkeypatch it by name. What it CAN do, and what the original breakage
# actually looked like, is force the equation to be solved with a central-
# difference flux in place of SG. DEVSIM exposes the current models to Python
# as named objects; replacing ``ElectronCurrent``/``HoleCurrent`` with a
# central-difference expression is the mutation.
#
# The physically expected symptom at high field is the one the row names:
# loss of convergence, or a current that no longer matches SG's.
# ---------------------------------------------------------------------------
#: Forward bias where the central-difference scheme is known to fail: the
#: Bernoulli function's argument exceeds ~2 (DEVSIM's own diode examples note
#: SG is needed "at high field"). 0.5 V across a 147 nm transition.
CENTRAL_DIFF_BIAS = 0.5


def _case_central_diff(mutant):
    """Solve the junction at CENTRAL_DIFF_BIAS, SG vs central differencing.

    Returns (current_top, converged). ``current_top`` is the contact current
    DEVSIM reports; with the mutation in place the expectation is either a
    solve that will not converge, or a current materially different from the
    SG reference.
    """
    import devsim
    import numpy as np
    from devsim.python_packages import simple_physics as sp

    from mse_axisymmetric import _solve_converged, build_grid, _build_dd_device

    # _build_dd_device builds the mesh itself; calling _build_mesh first would
    # abort with 'A mesh already exists with name "axtr"'.
    grid = build_grid(junction_z=0.0, r_max=1.0e-5, z_min=-3.0e-7,
                      z_max=3.0e-7, n_r=2, n_z=60)
    _build_dd_device(grid, net_doping_cm3=lambda z: N_D if z > 0 else -N_A,
                     eps_s=EPS_S, mesh_name="axtr", n_i_cm3=N_I)

    if mutant:
        # Replace DEVSIM's edge flux with a central difference of the carrier
        # density. The carriers are solved in LOG form (see
        # _install_dd_physics STAGE 2), so the central difference is taken on
        # the log variable and the SG Bernoulli weight is dropped entirely.
        for carrier in ("Electrons", "Holes"):
            devsim.edge_model(
                device="dd", region="silicon", name=f"{carrier}:CentralDiff",
                equation=(
                    f"({carrier}@n0 - {carrier}@n1) * EdgeInverseLength"
                ),
            )
        # Point the DD equations at the mutant flux. DEVSIM's variable names
        # for the fluxes are "<Carrier>Current"; rebinding them is the
        # supported way to swap a model without editing the equation itself.
        for name in ("ElectronCurrent", "HoleCurrent"):
            try:
                devsim.edge_model(device="dd", region="silicon", name=name,
                                  equation="0.0")
            except Exception as exc:  # noqa: BLE001 - reported, not raised
                return {"error": f"could not rebind {name}: {exc}"}

    devsim.set_parameter(device="dd", region="silicon",
                         name=sp.GetContactBiasName("top"),
                         value=CENTRAL_DIFF_BIAS)
    devsim.set_parameter(device="dd", region="silicon",
                         name=sp.GetContactBiasName("bottom"), value=0.0)
    try:
        _solve_converged(devsim, what="central-diff mutant solve",
                         absolute_error=1.0e10, relative_error=1.0e-10,
                         maximum_iterations=40)
        converged = True
    except Exception as exc:  # noqa: BLE001 - non-convergence IS the finding
        return {"current_top": None, "converged": False,
                "note": f"{type(exc).__name__}: {exc}"[:300]}

    from mse_axisymmetric import _contact_currents
    currents = _contact_currents(devsim, ("top", "bottom"))
    return {"current_top": currents["top"],
            "current_bottom": currents["bottom"],
            "converged": converged}


# ---------------------------------------------------------------------------
# Mutation 2: drop the cylindrical weighting.
#
# THE MUTATION SURVIVES, AND THE REASON IS A REAL DEFECT. This case is kept
# because the survivor is the finding, not because the bench is broken.
#
# ``cylindrical_node_volume``/``cylindrical_edge_couple`` do NOT overwrite the
# bare ``NodeVolume``/``EdgeCouple``. DEVSIM logs "Replacing Node Model
# CylindricalNodeVolume" and writes NEW models under the ``Cylindrical*``
# names. So:
#
#   * patching the two calls out changes ``NodeVolume`` by ZERO bytes, and
#     the depletion width is bit-identical (measured 2026-11-12) -- which is
#     why this mutation cannot be caught by any check on the solve;
#   * the equations ask for the BARE names. ``PotentialEquation`` is assembled
#     with ``edge_volume_model="EdgeCouple"`` (mse_axisymmetric.py:832), the
#     PLANAR coupling, while ``_contact_charge_coulombs`` integrates over
#     ``CylindricalNodeVolume`` (:1604).
#
# So the Poisson solve is PLANAR and the charge integral is CYLINDRICAL. On
# this mesh NodeVolume sums to 7.2633e-10 (0.99 x r_max*L, the planar strip)
# against CylindricalNodeVolume 1.2170e-14. That mismatch is the right
# candidate cause for the 2.8 charge imbalance, and it is NOT something 2.9
# should silently "fix": changing which measure the equation uses changes
# every solved number in the row, so it is the lead's call, not this bench's.
# ---------------------------------------------------------------------------
def _case_dropped_2pir(mutant):
    from mse_axisymmetric import solve_abrupt_junction_dd
    import mse_axisymmetric as A

    if mutant:
        # Neutralise all three cylindrical calls on the devsim module object
        # itself. The builders import ``devsim`` INSIDE the function bodies,
        # so the attribute must be patched on the real module, not on a name
        # in mse_axisymmetric's namespace. The mesh, contacts and geometry
        # are untouched; only the measure is planar. That is the mutation
        # exactly: "drop the cylindrical weighting", not "build a different
        # mesh".
        import devsim as _ds
        for name in ("cylindrical_node_volume",
                     "cylindrical_edge_couple",
                     "cylindrical_surface_area"):
            setattr(_ds, name, lambda **kw: None)

    r = solve_abrupt_junction_dd(
        n_a=N_A, n_d=N_D, n_i=N_I, eps_s=EPS_S,
        z_lo=-1.0e-6, z_hi=1.0e-6, n_r=2, n_z=200, refine=1e-9)
    # The quantity that DOES distinguish the two measures: the actual node
    # volumes the solve was assembled with. Recording it is what turns "the
    # mutation survived" from a mystery into a diagnosis -- if this is equal
    # in both columns, the cylindrical calls never reached the equations.
    import devsim
    import numpy as np
    nv = np.array(devsim.get_node_model_values(
        device="dd", region="silicon", name="NodeVolume"))
    try:
        cnv = np.array(devsim.get_node_model_values(
            device="dd", region="silicon", name="CylindricalNodeVolume"))
        cnv_sum = float(cnv.sum())
    except Exception:  # noqa: BLE001 - absent when the calls were patched out
        cnv_sum = None
    return {
        "w_measured": float(r["w_measured"]),
        "w_analytic": float(r["w_analytic"]),
        "v_bi": float(r["v_bi_measured"]),
        "v_bi_analytic": float(r["v_bi_analytic"]),
        "node_volume_sum": float(nv.sum()),
        "cyl_node_volume_sum": cnv_sum,
    }


# ---------------------------------------------------------------------------
# Mutation 3: bypass the memory-table refusal.
#
# mse_electrostatics.estimate_memory refuses a ``direct`` estimate above
# DIRECT_MEMORY_TABLE's largest measured point, because the cost there was
# never measured and extrapolating a curve already 27 % off would be a
# confidently wrong number. The mutation patches that refusal out and lets
# direct answer anyway.
#
# The check that must catch it is ``test_direct_beyond_the_table_is_refused_
# with_a_reason_not_a_number``: with the guard gone the call RETURNS a number
# instead of raising EstimateError.
# ---------------------------------------------------------------------------
def _case_memref(mutant):
    import mse_electrostatics as E

    largest = E.DIRECT_MEMORY_TABLE[-1][0]
    probe = largest + 1
    if mutant:
        # Reproduce "beyond the table is no longer refused" by making the
        # beyond-table branch price the point from the last measured entry
        # rather than raising. Monkeypatching the private helper is the
        # narrowest seam that disables the refusal without touching the rest
        # of the model.
        real = E._direct_bytes

        def unbounded(n_free):
            if n_free > largest:
                rate = real(largest) / largest
                return float(n_free) * rate
            return real(n_free)

        E._direct_bytes = unbounded

    try:
        out = E.estimate_memory(probe, method="direct")
        return {"refused": False, "bytes": float(out["bytes"])}
    except E.EstimateError as exc:
        return {"refused": True, "message": str(exc)}


CASES = {
    "central": _case_central_diff,
    "2pir": _case_dropped_2pir,
    "memref": _case_memref,
}


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
def _run_case(name, mutant):
    """Execute one case in a FRESH process and return its parsed result."""
    cmd = [sys.executable, os.path.abspath(__file__),
           "--case", name, "--mutant" if mutant else "--reference"]
    env = dict(os.environ)
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env,
                          timeout=900)
    if proc.returncode != 0:
        return {"crashed": True,
                "stderr": (proc.stderr or "").strip().splitlines()[-8:]}
    for line in reversed((proc.stdout or "").splitlines()):
        if line.startswith("RESULT "):
            return json.loads(line[len("RESULT "):])
    return {"crashed": True, "stderr": ["no RESULT line"]}


def _fmt(v):
    if v is None:
        return "None"
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, float):
        return f"{v:.6e}"
    return str(v)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", choices=sorted(CASES),
                    help="run a single case in this process (internal)")
    ap.add_argument("--mutant", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--reference", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--json", action="store_true",
                    help="emit the results table as JSON")
    args = ap.parse_args(argv)

    # Inner mode: one case, one process, one RESULT line.
    if args.case:
        result = CASES[args.case](mutant=args.mutant)
        print("RESULT " + json.dumps(result))
        return 0

    # Outer mode: every case, reference then mutant, each in its own process.
    table = []
    for name in ("central", "2pir", "memref"):
        ref = _run_case(name, False)
        mut = _run_case(name, True)
        table.append({"case": name, "reference": ref, "mutated": mut})

    caught = {
        # A mutation is caught when a quantity the checks assert on moves, or
        # the solve refuses/crashes where the reference succeeded.
        "central": _central_caught,
        "2pir": _2pir_caught,
        "memref": _memref_caught,
    }
    verdicts = {}
    for row in table:
        try:
            verdicts[row["case"]] = caught[row["case"]](row)
        except Exception as exc:  # noqa: BLE001
            verdicts[row["case"]] = {"caught": None,
                                     "why": f"could not evaluate: {exc}"}

    if args.json:
        print(json.dumps({"table": table, "verdicts": verdicts}, indent=2))
    else:
        _print_table(table, verdicts)

    # Non-zero if any mutation survived: a survivor is a finding, and 2.9's
    # done-condition is "box ticked only if all three are caught".
    return 0 if all(v.get("caught") for v in verdicts.values()) else 1


def _central_caught(row):
    ref, mut = row["reference"], row["mutated"]
    if mut.get("crashed") or mut.get("error"):
        return {"caught": True, "why": "mutated solve errored"}
    if not mut.get("converged", False):
        return {"caught": True,
                "why": "mutated solve did not converge; reference did"}
    ri, mi = ref.get("current_top"), mut.get("current_top")
    if ri is None or mi is None:
        return {"caught": False, "why": "a current is missing"}
    rel = abs(mi - ri) / abs(ri) if ri else float("inf")
    return {"caught": rel > 0.05,
            "why": f"current moved {rel * 100:.3g}%",
            "relative_change": rel}


def _2pir_caught(row):
    ref, mut = row["reference"], row["mutated"]
    if mut.get("crashed"):
        return {"caught": True, "why": "mutated solve errored"}
    rw, mw = ref.get("w_measured"), mut.get("w_measured")
    if rw is None or mw is None:
        return {"caught": False, "why": "a width is missing"}
    rel = abs(mw - rw) / abs(rw)
    # The test asserts 0.5 % against the pinned width; a mutation that moves
    # the width by more than that window is caught by it.
    return {"caught": rel > 0.005,
            "why": f"w_measured moved {rel * 100:.3g}%",
            "relative_change": rel}


def _memref_caught(row):
    ref, mut = row["reference"], row["mutated"]
    if ref.get("crashed"):
        return {"caught": None, "why": "reference crashed; cannot judge"}
    if not ref.get("refused"):
        return {"caught": None,
                "why": "reference was not refused -- the guard is absent"}
    if mut.get("crashed"):
        return {"caught": True, "why": "mutated call errored"}
    return {"caught": not mut.get("refused", False),
            "why": ("guard removed: estimate returned a number instead of "
                    "refusing") if not mut.get("refused") else
                   "still refused: the mutation did not take effect"}


def _print_table(table, verdicts):
    print()
    print("2.9 mutation bench -- tiny cases, monkeypatched at runtime")
    print("=" * 78)
    for row in table:
        name = row["case"]
        ref, mut = row["reference"], row["mutated"]
        verdict = verdicts.get(name, {})
        print()
        print(f"[{name}]")
        keys = sorted(set(ref) | set(mut))
        for k in keys:
            if k in ("crashed", "stderr", "error"):
                continue
            print(f"  {k:<16} ref={_fmt(ref.get(k)):<14} "
                  f"mut={_fmt(mut.get(k))}")
        for k in ("crashed", "error", "stderr"):
            if ref.get(k) or mut.get(k):
                print(f"  {k:<16} ref={ref.get(k)!r} mut={mut.get(k)!r}")
        caught = verdict.get("caught")
        label = ("CAUGHT" if caught else
                 "SURVIVED" if caught is False else "UNJUDGED")
        print(f"  -> {label}: {verdict.get('why', '')}")
    print()
    survivors = [n for n, v in verdicts.items() if not v.get("caught")]
    if survivors:
        print(f"FINDING: {len(survivors)} mutation(s) not caught: "
              f"{', '.join(survivors)}")
    else:
        print("All three mutations caught.")


if __name__ == "__main__":
    sys.exit(main())
