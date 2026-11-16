# Facts for the solver deep dive — public source `7248447`

Every claim below is checkable at the public repo commit `7248447`
(2026-11-09). Citations are `path:line` or `path:function`. Where a
docstring and the code disagree, the code is reported and the difference
flagged. Where a number exists only in private history it is **omitted**.

Three words are used precisely and should survive into the draft:

- **analytic** — compared against a closed-form answer the code does not use.
- **self-consistency** — two of our own methods agreeing (catches typos, not
  model error).
- **regression pin** — a recorded number asserted to not drift (catches
  breakage, proves nothing about physics).

---

## 1. Mesh → solver

There are **two meshers for two solvers**, and they produce different
objects. The FEM path gets a tetrahedral mesh; the FDTD path gets a
**voxel** grid. They do not share a mesh representation.

**FEM path.** `mse_maxwell_solver.solve` (`dockerfiles/maxwell_solver/mse_maxwell_solver.py:234`)
meshes first, then calls the eigensolver. Two branches:

- one-part vacuum: `MESH.load_surface` then `MESH.tetrahedralize`
  (`mse_maxwell_solver.py:351-356`);
- multi-part: `PARTS.load_parts` (which validates the PLC) then
  `PARTS.merged_surface` then `tetrahedralize` with a region attribute per
  part (`mse_maxwell_solver.py:341-350`).

The mesher is **TetGen**, via the `tetgen` Python binding
(`mse_meshing.py:805` onward).

**Quality checks (FEM).** These are real refusals, not warnings:

- `mindihedral=20, minratio=2.0, fixedvolume=True` on the one-part path
  (`mse_meshing.py:817`). Comment at `:814-816`: "minratio/mindihedral keep
  element quality up; fixedvolume makes maxvolume binding."
- `docheck=True` on the multi-part path (`mse_meshing.py:894`) — described
  at `:838` as "the **OVERLAP instrument**. TetGen checks its own PLC".
- A **per-region resolution verdict**, `_resolution_verdict`
  (`mse_meshing.py:184`). Each region is judged against *its own* required
  edge, not the wall's. The docstring at `:199-203` states why: the guard
  used to compare the whole mesh's median edge against the wall's
  allowance, and a cap retry could leave a dense core "several times
  coarser than its own rule while the wall's median still sits inside the
  wall's allowance." The refusal threshold is
  `MAX_EDGE_OVERSHOOT = 1.6` (`mse_common.py:110`).
- The target edge is `wavelength_m / edges_per_wavelength`, with
  `MSE_EDGES_PER_WAVELENGTH` default 7 (`mse_common.py:250-251`).
- `MAX_MESH_ATTEMPTS = 4` (`mse_meshing.py:129`) — a cap retry loop.

**A measured failure of the sizing field, worth quoting** because it is the
kind of thing a science writer can use. `mse_meshing.py:1817-1821`:

> "asked for 3 nm in the oxide it built 605,240 tets and still left a
> 12.0 nm-tall element in the 12 nm layer — the field is a target, not a
> bound. Three sub-slabs give 108,378 tets (400 nm bulk edge) and a 4.00 nm
> worst span, by construction."

**FDTD path.** `fdtd_voxel.voxelise` (`fdtd_voxel.py:483`) returns
`{"eps", "pec", "metals"}`. Materials are sampled per node by a volume
average over the dual cell (`fdtd_voxel.py:518-520`,
`fdtd_grid.average_eps`). Inside/outside is a +z ray count with a jitter
(`fdtd_voxel.py:17-23`) so "no ray can pass through an edge or vertex."

