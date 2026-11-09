# Tasks — electrical-simulation (general-purpose electrical solver; paper 1 is a bench)

Every local run uses `nice -n 19` and `(ulimit -v 4194304; ...)` with tiny inputs, per the
rig's tier-1 rule. Mid-size runs go to the Jetson (tier 2) one at a time; cluster runs are
bounded Jobs in `mode-search-engine` (tier 3). Each numbered item is one reviewable commit.
Every bench check prints its value, reference and tolerance, and each mutation scenario is
proven red once (mutate, confirm exit 1, revert) before the check counts.

## 0. Owner decisions
- [x] 0.1 **SUPERSEDED 2026-11-02 by 0.3 (owner chose a general solver; loss in scope).
      NOT the owner's current answers; kept verbatim only as the record rev2 was built on.**
      Questions sent; the owner answered in Slack on 2026-11-01:
      1 = **c**: the first device is the paper-1 nanowire QD with a gate or p-i-n contact.
      2 = **full electrical analysis**: electrostatics, the Stark shift vs voltage and p-i-n
      injection / I-V (drift-diffusion), with emission energy, dipole and timing feeding the
      existing Purcell runs.
      3 = **show results in the web app**.
      4 = **full 3D**.
      5 = **just paper 1**: "We'll be investigating the Majorana 2 paper next."
      6 = **"I'm not sure, try loss"**.
      These moved Phase 1, so the specs were revised before any code (this revision).
      Superconductors moved to the not-started change `superconductor-models`.
- [x] 0.2 Fetch every source marked **(unsure)** before a test quotes it, read every value
      the materials library will ship from its cited source, and correct `design.md` where
      it is wrong: paper 1's dot material, size and lifetime/Γ₀; the effective masses and
      ε_s of every library semiconductor (Vurgaftman 2001); InP n and free-carrier
      absorption at the emission wavelength; the Finley 2004 article number; DEVSIM's
      aarch64 wheels, mesh import route, cylindrical option and linear solvers; Sesame's
      venue and dimensionality. No library number ships from memory.
      **TICKED 2026-11-05 by the lead's call (`qitem-20261105101719`, elec 1.10a step 1),
      merge `ee4e1b5`.** The *task* — fetch and verify rather than quote from memory — is
      done: the fetch was attempted, and where it failed the failure is recorded.
      **The one open item is CARRIED FORWARD, not closed, under 1.9's open evidence:**
      the InAs_xP_1-x gap and bowing. Earlier status, kept for the record:
      Every dot value that
      ships is now either cited with table/page or marked ASSUMED (see
      `dot_material.py`), which is what 1.9c step 4 asked to confirm. The one
      remaining item is the InAs_xP_1-x band gap and bowing parameter: the
      bounded retrieval came back EMPTY (AIP returns 403; four searches found
      nothing), so that number is recorded as NOT SOURCED rather than filled in.
      Ticking 0.2 would assert a fetch that did not happen. It stays open until
      someone with table-level access to a III-V compilation supplies the gap,
      the offset split and the bowing parameter with section and table.
      **Resolve this FIRST — it decides whether "a ok" has a cheap path at all:** can
      DEVSIM's custom models carry the 2πr weight on node volumes and edge couplings in a
      cylindrical (r, z) mesh (`design.md` §2)? If yes, record the call with a pointer to
      its docs and release. If no, say so here and in `design.md`, and re-price the
      fallback before any axisymmetric code is written: a junction-resolving 3-D only (about
      100 GiB, §5 — does not fit our quota), or a handwritten 2-D solver (scope this
      change currently does not carry). This is the one (unsure) that a headline owner
      deliverable rests on, so it is not left until the other fetches are done.
      **ANSWERED 2026-11-02: yes, and it does not need a custom model.** DEVSIM 2.11.2
      (PyPI, verified on this VM with `DEVSIM_MATH_LIBS=libblas.so.3:liblapack.so.3`)
      ships `cylindrical_node_volume`, `cylindrical_edge_couple` and
      `cylindrical_surface_area`, which apply the 2πr weight directly, with the radial
      axis set by `raxis_variable` / `raxis_zero`. Measured, not read from the docs: on a
      radial strip `EdgeCouple` keeps its Cartesian values after the call (identical arrays)
      while `CylindricalEdgeCouple` scales with r, so the *coupling* — the term that would
      have been wrong if only volumes were weighted — is genuinely cylindrical, and the
      equations must name the `Cylindrical*` models or they silently solve Cartesian. The cylindrical
      volume differs from the exact annulus by exactly `1 + 1/(9·N_r)` on a uniform grid
      and converges at first order (checked at N_r = 10, 20, 40), so refine toward r = 0.
      Evidence and the residual caveat (topology quirks; a full L5 not yet assembled)
      are in `design.md` §2. The 3-D fallback is therefore not needed for the axisymmetric path.
      - **aarch64 (Jetson): answered, yes.** `pip install devsim==2.11.2` builds and imports
        on the Orin (aarch64, Python 3.10.12) in a venv under `~/mse-bench`, and needs **no**
        `DEVSIM_MATH_LIBS` — the aarch64 wheel bundles its own BLAS ("Skipping libblas.so",
        UMFPACK 5.1 loaded). The cylindrical API then works there unchanged (a 6-node
        axisymmetric strip returned cylindrical node volumes summing to 9.948377). This is
        the opposite of the x86-64 wheel, which does need the system BLAS pointer.
      - **mesh import: answered, yes.** `create_gmsh_mesh(file=…, mesh=…)` then
        `add_gmsh_region(mesh=…, gmsh_name=<physical name>, region=…, material=…)`, then
        `finalize_mesh` / `create_device`. A TetGen tetrahedral mesh loads directly: DEVSIM
        derives its boundary triangles, lines and points from the tets, so no separate
        surface file is needed. A 2-D triangle mesh loads the same way for the axisymmetric
        path, with the cylindrical models applying on top of it. Two reader rules cost time
        and are worth knowing: the physical number must be positive (tag 0 is rejected), and
        the element line is Gmsh 2.2 `id type ntags physical_number geometric_tag nodes…`
        with `ntags = 2`. The reader takes `ilist[3]` as the physical number, so inserting a
        separate element index before it puts each element in the group numbered by its own
        element index and breaks region selection by name without an error.
- [x] 0.3 The owner's answers, in their own words (Slack, 2026-11-02). Only two messages
      were sent: 13:19Z, *"Your questions about p-I-n diodes make me think that you're not
      creating a general-purpose electrical simulation ability for our solver. If you are,
      then please enlighten me."* and 13:33Z, *"General ok a ok b yes"*, answering the
      lead's three options:
      - **general ok** = a general electrical job: any parts and materials, optional
        doping, any number of contacts; the QD analysis is an optional add-on and paper 1
        is validation.
      - **a ok** = 3-D current flow ships with a pre-run size check that refuses runs that
        will not fit the quota, plus a faster 2-D option for round shapes; no quota increase
        is asked for.
      - **b yes** = "try loss" means optical absorption by metal contacts — so loss is
        **in scope for this change**, not deferred.
      Design choices made in service of those answers, and NOT owner statements: the
      shipped materials library and its contents; the axisymmetric form being a cylinder;
      the 3-D estimate being priced from the device's own arrays and never retried coarser
      (task 2.4). These are recorded as design in `design.md`.

## 1. Phase 1: electrostatics and the Stark shift
- [x] 1.1 `tetrahedralize(..., sizing=None)`: a per-part target edge built into a `-m`
      background mesh. The default path stays byte-for-byte today's; the maxwell-solver tests
      stay green. Test that the graded mesh's edge in each part is within its target.
      **Fix (reviewer): the override test never reached the guard.** The first fixture
      (n=1.5 core, 4 modes) gave the core a 0.617 mm optical allowance against a 0.273 mm
      achieved edge, so deleting the override changed nothing and the test still passed 10/10.
      Rebuilt on a fine-optics fixture (n=3.5 core, 16 modes): deleting the override makes the
      guard REFUSE, naming the core at 1.642× its optical allowance (needs 0.1665 mm, achieved
      0.2734 mm); with the override present the same build is ACCEPTED at 1.094× its caller
      allowance (0.25 mm). The test now asserts that inequality against the plan the build
      used, so it fails if the fixture stops reaching the line.
- [x] 1.2 P1 assembly with per-part ε_s; one-tet element matrix against the closed form;
      row sums 0. **Done** (`mse_electrostatics.py`: `check_tet_regions`, `eps_by_tet`,
      `element_stiffness`, `assemble_stiffness`). The material is the TET's, from the mesh's
      `region_of_tet`, not its nodes' — a node-derived part cannot represent a boundary that
      runs through a shared face. `mse_fem.tet_geometry` was extracted to module level and is
      now shared, so the `inv(J).T` trap has one home. Tests use relative tolerance: every
      matrix entry is ~1e-11 (ε₀), i.e. far below `np.allclose`'s default `atol=1e-8`, so an
      absolute floor that large would make every comparison vacuous — both the closed-form and
      assembled-matrix assertions pin `atol=0.0`. (An earlier note here claimed the default
      masked a live "3.5% difference"; that figure was never reproduced and is withdrawn — the
      default is a trap for future mismatches, not a present error.)
      Mutations checked: dropping `eps_tet` fails (a)+(d); dropping the transpose in
      `tet_geometry` fails (a) only, which is why (a) has to exist.
      **Interface physics (lead ruling).** The "solved 2× wrong" finding was a
      layers-swapped exact column, not an assembly bug. Added the test that pins the closed
      form: a 1:2 layered block, interface on a node plane, φ = ε_b/(ε_a+ε_b) = 0.6667 exact
      to 2.1e-15 at every node; parametrised over 1:2, 2:1, 1:4, 4:1 so a swapped fixture lands
      on 1/3 or 1/5. Asserted that no tet spans the interface — that conforming property is
      what makes it exact. Mutations (cache cleared first): swap layers → 0.3333; one ε
      everywhere → 0.5000; both red 4/4, restore green 18/18. The docstring no longer claims
      "the whole of the multi-material physics": exact for a conforming interface, not handled
      for a tet spanning two materials, and `check_tet_regions` does not detect one.
- [x] 1.3 Electrode Dirichlet reduction, direct solve through `mse_backend.factor`, input
      refusals, the maximum-principle test.
      **Done.** `mse_electrostatics.solve(points_m, tets, parts, region_of_tet, eps_static,
      electrodes)` returns `phi`/`free`/`electrodes`/`backend`/`n_free`. A contact is a PART:
      every node of every tet in it is held, including nodes shared with the driven material,
      which is what puts the value at the contact rather than one element away. The reduced
      system is `K_ff phi_f = -K_fe phi_e` solved through `BACKEND.factor(..., spd_lu=SPD_LU)`
      (never `spsolve`), so the backend seam and its refusal behaviour are shared with the
      eigen path. Refusals all precede factorising: no electrode; an electrode that is not a
      part; a non-finite potential; two electrodes sharing a node at different volts; an
      assembled part with no eps_static; eps_static < 1 (the shape of an optical index in a
      permittivity slot). A floating dielectric is solved, not refused. Measured on the
      two-layer block: interface potential exact to 2.2e-16 on a 2-D free-node set; maximum
      principle holds at -2 V / +5 V.
      **`skip` is a refusal contract, not a physics knob.** Measured: assembling the held
      parts' tets versus excluding them changes the matrix by 8.4e-12 over 352 entries and
      changes `phi` by exactly 0.0 — the fixed rows and columns are dropped from `K_ff` and
      the fixed values overwritten either way. The M2 mutation (do not exclude) therefore
      SURVIVES, correctly: it removes nothing the answer can see. `skip` is kept because an
      electrode part has no permittivity to supply, and a test pins the 0.0 agreement so a
      later reader neither deletes it nor defends it with a test that cannot fail.
      **Count correction (reviewer).** The 1.3 handoff quoted "30 tests / 77
      passed"; those were read before 1.4 added tests to the same file and can no
      longer be reproduced. On the 1.4 tree the file runs 37 and the six affected
      suites 138 passed / 6 skipped. The measurements below are unchanged; only
      the totals moved. (Re-measured at 1.4's completion, after two more tests
      joined the file: `pytest tests/test_electrostatics.py` 39, and
      `pytest tests/test_electrostatics.py tests/test_solver_sizing.py
      tests/test_maxwell_solver.py` 78 passed / 6 skipped. Suite composition
      differs from the reviewer's six, which is why the second figure is not
      140; the three named above are the ones this branch can run locally in
      under a minute.)
      Five mutations, `__pycache__` cleared between mutate and restore each time:
      eps_tet dropped -> red; skip dropped -> survives (above); shared-node refusal dropped
      -> red; eps<1 refusal dropped -> red; electrode exemption dropped -> red (8 failures).
      The first attempt at the interface test had the fixture wrong (electrodes at slabs
      0.083 wide, so the linear answer spans the GAP not the box) and the code was right.
