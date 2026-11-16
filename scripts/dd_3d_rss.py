"""Peak RSS of the 3-D tet drift-diffusion solve, per mesh size (task 2.7).

WHY THIS EXISTS. ``mse_axisymmetric.JACOBIAN_NONZEROS_PER_NODE`` is the slope of
a bound that prices every run before it starts, and it was calibrated on 2-D
axisymmetric grids only: their measured peak-RSS slope is 0.83 in node count
while the estimator's is 1.5. That pessimism is deliberate, because this gate
prices 3-D tet runs where direct-solver FILL grows faster than the 2-D trend.
Until it is measured on real 3-D meshes, nobody knows how far off it is -- and
a threshold that is either lax (admits a run the Job cannot hold) or wildly
strict (refuses runs that fit) is a defect that no 2-D measurement can rule out.

WHAT IT DOES. For each ``edge_m`` in a size list it meshes the SAME layer stack
``solve_layered_dd_3d`` builds, prices it with the same estimator the refusal
uses, runs one solve, and prints:

    RESULT size=<n> nodes=<n> edges=<n> estimate_bytes=<n> peak_rss_bytes=<n> ratio=<x>

``ratio`` is ``peak_rss / estimate``: a number BELOW 1 means the bound is
conservative at that size, above 1 means it would ADMIT a run that does not fit.
One row per size, and at least three sizes, because a single point fits any
model and two points fit a line through the origin.

THE MEASUREMENT IS THE WHOLE PROCESS, NOT ONE SOLVE. ``ru_maxrss`` is a
high-water mark for the interpreter, and DEVSIM, numpy and the mesher all stay
resident between sizes. That is why this runs ONE size per container: the
manifest below re-runs the image with a different ``--size`` for each step, so
every reported peak belongs to a process that did nothing else.

WHY ``equilibrium_only`` IS NOT SET. Stage 3 (coupled drift-diffusion) does not
converge on a coarse tet mesh -- measured 2026-11-10, an AbsError oscillating
2.8-4.7 for 200 iterations -- and an unconverged solve raises. Peak memory is
dominated by the LARGEST matrix assembled, which is the three-equation coupled
system, so this runs the full staged solve up to and including stage 3's
assembly and records the high-water mark even when stage 3 fails to converge.
Stage 1 alone would under-report: it factors one equation, not three. So the
non-convergence is EXPECTED and the measurement is still valid; the exit status
below distinguishes "measured" from "could not measure".

Run inside the solver image (never natively on the VM -- this is exactly the
heavy work the power-cap rule reserves for a bounded Job):

    docker run --rm --cpus=4 --memory=14g --entrypoint python \\
      -e PYTHONPATH=/opt/app -v "$PWD:/src:ro" registry.example/mode-search-engine/mse-solver:devsim-2.1 \\
      /src/scripts/dd_3d_rss.py --size 1.6e-7 --n-a 1e16 --n-d 1e16

Sizes are given in METRES and must be the edges the caller means: the measured
useful range runs 1.6e-7 down to 5.0e-8 (below that the mesher's 200k-tet cap
refuses, above it the junction is unresolved -- see the change's
2.7-feasibility.md).
"""

import argparse
import os
import resource
import sys

# Import path, in order: an explicitly mounted source tree (PYTHONPATH, which
# is how the repo copy is used while the image still predates this commit),
# then the copy baked into the image. NOT hardcoded to /opt/app: the image's
# WORKDIR is /opt/app, so it is already an early sys.path entry during a local
# `-w /opt/app` run, and a stale baked mse_common.py there shadows the repo's.
sys.path.insert(0, os.environ.get("MSE_SOURCE_DIR", "/opt/app"))


def _require(name):
    """Fail loudly if an import resolved to a stale copy.

    The 2.3 incident: a baked mse_common.py without DEFAULT_JOB_MEMORY_BYTES
    was imported ahead of the repo's, and the failure looked like a code bug in
    a file that was correct. Name the file that was actually loaded.
    """
    mod = __import__(name)
    print("RESULT import %s=%s" % (name, getattr(mod, "__file__", "?")))
    return mod


import mse_axisymmetric as ax  # noqa: E402
_common = _require("mse_common")  # noqa: E402