FDTD voxelisation checks: overlapping parts refused ("parts may touch, but
not share volume", `fdtd_voxel.py:198`), non-positive index refused, bad
boundary refused, zero-area triangles refused (`fdtd_voxel.py:93`). Layout
checks: sources/probes may not lie in the PML (`fdtd_layout.py:123-124`),
and may not sit on conductor nodes (`fdtd_layout.py:139-160`).

**Honest gap:** there is **no** triangle-quality, watertightness or
manifold check in the FDTD voxel path — the geometry is sampled, not
meshed, so those checks belong to TetGen on the FEM side only.

---

## 2. FEM eigensolver

**The weak form** is the curl-curl problem in edge-element (Whitney 1-form)
form:

    A x = k² B x

with `A` the curl-curl stiffness and `B` the **ε-weighted mass matrix**.
The element is the **lowest-order Nédélec edge element on linear tets**
(`mse_maxwell_solver.py:5`: "lowest-order Nedelec"). Whitney forms are named
in `mse_fem.py` and `README.md`.

**Materials enter through `B`.** `mse_eigen._solve_modes_on`
(`mse_eigen.py:239`) documents that the projector is built from `B` "and
that is correct for every material because `B` IS the eps-weighted mass".
The code is explicit that there is **no separate `M_eps`** argument, with
this reasoning at `mse_eigen.py:265-271`:

> "Two parameters that must agree are two parameters that can drift, and
> the failure they produce — a projector built from the vacuum mass while
> the eigenproblem uses the eps-weighted one — enforces `div(E) = 0`
> instead of `div(eps E) = 0`."

`eps_r` is defined in **one** place, `n_region²` per tet
(`mse_maxwell_solver.py:361-390`), and everything reads that array.

**Dispersion is not in the eigenproblem.** In `mse_fem.py`, materials are
real `n` (`eps_r = n²` per tet, above). The dispersive (Drude–Lorentz) model lives in the FDTD path only
(`fdtd.py:474` onward). Do not say the FEM solver has a dispersive mode.

**Boundary conditions:** PEC. Tangential E is constrained at the wall; the
free edges are what is solved for. Eigenvalues come back as `k²` in 1/m²,
ascending (`mse_eigen.py:283`).

**The shift strategy is the interesting part, and it is a real
engineering story.** Naive shift-invert fails here, because the curl-curl
operator has a large null space of gradient fields, and `B` is singular on
it. `mse_eigen.py:1-32` describes the fix — **projected shift-invert**:

1. Build the discrete gradient `G` on free edges against interior nodes:
   `G[e, j] = +1`, `G[e, i] = -1`. For a simply-connected cavity
   `null(A_free) = range(G_f)` exactly (`mse_eigen.py:13-15`).
2. Use a **negative** shift `sigma = -s`, `s ~ (pi/D)^2`, so `K = A + sB` is
   SPD and factorises once (`mse_eigen.py:16-18`).
3. Project out the null space with the B-orthogonal projector
   `P y = y − G_f (G_fᵀ B G_f)⁻¹ G_fᵀ B y` (`mse_eigen.py:19-21`).
4. `eigsh(A, k, M=B, sigma=-s, which='LM', OPinv=P∘K⁻¹, v0=P(random))`
   (`mse_eigen.py:22`). SciPy maps back `lambda = sigma + 1/theta`, so the
   lowest physical modes are the *largest* `theta`.

The payoff, stated at `mse_eigen.py:24-26`: "With the null space projected
out there are no spurious vectors to filter, so the
`lambda < 1e-6 * max(lambda)` test becomes an **assertion rather than a
filter**." That is the clean, quotable line: the algorithm removes the
failure mode instead of detecting it afterwards.

**Library:** SciPy's `scipy.sparse.linalg.eigsh` (ARPACK). `SHIFT_FRACTION = 1.0`
(`mse_eigen.py:39`).

**First principles:** this derivation is proper for the writer to source
from Nédélec (1980) and Whitney (1957) — but note the **code does not cite
those papers**; it uses the names. Yee is named in `fdtd.py` without a
citation. **Berenger is not mentioned anywhere** — the PML is CPML, not
Berenger's split-field, and attributing it to Berenger would be wrong.

---

## 3. FDTD

**Yee scheme.** The layout is stated at `fdtd.py:6-9`:
`Ex(i+½,j,k) Ey(i,j+½,k) Ez(i,j,k+½)` / `Hx(i,j+½,k+½) …`, "so each H
component is the complement of the E one it curls." The loop is
`update_h` / `update_e` inside `simulate` (`fdtd.py:3433`, `:3459`): E at n
→ H at n+½ → E at n+1.

**Courant limit** is computed, not a constant:
`courant_limit` (`fdtd.py:175`) returns `1/(c0√(Σ 1/h²))`; a safety factor
`SAFETY = 0.99` (`fdtd.py:88`) multiplies it (`courant_dt`, `fdtd.py:208`).
There is **no `assert`** — it raises if outside (0,1) (`fdtd.py:203-206`).

**Absorbing boundary is CPML** (convolutional PML), **not** Berenger
split-field and not UPML. The code cites no paper for CPML; the standard
attribution (Roden & Gedney, 2000) is the writer's to source. The recursion is `corrected(...)`
(`fdtd.py:3299`): `store *= a; store += b·raw; return raw + store`, with
`kappa = 1`. Default `DEFAULT_PML_CELLS = 10` (`fdtd.py:103`). Profile:
`sigma_max = (m+1)·ln(1/R)/(2·eta0·t)`, `m = 2`, `R = 1e-12`
(`fdtd.py:104-105`, `:1047-1051`). **Measured reflection** (`fdtd.py:92-99`, on a 1-D
reduction of the update): worst amplitude **3.6e-3** at 75° incidence and
40 cells/wavelength, and **3.0e-4** at normal incidence (20 cells/wavelength).
The 3.6e-3 is the worst case of a sweep, not the typical reflection. The file
also says grazing incidence on a fine grid is what this grading cannot fix.

**Gold dispersion.** This is the **Lorentz–Drude** model — one Drude term
plus Lorentz oscillators — evaluated by `permittivity(metal, frequency)`
(`fdtd.py:586-593`):

    eps(w) = 1 + Σ_j f_j·wp² / (w_j² − w² − i·w·G_j)

It is **not** critical points. Three gold fits ship, each with its own
measured error:

| key | source | worst relative eps error |
|---|---|---|
| `Au` (Rakić) | Rakić et al., Appl. Opt. 37, 5271 (1998) | — |
| `Au-palik` | Palik, Handbook… (1985), p. 290 | **1.4951%** at 652.5 nm (`fdtd.py:536`) |
| `Au-jc` | Johnson & Christy, PRB 6, 4370 (1972) | **0.4080%** at 892.0 nm (`fdtd.py:560-561`) |

The J&C fit is fitted to `data/jc_au_nk.csv` from refractiveindex.info
(`fdtd.py:548-551`). These three numbers are checkable and excellent for a
story: the best fit is 0.4% over its band.

**Graded mesh and thin films.** `graded_axis` (`fdtd_grid.py:124`) with
`MAX_RATIO = 1.3` (neighbour spacing ratio), `MIN_CELLS = 4` (cells across
a layer thinner than the coarse cell), `GROWTH = 0.2` per cell
(`fdtd_grid.py:35-37`). Neighbour spacing obeys
`h[i] ≤ h[i−1] + GROWTH·gap`; violations are repaired by shrinking ×0.7, up
to 60 attempts (`fdtd_grid.py:167-170`).

The **grid-line detail** is a good measured anecdote. `fdtd_layout.py:14-19`:
every flat face gets a grid line along its normal axis, because without
them "the film read **one cell too thick on almost every grid offset** from
its faces (the reviewer measured **5 cells for a 4-cell film at 19 of 20
offsets**)."

---

## 4. Resonance extraction

**Neither Prony nor pure matrix pencil — it is FDM (Harminv) plus an SVD
matrix pencil as a cross-check.** "Prony" appears **nowhere** in
`resonances.py` or `docs/resonances.md`. Entry point
`find_resonances`, default `method="fdm"` (`resonances.py:922`).

- **FDM** = filter-diagonalisation of Mandelshtam & Taylor, *J. Chem.
  Phys.* 107, 6756 (1997), as implemented in Harminv (`resonances.py:17-24`).
  Poles `u_k = exp(−2πi f_k dt − γ_k dt)` (`:375-376`).
- **Matrix pencil** = Hua & Sarkar, *IEEE Trans. ASSP* 38, 814 (1990)
  (`resonances.py:30`, `:409-410`). SVD → `V₁,V₂` → `A = V₂·pinv(V₁)` →
  `eig(A)` (`resonances.py:459-473`). The docstring at `:34-38` calls it
  "global (no window enters the algebra) and algebraically unrelated to the
  FDM, which is what makes it a cross-check."

**Model order is chosen, not fixed.** Pencil rank: keep singular values
above `1e-10·s₀` and above `2.5×median` noise floor, capped at `L//2`,
with `L = min(N//3, 256)` (`resonances.py:460-464`, `:412`, `:418`, `:441`).
FDM basis: `n_basis = ceil(1.1 · (f_max−f_min) · (M+1) · dt)` (`:392-393`).
There is **no AIC/BIC** anywhere.

**Cramér–Rao bars** come from the **full multi-mode Fisher matrix**:
`cramer_rao(modes, dt, n, sigma², *, real)` (`resonances.py:633`), citing
"the inverse of the Fisher matrix of the full multi-mode model (Kay 1993,
eq. 3.31)" (`:638-639`). The short-record formula is
`std(f) = std(γ)/(2π) = √(6/(SNR·N))/(2πT)` (`:61-63`). Noise variance is
**estimated**, from the lower 80% of the periodogram (white noise's
periodogram is exponential; `mean lower 80% = 0.5981·N·σ²`, `:530-532`).
Bars reported at `error_sigma`, default 3 (`:924`).