- [x] 1.4 AMG-CG path (`pyamg`) with the checked residual; the direct-vs-AMG agreement test.
      The switch is `AMG_NODE_CROSSOVER` (5 × 10⁵ nodes, `design.md` §5), a named estimate
      with its arithmetic beside it, not a derived limit — the task proves both paths agree
      either side of it, and names it as the line to revisit when 2.6 measures the real
      per-node cost.
      **Done.** `amg_solve` (smoothed aggregation + CG) and `solve(..., method="auto" |
      "direct" | "amg")`. `solve` returns `method` and `residual` too.
      - *The residual is recomputed against `A` and `b`, never read from pyamg's
        `residuals` list.* That list is relative to pyamg's own initial residual, so it
        answers "how much did I improve" while the caller needs "is the answer right".
        Measured consequence: pyamg warns "Indefinite matrix detected in CG, aborting" on a
        reduced operator it dislikes and returns **x = 0 with relative residual 1.0** — a
        silent wrong answer. The checked residual turns that into a refusal, pinned by a test.
      - *`AMG_RTOL` is 1e-12, and it was measured, not chosen.* 1e-10 was the first value;
        the direct path is exact to 1.2e-15 on the contact-chain fixture, so all the
        difference is AMG's, and at 1e-10 AMG's error against a known-linear answer reached
        6.4e-11 — too close to the bound to assert against. At 1e-12 it is 1.9e-13. The
        agreement test's tolerance is `AMG_RTOL` and its docstring says where it came from.
      - *`method="direct"` exists so the crossover can be proven either side.* Tier 1 cannot
        build a 5 × 10⁵-node mesh, so without it the agreement test could only compare AMG
        with direct above the line. An unknown `method` is REFUSED rather than treated as
        `auto` — a silent fallthrough is the same failure as `MSE_SOLVER_BACKEND=cuda`.
      - *Crossover routing tested in both directions.* Below: `auto` is direct. Above:
        `auto` is AMG (by lowering the constant under a small fixture, since the real one is
        unreachable in tier 1). Mutating `>=` to `>` fails the at-the-line test; deleting the
        auto clause fails it; neither red before these tests existed.
      - *Five mutations, `__pycache__` cleared between mutate and restore:* crossover `>=` ->
        `>` red; auto clause deleted red; method validation deleted red; AMG setup replaced
        by plain scipy CG red; checked residual loosened to `rtol * 1e12` red (2 tests).
        The plain-CG one is the one that mattered: it left EVERY other AMG test green,
        because plain CG converges on these fixtures too, so a test spying on
        `smoothed_aggregation_solver` was added to see the preconditioner at all.
      - Reviewer note 1 (1.3): the `skip` guard cannot be reached through `solve`, so it is
        tested by calling `assemble_stiffness` directly rather than dropped — the assembler
        is a public entry point.
- [x] 1.5 `field_at` and `capacitance_matrix` from the residual charge; three-electrode
      symmetry test.
      - Done. Three-electrode stack with two gaps 3x apart, checked against the exact
        series capacitances, plus a two-plate plate value pinned as measured (1.700e-12 F)
        and its mesh independence. `field_at` checked against -V/d with its SIGN asserted,
        and refused both outside the mesh and inside a held electrode.
      - The three-electrode test caught two real bugs and one process failure:
        `_electrode_charge` negated `K phi` and its docstring asserted that negation was
        the charge (a global sign error every symmetric fixture hides), and the
        `_barycentric` constant `c` contracted against a TRANSPOSED gradient, which
        broadcast a tet-by-tet matrix instead of testing any point.
      - The process failure is the one worth recording: the task said "symmetry test", and
        a transposed `C` IS symmetric, so writing `C[j, i]` instead of `C[i, j]` passed
        the whole 45-test suite FOUR times. No mesh in these fixtures can break reciprocity
        (measured max |C - C^T| = 0.0), so the orientation is unpinnable through `solve`.
        Fixed by splitting `assemble_capacitance` out and pinning the convention on
        deliberately non-symmetric charge maps. The task's "symmetry test" wording would
        have shipped the bug; a symmetry property cannot test an index convention.
- [x] 1.6 Bench fixtures (two-layer slab, concentric spheres, sphere between plates) and
      `scripts/electrostatics_bench.py`. Prove the ε_s-ignored mutation.
      **Lead decision 2026-11-04:** the paper-1 wire fixture moved to 1.6b. Its geometry and
      both ε_s values are still marked unsure, and 0.2 says no test quotes an unsure value.
- [x] 1.6b The paper-1 wire with a top electrode, as a bench fixture labelled UNVALIDATED
      until compared with paper 1. Built at `scripts/paper1_wire_electrode.py` with
      `tests/test_paper1_wire_electrode.py` (15 tests). Same placement and shape as its
      sibling `scripts/paper1_nanowire.py`, which is also a standalone bench script, not
      solver-package code: the "not `scripts/`" note in 1.6 history below is about the
      ELECTROSTATICS fixtures (slab/spheres), which are imported by the solver package and
      run in the container. This one is a bench that stands on its own.
      **The fixture's headline result is a NEGATIVE, and it is measured.** The 12 nm oxide
      inside a 1567 nm stack cannot be resolved by any mesh the current one-part path can
      build: tet z-span falls only as ~n^(-1/3), and the SPREAD is wide -- at n_modes 200
      (153k tets) the MEDIAN element spans 20.4 nm in z and the WORST spans 51.7 nm (at
      n_modes 20 the worst is 110.4 nm), so even the median is 1.7x the oxide. |E| at the
      probe moves **40.1 %** and NOT monotonically across n_modes 20/60/120 (557, 780, 690
      kV/m per volt). Tets STRADDLE the layer boundaries -- measured at n_modes 20, 1064 of
      9775 tets (10.9 %), with 555 crossing z=120 nm and 544 crossing z=132 nm -- so the
      per-centroid layer labels are applied to elements whose
      permittivity is not uniform -- that, not the physics, is what moves. **No field value
      from this fixture is quotable**, and the script and its tests say so (`--convergence`
      prints the spread; `test_the_field_is_not_converged_in_the_mesh` pins it, and
      `test_tets_straddle_layer_boundaries` pins the straddle count so the claim cannot
      drift back to "the label is exact").
      **Reviewer correction 2026-11-04 (`qitem-20261104052338`):** two figures here were
      MAX tet z-span presented as if typical, and one docstring in the function claimed
      TetGen puts Steiner points on the facets so a tet "never straddles a boundary" --
      false, and directly contradicting this entry. Both corrected in `c1819ea`; the
      correction is recorded rather than silently edited because the false comment was the
      shape of error the 0.2 round kept finding: a true-sounding statement about the wrong
      thing, in the code a maintainer would read when deciding the label is safe.
      A fifth control (field falls when the top electrode is withdrawn) is **GONE, not
      merely disabled**: it needed two-part input, which wall (a) does not permit. Do not
      rebuild it here. It becomes worth filing when `mse_meshing` gains internal facets or a
      graded electrical upload -- the same condition that unblocks walls (a) and (b).
      Two walls, both measured, neither fixable in this file: (a) `PartSet` refuses touching
      parts and requires one part to enclose all others, so the four layers cannot be four
      parts (a 12 nm oxide cannot enclose a 1375 nm wire); (b) `sizing=` is REFUSED on a
      one-part upload, so there is no graded path for an electrical mesh. A gate needs a
      change to `mse_meshing` (internal facets at the layer planes, or a graded
      electrical upload), not to the fixture.
      **What IS established:** the solver runs end to end on the paper's geometry; the prism
      volume matches the closed form exactly (rel < 1e-9); the solid is watertight, Euler 2;
      the result is exactly linear in the applied volts (max |dE| = 0 at 2V/2 vs 1V and at
      -1V vs 1V); and direct and AMG agree to 1e-5 on this fixture.
      **Geometry departure, reported not hidden:** every layer carries the wire's hexagonal
      outline, so the electrode is a hexagon of the wire's size rather than the square pad
      plus `ELECTRODE_PAD_NM`; `footprint_error()` returns the 2.408x area ratio that says so.
      `--no-top` and `--heights-run` (the two controls in the earlier draft) were REMOVED when
      the geometry became one solid: a single prism has no withdrawable electrode, and
      leaving flags that do nothing would have been a control that is not a control.
      **1.6 history:** Built and proven: two-layer slab,
      concentric spheres, sphere between plates; the bench and its fixtures live in
      `dockerfiles/maxwell_solver/` beside the solver they exercise (not `scripts/`, so they
      import with the rest of the package and run from a container). Fixtures are in
      `mse_bench_fixtures.py`, the runner in `electrostatics_bench.py`, tests in
      `tests/test_electrostatics_bench.py`. NOT done: the paper-1 wire with a top electrode.

      **The ε_s-ignored mutation is proven.** In `element_stiffness`, dropping the
      `eps_tet` factor turns all three scored quantities red (slab 5.86e-01, shells
      capacitance 6.02e-01, shells interface 9.97e-01), and a 1% error in one shell's eps
      scores 8.98e-03 against a 2e-3 tolerance. Both are now tests, not one-off runs.

      **Review round (1.6 fixes).** The reviewer found that `SPHERE_N_R` was chosen
      because it passed, not because it converged, and that the comments were prose
      rather than measurements. Both correct. `--sweep` now runs three tables; reproduce
      them with `python electrostatics_bench.py --sweep` (they are printed, not stored).
      The honest order estimate is the JOINT sweep (both resolutions refined together):
      capacitance error 6.75e-04 (n_r 16, theta/phi 8/16) -> 1.69e-05 (96, 24/48) at an
      observed order of 2.06-2.08, and the scored mesh (n_r=48, 16/32) sits at 7.05e-05.
      Neither one-dimensional table supports an order claim. Radial-only goes 7.05e-05
      (48) -> 4.15e-07 (128), ~170x for a 2.7x change in h: not order 2, almost certainly
      radial against angular error cancelling, so 4e-7 is not the mesh's accuracy.
      Angular-only RISES, 6.09e-06 at 6/12 -> 7.80e-05 at 24/48; 6/12 is an accidental
      cancellation, not a floor, and at the scored 16/32 the angular error is comparable
      to the radial one and of opposite sign. `rel_ideal` is 7.53e-02 at n_r=8 and
      7.22e-02 for n_r >= 16, and never converges: the conductor shell faces are pinned
      at `r_in+t_shell` with `t_shell` independent of n_r, so that gap is geometry, not
      discretisation. It is reported, never scored.
      `TOL_SHELL` is 5e-4 (7x the floor, 3.3x below the weakest 1% perturbation).
      `TOL_PHI_SHELL` is 5e-3 and is a SANITY CHECK, not an eps detector -- all four
      perturbations move phi by only 0.2x-0.4x of it, and a test freezes that so it
      cannot later be claimed as coverage. `perturbation_table()` scores all four
      against references rebuilt from UNPERTURBED eps, closing the circularity that
      made the first bench blind to a wrong eps.
