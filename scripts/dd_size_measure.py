"""Peak RSS of one coupled drift-diffusion solve vs the estimator (task 2.5).

Run INSIDE the solver image, never natively: a DEVSIM solve is exactly the
heavy work the VM must not do.

    docker run --rm --cpus=2 --memory=2g -v "$PWD:/src:ro" \
      -e DEVSIM_MATH_LIBS="libblas.so.3:liblapack.so.3" \
      --entrypoint python registry.example/mode-search-engine/mse-solver:devsim-2.1 -I \
      /src/scripts/dd_size_measure.py

Prints the estimate, the measured peak RSS and their ratio. The ratio is
REPORTED, not tuned: the estimator's factors are documented constants and the
test asserts same-order agreement, because a factor fitted to one measurement
on one machine is a curve fit rather than a model.
"""

import os
import resource
import sys

sys.path.insert(0, "/src/dockerfiles/maxwell_solver")

import mse_axisymmetric as m  # noqa: E402


def peak_rss_bytes():
    """Peak RSS this process has reached, in bytes."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024


def main():
    n_z = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    n_r = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    refine = 1e-9
    # This must be the grid solve_abrupt_junction_dd builds, or the comparison
    # is between two different meshes and means nothing. It builds
    # build_grid(0.0, r_max=max(4*refine, 1e-8), z_min=z_lo, z_max=z_hi, ...).
    grid = m.build_grid(0.0, r_max=max(4.0 * refine, 1.0e-8),
                        z_min=-2e-6, z_max=2e-6, n_r=n_r, n_z=n_z,
                        refine=refine, refine_halfwidth=1.5 * m.analytic_depletion_width(
                            11.7, 1e18, 1e18, m.analytic_v_bi(1e18, 1e18, 1.0e10)))
    estimate = m.estimate_job_bytes(grid)
    print("RESULT grid %dx%d nodes=%d estimates=%dB (%.3f GiB)"
          % (n_r, n_z, grid.n_nodes, estimate, estimate / m.GIB))
    print("RESULT rss_before_solve=%dB" % peak_rss_bytes())

    m.solve_abrupt_junction_dd(
        n_a=1e18, n_d=1e18, n_i=1.0e10, eps_s=11.7,
        z_lo=-2e-6, z_hi=2e-6, n_r=n_r, n_z=n_z, refine=1e-9)

    peak = peak_rss_bytes()
    ratio = peak / float(estimate) if estimate else float("nan")
    print("RESULT peak_rss=%dB (%.3f GiB) estimate=%.3f GiB ratio=%.2fx"
          % (peak, peak / m.GIB, estimate / m.GIB, ratio))


if __name__ == "__main__":
    main()
