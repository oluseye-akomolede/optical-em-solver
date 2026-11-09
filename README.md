# optical_experiments

A 3-D electromagnetic solver platform for optical and RF structures, built to answer questions about real devices: what are the modes of this cavity, what does this coat of gold reflect, where does this photonic crystal put its band gap.

I designed it and directed an AI agent team that wrote it. The architecture, the choice of what to validate and against what, and the judgement of which answers to trust are mine. The code is the team's, written against specs I reviewed.

## What it does

Upload a meshed 3-D model, pick the material from a library (gold optical constants from both Palik's handbook and Johnson and Christy ship in `data/`), and the platform computes the structure's electromagnetic modes on a small self-hosted Kubernetes cluster.

Three solvers sit behind one web app:

- **Frequency domain, vector eigensolver.** Lowest-order Nedelec (Whitney) edge elements on linear tetrahedra (`dockerfiles/maxwell_solver/mse_fem.py`), assembled as a sparse generalized eigenvalue problem. Edge elements are the right choice for vector fields because nodal elements produce spurious modes.
- **Time domain, FDTD.** A voxelised finite-difference time-domain solver with graded meshing, thin-film refinement and dispersion fitted to measured metal data (`dockerfiles/maxwell_solver/fdtd.py`).
- **Resonance extraction.** Prony and matrix-pencil analysis of the time-domain record, with error bars from the Cramer-Rao bound (`docs/resonances.md`).

Jobs are queued in Postgres and claimed by a long-lived worker process on an NVIDIA Jetson Orin Nano (`worker/mse_worker.py`). The worker keeps its CUDA context warm on purpose, because re-initialising per job is the cost the design exists to avoid.

## How it is validated

Every solver is checked against an answer known independently, and a benchmark that fails its gate fails loudly rather than printing a number.

- **Parallel-plate cavity.** A thin dielectric film between PEC plates, driven with E normal to the plates, must reproduce the analytic lateral modes to within 1%, at two film thicknesses (`scripts/fdtd_bench_v5.py`). The modes depend on the index, not the film thickness, so matching them shows the film is actually seen by the grid.
- **Gold slab reflectance.** A plane wave on a gold slab must reproduce the analytic Fresnel reflectance to within 0.02 (absolute) across the pulse band (`openspec/specs/time-domain/spec.md`).
- **Published band gap.** The MPB tutorial's triangular rod lattice (TM, r = 0.2a, eps = 12) must reproduce the tutorial's printed 1-2 gap to within 1% of midgap (`openspec/specs/photonic-bands/spec.md`).
- **Photonic crystal bands.** A Bloch-periodic pulse run must land within 1% of the band solver's frequencies at the same k, for both polarizations, with every excitable band in the pulse window present (`scripts/fdtd_bench_v6.py`). A deliberately wrong k-to-phase mapping moves every line by far more than 1%, so the benchmark catches the failure the symmetry checks cannot see.
- **Nanowire cavity from a published paper.** A hexagonal InP nanowire quantum-dot cavity on a gold mirror (arXiv:2601.04440), set up with the geometry pinned from the paper (a wire 1375 nm by 420 nm, a 12 nm SiO2 buffer, a 10 nm mesh in the wire), and the hexagonal width converted through the paper's own relation, 2s = 1.14 D (`scripts/paper1_nanowire.py`).
- **Resonance extraction.** The reported error bars are checked against both the Cramer-Rao bound and simulated noise: on complex records at 10 dB, the largest excursion in 240 draws was 3.1 sigma (`docs/resonances.md`).

## How to run it

The web app and the worker are separate processes. Dependencies are in `requirements.txt` (Flask, boto3, trimesh, Werkzeug).

```sh
pip install -r requirements.txt
python -m web.app                 # the web app and job API
python -m worker.mse_worker       # the GPU worker, needs the CUDA solver tree
```

`worker/README.md` documents the JetPack and cuDSS setup on the Orin, including why the Jetson aarch64 build of cuDSS is required rather than the pip wheel.

The benchmarks run standalone against the solver tree and print their gate result:

```sh
python scripts/fdtd_bench_v5.py
python scripts/fdtd_bench_v6.py
```

## Status

This is a working research platform, not a product. The three solvers run and are gated against known answers. Mesh generation for arbitrary imported geometry is the least settled part. Some benchmarks document their own boundaries in the file header, and those notes are the reading of what is proven and what is only supported.

The tests directory holds the contract and integration tests; the tests that need a GPU or a running cluster are skipped when neither is present.

## What is not here

The decks, papers and internal working notes around this platform are not in this repository, and neither is any cluster configuration. What is here is self-contained: the solver, the app, the benchmarks and the material data.