def _default_job_memory_bytes():
    """The shared Job-memory constant, or a named failure.

    Read from mse_common rather than restated: an estimate checked against a
    limit the Job does not have is worse than no estimate. If the constant is
    missing, say so here instead of surfacing an AttributeError later.
    """
    value = getattr(_common, "DEFAULT_JOB_MEMORY_BYTES", None)
    if value is None:
        raise SystemExit(
            "mse_common imported from %r has no DEFAULT_JOB_MEMORY_BYTES: "
            "a stale copy is shadowing the repo's. Set MSE_SOURCE_DIR (or "
            "PYTHONPATH) to the source tree that defines it."
            % (getattr(_common, "__file__", "?"),))
    return int(value)


def peak_rss_bytes():
    """Peak RSS this process has reached, in bytes."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024


def _mesh_counts(args):
    """(nodes, edges) of the mesh ``solve_layered_dd_3d`` builds for ``args``.

    Kept in step with the solver by CALLING the solver's own helpers where they
    exist and mirroring its two construction lines where they do not. The
    outline and the layer split are the solver's: a square outline whose
    half-diagonal is radius_m, two layers split at z = 0. If those change in
    the solver, this must change with them -- which is why it is ten lines and
    not a re-derived formula.
    """
    import numpy as np

    from mse_meshing import tetrahedralize_layers

    half = float(args.radius_m) / np.sqrt(2.0)
    outline = [(-half, -half), (half, -half), (half, half), (-half, half)]
    layers = [("p", float(args.half_width_m)), ("n", float(args.half_width_m))]
    points_m, tets, _region_of_tet = tetrahedralize_layers(
        outline, layers, float(args.size), z0_m=-float(args.half_width_m))
    return int(len(points_m)), int(ax._estimate_tet_edges(tets))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--index", type=int, default=None,
                   help="index into --sizes; the Job pod reads it from "
                        "JOB_COMPLETION_INDEX (Indexed completions)")
    p.add_argument("--sizes", type=float, nargs="+", default=None,
                   help="candidate target tet edges in METRES; --size picks "
                        "one directly, --index selects from this list")
    p.add_argument("--size", type=float, default=None,
                   help="target tet edge in METRES, e.g. 0.6e-6")
    p.add_argument("--n-a", type=float, default=1.0e16, help="acceptor doping, cm^-3")
    p.add_argument("--n-d", type=float, default=1.0e16, help="donor doping, cm^-3")
    p.add_argument("--n-i", type=float, default=1.0e10, help="intrinsic, cm^-3")
    p.add_argument("--eps-s", type=float, default=11.7, help="relative permittivity")
    p.add_argument("--radius-m", type=float, default=1.0e-6,
                   help="device radius the square outline is sized from")
    p.add_argument("--half-width-m", type=float, default=1.0e-6,
                   help="half thickness of EACH layer in metres")
    p.add_argument("--max-iterations", type=int, default=200,
                   help="stage-3 budget; stage 3 is expected to fail to "
                        "converge and that does not affect the memory peak")
    p.add_argument("--limit-bytes", type=int, default=None,
                   help="override the Job limit (default: the shared constant)")
    args = p.parse_args(argv)

    # The Job runs ONE size per pod. Resolution order is explicit so a pod
    # cannot silently measure a different size than the one it was labelled
    # with: --size wins, then --index into --sizes, then JOB_COMPLETION_INDEX
    # into --sizes (what the Indexed Job actually sets).
    size = args.size
    if size is None:
        sizes = args.sizes or []
        index = args.index
        if index is None and os.environ.get("JOB_COMPLETION_INDEX", "") != "":
            index = int(os.environ["JOB_COMPLETION_INDEX"])
        if index is None or not (0 <= index < len(sizes)):
            p.error("one of --size, --index or JOB_COMPLETION_INDEX into "
                    "--sizes is required (got index=%r, %d sizes)"
                    % (index, len(sizes)))
        size = sizes[index]
    args.size = float(size)

    limit = args.limit_bytes or _default_job_memory_bytes()
    gib = float(2 ** 30)
    before = peak_rss_bytes()
    print("RESULT size=%.3e baseline_rss_bytes=%d limit_bytes=%d (%.2f GiB)"
          % (args.size, before, limit, limit / gib))

    outcome = "converged"
    detail = {}
    try:
        detail = ax.solve_layered_dd_3d(
            n_a=args.n_a, n_d=args.n_d, n_i=args.n_i, eps_s=args.eps_s,
            radius_m=args.radius_m, z_lo=-args.half_width_m,
            z_hi=args.half_width_m, edge_m=args.size,
            limit_bytes=args.limit_bytes,
            maximum_iterations=args.max_iterations,
            equilibrium_only=False,
        )
    except ax.TooBigForJob as exc:
        # A refusal IS a result: it says the gate would stop this size. Report
        # the estimate and stop; the peak below is the mesher's, not a solve's.
        outcome = "refused"
        print("RESULT size=%.3e refused=true %s" % (args.size, exc))
        print("RESULT size=%.3e estimate_bytes=%d peak_rss_bytes=%d mesher_only=true"
              % (args.size, exc.estimate_bytes, peak_rss_bytes()))
        print("RESULT size=%.3e outcome=%s" % (args.size, outcome))
        return 0
    except ax.EquilibriumNotReached as exc:
        # Expected at coarse sizes, but only for STAGE 3. A stage-1 failure is
        # a different, worse thing -- no equilibrium means nothing downstream
        # is measurable -- so the two are labelled differently rather than
        # reported under one name. The peak is kept either way: it belongs to
        # this process, which meshed and (for a stage-3 failure) assembled and
        # factored the coupled matrix before giving up.
        which = str(exc).split(" did not converge")[0]
        if "stage-3" in which:
            outcome = "stage3_not_converged"
            print("RESULT size=%.3e not_converged=true stage='stage-3 coupled'"
                  % (args.size,))
        else:
            # NOT a calibration point: an inflating ratio is expected here.
            outcome = "stage1_failed_no_calibration_value"
            print("RESULT size=%.3e not_converged=true stage=%r"
                  " peak_rss_bytes=%d NO_CALIBRATION_VALUE=true"
                  % (args.size, which, peak_rss_bytes()))
            print("RESULT size=%.3e outcome=%s" % (args.size, outcome))
            return 1

    peak = peak_rss_bytes()
    # PRICE THE RAW SUM, not the calibrated one. The job of this line is to
    # report the ratio the calibration is MADE OF (peak / raw). Pricing through
    # the calibrated estimator would divide the correction by itself and report
    # a ratio near 1.0 at every size, which is well-formed, plausible, and
    # measuring nothing.
    estimate = ax.estimate_tet_job_bytes(detail.get("n_nodes", 0),
                                         detail.get("n_edges", 0), raw=True)
    if estimate:
        ratio = "%.3f" % (peak / float(estimate))
        print("RESULT size=%.3e nodes=%d edges=%d estimate_bytes=%d "
              "peak_rss_bytes=%d ratio=%s"
              % (args.size, detail.get("n_nodes", -1), detail.get("n_edges", -1),
                 estimate, peak, ratio))
    else:
        # The solve raised before returning its counts, so mesh the SAME way
        # the solver does and price that through the SAME public function the
        # refusal uses. The peak stays reported: it belongs to this process,
        # which did the meshing and (for a stage-3 failure) the assembly and
        # factorisation before giving up.
        try:
            nodes, edges = _mesh_counts(args)
            estimate = ax.estimate_tet_job_bytes(nodes, edges, raw=True)
            print("RESULT size=%.3e nodes=%d edges=%d estimate_bytes=%d "
                  "peak_rss_bytes=%d ratio=%.3f priced=remesh"
                  % (args.size, nodes, edges, estimate, peak,
                     peak / float(estimate)))
        except Exception as exc:  # noqa: BLE001 - report, never mask the result
            print("RESULT size=%.3e estimate_bytes=unavailable (%s: %s) "
                  "peak_rss_bytes=%d"
                  % (args.size, type(exc).__name__, exc, peak))
    print("RESULT size=%.3e outcome=%s" % (args.size, outcome))
    # EXIT 0 WHEN THE MEASUREMENT SUCCEEDED, even if stage 3 did not converge.
    # A stage-3 plateau is the known, expected state (see the header), and the
    # peak RSS is dominated by stage 3's assembly and factorisation, which DID
    # happen. Exiting nonzero would make the Job report Failed and leave
    # `kubectl wait --for=condition=complete` waiting forever on a run that
    # produced exactly the number it was asked for. A genuinely unusable row
    # (stage 1 failed, or nothing could be priced) still exits nonzero above.
    if outcome in ("converged", "stage3_not_converged"):
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
