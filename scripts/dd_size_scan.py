"""Scan the drift-diffusion estimate across sizes (task 2.5).

Answers: which meshes does the estimator refuse, and are those the ones that
would actually exceed the Job's memory. No solve here — this is the estimator
alone, so it is cheap and never the VM's heavy work.

    docker run --rm --cpus=2 --memory=2g -v "$PWD:/src:ro" \
      -e DEVSIM_MATH_LIBS="libblas.so.3:liblapack.so.3" \
      --entrypoint python registry.example/mode-search-engine/mse-solver:devsim-2.1 -I /src/scripts/dd_size_scan.py
"""

import sys

sys.path.insert(0, "/src/dockerfiles/maxwell_solver")

import mse_axisymmetric as m  # noqa: E402
import mse_common  # noqa: E402


def main():
    limit_gib = mse_common.DEFAULT_JOB_MEMORY_BYTES / 2.0 ** 30
    print(f"job memory limit: {limit_gib:.1f} GiB")
    print(f"{'n_z':>6} {'n_r':>4} {'nodes':>8} {'edges':>9} {'estimate':>10} {'verdict':>10}")
    for n_z, n_r in [(2000, 12), (4000, 12), (8000, 12), (12000, 12),
                     (2000, 60), (4000, 60), (8000, 60), (16000, 60)]:
        grid = m.build_grid(0.0, r_max=1e-8, z_min=-2e-6, z_max=2e-6,
                            n_r=n_r, n_z=n_z, refine=1e-9,
                            refine_halfwidth=1.5 * m.analytic_depletion_width(
                                11.7 * 8.854e-12, 1e18, 1e18, 1e10))
        est = m.estimate_job_bytes(grid)
        gib = est / 2.0 ** 30
        verdict = "refuse" if gib > limit_gib else "allow"
        print(f"{n_z:6d} {n_r:4d} {grid.n_nodes:8d} {((grid.n_r-1)*grid.n_z + grid.n_r*(grid.n_z-1)):9d} "
              f"{gib:8.2f}GiB {verdict:>10}")


if __name__ == "__main__":
    main()