**Measured performance, with the honest failure modes.** From
`docs/resonances.md`:
- median actual error 0.67–0.8 of the reported 1σ (`:136-138`) — the bars
  are well calibrated;
- the short-record formula is **20% optimistic** at `γT = 0.5` (`:137-138`);
- raw (unpolished) bars scatter at **2.5–3.5×** the bound (FDM) and ~2×
  (pencil), which is *why* polishing is the default (`:163-165`);
- at 0 dB on a real record one seed in 40 was **5.4σ off in Q**; the
  likelihood in (f,γ) is no longer single-peaked (`:146-148`);
- do not read the bars as bounds below ~10 dB (`resonances.py:102-104`).

**Status:** no production code outside the module and its tests calls
`find_resonances`. It is **not yet wired into the app**. Do not describe it
as running in the pipeline.

---

## 5. Electrostatics / semiconductor solvers

These are **in the public tree** but are **not** on the FEM/FDTD mesh
pipeline described above, and the **DEVSIM drift-diffusion + axisymmetric
electrical stack is NOT in the public sync** (merged after 2026-11-09). If
the draft mentions it, say it exists and is unreleased. One line each from
the public code:

- `coulomb.py` — "The first-order electron–hole Coulomb term and the exciton
  energy E_X(F)" for a single InAsP quantum dot, two confined carriers in a
  uniform Cartesian box (`coulomb.py:1-6`).