- [x] 1.6c Layered stacks as conforming regions, graded at thin layers (unblocks 1.10).
      `mse_meshing.tetrahedralize_layers` builds ONE PLC with an internal facet at every
      layer plane, so TetGen cannot put an element across one; region ids are TetGen's
      attributes from per-sub-slab seeds. A layer thinner than `LAYER_ELEMENTS_ACROSS` (3)
      bulk edges is split into 3 sub-slabs of the same region, which GUARANTEES 3 elements
      across it; TetGen's quality bound grades out from there. Spec: `electrostatics`,
      "A layer stack SHALL mesh as conforming regions". Tests: `tests/test_layered_mesh.py`.
      - *Sizing field tried first and rejected, measured (scratch prototype, not kept):* a
        z-graded `-m` background asking for 3 nm in the paper-1 oxide built 605,240 tets
        and still left a 12.0 nm-tall element (a target, not a bound; that run used
        mindihedral 20). Sub-slab facets: 108,378 tets, worst oxide span 4.00 nm.
      - *`mindihedral` is 18 here, not 20, measured:* at 20 the thin-layer capacitor built
        4,878..75,443 tets over edges 20..80 nm with no order in the edge (a refinement
        cascade); at 18 it built 3,113..3,994 at every 5 nm step. `LAYER_MIN_DIHEDRAL`.
      - *Straddles:* 0 crossing / 0 mislabelled on the capacitor and the paper-1 stack. The
        control (same PLC, internal facets removed, centroid labels) straddles 109..799 tets.
      - *Thin-layer capacitor vs exact 1-D series C* (`python electrostatics_bench.py
        --layered`): conforming C rel err 0 / 9.5e-15 / 7.5e-15 at 3,113 / 8,128 / 31,281
        tets. This is round-off and has NO observed order: the 1-D potential is piecewise
        linear with kinks only on mesh facets, so it is in the P1 space and Galerkin
        reproduces it on any conforming mesh. The centroid control: 1.14e-01 / 8.53e-02 /
        5.56e-02, observed order 0.42 then 0.62, thin-layer field off 68 % / 69 % / 21 %.
      - *1.6b rerun on the layered mesh* (`python scripts/paper1_wire_electrode.py
        --layered-convergence`): |E| at the dot 707482.993 V/m per V at 9,710 / 37,924 /
        107,437 tets, spread 7.9e-15, equal to the fixture's exact 1-D value. **It
        converges.** The 40.1 % spread was the centroid labels, all of it. Caveat that
        keeps the fixture UNVALIDATED: every layer has the wire's outline (footprint_error,
        2.408x), so this fixture is a 1-D stack; the paper's wider pad and its fringing
        field are not modelled, and the layered path only takes one common convex outline.
      - *1.6b's own tests unchanged:* `test_the_field_is_not_converged_in_the_mesh` still
        runs on the ONE-PART mesh with its 20 % bar and still passes (40.1 %); the new
        layered test holds the same 20 % bar from the other side plus a 1e-9 check against
        the 1-D value. `EPS_INP` now reads `dot_material.INP_EPS_S` instead of retyping 12.5.
      - *Mutations (`__pycache__` cleared):* interface facets dropped -> 9 red (straddle
        assertion fails on 318 crossing tets, not an exception); seed id by sub-slab instead
        of layer -> 9 red; thin-layer split disabled -> 3 red.
      - *Not done:* the withdrawn-electrode control 1.6b removed is now buildable (the stack
        has separate regions) but was not rebuilt; non-convex or per-layer outlines (the
        paper's square pad) need a polygon-with-holes facet triangulation.
- [x] 1.7 Measure the per-node memory of both solve paths from the bench RSS, replace the
      `design.md` §5 estimates with the measured figures, and wire `budget=` refusals.
      **DONE, measured on the cluster.** The Jetson never answered (DNS resolves
      10.0.0.x; 0/2 pings, ssh dies at the banner exchange), so the lead ran
      `solve_memory_bench.py` as a bounded Job on `gpu-node-b` (2 cpu / 6 GiB, no GPU,
      code at `b3bbdc1`) instead — and the cluster is where solves actually run, so these
      are the right device's numbers. Full provenance in `memory-bench.md`.
      - *Done:* `estimate_memory()`, `check_budget()` and `solve_memory()`, wired into
        `solve(..., budget=)`. The check runs BEFORE `assemble_stiffness`, not before the
        factorisation — assembly is the first big allocation, so a later check would spend
        the memory it protects. `EstimateError` subclasses `MemoryError` (that is the failure
        it stands in for) and the message names the estimate, the budget, the path and the
        "coarser mesh" lever. `budget=None` reads THIS process's admission ceiling
        (`admission_budget()`, at call time), and `budget=NO_DEVICE` skips the check — the
        same three meanings `fdtd.check_limits` uses, re-exported from `fdtd` rather than
        reinvented, because a module running on the control plane while the solve runs
        elsewhere must be able to say "I am not on the run's device" explicitly.
        `web/td_form.py` already passes `NO_DEVICE` for exactly this.
      - *Measured AMG, power law fits:* `bytes = 12812 * n_free^0.91`, worst point 2.0 %
        off over `n_free` 1,859..27,869 (~5 kB/unknown at the top). Above that range the
        law is scaled by `AMG_EXTRAPOLATION_MARGIN` (1.5) and the estimate reports
        `extrapolated: True`, which the refusal message renders as "extrapolated, with a
        1.5x margin applied".
      - *Measured DIRECT, no law fits:* seven points from 1,859 to 112,847 unknowns
        (10.9 MB → 4,797 MB). Power law 27 % off its own worst point, linear 277 %.
        Bytes/unknown climb 5.86k → 42.5k with a **2.2× jump** between the last two
        points — SuperLU switching ordering strategy, an algorithm change rather than a
        curve.
        So direct interpolates `DIRECT_MEMORY_TABLE` in log-log space and **refuses above
        112,847 unknowns** with an `EstimateError` recommending AMG.
      - *Mutations, three, each caught by a different test:* margin 1.5→1.0 (caught by the
        margin test); direct refusal pushed beyond reach (caught by the refusal test); and
        **log-log → linear interpolation, which SURVIVED the first suite** — the
        midpoint-in-the-gap test passes for a straight line too. A curvature test was added
        that compares the log-log value against the linear one at the geometric mean of each
        gap, and now kills it. Recorded because a surviving mutation is the finding, not a
        footnote.
      - *Product consequence, and it changed the story:* every graded mesh the product
        builds (E1 2.4e5, E2 1.27e6) is above the direct table, so **all of them take AMG**;
        direct is refused for all four §5 meshes. E2 prices at 6.42 GiB (40 % of a 16 GiB
        container) — it fits, but does not fit the 6 GiB Job it was measured in. E3 (the
        uniform mesh today's one-size path would build) is **31.5 GiB and does not fit**,
        which makes the graded sizing field load-bearing rather than an optimisation.
      - *A bug the measurement exposed, now fixed:* `AMG_NODE_CROSSOVER` (5e5) sits **above**
        the direct table's top (112,847), so `auto` in that band chose direct and then
        could not price it — refusing a solve AMG could do, for the product's *normal* mesh
        size. `_direct_is_viable()` now consults both limits (the speed crossover AND the
        knowledge ceiling) so they cannot drift, and `auto` takes AMG in the band while
        `method="direct"` still refuses there. A new test covers the band, proven by
        mutating the fix away. The old test sampled at `crossover + 1`, past both limits,
        which is why it passed while the bug lived.
      - *Known weak point:* the crossover itself is still a speed choice with no measurement
        on either side. What changed is that it can no longer cause a false refusal.
      - *Corrected:* the old §5 claim that "a direct LU at 5e5 nodes is ~5.8 GiB, so memory
        does not set the crossover" rested on the nested-dissection fill formula, which the
        measurements do not support. Removed. The VM four-point run that found no usable
        model is kept in §5 as the reason a wider range was needed.

- [x] 1.8 `stark.py`: the 7-point effective-mass operator on a Cartesian box, LOBPCG, the
      field interpolated from the tet solve. Harmonic-oscillator and Airy checks.
      - *Both analytic cases proven by MEASURED CONVERGENCE ORDER, not tolerance:*
        harmonic 2.00 / 1.99 across 160->320->640 cells, Airy 2.00 / 2.00 across
        240->480->960. A tolerance cannot tell a correct second-order operator from a
        wrong one that happens to be close; the order can. `test_stark.py` is 16 tests.
      - *Sign of the Laplacian was wrong on the first attempt* (diagonal `-2t` instead of
        `+2t`), giving a spectrum from -2t to 0: every energy negative, which a kinetic
        operator alone cannot produce. Reproduced against this commit: `main = -2.0 * t` in
        `laplacian_1d_eV_nm2` (the 1-D operator the analytic tests use, NOT the 3-D
        `build_laplacian_eV_nm2`) fails 7 of 16, all four analytic tests among them.
        `test_laplacian_is_positive_semidefinite` catches it in one line.
        *Corrected 2026-11-04:* an earlier version of this note claimed "the analytic
        tests passed anyway -- their tolerances were loose enough". That is false at
        this commit and the reviewer showed it by running the mutation. What I had
        actually observed was a looser intermediate `harmonic` on a coarse box, not the
        committed tests; I generalised a transient observation into a property of the
        record. The committed tests are tight enough to catch the sign error.
      - *Particle-in-a-box formula:* the correct value is `K(pi/L)^2`, where `K` is already
        `hbar^2/2m`, NOT `pi^2 K / (2 L^2)`. The wrong formula gives exactly half, a ratio
        of 2.0000 that does not move with the grid -- which is how it was distinguished
        from a discretisation error (that would converge away). Measured ratio 0.99998.
      - *Parallel-plate field is NOT hit exactly, and that is correct physics.* On the axis
        at 4 um x 4 um x 0.6 um (the gap is 0.6 um; an earlier note said 0.4 um, which was
        wrong) the error is 14.28% / 9.96% / 8.79% at n_modes 8/16/30, converging toward
        -1/d. The evidence for fringing rather than a solver defect is that the error falls
        monotonically under refinement at fixed geometry; a bad operator would not improve.
        *Corrected 2026-11-04:* an earlier note claimed "a 1.2 um box is WORSE (21.85%)" and
        offered that as the decisive signature. It does not reproduce and is withdrawn, not
        explained.
        *Corrected again 2026-11-04:* the replacement pair (1.2 um 8.98% vs 4 um 10.54%, then
        labelled "a fixed 0.2 um gap") was also wrong and is deleted rather than replaced. The
        reviewer found their own helper holds the top and bottom 0.6 um at fixed potential, so
        the gap is extent - 1.2 um and CHANGES with the box. Measured gaps: 1.2 um box ->
        1.08 um, 4 um box -> 3.88 um. A cross-box comparison at "fixed gap" is comparing two
        different geometries.
        *Corrected a third time, same day:* the note that replaced it stood on a refusal, and
        the refusal was for the wrong box. The helper refuses extent_m=1.2e-7 (0.12 um) with
        n_modes 8/16, and that refusal is gone by 0.2 um (solved, gap 80 nm) and at 1.2 um
        (solved, 112/167 electrode tets). "1.2e-7 m is the 1.2 um box" was a factor-of-ten
        error of the same kind as the pair it replaced, and the 4 um gap is 3.88 um, not 2.8.
        Resolved by dropping the refusal sentence entirely, not by re-quoting a boundary.
        Nothing is now claimed here about box size in either direction: the error falls
        monotonically under refinement at fixed geometry, and that is all.
        The test asserts the convergence direction and a bound, not a single value.
      - *V/m -> eV/nm is `* 1e-9` and nothing else.* A volt across a nanometre is 1 eV/nm
        because the electron charge cancels between the volt and the electron-volt.
        Dividing by `e` as well (the obvious-looking mistake) gives a spectrum in the
        millions of eV. End-to-end measured error 1.3e-4.
      - *The field sign is asserted, not discarded.* A sign flip in `field_on_grid` was
        caught by only ONE test while the end-to-end check took `abs()`; it now asserts
        `E_z < 0` before entering the Airy case, and two tests catch the mutation.
      - *A `Box` takes CELLS per axis (`n`), so it has `n + 1` nodes;* `lowest_states_1d`
        takes NODES. Passing one where the other belongs shifts the walls and changes the
        answer without an error.
- [x] 1.9 First-order Coulomb term, E_X(F), the p/β fit and `scripts/stark_bench.py`. Prove
      its mutations. **Done 2026-11-04, reviewer PASS @`dde355f` then @`8c531ad` and
      @`3bb460d` (the β caveat moved into the cell); merge `388640c` + `1f1ce4d`.
      OPEN EVIDENCE carried under this task: 1.9c's offset retrieval came back empty
      (`qitem-20261105042005`, `0dd7009`), so β is not quotable and the sweep is the
      deliverable. The threshold that matters is measured: the electron needs a z-well
      depth just above 0.6 eV and is loose at every swept depth.**
      - **Ruling 2026-11-04 (`qitem-20261104102757`, "2 + 3"): cited endpoints, an
        ASSUMED interpolation, and a sweep of the well depth. Docstrings first.**
      - Docstrings fixed: `sawtooth_potential` now states plainly that it adds NO well,
        so the old "+ well" case was a free particle in the box. (The physics defect:
        `<z^2>` came back as 95.27 nm^2, the bare-box `L^2(1/12 - 1/(2 pi^2))`, while
        the docstrings called the carrier a quantum dot.)
      - `well_depth_eV` / `well_height_nm` threaded through `_potential_grid`,
        `_ground_state` and `exciton_energy_eV`; `None` keeps today's behaviour.
      - **Confinement is now measured, not asserted.** `test_a_deep_well_actually_confines_the_state`
        pins that a bare box reproduces `L^2(1/12 - 1/(2 pi^2))` (52.2762 measured vs
        52.2764 analytic for L = 40 nm; 4.7049 vs 4.7049 for L = 12 nm) and that a 0.6 eV
        well narrows `<z^2>` by more than 20x. Mutation: dropping the well makes it fail
        with `<z^2>` equal to the bare-box value, which is the exact trap.
      - **Validation on a known answer (finite square well).** The ground state solves
        `u tan u = sqrt(v0 - u^2)`, `E = u^2 K/(m a^2)`; `test_finite_square_well_recovers_the_bound_state`
        pins it. Measured errors at 127/255/511 cells: 1.13e-2, 5.30e-3, 2.55e-3.
      - **Measured convergence order, which is the point of the proof.** O(h^2) on any
        smooth case -- harmonic 2.04 / 2.14 across 40->80->160->320 cells, reproducing the
        existing pin; transverse box 1.91 / 1.98 / 1.99 / 2.00. The finite square well is
        **O(h)**: 1.16 / 1.09 / 1.05 / 1.04. That is correct behaviour, not a defect: a
        node-sampled step lies between grid points, so the effective well width carries an
        O(h) error. Recorded here so a later reader does not "fix" it.
      - *Trap worth keeping:* a barrier mask whose half-width equals the box half-width
        puts the step on the Dirichlet walls, where the potential value is unused. The
        solver then silently returns the INFINITE-well energy: measured 0.0734434 against
        the true 0.0471547, stable at every resolution, so it looks converged. It is not.
        Any well must be strictly narrower than its box.
      - *Instrument lesson:* three separate alarms during this proof ("E is 12x too
        large", "the potential is ignored", "transverse couplings are missing") were all
        wrong, and each came from comparing numbers produced by DIFFERENT boxes -- a 1-D
        formula applied to a 3-D box, an analytic transverse term from a different z
        extent, an elementwise diff on a degenerate pair. Cross-box subtraction is the
        failure mode here; subtract only within one box family.
      - **`scripts/stark_bench.py`, the depth sweep (ruling item 3).** Prints, for each
        well depth, `E_X(0)`, the electron and hole `<z^2>`, `beta`, and the Stark shift
        at each field. Defaults: depths 0/0.1/0.2/0.3/0.5/0.8 eV, fields 0/0.1/0.2/0.4
        eV/nm, well height 4 nm, box 12x12x16 nm at 6x6x40 cells. Measured:
        `beta` = -10.008, -8.601, -6.989, -5.306, -1.985, +0.882 -- it **changes sign**.
        `<z^2>` for the hole falls 8.364 (bare box, exactly the analytic value) -> 1.377
        -> 1.086 -> 0.987 -> 0.904 -> 0.853 nm^2; the electron 8.364 -> 4.936 -> 3.244
        -> 2.439 -> 1.759 -> 1.391 nm^2.
      - **CONFINEMENT CRITERION, corrected 2026-11-04 (reviewer finding 1).** The first
        version compared `<z^2>` to half the bare-box value, which reads BACKWARDS: at
        depth 0 a free particle sits exactly at the box ceiling, and that rule called it
        confined. Confinement is a LENGTH, so the criterion is now the tight-well ceiling
        `h^2/12` (1.333 nm^2 for the 4 nm well), which depends on the well, not the box.
        Under the corrected rule the HOLE is unconfined at 0 and 0.1 eV only, but the
        ELECTRON is unconfined at EVERY swept depth: rows 0.2-0.8 eV are
        electron-limited, so the exciton extent is set by the box and they are not a
        dot's either. This STRENGTHENS the negative result below.
      - **NON-PERTURBATIVE FIELDS, added 2026-11-04 (reviewer finding 5).** The default
        sweep's largest shift (4.89 eV) exceeds the smallest `E_X(0)` (0.081 eV) by 60x.
        Both carriers are driven up the ramp past the well, which is outside the regime
        the quadratic p/beta fit assumes; the bench now prints a warning saying the
        large-field rows are a model probe. Fields are also reported in kV/cm alongside
        eV/nm (1 eV/nm = 1e4 kV/cm), so `EV_PER_NM_TO_KV_PER_CM` is no longer an unused
        export.
      - **What the sweep concludes, stated plainly in the bench output:** the p/beta fit
        is well-defined at every depth, but `beta` is a property of FOUR assumed numbers,
        not one: the well DEPTH, the well HEIGHT (4 nm assumed; the cited TEM range is
        3-7 nm), the alloy masses (linear interpolation, ASSUMED) and `eps_s` (the InP
        host's, ASSUMED for an InAsP dot). A single beta needs four citations. This is a
        NEGATIVE result about the deliverable's headline number, and it is the honest one.
      - The bench refuses `--height >= --z-extent` with an error naming the
        infinite-well trap, and refuses a field sweep with no zero point.
      - `tests/test_stark_bench.py` (11 tests) pins the sweep's discrimination, the
        bare-box calibration, the refusals, the well-ceiling criterion, the
        non-perturbative warning, and the beta-cell marker. Mutations caught: dropping
        the well from `_potential_grid` fails 3; reverting the criterion to
        `0.5 * bare` fails the ceiling test; never flagging an electron-limited row
        fails the bare-number test; flagging every row fails the held-electron test.
      - **THE BETA COLUMN CARRIES ITS OWN CAVEAT, 2026-11-05 (reviewer CHANGES-NEEDED
        @8c531ad, on the lead's stricter bar).** The emitted table printed `beta` as a
        bare number on every row, including the four where `<z2>e` was above the
        tight-well ceiling the same script computes. The prose saying those rows are
        "not a dot's either" sat sixteen lines BELOW the table -- and the table is what
        gets screenshotted and the number lifted from. Electron-limited rows now print
        `blank*` with a one-line key directly under the table naming the depths. In the
        default sweep every row is electron-limited, so the honest output is that beta
        is blank on all six; the test pins depth 0.2 specifically so a later edit cannot
        restore a bare number there.
      - **1.9c, 2026-11-05: THE OFFSET CITATION CAME BACK EMPTY. Recorded, not
        filled in.** A bounded one-pass retrieval (as the lead specified) for the
        standard III-V compilation -- Vurgaftman, Meyer & Ram-Mohan, J. Appl. Phys.
        89, 5815 (2001) -- returned nothing usable: the AIP landing page answers
        HTTP 403 to automated retrieval, and four searches (the paper by title and
        author; the InP/InAs gap table; the InAsP bowing parameter; a narrowed
        value-based query) returned no hits. **Nothing was written from memory.**
        A control query ("indium phosphide band gap") did return a result, quoting
        ~1.34 eV with no source -- which is exactly the kind of unsourced number
        this change refuses to use, so it was discarded. What is needed to close
        this: table-level access to that paper (or an equivalent compilation), and
        a citation of section and table for each of the InP gap, the InAs gap, the
        InP/InAs offset split, and the InAsP bowing parameter. The sweep remains
        the answer until then, as the lead's step 3 provides.
      - **1.9c: HOW FAR SHORT THE ELECTRON FALLS, measured (the part that does not
        need the missing citations).** The lead's rough figure checks: the 4 nm
        infinite-well electron level at m_e = 0.08 is **0.2938 eV**. Sweeping a
        z-only square well, the electron first satisfies the h^2/12 = 1.333 nm^2
        criterion at a depth just above **0.6 eV** (0.30 and 0.50 eV: loose, 2.139
        and 1.464 nm^2; 0.60 and 0.80 eV: confined, 1.316 and 1.137 nm^2). So a
        realistic conduction offset sits well short of what this model needs, and
        the reviewer's "unbound at every swept depth" is not merely a range
        artifact -- sweeping deeper would not rescue it until ~0.6 eV. Pinned by
        `test_the_electron_needs_an_unrealistically_deep_well_to_bind`, which
        fails if the threshold is shrunk to make the dot bind.
      - **1.9c: NAMING THE LIKELY CAUSE -- measured zero-points, hypothesis
        flagged as hypothesis.** The lead asked that if the electron does not
        bind, the plausible cause be named: the 1-D z model leaves out the 18 nm
        lateral confinement. Measuring the two zero-points at m_e = 0.08 gives
        **0.2938 eV (z, 4 nm) against 0.0145 eV (lateral, 18 nm)** -- the lateral
        term is twenty times smaller. That is a measurement, and it does NOT by
        itself prove the 1-D model overstates the needed depth. **The mechanism
        is a hypothesis, not established here:** it would be that the 1-D model
        assigns the electron's entire zero-point to the z axis and ignores the
        lateral degree of freedom, so z well depth is being asked to supply an
        energy that a real 3-D state partly supplies laterally. What would test
        it: a 3-D solve on this box including the lateral level in the energy
        reference, then comparing the z-depth at which the electron binds.
        Building that model is deliberately OUT OF SCOPE for this row (the lead's
        instruction), and neither the offset nor the mass was tuned to make the
        dot bind.
      - **SILENT LOBPCG FAILURE, fixed 2026-11-04 (reviewer finding 3, made REQUIRED by
        the lead).** `scipy`'s `lobpcg` reports a missed tolerance only through a
        `UserWarning` and then returns whatever it has, so `lowest_states` was handing
        back unconverged eigenvalues with nothing to distinguish them. It happened on
        this change's own sweep (12 of 159 electron solves). `lowest_states` now measures
        the true residual `||Hv - Ev||/(|E|||v||)` per pair and raises `StarkError`
        unless it is below `residual_tol` (default 1e-6), or returns a `converged` array
        with `return_converged=True`. `residual_tol` is deliberately NOT `tol`: `tol` is
        LOBPCG's internal estimate, while the measured residual floors near 5e-10 and
        does not improve with more iterations, so binding the check to `tol` would
        reject correct solves. Tests force failure with `maxiter=3` (raises) and check a
        good solve still passes (does not fire); mutations both ways are caught.
      - **Test counts, corrected 2026-11-04 (reviewer finding 2).** The round's message
        reported "113 passed" as if it were this change's; that was the WHOLE electrical
        suite. This change touches these files: `test_stark.py` 21, `test_stark_bench.py`
        9, `test_exciton.py` 22, `test_paper1_wire_electrode.py` 15 = 67 passing. Both
        numbers are counted from the run output, not transcribed.
      - **The E_C sign, documented 2026-11-04 (reviewer finding 4).** `e_c` is negative
        and correct. `e_e` and `e_h` are energies from a band edge at zero, and the field
        pulls both carriers up the ramp, so each can sit below zero; `e_x` is a SPACING
        between levels, not an absolute energy, and `e_c` is the attractive correction to
        it. Comment added at the call site because the next reader would otherwise read a
        negative attraction as a sign bug.
      - **Finite-square-well convergence order, stated precisely 2026-11-04.** Measured
        1.09 / 1.05 / 1.04 -- FIRST order, and that is correct, not a defect: the
        potential step is sampled at nodes, so the well width the discrete problem solves
        is uncertain by up to one cell and `dE/da` is nonzero. Smooth (harmonic 2.04 /
        2.14) and hard-wall (transverse 1.91-2.00) cases pin the difference. The old
        assertion `min(orders) > 0.9` would have passed at 0.91; it now asserts
        `1.0 < min < max < 1.5`, which pins the order the test documents.
- [x] 1.9a Lateral confinement of the dot (follow-on to 1.9; reviewer: "the electron is not
      held at any swept depth -- is the missing lateral size the cause?"). Spec: `stark-shift`,
      "The dot SHALL have a lateral extent, proven on exact answers".
      **Done, merge `b27542f`.**
      - **Answer: no. Lateral size is not the cause, and it slightly LOOSENS the electron along
        z.** The 1.9 well already had lateral walls: the hard 12 nm box, tighter than the 18 nm
        dot. A finite lateral barrier lets part of the state sit beside the dot, where there is
        no z-well, so the effective z-depth falls. Measured at 0.8 eV, same cell mask and grid,
        32 nm box: `<z^2>e` 1.2460 filling the box -> 1.2507 with the 15.95 nm dot
        (`test_lateral_confinement_does_not_tighten_the_electron_along_z`).
      - **What did move the 1.9 verdict is the step's sampling, not the physics.** The 1.9
        `node` mask counts both face nodes as inside, so the 4 nm well is 4.4 nm at h_z = 0.4.
        Exact 1-D answer (`stark.finite_well_in_box`, 4 nm, 0.8 eV, m_e 0.0686, 16 nm box):
        `<z^2>` = 1.2574 nm^2, BELOW the 1.333 ceiling. The node mask reads 1.391 / 1.322 /
        1.289 / 1.273 at n_z 40/80/160/320: first order, converging to the exact value from
        above, and already under the ceiling at n_z = 80. So 1.9's "electron not held at 0.8
        eV" was a grid artefact of the mask; the exact 1-D crossing depth is 0.714 eV. The
        `node` mask stays the default, so every 1.9 number is unchanged (pinned
        bit-for-bit by `test_node_mask_without_lateral_is_exactly_the_1_9_potential`).
      - **Model.** A square box dot, `exciton.dot_fill_fraction`, host barrier around it at the
        same depth (in a nanowire InP is above, below and around the dot). A box, not a
        cylinder: `stark.py` is a uniform Cartesian 7-point grid (design §1 fixes L3 on it), so
        a box's faces lie on grid planes and a cylinder's would be a staircase. Bench default
        side: the equal-AREA square of `DOT_DIAMETER_NM` (D sqrt(pi)/2 = 15.952 nm), the same
        equal-area rule design §1 uses for hexagon -> cylinder. Masses, eps_s and height are
        the 1.9 inputs, unchanged; nothing was tuned.
      - **The `cell` mask** weights each node by the fraction of its dual cell inside the dot,
        so the well width is exact on any grid. Proven by measured order, faces on nodes,
        8 nm cube at 8/16/32 cells (`tests/test_lateral_dot.py`): hard-wall limit (V0 = 1e6 eV)
        1.981 / 1.994; separable finite box well vs three exact 1-D roots 1.857 / 1.962;
        lateral-fill limit (the 1.9 model) vs exact 1-D + hard box 1.847 / 1.960. The
        non-separable dot has no closed form: it self-converges at 1.95 on 16/32/64 (1.82 on
        8/16/32, where h = 1 nm is pre-asymptotic) and is bracketed exactly,
        E_sep(V0/3) < E_dot < E_sep(V0): 0.25376 < 0.29770 (Richardson) < 0.29914 eV.
        Faces OFF nodes converge but not at a clean order (the sub-cell offset changes with h);
        measured in a scratch run, not pinned.
      - *Bound I set before measuring, corrected:* the order tests first asserted
        `min > 1.85`, a number I had not measured; the lateral-fill limit measured 1.847 and
        failed. The bound is now `1.8 < min, max < 2.2`, the bar 1.8's harmonic/Airy tests
        already use. Recorded so it does not read as a bound tuned to pass.
      - **The sweep, rerun with the lateral dot.**
        `python -I scripts/stark_bench.py --lateral --transverse 32 --n-xy 16` (75 s, peak RSS
        603 MiB under `ulimit -v 4194304`). Electron, zero field, depths 0.1/0.2/0.3/0.5/0.8 eV:
        E_e 0.0875 / 0.1225 / 0.1462 / 0.1774 / 0.2058 eV, all below V0, so the electron is in
        a BOUND state of the dot at every depth; P_in 0.566 / 0.718 / 0.799 / 0.878 / 0.926;
        `<z^2>e` 5.313 / 3.368 / 2.426 / 1.653 / 1.251. On the 1.9 length criterion the
        electron is held at 0.8 eV only; the extra depths (`--depths 0.6 0.7 0.75`) put the
        crossing between 0.70 (1.344, not held) and 0.75 (1.294, held). Laterally
        (`<x^2>e <= s^2/12` = 21.2) it is held at every depth. Grid check at n_z = 80: 0.7 ->
        1.351, 0.8 -> 1.259, same verdicts. Side check with the circumscribing 18 nm square
        (`--lateral 18 --transverse 34 --n-xy 17`): 0.7 -> 1.342 not held, 0.75 -> 1.292 held.
        Without the lateral dot, cell mask (`--mask cell`): 0.8 -> 1.246 held, 0.5 -> 1.636 not.
      - **beta.** With the lateral dot the 0.8 eV row is no longer electron-limited and prints
        beta = 0.816, but that fit spans fields up to 0.4 eV/nm, which the bench already flags
        as non-perturbative (shift 4.88 eV against E_X(0) = 0.0227 eV). It is not a quotable
        beta, and the four-assumptions caveat from 1.9 stands unchanged.
      - The bench's binding table reports three tests side by side and does not merge them:
        below the continuum edge (V0 with a lateral dot; without one, V0 + the box column's
        lateral energy, 0.0761 eV for the 12 nm box, because there the walls are part of the
        model), P_in, and the length criteria. The verdict lines still use the 1.9 criterion.
      - `stark.finite_well_in_box` first scanned uniformly in E and returned an EXCITED state for
        a thin well (several roots in one interval), and its tan/cot form lost the 1e7 eV root
        beside the pole. Now pole-free and scanned in k at pi/(4L); both cases are tests.
      - `coulomb._screened_pair_energy` block 4096 -> 1024: memory only (the 32 nm box has ~12k
        nodes, a 4096-row block is a 1.2 GB displacement array). Same sum.
      - Mutations (each reverted): dropping the lateral faces from `dot_fill_fraction` fails 2
        (hard-wall limit, lateral-vs-z; the bracket does NOT catch it, 0.27992 eV lies inside,
        and its docstring says so); node sampling inside the cell mask fails 7; the 1.8
        half-factor in `hard_box_ground_eV` fails 3; coth -> tanh in `finite_well_in_box` fails
        3; the potential ignoring `well_lateral_nm` fails 2.
      - Tests: `test_lateral_dot.py` 11, `test_stark_bench.py` 11 -> 15; with `test_stark.py`
        21 and `test_exciton.py` 22, 69 passing.
      - *Not proven:* the BenDaniel-Duke mass step (the dot mass is still used in the barrier,
        as in 1.9); a cylinder (not built, by the choice above); the openspec CLI is not
        installed here, so the delta is not machine-validated.
- [x] 1.10a Per-region outlines in layered meshing (a pad wider than the wire).
      2026-11-05. `per_region_stack_plc` + `tetrahedralize_per_region`, and
      `tetrahedralize_layers`' single-outline path is untouched (its 21 tests still pass
      unchanged).
      - The blocker was structural, not numerical: every layer in `layer_stack_plc`
        shares one `xy` ring, so a pad wider than its wire could not be represented at
        all -- the only options were a wire as wide as the pad, or no pad.
      - Interfaces now come in two shapes: identical rings (a separating facet, which
        must be its OWN duplicated sheet) and a narrower region resting inside a wider
        one (an annulus plus the narrow region's own bottom cap, also its own sheet).
      - **Measured, pad r=120 over wire r=50, edge 40 nm, n_across=2:** 1970 tets,
        516 points, regions {0,1,2} all present, `crossing` 0 on both planes,
        `mislabelled` 0. Region extent `rmax` 120 / 120 / 50: the pad really is wider.
      - What each defect looked like when crossed, so the next reader does not have to
        rediscover it:
        - facet dropped entirely -> TetGen ignores the seeds: 606 tets ALL region 0,
          256 crossing (silently one region -- the dangerous one).
        - facet sharing the walls' ring -> 16 edges used three times (non-manifold).
        - duplicated facet welded to the walls -> same, 16 rim edges used once.
        - duplicated facet doubled on one hub -> 16 edges used FOUR times (the two fans
          share their spokes).
        - free-standing duplicated sheet -> the answer: an open surface with a free
          rim, which is what a TetGen facet actually is. 0 crossing, 0 mislabelled.
      - Tests: `test_layered_mesh.py` -> 25. Three mutations all caught:
        (a) give every layer the widest ring -> the width test AND the containment test
        fail; (b) delete the pairwise containment check -> the refusal test and
        `test_outlines_must_narrow_monotonically_upward` fail.
      - *Correction (2026-11-05, reviewer-caught):* two record defects fixed.
        (i) The "widest ring" guard compared a ring against itself
        (`_ring_contains(rings[i], r)` with `r is rings[i]`), so it could never fire;
        deleted rather than repaired, since the pairwise check is the one statement
        of the invariant. (ii) The count was quoted as "1548 tets, 393 points" -- an
        earlier construction's number, never re-measured. The test's own call gives
        **1970 tets / 516 points**. This is the third prose count this change got
        wrong by quoting instead of re-running; counts here are now measured at the
        call the test makes.
      - *Not proven:* the pad/wire junction is not yet driven from the paper-1 fixture;
        1.10a supplies the mesher, not the stack. The 8-gon rings resample to a common
        `n_ring`, so a call with mixed resolutions is rounded up to the finest.
        The outlines must also narrow monotonically UPWARD (a pad on top, or a
        wide-narrow-wide sandwich, is refused) -- which suits the paper-1 stack, where
        the pad is at the bottom.
- [x] 1.10c Wide-narrow-wide meshing from the paper-1 fixture, and the pad field.
      2026-11-06.
      - The mesher now accepts a wide-narrow-wide sandwich. The invariant is no longer
        "outlines narrow monotonically upward" but "adjacent outlines must NEST" (one
        contains the other), which is what a usable device needs. Rings of equal radius
        nest, so 40/40/120 is legal; a genuinely crossing pair is still refused.
      - `mesh_fixture_padded` drives the paper's real footprint from the fixture:
        mirror r=299.4 nm, oxide and wire r=239.4 nm, top r=299.4 nm. The 60 nm pad
        overhang is real in the mesh, not just in the call.
      - **The field measurement is a NEGATIVE, and it is a defect, not physics.**
        The padded and flat fixtures give the same field to ~1e-7, and that looked
        like "the pad does not perturb the field". It is not: the solved potential
        varies by **8e-16 across x within a z-level** -- the solve is exactly 1-D.
        Cause, measured: the free (solved) nodes stop at **r = 239.4 nm**, so there
        are **zero free nodes in the pad overhang**. The wide annulus sits over empty
        space, because the fixture meshes no ambient medium outside the wire. The only
        Dirichlet contact the wire sees is its own rim, and the stack is therefore the
        1-D series problem the flat fixture already solves exactly.
      - So the "pad changes nothing" number must NOT be reported as a result. It is
        pinned by `test_the_padded_solve_is_still_one_dimensional`, which fails the
        moment the ambient is meshed (mutation: widen the oxide to the pad outline ->
        free nodes reach the overhang -> the pin fails, as it should).
      - *Not done, and why:* measuring a real fringing field needs the surrounding
        medium as a meshed region (with its own permittivity). That is a device-model
        decision -- what is the ambient, and what is its eps -- not an implementation
        detail, so it is escalated rather than guessed.
      - Two instrument errors made on the way, recorded so they are not repeated:
        (i) probes at x=230 nm were reported "outside the mesh" -- correct, because the
        hexagon's INRADIUS is 207.3 nm while its circumradius is 239.4; the probe was
        outside the wire. (ii) grading `phi` spread by `np.round(z, 9)` merged adjacent
        z-levels and manufactured an 8e-4 lateral spread out of nothing; exact-z
        grouping gives 8e-16.
      - `straddle_counts` fixed to use the MESH's own planes (`planes_m`) instead of
        always reading the flat stack's, and to fall back when a fixture carries none.
      - Review round (2026-11-06). First submission quoted the pad as **839.4 nm** in
        four places; it is **299.4** = circumradius 239.4 + `ELECTRODE_PAD_NM` 60, and
        839.4 came from an unrelated 600 nm perturbation run carried across by hand.
        Fifth carried-forward number in this change after 83/81, 113/67, 1548/1970 and
        109. Corrected and pinned by `test_the_pad_radius_is_the_wire_plus_the_margin`
        against LITERAL values. The first version of that pin derived the expectation
        from the same two constants the mesh uses, so mutating `ELECTRODE_PAD_NM` to 660
        moved both sides and the test still PASSED -- circular, the same defect as 1.6b's
        oxide test, reproduced while writing a test meant to stop numbers drifting. With
        literals the same mutation FAILS it.
      - Second review round: `mesh_fixture_padded`'s docstring still promised "a 3-D
        fringing field, not field_per_volt_1d's series value" -- the opposite of what the
        pin above measures, and the more quotable of the two because it is a docstring in
        `scripts/`. Replaced with the measured statement (free nodes stop at r=239.4,
        ~1e-16 lateral spread, reproduces `field_per_volt_1d`) plus a pointer to the test
        that fails once the ambient is meshed. The other 3-D/1-D mentions in the file
        describe the FLAT fixture and are accurate.
      - **PASS @37cc34f**, "docstring claims reproduce (239.4 nm, ~1e-16)". Still
        unruled and still the lead's: the ambient medium.

## 2. Phase 2: drift-diffusion (general parts, any contacts, both forms)
- [ ] 2.1 Install DEVSIM in the solver image; a smoke that imports it and records its
      version. Confirm the mesh route (task 0.2).
      **In progress 2026-11-09.** `devsim==2.11.2` added to
      `dockerfiles/maxwell_solver/requirements.txt`. The wheel is `cp39-abi3
      manylinux_2_28`, so the `python:3.12-slim` base (stable ABI, glibc far past
      2.28) needs no *Python* change for it.

      **Correction, measured in the built image: it does need system packages.**
      My first version of this entry said "no Python or system package change".
      That was inferred from wheel metadata and it is wrong. `import devsim` in
      the built image dies with:

          Loading "libblas.so": MISSING DLL  (openblas, lapack, blas)
          RuntimeError: Issues initializing DEVSIM

      DEVSIM dlopen()s a BLAS at import time. Two things that look like they
      should satisfy it do **not**, both measured:

      - **The bundled OpenBLAS from numpy/scipy.** The wheels carry their own
        (`libscipy_openblas64_-*.so`, `libscipy_openblas-*.so`). Loading either,
        or both, gives `MISSING SYMBOLS`: they are privately mangled (the numpy
        one is ILP64) and do not export the reference `libblas`/`liblapack`
        symbol set DEVSIM looks up.
      - **Bare `libblas.so`.** That name is the `-dev` symlink, absent from the
        runtime image; the `libblas3`/`liblapack3` packages install
        `libblas.so.3`/`liblapack.so.3`. Naming the bare form in
        `DEVSIM_MATH_LIBS` fails with `MISSING DLL` even when the package is
        installed.

      Fix, both in the Dockerfile: apt-install `libblas3` and `liblapack3`, and
      set `DEVSIM_MATH_LIBS="libblas.so.3:liblapack.so.3"` — the same value task
      0.2 reached on the host, which I should have carried across instead of
      re-deriving.

      **The mesh route, measured.** 0.2 had established DEVSIM's reader rules in
      prose; nothing in the repo turned our mesh into a file it could read, so
      that step did not exist yet. `dockerfiles/maxwell_solver/mse_devsim_mesh.py`
      writes a Gmsh 2.2 4-node-tet file from what `mse_meshing` returns
      (`points_m`, `tets`, `region_of_tet`) plus the part names, in metres.

      The load-bearing detail is 0.2's silent-failure rule: DEVSIM takes
      `ilist[3]` (with `ntags=2`) as the physical number, so an inserted element
      index regroups every element and region-by-name lookup fails with NO
      error. `test_the_physical_number_is_where_the_reader_looks` pins the whole
      field layout — id, type, ntags, physical, geometric, 4 nodes, 9 fields —
      rather than just the tag, because the tag being right is not enough if the
      position moved.

      **One mistake recorded rather than tidied away:** that test first asserted
      `len(fields) == 7`. The writer was correct; my arithmetic was wrong
      (id+type+ntags+2 tags+4 nodes = 9). The assertions that matter —
      type 4, ntags 2, physical 1 — passed throughout, so the failure was in the
      count only, and it is fixed rather than relaxed.

      **Second writer defect, found only by running DEVSIM in the image.** The
      first build's smoke got as far as `create_gmsh_mesh` and died with
      `line: 6: syntax error`. The `$PhysicalNames` block had an extra bare `2`
      line between the count and the names — I had put the element dimension on
      its own line instead of on each name line. The format is a count followed
      by one `tag dim "name"` line per name, nothing between.

      Every host test passed with that file. They asked whether
      `"$PhysicalNames"` appeared in the text, and it did; the two in-image
      tests that would have parsed the block skip on the host because DEVSIM
      is not installed there. So the block's *shape* was asserted by nothing
      that ran. `test_the_physical_names_block_has_exactly_count_plus_names`
      now parses it a line at a time, and reintroducing the stray `2` fails it
      (mutation-checked). The general lesson matches the series: a host test
      that greps for a marker is not a test of a file format.

      **Third writer defect, same shape, one line lower.** With the block
      fixed, DEVSIM moved to `line: 10: syntax error` in `$Nodes`. The node
      coordinates were written with `!r`, which reprs a numpy scalar as
      `np.float64(0.0)`. I had reached for `!r` as the "exact" choice; it
      produced a file no parser accepts. Now `float(x):.17g`, which round-trips
      a float64 exactly, so exactness is kept without the repr.

      **Fourth writer defect, and the one that cost the most: the two fields in
      `$PhysicalNames` were TRANSPOSED.** The line `3 1 "lower"` is DIMENSION
      then TAG; the writer emitted `1 3 "lower"`. This is the worst kind of bug
      in this series because **nothing rejects it**. The file parses, the mesh
      loads, `add_gmsh_region` returns without error, the device builds with
      all 91 coordinates — and every region holds ZERO nodes, because the
      reader took dimension 1 (a line) and no tetrahedra match a line group.
      DEVSIM even prints `Physical group name 1 has 144 Tetrahedra`: it read
      the NAME as `1`, which was the visible clue and which I walked past
      repeatedly while looking for coordinate and scale problems.

      The test did not catch it because `test_the_physical_names_block_has_
      exactly_count_plus_names` asserted `(tag, dim) == (str(i), "3")` — the
      same transposed order. **The test locked the defect in rather than
      catching it**, which is the circular-test failure mode from 1.10c and the
      dead-guard failure from 1.10d, now applied to a format assertion. Fixed
      to `(dim, tag) == ("3", str(i))`, mutation-checked.

      What finally found it was diffing a hand-written known-good file against
      the writer's output with `cat -A`. Ten probes before that tested scale,
      quoting, reserved names, tag numbers and topology — every one of which
      was fine — because I was bisecting by hypothesis instead of diffing
      against the working example I already had.

      **Verified in the image, end to end.** `devsim_smoke.py` on the rebuilt
      image prints `physical_numbers={'lower': 1, 'upper': 2}`, `Physical group
      name lower has 144 Tetrahedra`, `Region lower has 52 nodes`,
      `devsim_nodes_lower=52`, `devsim_nodes_upper=52`, `ROUTE=ok`, exit 0. Two
      node-counting attempts before that failed on DEVSIM API misuse, not on
      the mesh: `node_model=` is not a `set_parameter` option, and
      `devsim.node_model()` is for solution variables and requires an
      `equation`. `get_element_node_list` answers the question with no model,
      which is what the smoke uses now.

      **And a process error worth recording beside them.** I chained the
      rebuild and the smoke with `&&` and read the exit code as the verdict.
      The build had in fact FAILED (wrong build context: the Dockerfile is in
      `dockerfiles/maxwell_solver/` but its `COPY` paths are repo-relative, so
      it must be built with `-f ... .`), and because `docker build` was piped
      into `tail`, the pipeline's status came from `tail`, not from the build.
      The smoke then ran against the STALE image and reproduced the old
      `line: 10` error, which I nearly reported as "the fix did not work".
      Correct form: `-f dockerfiles/maxwell_solver/Dockerfile .` with the repo
      root as context, and never take a success signal from a pipeline's tail. `test_every_number_in_the_file_parses_as_a_float`
      now parses the Nodes and Elements blocks numerically; reintroducing `!r`
      fails it (mutation-checked, file restored byte-identical).
- [ ] 2.2 The materials library with cited sources per parameter, and the per-part override
      path. Its test checks a sampled subset against the cited sources and refuses an
      uncited entry.

      **PARTIALLY DONE 2026-11-09; the data is blocked, the machinery is not.**
      `dockerfiles/maxwell_solver/mse_materials.py` + `tests/test_materials_library.py`.
      Done: all ten spec'd materials present with the spec'd parameter schema; per-part
      override; the manifest source map (`resolve` returns `"library: <name>"` /
      `"override"` per parameter); unknown material refused with `ValueError` naming it and
      listing the library; a test checks a sampled subset against its cited source
      (Si 11.68, GaAs 12.4, InP 12.5, SiO₂ 3.9, air 1.0).

      **Not done, and the suite says so rather than hiding it.** The central requirement —
      "each SHALL be read from its cited source before it is written into the library ... A
      number quoted from memory SHALL NOT ship" — is met for **5 of 34** parameters. The
      authoritative compilation, Ioffe/NSM, is **unreachable from this seat**: WebFetch
      returns "self signed certificate in certificate chain" on every path tried; `curl`
      returns nothing; WebSearch returns no results. What did come back (Wikipedia's
      "Relative permittivities ... at room temperature under 1 kHz") has ε_s only, and is
      cited as the secondary source it is, with the primary each row points at recorded.
      No InP, SiC, Al₂O₃, HfO₂, Au or Ag permittivity; no n_i, mobilities, lifetimes or
      radiative coefficient for anything.

      Every unretrieved parameter is carried as NaN with `verified=False`, and
      `test_every_shipped_parameter_is_cited` runs `require_cited()` against the shipped
      library under `xfail(strict=True)` — it fails today naming all 29 missing parameters,
      and flips to a hard failure if the gap is ever closed without removing the mark.
      `test_the_gap_is_what_the_xfail_claims_it_is` pins exactly which materials have a gap,
      so neither an invented value nor a silently dropped citation can pass.

      I did not fill the remaining 29 from memory, and this needs a decision the lead
      holds: either retrieval is unblocked (a certificate/host path that reaches Ioffe or
      an equivalent handbook) or 2.2 ships partial and the §2.3+ solves state which
      parameters they are still waiting on.

      **RESOLVED 2026-11-09: the lead chose decision 2 and Ioffe is reachable with
      `curl -k`.** Superseding the BLOCKED paragraph above, which is kept as the record of
      the state before that. `curl -sS -k` returns 200; the site's certificate chain is
      the problem, not the network. Filled **18 of the 29** gaps from
      `www.ioffe.ru/SVA/NSM/Semicond/{Si,GaAs,InP,SiC}/{basic,bandstr,electric,optic}.html`,
      each citing the page URL, the row, and the retrieval date. **23 of 34 parameters are
      now cited; 11 remain.**

      Every Ioffe-sourced value's note records **"fetched with curl -k: TLS certificate
      NOT verified"**, so a reader knows the provenance; no credentials, no cookies, no
      fetched content piped into a shell, and the HTML was kept out of the repo.

      Four judged decisions, recorded because each could reasonably have gone the other way:
      - **Mobility ceilings stay ceilings.** Ioffe's basic rows read `<=1400`, `<=450`,
        `<=5400`, `<=200`, `<=400`, `<=8500` — bounds, not typical values. Where the same
        page also gives a weakly-doped drift formula (GaAs `8000(300/T)^(2/3)`, InP
        `(4.2-5.4)e3(300/T)`) the 300 K value of the FORMULA is used for GaAs (a measured
        drift mobility, not a ceiling) and the ceiling/upper edge for the rest. Each note
        says which. InP's range is not collapsed to a point.
      - **Lifetimes are Ioffe's "~" values.** GaAs tau_h ~3e-6, tau_e ~5e-9; InP tau_h
        ~3e-6, tau_e ~2e-9. The page's own approximate qualifier is kept in the note.
      - **SiC is a polytype family.** Ioffe gives 3C 9.72, 6H ordinary 9.66 / extraordinary
        10.03, and says the 6H value "is usually used" for 4H. The library records 6H
        ordinary 9.66 and notes that a 4H solve sits on that approximation and a 3C or
        anisotropic solve is NOT covered. This is the one place the library answers "SiC"
        with a polytype choice the spec did not make.
      - **A disagreement is recorded, not averaged.** Wikipedia's table says Si eps_s =
        11.68; Ioffe/NSM `Si/basic.html` says 11.7. The library keeps 11.68 (the source
        already cited for it) and the Si entries' notes carry both.

      Still missing (11), left NaN and refused, for the lead's second-source pass:
      **Al2O3, HfO2, Au, Ag** permittivities (Ioffe/NSM is semiconductors only;
      `SVA/NSM/Dielectrics/` returns 404) and **Si tau_e/tau_h** (Ioffe has them only as
      figures vs doping, no tabulated number) and **SiC n_i, mu_e, mu_h, tau_e, tau_h**
      (n_i is a figure vs temperature; the fetched `SiC/electric.html` has no tabulated
      mobility or lifetime).

      `require_cited` stays `xfail(strict=True)`. `test_the_gap_is_what_the_xfail_claims_it_is`
      now pins the IDENTITY of the 11 remaining (material and parameter), compared against
      `gaps()`, so filling one requires editing the expectation and inventing one fails it.
      **Mutation-checked:** adding an invented `Si tau_h` (unretrieved value marked verified)
      fails both that test and the report-count test; reverting returns 14 passed, 1 xfailed.
      The first mutation attempt silently did not apply — the anchor string was absent — so
      "nothing failed" briefly meant "nothing changed"; redone and `diff`-confirmed applied.

   **Review of @7170536 (2026-11-09): PASS with four corrections. Applied, not overwritten:**

   - **(a) The sampled subset was only `eps_s` (substantive).** The reviewer multiplied GaAs
     n_i by 1000 with its citation intact and the suite stayed green: the test that checks a
     sampled subset against its source (spec scenario) checked one kind of number out of six.
     Added `test_the_filled_values_across_kinds_are_the_ones_read_from_the_source`, which types
     15 expected values a second time with their Ioffe page and row beside them, spanning
     `n_i_300K`, `mu_e`, `mu_h`, `tau_e`, `tau_h` and `B_rad` across Si, GaAs and InP, and
     asserts the cited page name appears in each basis. **Mutation-checked:** GaAs n_i
     2.1e6 -> 2.1e9 fails it, naming the value, the expectation and the page; reverted.
   - **(b) The xfail reason was stale.** It still said Ioffe was unreachable and the kinds
     were never read, which stopped being true at @7170536. Rewritten to name the 11 missing
     parameters and say why each has no row.
   - **(c) The module docstring said an unretrieved entry "FAILS THE SUITE".** Unseated: it is
     an `xfail(strict=True)`, so the test fails and is EXPECTED to fail; the suite is not red.
     The docstring now describes it accurately, including that closing the gap without
     removing the mark turns the suite red.
   - **(d) Si eps_s used the secondary Wikipedia figure.** It now carries **11.7** from the
     primary Ioffe `Si/basic.html` 'Dielectric constant' row, with 11.68 mentioned in the note
     as the secondary disagreement. **Swept:** GaAs, SiO2 and air remain `_eps_s` (Wikipedia);
     each is the only reachable source for that material and each note says it is secondary.
     No other `verified=True` rests on a secondary source.
   - **Process error of mine, recorded:** after the mutation I restored from a backup with
     `cp` and pytest then still reported the mutation failing. It was stale cached bytecode; the
     file was already correct. I confirmed the file's bytes before concluding, but the useful
     lesson is to clear caches (or run with `PYTHONDONTWRITEBYTECODE=1`) before reading a
     post-mutation result.
- [ ] 2.3 Axisymmetric (r, z) form with the 2πr weight; the abrupt-junction V_bi, depletion
      width and cylinder-area checks.
- [ ] 2.4 Ideal-diode slope, current conservation, the Debye-length refusal, and the
      multi-terminal check (three doped regions, four ohmic contacts).
- [ ] 2.5 The size check: price the 3-D run from the mesh it would build — node and edge
      counts of the actual geometry through the allocator's array sizes — and refuse
      terminally against the Job's 16 GiB, naming the estimate, the limit and the
      axisymmetric form when the device is round. Two-geometry test proves the estimate is
      the device's own. A native solve is never attempted to find out.
- [x] 2.6 The roundness check: circumradius/inradius within 2 % for the axisymmetric form,
      measured from the uploaded geometry, refused at upload naming both figures.
      **Done (measurement + upload refusal; the route call is 4.3's).**
      `mse_geometry.measure_roundness` / `require_round` (numpy only, so the web image runs
      it; `NotRoundError` is a `ValueError`, as the spec asks) and the limit
      `mse_geometry.ROUNDNESS_TOLERANCE = 0.02`. `web/meshing.refuse_unless_round(data,
      units)` turns it into the app's `UploadError`. It splits with
      `mse_parts.split_obj_parts`, not `load_parts`, because `load_parts` adds the optical
      cavity's PEC-wall rule (first part encloses the rest) and refused a two-part
      electrical fixture for that reason on the first run. Method: the spec's
      "measured per loop" scenario.
      - **Where it is wired.** No electrical upload arm exists yet (4.1–4.2), so no route
        calls it. The call belongs in the `elec` upload arm in `web/app.py`, right after
        `validate_upload` and only when the form asks for `axisymmetric`, in the same
        `except UploadError` -> flash pattern the cavity (`validate_upload`, ~l.1044) and td
        (~l.1261) arms use. That is task 4.3's "roundness refusal surfaced at upload".
      - **Measured** (`python scripts/roundness_check.py`):
        256-gon R = 2: ratio 1.000075 pass; 24-gon 1.008629 pass; 16-gon 1.019591 pass;
        12-gon 1.035276 refused; hexagon R = 239.4 nm: r = 207.326 nm, 1.154701 refused;
        ellipse a/b = 1.03: 1.030073 refused; a/b = 1.015: 1.015074 pass; tilted + offset
        cylinder 1.000075 pass (about the coordinate z axis instead: 16.03); squat L = 2R
        (normal tensor isotropic) 1.000075 pass.
      - **Tests** `tests/test_roundness.py`, 10 tests, `python -m pytest
        tests/test_roundness.py -q` -> 10 passed.
      - **Mutation** (`ROUNDNESS_TOLERANCE` edited, `__pycache__` cleared, pytest exit
        code read directly): 0.04 -> exit 1 (3 failures, incl. the 3 % ellipse now
        accepted); 0.01 -> exit 1 (4 failures, incl. the 1.5 % ellipse now refused);
        restored 0.02 -> exit 0.
      - **Not covered.** Taper: a cone's loops are each round, so it passes, but the (r, z)
        builder is an equal-area cylinder (design 0.3) and would not represent it; 2.3's
        builder should refuse or mesh a varying radius. A device whose roundest axis is not
        an eigenvector of either tensor cannot exist for a body of revolution, but a
        near-round non-symmetric body is measured only about those six candidates.
- [ ] 2.7 Coarse 3-D form on the tet mesh, admitted only when 2.5's estimate fits; the
      axisymmetric-vs-3-D agreement at ≤ 10¹⁶ cm⁻³ (tier 2 or 3, measure RSS).
- [ ] 2.8 Transient: charge balance and junction capacitance; g(t) at the dot.
- [ ] 2.9 `scripts/dd_bench.py`. Prove the central-difference, dropped-2πr and
      table-priced refusal mutations.

## 3. Phase 3: coupling into the Purcell runs, and loss
- [ ] 3.1 The paper-1 bench writes `purcell_spectrum.npz` (via `np.savez`, as the bench already
      does for its other records) from the F it already prints.
- [ ] 3.2 `emitter_coupling.purcell_at`, `rate` and `timing` with their checks, reading back the
      `.npz` 3.1 writes.
- [ ] 3.3 `scripts/contact_loss_bench.py` (`optical-loss`, in scope per "b yes"): it takes any
      named absorber part, not only paper 1's gate. The weak-film inverse-Q check and its
      mutation, the far-conductor check, the two-part check, then the paper-1 wire with and
      without its contact as one fixture (tier 2, one run at a time). Report ΔQ, ΔF and the
      Q_fca estimate; skip Q_fca when the device has no doped segment.

## 4. Phase 4: web app
- [ ] 4.1 `elecs` column, the `elec` kind in the app's and worker's kind lists, the request
      keys and refusals.
- [ ] 4.2 The upload arm and the posted-equals-read test.
- [ ] 4.3 The launcher's electrical Job shape (both forms), the pricing refusal, the `pc`
      refusal test updated for the second shape, and the roundness refusal surfaced at
      upload.
- [ ] 4.4 Result files and the result page; the plotted-points test and its wrong-key
      mutation; a render check of a real finished `elec` job.

## 5. Close
- [ ] 5.1 Reviewer checks each scenario against its test and runs the benches.
- [ ] 5.2 Archive this change.

## 1.10d -- the surrounding medium, and the measurement that says it still is not a field (2026-11-06)

Lead's item: "mesh the surrounding medium (any material), then the fringing field
at the dot". The medium is meshed; the fringing field is **not** what came out, and
the negative result is the record.

**What was built.** ``mesh_fixture_padded(ambient=..., factor=...)`` adds the medium
as an ordinary fifth region with its own permittivity (:data:`AMBIENT_EPS`: air /
vacuum / bcb), in three pieces that enclose the device -- a slab under the mirror, a
ring around the stack out to the pad's outline, a slab over the top electrode -- to
a domain box of ``factor`` x the pad radius. Device geometry is 1.10c's, unchanged.
Solvers: ``field_at_the_dot`` / ``field_at_the_dot_at`` / ``scan_at_the_dot`` (the
first reports the CONTAINING REGION with each sample, because phi is piecewise
linear and E therefore piecewise constant per element, which makes a bare number
ambiguous).

**Measured, and it is not a fringing field.** A lateral scan at the dot's z, three
mesh sizes (33 405 / 58 901 / 89 255 tets) x three ambients (air, vacuum, bcb):

  x (nm)   0 ... 200    205     210 ... 500
  E_z    -707.5         -707.5  -0.0     kV/m/V

The value on the axis is -707.5 kV/m/V and DOES NOT MOVE with mesh size or with
ambient permittivity: this is the 1-D series value, and the field is exactly the
same as the pin 1.10c recorded. The rim, where the field falls to zero, stays at
~207 nm -- the wire's flat-to-flat edge -- although the pad's metal now begins at
299.4 nm. Nothing about the pad's edge appears in the field.

**Why -- root cause found, and it is a MESHING defect, not a physics result.**
The medium is meshed as a "ring" with two closed hexagon boundaries: the inner
one follows the device's outline, the outer one is the domain box. Filling the
region between them as one PLC does **not** produce an annulus. Measured: at
factor 4, **508 of 22 186** medium elements have *all four vertices* inside the
pad's footprint -- one spans r = 0 to 127 nm, z = 868 to 2367 nm, volume
4.85e7 nm^3; another spans z = -208 to 1583 nm. At factor 8, 434 do. The
"medium" therefore contains elements sitting inside the wire, and a probe at the
dot's axis is contained by those elements as well as the wire's own.

That is why refining the medium changed nothing: the medium is not, in the
solved system, a distinct body. Consequence, stated plainly: **1.10d does not
produce a fringing field, and 1.10c's pinned 1-D result stands unchanged.** The
fix is to build the annulus as a genuine shell (inner boundary duplicated as a
separate face, outer boundary separate, nothing filled across the device's
interior) or to mesh the medium with a hole in it -- not attempted here; it is
the next task, not part of this measurement.

**Guards added so the failure cannot be silent again:**
- ``solve_wire`` raises if the mesh has no top electrode (previously every node came
  back at 0 V, a constant zero field reported as a number).
- ``scan_at_the_dot`` reports ``part`` per sample; without it the run at
  z = 1477 nm read ``wire`` at x = 0 because the dot's z is exactly the top
  electrode's underside, and the lowest-index containing tet won the tie.
- ``inside`` distinguishes "past the rim" from "off the mesh": ``field_at`` raises
  one message for inside-an-electrode, outside-the-solid and failure alike.

Falsified along the way, and worth recording because each looked like the answer:
"the ambient is much less polarisable than the wire, so the field shorted through
the substrate" (bcb, 2.65, identical); "the box is too small to admit fringing"
(factor 4 -> 16, identical); "the ambient walls need a Dirichlet value" (pinning
them changed nothing); "the pad is missing from the region list" (420 tets, r max
299.4, present).

**Not claimed:** any fringing field, any dependence of the dot's field on the pad,
or that the ambient permittivity is irrelevant to the physics. Only that this
fixture, measured, does not produce the effect it was built for.

**Review follow-up (2026-11-06): one guard was dead, and testing it is what said
so.** The review noted that the ambient-name guard had no test. Writing one
surfaced that there were two guards -- ``materials`` and ``mesh_fixture_padded``
-- and only the first could ever fire, because ``mesh_fixture_padded`` calls
``materials(ambient)`` when it assembles the solve input. Mutation check, in the
order it happened: deleting the ``materials`` guard failed its test immediately
(as it should); deleting the copy in ``mesh_fixture_padded`` broke **nothing**.
My first attempt at the second mutation silently did not apply (whitespace), so
it "passed" for the wrong reason; re-running it with an ``assert old in s``
landed the edit and confirmed the guard is genuinely unreachable. The copy was
deleted rather than covered, and the surviving guard now has a test that fails
if it is removed. This is the fourth dead guard in this change series after
1.10a's ``_ring_contains``, so the pattern is "a defensive check next to a
caller that already validates upstream" -- worth looking for on every review.


## 1.10e: one conforming mesh for device and medium -- the fringing field appears

Task 1.10e (2026-11-06), lead's ruling after 1.10d: do not build a duplicated-face
annulus; mesh the device and the medium in ONE TetGen call, with the medium an
ordinary region selected by a seed point outside the device, so the interface nodes
are shared. 1.10d's two ``tetrahedralize_per_region`` calls returned two independent
meshes that were then concatenated, which is why they shared no nodes and why the
medium's PLC filled straight across the device interior.

**What was built** (``dockerfiles/maxwell_solver/mse_meshing.py``):
``surrounded_stack_plc`` + ``tetrahedralize_surrounded``, a general capability for
any part set -- a surrounding-medium region around an arbitrary layer stack, not
paper-1 code, because the owner's product is the general solver. Two construction
defects were found and fixed while getting TetGen to accept the PLC, both from the
same root cause (the box walls run as full-height bands while the circular layer
boundaries carry a fan cap across the same plane):
- the box-wall edges were driven twice (16x and 6x) and the device boundary edges
  once, leaving the surface open;
- the medium's side shell and its own top/bottom slabs shared the box walls, so
  those facets were duplicated.

**The meshing defect is gone, and it is checked on the mesh that comes back**, not
assumed from the construction. ``_check_medium_outside_device`` refuses a mesh in
which a medium element sits strictly inside a layer's own envelope. 1.10d measured
508 of 22 186; the one-PLC mesh measures **5 of 21 050**, and all 5 are interface
elements -- 0 strictly interior. The rule is therefore "inside AND touching no
device node", because the interface is a fan triangulation and a correct boundary
element legitimately straddles it. Mutation-checked: relabelling an interior column
as medium raises (103 elements); removing the medium raises; the correct mesh passes.

  **Correction (2026-11-06, review of 1.10e @0f89cbe).** The "103 elements" above
  was a hand-run and the guard was never exercised by any test -- the reviewer's
  note was right, and it is the same defect as 1.10a's ``_ring_contains`` and
  1.10d's duplicate ambient check: a number quoted for a branch nothing re-checks.
  ``test_the_medium_outside_device_guard_bites_on_both_sides`` now drives the guard
  with synthetic meshes in both directions, and is mutation-checked (disabling
  ``if bad:`` makes it fail with DID NOT RAISE; restoring makes it pass). Measured
  through that test: **8 of 8** column elements reported inside at r = 0 and
  r = 120 nm, and a column at r = 450 nm passes. The **103** is not reproduced by
  the committed test and should not be quoted; the mechanism is what the test pins,
  and the count depends on how many elements the ad-hoc column happened to hold.
  The "removing the medium raises" leg is covered by the same test's zero-medium
  case (``no medium elements``).

**Conformity, measured positively:** every one of the 1 411 device boundary nodes
appears in a medium element (0 missing). The earlier 44.4% figure was interior
device nodes, which are not expected in any medium element -- a bad instrument, not
a defect, and recorded because it looked like one.

**The field now has three-dimensional structure.** Replacing 1.10d's negative pins:

| quantity | 1.10d (two meshes) | 1.10e (one PLC) |
|---|---|---|
| lateral phi spread within a z-level | ~1e-16 | **0.17 V** |
| E_z at the dot | -707.5 kV/m/V (1-D series) | **-762 kV/m/V** |
| E_z at x = 350 nm (outside the 299.4 nm pad rim) | ~0 | **-620 kV/m/V** |

The field reaching beyond the pad, from a pad held at 1 V, is the fringing field
1.10c and 1.10d could not produce.

**What is converged, and what is NOT.** Both measured, and separating them is the
point:
- **Mesh: converged.** Fixed box factor 2, n_across 5/6/7: -764.19, -764.92,
  -764.25 kV/m/V -- a spread of **0.095%**.
- **Box: NOT converged.** Fixed n_across 6, factor 2/3/4: -764.92, -815.45,
  -838.39 kV/m/V -- still moving ~3% per step and separating less each time, so it
  approaches roughly -850 without reaching it. The natural (zero-normal-field)
  condition on the domain wall is what makes the box matter: shrink it and the
  medium beside the pad is truncated closer to the device.
- The **off-axis** value at x = 350 nm is not usable at all: -578 / -490 / -287
  kV/m/V at factor 2 with n_across 5/6/7, because that probe sits *in the medium*
  and moves with the truncation. Only the on-axis, mesh-converged value is stable.

So: **the dot's field is mesh-converged but box-dependent, and its absolute value
must not be quoted as the device's field until the box is converged** -- which is a
bench question, not a tier-1 one. The ambient permittivity does reach the solve:
bcb is 8.07% stronger than air at the same mesh (55 592 tets), far beyond the 0.1%
mesh artefact.

**Tests:** 33 in ``tests/test_paper1_wire_electrode.py``, 145 across the four
affected suites (paper-1, layered mesh, electrostatics, stark). Three 1.10d tests
were inverted rather than relaxed, and each had said in its own docstring that its
failure would be the good outcome -- two of them failed exactly as written and were
replaced, which is the intended way for a pinned negative result to retire. The
1.10c 1-D pin is replaced by ``test_the_padded_solve_is_now_genuinely_three
_dimensional``. A new test pins that the box still moves the field, so if that ever
stops it surfaces as a failure rather than as a quietly quoted number.

**Housekeeping:** ``_skipped.face`` / ``_skipped.node`` entered the branch in 7f2e4a6
(1.10d) and are deleted here, with ``_skipped.*`` added to ``.gitignore``; TetGen
writes them when it refuses a PLC.

## 1.10f: the box limit for the fringing field -- extrapolated, and the sizing knob that does not exist

Task 1.10f (2026-11-08), lead's ruling: converge the box size for the fringing field.

### The answer

The dot field converges as the box grows. Fixed discretization (edge 200 nm,
n_across 6), air, natural outer boundary:

| box factor | tets | E_z at the dot (kV/m/V) |
|---|---|---|
| 2 | 55,592 | -764.92 |
| 3 | 51,552 | -815.45 |
| 4 | 60,228 | -838.39 |
| 6 | 69,539 | -855.53 |
| 8 | 87,939 | -855.78 |

Richardson in 1/L (the box is linear in the factor) gives **-895.1** kV/m/V;
in 1/L^2 gives **-863.2**. The two bracket it, so the converged value is
**-879 +- 16 kV/m/V**.

This is the number the write-up may quote, and it is a LIMIT OF THIS MODEL:
the outer boundary is natural (zero normal field), not a chosen ambient. The
real device's surroundings are not this box. 1.10e's -762 was this quantity
measured in the SMALLEST box, not a different field.

**Correction (2026-11-08, review of 1.10f @082baee).** The table first written
here is kept below, unedited, under its original label, because the wrong
ladder is part of the record rather than something to be replaced by the right
one:

| box factor | tets | E_z at the dot (kV/m/V) | step |
|---|---|---|---|
| 2 | 35,985 | -761.64 | -- |
| 3 | 35,384 | -811.00 | -6.48% |
| 4 | 47,437 | -839.72 | -3.54% |
| 6 | 49,699 | -851.02 | -1.35% |
| 8 | 71,758 | -852.38 | -0.16% |

Those are the **n_across=3 DEFAULT** values, mislabelled "n_across 6": factor 2
gives -761.64 at the default and -764.92 at n_across 6. The measurements were
real; the label came from the wrong sweep, because my first sweep omitted the
keyword and I annotated it from the second sweep that passed it. The limit moved
only -875 -> -879 so the headline survived, but the ladder did not: at
n_across 6 the factor 6->8 step is 0.25 kV/m/V, not 1.36.

Why no test caught it, recorded because the same shape recurs in this change
series: ``test_the_box_limit_is_the_quotable_number`` builds its own meshes with
``n_across=6`` explicitly, so it computed the CORRECT ladder throughout while
its docstring quoted the incorrect one. **A test whose prose and whose
computation are independent cannot detect a disagreement between them.** The
new ``test_the_quoted_ladder_is_the_one_this_fixture_produces`` measures factor
2 at both n_across settings, asserts they differ, and asserts the quoted anchor
is the n_across=6 one; mislabelling it now fails (verified by mutation: it
reports -764.92 against a -761.64 anchor, 3.28 apart).

``test_the_box_limit_is_the_quotable_number`` pins the shape of the approach
(monotone, steps shrinking, first step >3% so factor 2 is not already
converged) and the agreement of the two Richardson forms. If a future change
breaks any of that, the test fails and the number must stop being quoted.

### The knob that does not exist

The task said "grade the medium coarser away from the device". That was
attempted and is NOT POSSIBLE in this stack, by two independent mechanisms,
both measured:

1. **Per-region volumes are inert.** Adding a ``medium_growth`` factor through
   ``add_region``'s ``max_vol`` gave 2.5/3.0/4.0/6.0 identical element counts,
   all LARGER than 1.0 -- saturation, not grading. ``mse_meshing`` already
   recorded this on a nine-order sweep (line ~857), with the instrument errors
   that produced a wrong earlier ``varvolume`` claim beside it. **I rediscovered
   a finding this module already documented**, from the newer
   ``tetrahedralize_surrounded`` entry point, and only noticed when the sweep
   came out non-monotone.
2. **The wrapper drops the keyword ``maxvolume``.** ``tetrahedralize(maxvolume=x)``
   is silently ignored in tetgen 0.8.4: an exact 12-facet unit box yields 6
   tets at 1e-1, 1e-2, 1e-3 and 1e-4. The ``switches`` string does work --
   ``-a0.001`` gives 1,759 tets and ``-a0.0001`` gives 18,021 -- so the
   documented control is reachable, but only through ``switches``, and
   ``mse_meshing`` already documents that pair (``fixedvolume=True`` plus the
   keyword) as the working form for its own path.

What actually sets element size is the PLC's own facets (``mse_meshing``
module docstring, claim 2), which is why raising ``edge_nm`` 150 -> 600 nm
moves this fixture's count by only 9%: the outlines are already the resolution.
Grading the medium would need COARSE AMBIENT FACETS, and ``ambient_outline_m``
is four points per box wall -- there is nothing to coarsen.

So the medium is meshed at the device's resolution, and the convergence knob is
the BOX SIZE. The fixture docstring says so, next to the boundary-condition
note, so the next person does not go looking for a growth factor again.

**Recorded against myself:** the ``medium_growth`` parameter was written,
measured, found inert, and reverted before commit; it never reached a header.
The two probes spent establishing that cost several calls, most of them
re-learning what ``mse_meshing`` says three hundred lines from where I was
working.