- `stark.py` — "Effective-mass quantum-confined states on a Cartesian box":
  the confined-carrier eigenproblem given `m*`, a box, and
  `V = −e·phi`, turning an electrostatic field into an energy shift
  (`stark.py:1-6`).
- `exciton.py` — "The exciton Stark shift E_X(F) and the p/beta fit",
  `E_X(F) = E_e(F) + E_h(F) + E_C` (`exciton.py:1-6`).

These are effective-mass/envelope models on a **box**, not on a general
tetrahedral mesh.

---

## 6. How the framework calls them

The **real call path**:

    web app (Flask)  →  web/jobs.py  →  Kubernetes Job  →  mse_maxwell_solver.solve

Specifically:

1. `web/jobs.py` builds the Job's args (`--job-id --units --n-index
   --n-modes`, plus `--min-feature`, `--scale`) at `web/jobs.py:94-145`.
2. The image's entrypoint is the solver CLI, so those args land in
   `mse_maxwell_solver.solve` directly. There is **no separate worker
   process in between** on the CPU path — the Job *is* the solver process.
   (`mse_worker.py` in the worker/ tree is for the Jetson GPU bench seat,
   not the cluster Job path.)
3. `solve()` (`mse_maxwell_solver.py:234`) → `stage("meshing")` →
   `MESH.tetrahedralize` → `stage` → `EIG.solve_modes`
   (`mse_eigen.solve_modes`, `mse_eigen.py:133`).
4. `mse_backend.py` (`BACKEND.selected_backend()`) selects `cpu`/`gpu`,
   **resolved once** in `solve()` and passed explicitly, "so the mesh-count
   guard below and the factorisation cannot disagree about which machine is
   running — reading the env twice would let a test set it after the guard
   had already decided" (`mse_maxwell_solver.py:245-249`).

**Routing run before the solve** (`mse_maxwell_solver.py:399-430`): if the
actual tet count exceeds the CPU limit, raise `TooBigForProcessor` so the
app re-routes to the GPU queue; if it exceeds the absolute cap, raise
`MeshingError` the owner can read. The distinction is spelled out at
`mse_maxwell_solver.py:404-410`.

**GPU path:** cuDSS via nvmath (`mse_backend.py:19`). The GPU import is
**lazy and has no fallback** (`mse_backend.py:25`).

---

## 7. Validation — real measured numbers

**FEM, a true analytic check.** `tests/test_maxwell_solver.py:201`,
`test_box_first_ten_modes_match_analytic`: the first 10 modes of a
**10 × 7 × 5 mm PEC box** within **3%** of

    k² = (m·π/a)² + (p·π/b)² + (q·π/d)²

with the TE/TM selection rule that at most one index may be zero
(`test_maxwell_solver.py:1-12`). The expected `k` values are listed at
`:14-17` (`0.5478 0.7025 0.7721 …`, in 1/mm). The solver also asserts **no
spurious modes** (`:206`). `dockerfiles/maxwell_solver/README.md:58` says
"the box bench passes at **0.29%**" — a prose claim, not an assertion.

**Refractive-index scaling, exact** (`test_maxwell_solver.py:221-228`):
`k` is unchanged at `n = 1.5` and every frequency scales by exactly
`1/1.5`, `rtol = 1e-9`. This is a genuine physics check (the in-medium `k`
is a property of geometry alone).

**Photonic crystal, convergence order.** `tests/test_pc.py:940` matches a
transfer-matrix band to `rel ≤ 3e-4`, and `:950` asserts the convergence
order is between **1.7 and 2.3** (second order, as a P1 element should be).
Recorded convergence at `:876`: `6.9e-4 at div 16, 1.7e-4 at div 32,
4.3e-5 at div 64`; production mesh (div 40) sits at **1.2e-4**. That is a
clean, quotable table.

**FDTD: Purcell factor against the image-dipole law.**
(Corrected 2026-11-11 after blog-editor's check: an earlier version said the
FDTD test compares against an exact Sommerfeld integral. It does not. At
7248447 no test or benchmark imports `purcell_reference.py`.)
The FDTD **PEC mirror** reads the image-dipole law, a closed form defined in
the test itself (`image_dipole_factor`, `tests/test_fdtd_purcell.py:607`),
"to within **0.05** of it (the fixture's own sweep runs **+2.9 per
cent at gap 7 and −4.5** at gap 10 … what spends the difference is the
source's own cell, not the law)" (`tests/test_fdtd_purcell.py:33-35`,
`:79-82`, assertion at `:763-806`).
Separately, `purcell_reference.py` computes the Purcell factor of a dipole
above a planar stack from the Sommerfeld form (Novotny & Hecht, *Principles
of Nano-Optics*, 2006, ch. 10). Its own tests check it against closed forms,
e.g. glass-interface values to `1e-12` (`tests/test_purcell_reference.py:211-212`),
but no FDTD run is compared against it yet.

**FDTD: energy ledger.** The delivered power summed over the closed box is
**0.9999997** of the energy the grid gained, while the one-step-out variant
is **−40.2180** of it — "40 times too large, and negative"
(`tests/test_fdtd_purcell.py:30-32`). This is the kind of self-check a
science reader will enjoy: the wrong discretisation doesn't taste slightly
off, it fails by two orders of magnitude and the wrong sign.

**FDTD: metal fits** — the errors in the table in §3 are asserted:
`abs(worst − 0.014951) < 1e-5` and `abs(worst − 0.004080326) < 1e-9`
(`tests/test_fdtd_metals.py:143`, `:213`).

**Resonance extraction: Cramér–Rao calibration** — the table in §4, and
"the largest excursion in 240 draws was **3.1σ**" (`README.md:28`,
`resonances.py:100`, `docs/resonances.md:140`).

**Electrostatics:** `tests/test_electrostatics_bench.py:119` a slab matches
its closed form to `< 1e-9`; `:125` concentric shells match the meshed
series to `< 2e-3`.

**Weak spots found while checking** (`tests/`):
- `tests/test_materials_library.py:136` `xfail(strict=True)` — "exactly 11
  parameters have no source", pinned at `:266 assert absent == 11`. This is
  true at the public sync; the private tree has since cited 3 more (now 8),
  which will appear after the next sync.
- Several `skip`s for environment reasons (no GPU, no openssl, no trimesh
  boolean backend) — not physics.

---

## 8. What NOT to say, and what we're proudest of

### Do not say

- **The sizing field is a bound.** It is a *target*; the file measures
  605,240 tets and a 12.0 nm element in a 12 nm layer at a 3 nm request
  (`mse_meshing.py:1817-1821`).
- **The PML is Berenger's split-field.** It is CPML, and Berenger is not
  cited anywhere. The *measured* reflection at default settings is
  **3.6e-3** (`fdtd.py:92-99`) — honest, not magical.
- **The FEM solver is dispersive.** Materials are real `n`; dispersion is
  FDTD-only.
- **The resonance extractor is in production.** It is not wired in.
- **The electrical/DEVSIM stack is released.** It merged after 2026-11-09
  and is not in the public sync.
- **That imported-geometry meshing is solved.** `README.md:51`: "Mesh
  generation for arbitrary imported geometry is the least settled part." A
  good honest line to quote directly.
- **Photonic-crystal plan (`docs/photonic-crystal-plan.md:3`)** is "PLAN
  ONLY", and `:23` says "1e-6 is not achievable on a P1 mesh" — only
  `λ = 0` at Γ is exact. Do not overstate band-structure accuracy.
- **That every material parameter is sourced.** 11 have no source at the
  public sync (strict xfail); 8 after the next sync.

### Proudest results (each with a recorded number)

1. **Null-space removal turns a filter into an assertion.**
   `mse_eigen.py:24-26`: projected shift-invert leaves no spurious vectors,
   so `λ < 1e-6·max(λ)` is an assertion, not a cleanup. First 10 modes of a
   PEC box within **3%** of analytic (`test_maxwell_solver.py:201-212`);
   scaling law exact to `1e-9`.
2. **A closed-form check for a resonant measurement.** The FDTD Purcell
   factor above a PEC mirror is checked against the image-dipole law, not
   another simulation, and lands within **0.05** of it
   (`test_fdtd_purcell.py:33`, `:763`). The exact Sommerfeld reference
   (`purcell_reference.py`) exists but is not yet wired to any FDTD test.
3. **Error bars that are honestly calibrated and honestly capped.** The
   Cramér–Rao machinery reports **1σ** the estimate actually achieves to
   within ~20% (`docs/resonances.md:136-138`), and the docs *say* the bars
   fail below 10 dB and by how much. A method that publishes its own
   breakdown is the strongest thing here.

---

*Prepared 2026-11-11 by the mse builder; checked by the mse lead against
`7248447` (each cited number grepped at its path; four corrections made:
a file that is not in the public tree, an uncited CPML attribution, the
conditions of the 3.6e-3 reflection, and the material-gap count).*
