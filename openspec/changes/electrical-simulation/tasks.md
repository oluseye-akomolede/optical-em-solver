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

      **Second-source pass, @181d9cb (2026-11-11): 3 of the 11 filled, 4 reclassified as
      REFUSED, 4 left as retrieval gaps ending in a deliberate refusal.** Every one is
      now either cited or refused with a stated reason, so the row's "done" condition is
      MET; the `xfail` does NOT flip, because 8 parameters are still absent from the
      library (see below -- the xfail and the refusal are different questions).

      - **SiC n_i/mu_e/mu_h filled** from NASA Table 5.1 and TU Wien Table 2.3; all
        explicitly 4H-SiC. `mu_e = 800`, `mu_h = 115 cm^2/(V s)` at 10^16 cm^-3 doping,
        both from NASA. The columns are named, not positional.
      - **n_i RESOLVED by derivation, not by choosing a source (`f8f8f87`, figures
        corrected in the comment at the reviewer's request).** The first pass took NASA's
        ~1e-7 over TU Wien's 5e-9, reasoning that NASA labels the table "at 300 K". The
        review asked for the figure to be checked on its merits, and the arithmetic
        settles it: `n_i = sqrt(Nc*Nv)*exp(-Eg/2kT)` with Eg(4H) = 3.26 eV and T = 300 K
        gives **1.04e-8 cm^-3 even at m\* = m_0** (an impossible maximum), which is 9.6x
        *below* 1e-7. Over the plausible masses (m_e\* 0.2-0.37, m_h\* 0.4-0.82) the range
        is **1.56e-9 to 4.25e-9**, bracketing TU Wien's 5e-9. The library now carries
        **5e-9**.
      - **Two different Eg drops, both correct, not interchangeable.** To reach 1e-7 from
        the table's 5e-9 at fixed masses needs Eg lower by `2kT*ln(20) = 0.155 eV`
        (Eg = 3.105 eV). To reach it from the computed ceiling 1.04e-8 needs `0.117 eV`
        (Eg = 3.143 eV). An earlier draft quoted one drop and attributed it to the other
        comparison; the reviewer caught it.
      - **What the arithmetic does NOT support: "NASA's cell is a 6H number."** 6H's gap
        is ~3.02 eV, so 3.10-3.14 eV sits ~0.12 eV *above* 6H and ~0.12 eV *below* 4H --
        neither polytype. The honest reading is plain mis-scaling, and that is what the
        note now says. The first draft of this entry claimed the 6H connection, which the
        numbers do not license.
      - **TU Wien Table 2.3 states no temperature** (lead's source check). Its Eg 3.26 is
        described there as from liquid-He photoluminescence, i.e. low temperature, while
        the field name `n_i_300K` asserts 300 K. So 5e-9 is recorded as *the table's
        value*, and the 300 K arithmetic above is stated as conditional on both sources
        meaning ~300 K. The note does not put "300 K" into a source that never said it.
      - **TU Wien's 6H value (1.6e-6)** is high by ~3-5x against the same calc at Eg=3.02
        (3.1e-7 to 6.4e-7) but the same ORDER -- consistent with a fitted table, which is
        why its 4H cell is trusted over NASA's on arithmetic alone.
      - **The error direction mattered:** the first pass's ~20x error was on the side of
        the *larger* number, which would have put 10x too many intrinsic carriers in every
        4H solve.
      - **The trap to remember: "the table states 300 K" is a provenance fact, not a
        correctness fact.** It decided which cell to read, and I treated that as settling
        which cell was right. A label on a cell says what the author intended; it does not
        make the number possible.
      - **A recorded polytype MISMATCH, not silently mixed.** The library's SiC `eps_s`
        is 6H-ordinary (9.66, Ioffe's "usually used" value) while the new n_i/mu are 4H.
        `mu_e` is also ANISOTROPIC (parallel-to-c 800, perpendicular 60, a 13x spread) and
        the entry records 800 because a tet mesh has no c-axis convention. Both are
        flagged in the entry's notes; neither is averaged away.
      - **The ~20x 4H n_i disagreement is RESOLVED -- see the derivation above.** TU Wien's
        5e-9 is the physically possible value and is now in the library; NASA's 1e-7 is
        above the computed ceiling at 300 K. The conflict is no longer "unresolved between
        two sources": one source is wrong.
      - **Si tau_e/tau_h and SiC tau_e/tau_h are REFUSED, not pending.** TU Wien node72
        is quotable: "There are no reliable experimental data available to extract the
        corresponding parameters for a-SiC", and it proposes substituting Si lifetimes --
        an admission that no SiC number exists to read. For Si the reason is separately
        normative: a lifetime is the SAMPLE's property (doping, defects, process), not
        the material's, so the library must not carry one. DEVSIM's
        `CreateSiliconDriftDiffusionAtContact` hard-codes equilibrium carrier densities
        and exposes no surface recombination velocity, so a lifetime is not load-bearing
        on the current path either.
      - **Au/Ag eps_s REFUSED:** a metal has no static permittivity; it is a conductor
        (contact or equipotential). Optical frequency-dependent metal permittivity is a
        separate library, out of scope.
      - **Al2O3/HfO2 eps_s stay RETRIEVAL GAPS**, so they keep their own meaning: a
        quantity that exists and waits on a dielectric handbook. Mixing them into
        REFUSED would say retrieval can never succeed, which is false.
      - **`REFUSED` is DERIVED from the entries**, not a second hand-typed list. The first
        mutation attempt edited the hand list and silently passed -- because the hand list
        no longer existed and the mutation matched nothing. Same failure mode as the
        earlier anchor-string miss, and the reason the derivation is worth it.
      - **`resolve()` has ONE guard for absence, not two.** Two were written first (a
        REFUSED loop and an NaN check); mutated separately, each passed alone, which
        proved them redundant rather than complementary. Collapsed to the NaN check, which
        now names the KIND of absence. Mutation: disabling it fails
        `test_a_metal_cannot_be_used_as_a_dielectric`. An override is always honoured --
        refusing it too would turn "we will not guess" into "you cannot model gold".
      - Tests: 18 passed, 1 xfailed in `tests/test_materials_library.py`; 96 passed,
        4 skipped, 1 xfailed on the affected set.

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
- [x] 2.4 Ideal-diode slope, current conservation, the Debye-length refusal.
      **The multi-terminal (four-contact) check is NOT delivered** -- see 2.10.
      The skip reason on its test says so; it is not a silent pass.
      **The broken I-V was POLARITY, not the solver.** Forward bias is +V on the
      p-side; the doping puts n at z > 0 (the top contact), and I was raising the
      n-side, so every "forward" point was REVERSE bias. Measured: with +V on top,
      n*p at the junction fell as n_i^2*exp(-V/V_T) -- 4.413e16 at 0.2 V against
      4.338e16 predicted (0.3 %) -- which is what made a perfectly converged solve
      look like uncoupled carriers. The lead called this on the n*p direction alone.
      With +V on the bottom, n*p tracks exp(+V/V_T) to 0.5-2 %.
      **The measurement that settles it (2026-11-09, 1e18/1e18 junction, n_z=200,
      refine=5 nm):** 0.30 V 5.586e-13 A, 0.35 V 3.828e-12, 0.40 V 2.631e-11,
      0.45 V 1.812e-10, 0.50 V 1.248e-09, 0.55 V 8.602e-09. Every 50 mV step is
      x6.9, so the ideality factor is 1.002-1.005 per step and 1.003 on a
      least-squares fit over the whole range, against 1.000 ideal (k*T/q computed
      in the test from CODATA constants, not taken from the solver). The current
      entering one terminal equals the current leaving the other.
      **Conservation is an ABSOLUTE statement.** The terminal currents sum to
      1e-16..4e-15 A at every bias and the sum does not move when the iteration
      cap goes 40 -> 200, so it is solver round-off. A relative residual is
      therefore meaningless below the floor: at 0.1 V the current is itself
      ~1e-16 A and the ratio reads 0.5. `sweep_diode_iv` now reports
      `i_sum_residual_a` and the test judges on that, using the ratio only where
      the current is well above the floor. A first draft of the conservation test
      used the ratio everywhere and "failed" on round-off.
      **The equilibrium solve is now checked by the solver's own verdict.**
      `devsim.solve(info=True)` returns `{'converged': bool, 'iterations': ...}`;
      `_solve_converged` raises `EquilibriumNotReached` when it is False, and all
      four solves route through it. A first version of the guard RE-SOLVED and
      compared node values, and that missed a non-converging stage-1 solve
      (1.0 -> 1.49 -> 0.47 -> 0.94 for 30 iterations) because Newton revisits
      similar territory on a second call.
      **WITHDRAWN (lead correction, 2026-11-09):** I blamed the minority-current
      columns being exactly zero on `is_circuit=False` equilibrium pinning at the
      contact, and called it the cause of the broken I-V. Both halves are wrong.
      Pinning carriers to equilibrium at an ohmic contact IS the standard boundary
      condition -- the top contact is n+ at 1e18, so Electrons = 1e18 there at
      every bias is correct, and the current comes from the interior rather than
      from carriers moving at the contact. DEVSIM's own `diode_1d` has both
      contacts on the silicon region with `is_circuit=False` in this same image and
      conserves (top 0.018155, bot -0.018155 at 0.5 V, residual 8e-8). The real
      cause is the polarity above.
      **The Debye gate is tested in both directions** -- an accepted mesh
      reporting L_D = 4.088 nm at 1e18, and a refused one naming the region, the
      worst L_D and the local edge. A gate that only refuses is an outage.
      These two tests exercise `require_debye_resolved` DIRECTLY. That is
      narrower than "a solve on an unresolved mesh is refused": aside from the
      gate call, no code path here is shown to stop a solve, so read the claim
      as what the tests do and nothing more.
      **The six-point I-V above is NOT comparable to 2.3's W on mesh
      resolution** (reviewer finding 2, 2026-11-10). It was measured with
      `allow_unresolved=True` -- 16 nodes were left unresolved against the
      Debye gate, so the gate was deliberately bypassed to get the sweep. 2.3's
      W = 8.540e-08 m was measured on a mesh that RESOLVED L_D and passed the
      gate. Both results stand on their own terms; they differ in whether the
      mesh was resolved, so do not cite them side by side as agreeing.
      **Planar-swap crash (noted, not chased):** replacing the cylindrical
      `EdgeCouple` with a planar one kills DEVSIM natively with no Python
      traceback. Recorded so a later reader does not spend a wake on it; the
      axisymmetric path is the one that ships.
      **NOT DELIVERED -- the four-terminal check (2026-11-09).** The interior
      taps `c1`/`c2` are added on planes inside the silicon region, and DEVSIM
      creates no contact there: measured `get_contact_list` returns only `c0`
      and `c3`. Two reasons, and the second is the one that matters:
      (i) the module's own documented rule -- a contact creates nothing
      unless its box covers a region of a different material; and (ii) that
      rule is CORRECT for this geometry, because **a contact on a plane
      inside the bulk is not physical**. In a real nanowire a middle contact
      is a RING on the outer surface, carrying current in through the
      circumference. Splitting the region to fake an interior contact would
      have modelled something that does not exist (lead's ruling, 2026-11-09).
      The test is a `pytest.mark.skip` naming this, not a deleted test and
      not a silent pass. Work is tracked as 2.10.
      Two smaller things were fixed on the way in and are committed: the taps
      were being passed in metres into a cm mesh (they landed inside the metal
      row), and `build_grid` refined only the first junction, so the Debye gate
      correctly refused the second at a 20 nm edge. The three delivered checks
      (forward slope with n = 1.003, conservation on `i_sum_residual_a`,
      Debye refusal in both directions) all pass.
      **WHY 2.4 MOVED A 2.3 NUMBER BY 2.7 %, AND WHY 2.4 IS RIGHT
      (2026-11-10, lead's merge-blocking question).** W = 8.540402e-08 m on
      2.3, 8.770540e-08 m after 2.4 -- a 2.70 % shift in an ALREADY-SIGNED-OFF
      result. The cause is one line, the material `Permittivity`
      re-statement in `_build_dd_device`. `SetSiliconParameters` writes
      `Permittivity = eps_si * eps_0` from its OWN module constants,
      `eps_si = 11.1`, `eps_0 = 8.85e-14`, i.e. `9.8235e-13`, and 11.1 is
      DEVSIM's generic silicon -- not this material's cited `eps_s = 11.7`.
      Below 2.4 a caller passing 11.7 was silently solved at 11.1.
      The direction and size confirm it: W ~ sqrt(eps_s), so
      sqrt(11.7/11.1) = 1.02667 against the measured
      8.770540e-08 / 8.540402e-08 = 1.02695, 0.03 % apart. 2.4's width is
      the one computed with the cited material value, so **2.4 is right and
      2.3's W was 2.7 % low**.
      Ruled out by measurement, not argument, in this order: the merge itself
      (clean, no overlap); `build_grid` (z-lines byte-identical across
      revisions -- 598 nodes, same spacing, same endpoints); the stage-1
      tolerance `1e-12 -> 1e-10` (restoring 1e-12 changes nothing); the
      contact-current readout calls (readout only, not equation setup); and
      `n_i`/`n1`/`p1` re-statement (`n_i` is 1.0e10 in the module and the
      caller both, and toggling it alone does not move W -- kept so Poisson's
      charge term and the contact models agree if a caller ever varies it).
      Single-variable ablation settles it: re-stating Permittivity ALONE
      gives 8.770540e-08; dropping it ALONE gives 8.540402e-08.
      Refinement does not arbitrate -- each revision is converged to 6
      significant figures across a 3x refinement, so this is a change of
      material constant, not of accuracy.
      **The width test no longer hides a change this size.** Its tolerance
      was 10 %, which let a real 2.624 % shift pass; it now pins the measured
      8.7705404e-08 to 0.5 % (the value is stable to 3e-5 relative across 2x
      refinement in both `refine` and `n_z`, so the window is ~160x the
      numerical spread). Mutation-verified with the module load path asserted:
      dropping the Permittivity line reproduces 8.5404021e-08 and the test
      FAILS, as it should.
- [ ] 2.10 Multi-terminal contacts as SURFACE RINGS. The four-terminal check 2.4 promised is
      not deliverable in the bulk: a contact on a plane inside the silicon region is not
      physical, and DEVSIM correctly creates no contact there (measured
      `get_contact_list` -> only `c0`, `c3`). A middle terminal on a nanowire is a ring on
      the outer surface, so the model needs the contact on the `r = r_max` riser at a given
      z, with the current entering through the circumference. Deliver: ring contacts in
      `_build_mesh` (a vertical segment contact at `x = r_max` spanning a z window), the
      multi-terminal solve rebuilt on them, and the skipped
      `test_four_terminals_carry_currents_that_sum_to_zero` turned on and passing.
      Do NOT split the silicon region to fake an interior ohmic contact.
- [ ] 2.5 The size check: price the 3-D run from the mesh it would build — node and edge
      counts of the actual geometry through the allocator's array sizes — and refuse
      terminally against the **Job's 14 GiB**, naming the estimate, the limit and the
      axisymmetric form when the device is round. Two-geometry test proves the estimate is
      the device's own. A native solve is never attempted to find out.
      - **The limit is 14 GiB, not 16.** `web/app.py` builds the Job with
        `memory=CFG.JOB_MEMORY`, and `web/config.py` now reads that from
        `mse_common.DEFAULT_JOB_MEMORY_BYTES` (14 * 1024**3). The 16Gi in
        `manifests/mse/power-cap.yaml` is the namespace's *admission ceiling*, not the
        Job's limit: refusing against 16 would admit a 15 GiB run and let the kubelet
        OOM-kill it, which is the failure this task exists to prevent. One constant, read
        by the app (which builds the Job) and by the solver (which prices the run).
      - **Built.** `estimate_job_bytes(grid)` prices the mesh `build_grid` would hand
        DEVSIM, from `n_nodes` and the structured edge count
        `(n_r-1)*n_z + n_r*(n_z-1)` — no solve, no allocation.
        `require_job_memory(grid, limit_bytes=None, regions, contacts, roundness_ratio)`
        raises `TooBigForJob` (a `ValueError`) naming the estimate, the limit, node count,
        edge count and "before any solve", and adds the axisymmetric hint when the caller
        passes a round `roundness_ratio`. Both are called at the top of every DEVSIM solve
        in the module (`solve_abrupt_junction`, `solve_abrupt_junction_dd`,
        `sweep_diode_iv`, `solve_multi_terminal`), so the check gates real runs rather than
        sitting unused.
      - **A wiring defect the first version shipped, found by the reviewer at 095c50f.**
        `solve_abrupt_junction` called `require_job_memory(g)` with no `g` in scope -- a
        `NameError` on the one path no test drove. Fixed, and
        `tests/test_dd_size_wiring.py` now drives `solve_abrupt_junction_dd` through both
        an admitted solve and a refused one, so "gates real runs" is tested through a
        solve path and not only through the helper.
      - **A second defect, found while writing that test and NOT fixed here.**
        `solve_abrupt_junction` (the potential-only path) does not converge even with its
        own default arguments: `devsim_py3.error: Convergence failure!`, RelError
        1.00000e+00 / AbsError 3.26e-01, on `PotentialEquation`. It has no caller, which
        is why nothing noticed. 2.3 solved the same device by RAMPING (a first solve at
        `absolute_error=1.0`, then tightening); this path asks for `1e-9` in a single
        solve, so the series has nowhere to start. Recorded as its own task below rather
        than repaired inside a size-check change: it is a numerical-method fix, not a
        wiring fix, and the size check is not what makes it fail.
      - **Measured, and it does not support the n^1.5 term.** Peak RSS of one coupled
        drift-diffusion solve, inside the image at `--cpus=2 --memory=2g`:

        | nodes | peak RSS | estimate | est/real |
        |------:|---------:|---------:|---------:|
        | 6,432 | 0.112 GiB | 0.232 GiB | 1.8x |
        | 11,040 | 0.169 GiB | 0.521 GiB | 2.9x |
        | 20,280 | 0.290 GiB | 1.295 GiB | 4.6x |

        Measured log-log slope is **0.83** (0.76 between the first pair, 0.89 between the
        second). The estimator's `O(nodes * sqrt(nodes))` fill term gives slope ~1.5, and
        the disagreement *grows* with size: fitting the three points and extrapolating,
        the estimate at 95,484 nodes is 13.2 GiB where the trend predicts ~1.0 GiB
        (12.7x), and at 142,932 nodes 24.2 GiB against ~1.5 GiB (16.7x). So the current
        model would refuse a ~95k-node mesh that fits comfortably — a false refusal, not
        a safety margin, which is the failure mode 2.5's own text warns against.
        The estimate is still conservative everywhere measured (never below the true
        peak), so wiring it in cannot cause an OOM; the open question is only how much it
        over-refuses.
      - **Decided by the lead 2026-11-10: option (a), keep the cautious bound.** The
        three measured points are 2-D axisymmetric grids; this gate prices 3-D tet runs,
        where direct-solver fill grows faster than in 2-D. Moving the threshold along a
        2-D trend extrapolated 16.7x would admit exactly the runs we know least about.
        Over-refusal is the safe failure, and nothing 3-D exists yet to be refused.
        Options considered: (a) keep n^1.5 as a deliberately over-conservative bound and
        accept false refusals above ~90k nodes; (b) replace it with the measured slope,
        honest about what was observed but a fit to three points on one machine; (c) keep
        the bound and raise the refusal threshold to where the *measured* trend crosses
        14 GiB. The builder recommended (c); the lead ruled (a) on the 2-D-vs-3-D ground.
      - **What the constant is, stated plainly.** The 40x rate and the n^1.5 law were
        calibrated TOGETHER as ONE conservative bound — not as two independent physical
        claims about LU fill. The comment in `mse_axisymmetric.py` now says so, and says
        the bound is deliberately pessimistic rather than tuned to the measurements.

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
      **Also recalibrate 2.5's bound here (lead, 2026-11-10):** measure real 3-D peak RSS
      at ≥ 3 sizes in a bounded tier-3 Job, then revisit the threshold. 2.5's bound is
      calibrated on 2-D axisymmetric grids and is deliberately conservative for 3-D; it
      should not be moved until there are 3-D measurements to move it with.
      **STATE 2026-11-10 (measured, not estimated):** the 3-D route exists and runs.
      DEVSIM 2.11.2 in our image has NO 3-D mesh-creation API (`create_1d_mesh`,
      `create_2d_mesh`, `create_gmsh_mesh`, and nothing else), so 3-D must arrive as a
      gmsh tet file; `tetrahedralize_layers` + a boundary-group writer feed
      `create_gmsh_mesh`. Contacts additionally need dimension-2 physical groups, because
      `write_gmsh22` emits only 3-D tetrahedra groups and without surface groups
      `add_gmsh_contact` binds nothing: every terminal reads exactly 0 A while the solve
      reports converged. `write_gmsh22_with_boundaries` (committed `d312d2a`) emits them.
      **V_bi AGREES, and the "0.715 vs 0.875 V gap" reported earlier was MY ERROR.**
      Analytic at 10¹⁶/10¹⁶ is 0.714317 V; the 3-D form measures 0.715290 V and the
      axisymmetric form 0.715293 V — both within 0.14 % of analytic, 0.0004 % of each
      other. The 0.875 V baseline was never computed; it was carried from memory and
      matches the analytic value for heavier junctions (~0.87 V at ~5·10¹⁶). Nothing
      could have caught it by comparing the two solves, because neither was the bad
      number. See `2.7-feasibility.md` for the retraction.
      **OPEN:** stage-3 coupled drift-diffusion does not converge on the coarse tet
      mesh — and "does not converge" is the measured shape, not a loose description.
      `absolute_error=1e10` there is DEVSIM's own DD setting (`diode_2d.py`), not a
      mistake. Measured 2026-11-10 with the full iteration log: stage 1 converges in
      14 iterations (1.25e-1 → 6.73e-17, quadratic at the end); stage 3 falls once to
      3.3, then oscillates in a 2.8–4.7 AbsError band for all 199 remaining
      iterations. It never enters a decaying regime, so it is a plateau, not a slow
      approach, and a larger budget cannot fix it (120 and 200 give the same plateau).
      Cell Péclet number is ruled out: the mesh is 3.7× denser below the depletion
      edge (2.5e-7 m against a 67 nm edge), so advection is resolved. Remaining
      candidates are coupled-system conditioning through a coarse tet junction and
      the contact boundary treatment on a rough tet surface. The axisymmetric path
      reaches 1e-10 with the SAME staged physics, so the difference is the mesh shape,
      not the model. **Both candidates predict refinement helps and both predict the
      plateau, so the log does not choose between them** — that is what the refinement
      study has to do. Do NOT loosen the tolerance to make the solve pass: what the
      number should be is exactly the thing still unknown. Trajectory table in
      `2.7-feasibility.md` Finding 4.
      **RSS CALIBRATION, built and NOT run** (task 3; builder seats do not apply
      manifests): `scripts/dd_3d_rss.py` + `manifests/mse/dd3d-rss-job.yaml`, an
      Indexed Job with 4 completions × 1 pod each (4 CPU / 13Gi, inside the
      LimitRange's 4 CPU / 16Gi ceiling and leaving the app 5Gi of the namespace's
      18Gi) at edges 1.6e-7 / 1.0e-7 / 7.0e-8 / 5.0e-8 m. One size per pod because
      peak RSS is a per-process high-water mark and DEVSIM stays resident — a loop
      would report the largest size's peak for every row. Prints
      `RESULT size=… nodes=… edges=… estimate_bytes=… peak_rss_bytes=… ratio=…` per size.
      The script prices the mesh through the estimator's own function
      (`estimate_tet_job_bytes`, extracted from `_require_tet_job_memory` for this)
      so the ratio is not a comparison between two transcriptions of the formula.
      **THE SIZES ARE MEASURED, NOT ASSUMED** (2026-11-10, 1 µm radius, 2 µm stack,
      default n_across): 1.6e-7 → 1,136 nodes / 5,201 tets / 0.018 GiB estimate;
      1.0e-7 → 4,307 / 21,926 / 0.128 GiB; 7.0e-8 → 12,157 / 65,949 / 0.605 GiB;
      5.0e-8 → 32,430 / 181,319 / 2.627 GiB. A 3.2× linear span and 146× in estimate.
      5.0e-8 is the finest the image's 200k-tet cap allows (4.0e-8 needs 352,351 and
      the mesher refuses). Note these estimates are far BELOW the 13Gi limit, so
      "fits the Job" is not in doubt at any of them; what the run buys is the
      estimate-to-RSS RATIO, which is the number a recalibrated threshold needs.
      A single local data point at edge 1.6e-7 gave peak RSS 124.7 MB against a
      19.0 MB estimate — ratio 6.58 — but interpreter and DEVSIM baseline overhead
      dominate a solve that small, so that figure says nothing yet about the LAW.
      Whether the ratio grows (pricing law wrong, threshold unsafe for 3-D) or
      shrinks (fixed overhead, threshold conservative) toward larger sizes is exactly
      what the four-point run decides. Do not read the 6.58 as a verdict.
      **WIDTH AGREEMENT (2.7 part 2, lead 2026-11-10).** Why V_bi was not enough:
      it is fixed by the contact BC and n_i, and the reviewer showed a 5 %
      permittivity error leaves it unchanged. Width comes out of the Poisson solve.
      Measured 1e16, eps_s 11.7: 3-D vs axisymmetric 10-90 % width, 2.515978e-07
      against 2.603206e-07 m, a 3.35 % difference at edge 1e-7. THE SPAN IS A
      CLIFF, NOT A CONVERGENCE TAIL — the sweep is 26.0 % at 2.5e-7, 27.8 % at
      1.6e-7, 3.35 % at 1e-7, 1.24 % at 7e-8. At 1.6e-7 and coarser the 3-D width
      is SHORTER than the axisymmetric one, i.e. the depletion region is not
      resolved and the mesher's thin sub-slabs set the answer. A width comparison
      is physics only at edge ≤ 1e-7; above that it measures the mesh. The test
      `test_the_two_forms_agree_on_the_depletion_width` runs at 1e-7 with a 5 %
      window (≈1.5× the measured 3.35 % discretisation error, and explicitly a
      mesh bound, not a physics claim).
      **THE LEAD'S SUGGESTED MUTATION DOES NOT WORK, and the first explanation of
      why was also wrong. RE-MEASURED 2026-11-10 after review.** All figures are
      rel(w_3d, w_ax) at the test's fixture (n_a = n_d = 1e16, eps_s = 11.7, edge
      1e-7) — the quantity the test asserts. The earlier entry quoted the 3-D
      width's self-shift instead, which is a different, larger number, and that is
      why its figures would not reproduce.
      *Permittivity is CANCELLATION, not drowning.* A 5 % eps_s error raises the
      3-D width 2.515978e-07 → 2.611917e-07 m, TOWARD the axisymmetric
      2.603206e-07, so the ratio FALLS 3.35 % → 2.08 %. Discretisation error and
      permittivity error point the same way and partly cancel. Catching it needs a
      window < 2.08 %, which the clean 3.35 % already fails. This is a coincidence
      of sign at this mesh — if a mesh change flips it the mutant becomes catchable
      and the window was never chosen for it.
      *The doping evidence is much weaker than first recorded.* Measured, same
      quantity: n_d +5 % → 6.22 % (fails, but only 2.9 points above the clean
      3.35 %); n_d ×2 → 5.32 % (fails by 0.32 points); n_d −5 % → 0.93 %, n_d ×0.1
      → 1.02 %, n_a·n_d ×1.2 → 2.98 %, ×0.8 → 1.76 % — ALL PASS. The original
      4.06 % / 13.6 % figures were self-shifts and are withdrawn. At this fixture
      n_a == n_d, so swapping them is a no-op the test could never catch.
      The test's real catch is a large UPWARD n_d error and little else. It is kept
      (the only test reading a quantity out of the 3-D Poisson solve) with its
      docstring stating these margins. PERMITTIVITY REMAINS COVERED BY THE
      AXISYMMETRIC WIDTH TEST (0.5 % window, mesh where the signal resolves).
      **BIASED 3-D PATH, recorded plainly (lead's wording, verified 2026-11-10).**
      Any non-empty `biases` argument raises `EquilibriumNotReached` today, because
      a bias solve runs stage-3 coupled DD and stage 3 does not converge on the tet
      mesh. Verified directly with `biases=(0.3,)` at edge 2.5e-7: it raised. BIASED
      CURRENT HAS NEVER BEEN PRODUCED on the 3-D path. This is not a loose-tolerance
      issue and must not be described as one: raising the iteration budget or
      relaxing `relative_error` would not make a biased solve arrive, because the
      non-convergence is a plateau (Finding 4). It stays open with the refinement
      study.
      NOT YET MEASURED — every ratio column waiting on the Job is pending the lead's
      run, and no 2.5 threshold may move until it exists.
      **CALIBRATION RAN 2026-11-10 (lead, tier-3 Job `mse-dd3d-rss`, image 7dbd3b4,
      4 sizes, 13Gi / 4 CPU).** Results, from pod logs:
      | edge | nodes | raw estimate | peak RSS | ratio | stage-3 |
      |------|-------|--------------|----------|-------|---------|
      | 1.6e-7 | 1,136  | 18,944,907 B  | 123,490,304 B | 6.518 | NOT converged |
      | 1.0e-7 | 4,307  | 137,925,456 B | 503,398,400 B | 3.650 | NOT converged |
      | 7.0e-8 | 12,157 | 649,930,832 B | 1,519,611,904 B | 2.338 | converged |
      | 5.0e-8 | 32,430 | 2,820,904,163 B | — | — | **FAILED in UMFPACK** |
      The ratio FALLS with size, so the 6.5x at the coarsest size is fixed process
      overhead, not a pricing law — which is exactly what the earlier single local
      point could not decide and did not claim.
      **TASK 3, STATED HONESTLY: two of the four RSS points are NON-CONVERGED runs.**
      Stage-3 coupled DD did not converge at 1.6e-7 or 1.0e-7 (the known plateau,
      Finding 4). Their peak RSS is therefore the cost of a run that assembled and
      factored to a plateau and then stopped — a real high-water mark for those sizes
      under the shipped budget, but not a converged solve's cost. Only 7.0e-8 is a
      converged point. The fit below is quoted over the two LARGEST points, one of
      which is converged, so the slope it turns on is not all plateau data; that is
      stated rather than glossed.
      **TASK 1, THE RE-PRICING.** Fitting `peak = a + b * raw` with the two largest
      points gives a ≈ 0.22 GB and b ≈ 2.0 (the two residuals `peak - 2*raw` are
      2.275e8 and 2.198e8 B, agreeing to 3.5 %). Implemented as
      `TET_FIXED_OVERHEAD_BYTES = 2.20e8` and `TET_ESTIMATE_FACTOR = 2.0`, applied
      inside `estimate_tet_job_bytes` so the refusal and the published price cannot
      diverge, with `raw=True` returning the uncalibrated sum for the calibration
      script. The axisymmetric `estimate_job_bytes` is UNCHANGED — its slope has not
      been measured the same way. Direction matters and is now the opposite of what
      the old comment asserted: the pre-calibration gate called itself pessimistic
      for 3-D and was in fact OPTIMISTIC by ~2x, i.e. it admitted runs that died.
      Two tests pin this: `test_the_3d_price_is_calibrated_by_the_measured_factor`
      (fails if the factor is removed — mutation-verified by deleting the term, which
      failed both calibration tests) and
      `test_the_calibrated_3d_price_brackets_the_measured_peaks`.
      The calibrated price tracks the two bracketed peaks (4307 and 12157 nodes)
      to 1.5 % and 0.0 %; only the latter is a converged run.
      **TASK 2, THE 5.0e-8 FAILURE.** The image links `umfpack_di_*` — the 32-bit
      signed-integer index variant of UMFPACK 5.1 (`libumfpack_lgpl.so`, symbols
      `umfpack_di_symbolic` / `umfpack_di_numeric`, confirmed by inspecting the
      shipped loader). The failure is NOT the pod's 13Gi limit: the Job was not
      OOMKilled, UMFPACK itself returned its out-of-memory status. Measured locally,
      small probes only: the SAME edge 5.0e-8 solves fine with
      `equilibrium_only=True` at 32,430 nodes / 181,319 tets / 1.32 GB peak RSS,
      so neither meshing nor the stage-1 factorisation is the ceiling; the coupled
      stage-3 Jacobian on the same mesh is what dies.

      **CEILING, MEASURED (2026-11-10).** Reproduced the same failure locally with
      a 13 GiB container limit: edge 5.0e-8, coupled solve, raises
      `RuntimeError: umfpack numeric failed` after 360 s at **peak RSS 3,079 MB**.
      The limit is therefore NOT memory — the process died using 3 GB of a 13 GB
      allowance, so raising any Job `memory` limit cannot admit this size. The
      ceiling is structural inside `umfpack_di_numeric` (32-bit `di` workspace /
      tuple overflow), between the largest size that factors (edge 6.0e-8,
      18,957 nodes / 104k tets, stage 1 only) and 5.0e-8 coupled
      (32,430 nodes / 181,319 tets). Remedies are a solver-path change, a coarser
      mesh through the junction, or UMFPACK's 64-bit `dl` variant — none of them a
      bigger pod.

      **The size gate CANNOT exclude this failure.** Measured: the calibrated
      price at 5.0e-8 is 5.45 GiB against the 14 GiB gate, so the gate ADMITS it.
      This is not a calibration error — it is a shape mismatch. The gate prices
      peak memory, and the failing run peaked at 3.08 GB, BELOW its own 5.45 GiB
      price. A mesh can be too ill-conditioned to factor while looking cheap on
      every memory metric. Excluding this class needs a non-memory admission
      criterion (e.g. a factorisation-attempt with a bounded retry, or a
      conditional-number / pivot-growth check), which is NOT implemented and is
      proposed as task 2.13 rather than silently claimed here.

      **V_bi does not depend on stage 3.** `_install_dd_physics(...,
      equilibrium_only=True)` stops after stage 1, and `solve_layered_dd_3d`
      passes it through, because the built-in voltage is fixed by the
      equilibrium solution and no later stage can move it. The V_bi agreement
      tests use it: reading V_bi from a full DD run would have reported stage-3's
      convergence failure as a V_bi disagreement, which is a false diagnosis.
      The agreement band (3 %) is a PLACEHOLDER, not a measurement — an earlier
      docstring claimed it was the sum of measured mesh-resolution differences
      and that was never measured. Making it real needs the refinement study.
- [ ] PARTIAL 2.8 Transient: charge balance and junction capacitance; g(t) at
      the dot.
      **2026-11-11 (`qitem-20261111104128`).** `transient_pulse()` is written
      and RUNS: it ramps to `v_initial`, initialises DEVSIM's time data with
      `transient_dc`, then steps with `transient_bdf1`, returning t, v, q,
      i_contact and the integrated pair rate. Two things are verified:
      the recombination SIGN was backwards (fixed -- see below), and the
      terminal currents are conserved across the two contacts to 5e-16 A.

      WHAT IS NOT DONE: the charge balance `∫I dt = ΔQ + q∫R dt` does not
      close, and I could not make it close. Measured facts, so a successor
      does not re-derive them. DEVICE AND DRIVE, stated because the first
      version of this note omitted them and its numbers did not reproduce:
      `n_a=n_d=1e17`, `n_i=1e10`, `z ∈ [-3e-7, 3e-7]`, `n_r=2`, `n_z=200`,
      `refine=1e-9`, `refine_halfwidth=5e-8`; ramped to 0.30 V in 9 DC steps,
      then stepped to 0.32 V at `t=dt`; `t_end=4·dt`; SOLVER IMAGE
      `registry.example/mode-search-engine/mse-solver:devsim-2.1`.

      CORRECTION 2026-11-11 (lead finding, re-measured): the earlier note in
      this file claimed `∫I dt` was "the SAME to 3 digits" across dt and that
      the first post-step current reproduced "to NINE digits". BOTH WERE
      FALSE, and the way they were false is worth recording: the sweep ran
      several dt values in ONE process, the second and later calls died on
      `devsim_py3.error: A mesh already exists with name "axtr"`, and the
      tracebacks were mistaken for output rows. Re-measured in SEPARATE
      PROCESSES:
        dt=2e-12  ∫I dt=1.783931e-15 C  i[1]=5.47901268e-04 A
        dt=2e-13  ∫I dt=6.777648e-16 C  i[1]=1.07330438e-03 A
        dt=2e-14  ∫I dt=7.693615e-17 C  i[1]=1.08905568e-03 A
      So `∫I dt` falls roughly with dt while `i[1]` RISES and converges
      toward ~1.09e-3 A. That is the signature of a genuine displacement
      current at the step, not a constant artefact -- the opposite of what
      the old note concluded. The reviewer measured 9.81e-15 / 9.57e-15 /
      3.09e-15 C on their device and bias; a residual that moves with dt
      and with the device is itself evidence, and the two sets are recorded
      side by side rather than reconciled by picking one.
      `i[1]` vs `i[30]` on the same run: 5.4790126827e-04 vs
      2.4120750246e-11 A -- seven orders apart, NOT identical. The decaying
      transient is what one should expect; the "NINE digits" claim was the
      same misread output.
        - The solver is not broken: at a steady drive the recorded and
          directly-read contact currents agree to 16 digits, and the two
          contacts sum to -4.9e-16 A. The recorded value is genuine.
        - `ΔQ_mobile = -8.9e-24 C` and `q∫R dt = 1.2e-30 C`, so the two
          right-hand terms are ~1e9 times smaller than the left. The charge
          crossing the contacts is not going into the silicon's mobile
          carriers, and in a device this thin (2.5e-16 cm^3) there is almost
          no recombination to absorb it.
      NEXT: HYPOTHESIS, NOT A FINDING -- the balance may need the FIXED
      dopant charge and the metal-contact/interface charge rather than only
      mobile carriers. `Σq(p-n+Nd)V` is also ~0 (the device is neutral), so
      the right variable may be the charge on the contacts themselves. This
      is untested. Do NOT simply loosen the tolerance until the test passes,
      and do not treat the candidate above as established.

      MEASURED 2026-11-11 (`qitem-20261111113210`): the imbalance is not in
      my integral, it is in DEVSIM's step, and DEVSIM says so itself. When a
      transient solve is asked to converge on charge (`charge_error`, a
      separate tolerance from the equation residuals), it prints
      `Charge Relative Error` -- DEVSIM's own source calls this "the relative
      error between projected and solved charge during transient simulation".
      On a GENUINELY DRIVEN step (0.30 -> 0.32 V, bias set on the metal
      regions, currents ~5e-4 A) it reports **8.2e-2 falling to 1.5e-5**
      across the steps, and it CANNOT be tightened: forcing `charge_error`
      to 1e-6, 1e-8 or 1e-10 stalls at **1.08e-1** and the solve fails. So
      the step is genuinely not conserving charge, and `transient_pulse`'s
      `charge_error=1.0` was accepting steps whose charge error was ~1e-1.
      That is the mechanism behind `∫I dt != ΔQ`: the left side integrates
      the current DEVSIM produced, the right side is the charge that
      actually moved, and DEVSIM is telling us those differ by ~1e-1.

      Two control measurements pin the cause down and both are NO-OPS, which
      is why they are recorded rather than presented as fixes:
        - Setting the bias on the DEVICE parameter `top_bias` instead of the
          `metal_top`/`metal_bottom` regions gives a charge error of 2.3e-30
          (machine zero) -- but the electron current is 4.4e-34 A, i.e. the
          state does not move at all. Conserved because nothing happens.
        - A CIRCUIT contact (`circuit_contacts="top"`, `KTop`/`KTop.I`,
          driven with `circuit_alter(name="V1", value=...)` as DEVSIM's own
          `tran_diode.py` does) also reports 2.3e-30 -- and again `V1.I` is
          ~1e-37 A, another no-op. The circuit contact does NOT fix the
          balance; it merely stops the device moving.
      So the circuit-contact route is NOT the fix, and neither is a tighter
      tolerance. Anyone repeating these will get 2.3e-30 and should check the
      CURRENT before concluding conservation.

      LEADING HYPOTHESIS for a successor (untested, and deliberately not
      asserted): a `bdf1` step taken directly at a bias discontinuity projects
      charge poorly. The cure in the literature and in DEVSIM's own example is
      to avoid a hard step -- ramp in small DC increments to the new bias and
      let each transient step start from a charge-consistent state. The
      earlier "ramped rather than stepped" probe did NOT close the balance
      either, so treat this as a candidate to TEST, not to assume.

      **IT WAS TESTED AND IT FAILED (2026-11-11, same row).** Relaxing to a
      charge-consistent start does NOT rescue the step. Measured on the
      fixture (before -> 0.32 V, dt=2e-12):
        - Relax first (20 bdf1 steps at dt into a re-init `transient_dc`),
          then take the step: charge error **1.42e-07**, current does not
          move (1.42e-15 A before and after). Tiny error because nothing
          happens -- the same no-op signature as the two controls above.
          Check the current, not the error.
        - Via the integrator, 1 ramp step then 300 idle steps, 0.02 V:
          first post-step current **1.798e-03 A**; the same bias set at
          DEVICE scope gives the resting -2.3263e-15 A. Only the
          region-scoped drive moves anything, and it moves discontinuously.
      **CORRECTED 2026-11-11 (lead's row: "first find out why the re-solve
      is not happening"). The 11 % figure above is real as a number and
      WRONG as a diagnosis, and the "re-seed" record was a probe bug.**
        (a) The re-seed DID take effect. `probe_seed4.py` parsed its shift
            as `int(sys.argv[3])`, so the intended "-0.02" aborted with
            ValueError and the run reported was really shift=+0.02. Made it
            a float (`probe_seed5.py`) and re-ran with shifts +0.02, -0.02
            and +1.0 V: all three give finalI=-2.3263e-15 A. A one-Newton
            -iteration probe confirms the seed lands (Phi differs by exactly
            0.04 V between the +/-0.02 seeds after the first iteration), so
            the seed is applied and the solve then walks away from it. That
            is not a no-op: the transient step has a small Jacobian time term
            (dt=2e-12) and the initial guess barely matters.
        (b) THE 11 % IS NOT AN IMBALANCE. It is both contacts read from the
            SAME side of the step. `I(top)` and `I(bottom)` at the end of the
            bdf1 step return exactly the DC answer for 0.32 V
            (1.798112e-03 / -1.672860e-03, identical). The top and bottom
            legs of THIS fixture do not carry equal current in DC either --
            the two contacts see different areas -- so comparing them to each
            other was never a conservation test.
        (c) THE REAL CHECK, for a two-terminal device, is the SERIES current
            against the change in stored charge. Using the midpoint of the
            two legs as the series current I=0.5*(I_top-I_bottom), per step
            at 0.30 -> 0.32 V, dt=2e-12:
              step  pred=0.5*(I_{k-1}+I_k)*dt   actual dQ
                1        1.7355e-15            4.203e-21
                2        2.2421e-15           -2.521e-21
                3        6.5943e-16           -1.130e-21
                4        1.9930e-16           -3.796e-22
                5        6.0754e-17           -1.194e-22
                6        1.8569e-17           -3.682e-23
            So the charge balance is off by ~6 orders, now measured the
            right way. THAT is the open defect. Compare series current with
            stored charge, never the two contact legs with each other.
        (d) WHY the series current is so large: it is a dielectric-relaxation
            current, not conduction. On 2e-12 s the device is still
            redistributing charge after a bias jump; the current decays
            1.7355e-03 -> 4.3492e-06 A over six steps and the sign of dQ
            flips after step 1 (charge overshoot). Whether that decay is
            physical or an artefact of the half-step integration is the next
            thing to settle, and it is a property of the step, not of the
            start state.
        (e) DEVSIM reports `Charge Relative Error` 8.90211e-02 on the final
            accepted step, consistent with the ~6 order gap: the solver knows
            the step charge is poor. Raising `charge_error` (the 0.2 default)
            is NOT the fix; it is the solver telling us the same thing the
            table shows.
      Where the transient's electrode charge sits
      (metal region? contact node? the 2-node contact weight?) is the next
      thing to measure.

      HOW THOSE TWO NUMBERS WERE TAKEN (added 2026-11-11, reviewer finding:
      `transient_pulse` returns only the p-contact current, so the figure
      could not be re-derived from its dict):
        - Device: `transient_pulse`'s own construction -- `build_grid`,
          `_build_dd_device(net_doping=1e17 / -1e17, n_i=1e10,
          eps_s=11.7, mesh_name="axtr")`, extended solver/models/equations
          on, `n_r=2, n_z=100` (the integrator probe, coarser than the
          200-row fixture), `refine=1e-9, refine_halfwidth=5e-8`.
        - Contacts: the mesh's two ends, named `"top"` and `"bottom"`
          (`z>0` is n-side, `z<0` is p-side). `transient_pulse` picks
          `p_contact = "top"` for this doping and reports only that one.
        - Drive: 0.30 V reached by DC ramp, `transient_dc` init, then a
          single bias change to 0.32 V set at REGION scope (silicon,
          metal_top, metal_bottom) -- device scope moves nothing.
        - Probing: `_contact_currents(devsim, ("top","bottom"))`, i.e.
          `get_contact_current(equation=ece_name) + (...hce_name)` per
          contact, at the first bdf1 step. It is NOT `i_contact[1]` from
          the returned dict; that is the p contact alone and equals the
          `I(top)` above.
        - The DC pair quoted just below comes from the same probe before
          any step, on the same device.
      Also for a successor: a one-time re-seed (recreating the
      Potential/Electrons/Holes solutions from the pre-step state, with and
      without a +0.02 V shift, before applying the bias) removes the step
      COMPLETELY -- I(top) returns to -2.3263e-15 A for EVERY seed tried,
      including a deliberately wrong -0.02 V shift. A seed that cannot tell
      a wrong answer from a right one is evidence the re-solve is not
      happening, not evidence the balance closes. Do not read it as a fix.
      DC BALANCE FIGURE (measured on the fixtures above): with both contacts
      probed at 0.30 V after `_solve_at_bias`, I_top=-2.3263e-15 A and
      I_bottom=-8.2538e-16 A -- both ~1e-15, i.e. the device balances in DC
      and does not in transient.
      Not yet built: junction capacitance (`C = dQ/dV`) is still absent.

      One cheap thing IS proven: the recombination SIGN. See
      `tests/test_transient_pulse.py`, mutation-proved by flipping the return
      back to `-sum(...)`.

      `g(t)` is DELIBERATELY ABSENT, and this must not be "filled in":
      DEVSIM's SRH is non-radiative, so the radiative pair rate the emitter
      coupling needs is `B*n*p` over the dot, which requires a CITED
      radiative coefficient `B` for the dot material. None is in the
      library. `transient_pulse` returns the pair rate and the carrier
      densities so a caller holding a sourced `B` can form it; inventing the
      value here would be a number with no model behind it.

      Recombination sign, FIXED and sourced: `_recombination_per_second`
      returned `-sum(USRH*vol)` with a docstring claiming positive USRH means
      generation. `simple_physics.CreateSRH` line 257 defines
      `USRH = (np - n_i^2)/(...)`, so POSITIVE is net RECOMBINATION; the doc
      and the code both had it inverted. Measured on the device: np/n_i^2 =
      40.6 (excess pairs, so recombination) with USRH positive on 99.2% of
      nodes. The function now returns `+sum(...)`. Anchor this at the
      formula, never at the model name `ElectronGeneration` (which is
      `-q*USRH`, a continuity-term sign, not the sign of USRH).

      **Junction capacitance, MEASURED but NOT CONVERGED (2026-11-11,
      `qitem-20261111114334`).** `C = dQ/dV` from DEVSIM's own
      `get_contact_charge(contact="top", equation="PotentialEquation")` on the
      2.8 device (n_a=n_d=1e17, r_max=4e-8 m, i.e. 4e-6 cm, z_lo/hi=-3e-7/+3e-7 m,
      n_r=2, n_z=100). Each bias is an independent converged DC solve; the
      per-step `RelError` falls to 1e-13..1e-14 on the PotentialEquation.

      | V (V) | Q_top (C) | C=dQ/dV (F) |
      |-------|-----------|-------------|
      | 0.10  | 6.068600e-21 | — |
      | 0.20  | 8.354568e-21 | 2.285968e-20 @0.15 |
      | 0.30  | 1.131769e-20 | 2.963118e-20 @0.25 |
      | 0.40  | 1.512050e-20 | 3.802818e-20 @0.35 |
      | 0.50  | 1.995825e-20 | 4.837744e-20 @0.45 |

      **It rises monotonically with forward bias**, which is the direction a
      junction capacitance should take as the diode conducts. That is the
      only claim that holds today.

      > **SUPERSEDED the same day -- read the convergence block at the end of
      > this entry before using anything below.** These numbers were taken
      > with an UNGUARDED `devsim.solve` that does not raise on
      > non-convergence, and several of the states behind them had
      > `RelError = 1.0` (solver stopped at the iteration limit). The
      > n_z-dependence described here is real but is a roughly 1/n_z decrease
      > over this range; Q_inf is NOT established (the phase-2 five-point
      > refit puts it in 3.9--6.9e-21 C). Kept because the
      > measurements are real and the correction is the point.

      **IT DOES NOT CONVERGE, so do NOT quote these numbers as C.** Measured
      across the two resolutions that matter:
      - `n_r` 2 -> 4: C = 4.320281e-20 F BOTH times, identical to 6 digits.
        The radial direction is not what limits it.
      - `n_z` 100 -> 200: C = 4.320281e-20 -> 3.089105e-20 F, a 29 % DROP.

      A physical capacitance cannot depend on how finely z is sliced, so at
      least part of the remaining gap below the parallel-plate reference is
      discretisation, and the true converged value is not established.
      SUPERSEDED, see the corrections block at ~2050: this paragraph's
      "4.43e-19 F" reference and the "10x gap" are both wrong (correct
      reference 8.678486e-19 F, gap 20x-54x), and the n_z sequence does
      decrease roughly like 1/n_z once the fit is done over all five points
      (Q_inf itself unestablished, see ~1796). Left in
      place as the record of what was believed here. The reference itself is only a
      sanity scale: a real junction is not a parallel-plate capacitor, so
      agreement was never the pass condition -- convergence is, and it is
      unmet.

      **It also depends on the SOLVE PATH, which is worse than the mesh
      dependence.** The same nominal device driven by ramping through every
      step and solving at each (n_z=100, 0.30->0.50 V) gives a THIRD value,
      C = 2.711967e-20 F with q_lo = -3.253363e-22 C and q_hi = 5.098598e-21 C
      -- not the 4.320281e-20 above. Three paths, three values
      (4.32e-20 / 3.09e-20 / 2.71e-20) over one order of magnitude of
      spread. A quantity that moves this much under numerically reasonable
      choices is not a measurement yet.

      **No `junction_capacitance()` FUNCTION IS SHIPPED, deliberately.** One
      was written, run, and withdrawn in this session. It worked, and that
      was the problem: a clean callable that returns an unconverged,
      path-dependent number is exactly what invites a successor to quote
      `C = 2.7e-20 F` as a result. The measurement stands as a RECORD here;
      the code arrives with the convergence study that makes it a
      capacitance. `tests/test_transient_pulse.py` therefore carries no
      capacitance test, because a skipped test that cannot pass is noise.

      **ANSWERED (2026-11-11, later the same day): Q_top DECREASES ROUGHLY
      LIKE 1/n_z OVER THIS RANGE, and the "74 % drop" was that decrease
      measured mid-range. Q_inf is UNESTABLISHED** -- the phase-2 five-point
      refit (below) puts it anywhere in 3.9--6.9e-21 C, so the 1/n_z form is
      a description of these points, not a law that can be extrapolated to
      n_z -> infinity. The lead asked where terminal charge is integrated, on the
      hypothesis that mesh-dependence of Q at fixed bias might be the single
      cause behind both the balance and the capacitance failures. It is not.
      Two separate facts were conflated:

      *WHERE IT IS INTEGRATED.* `simple_physics.CreateSiliconPotentialOnlyContact`
      installs `edge_charge_model="contactcharge_edge"` =
      `Permittivity*ElectricField`, summed over the contact's edges with
      `EdgeCouple`. It is a **surface flux integral (Gauss law)**, NOT a
      volume integral of node charge. So `get_contact_charge` and
      `sum(NetCharge * NodeVolume)` are different quantities and must never
      be compared. For the record they differ by ~1000x here:
      `sum_vol = 2.31e-10` cm^3 (a volume) gives `sum_netq_vol = 8.86e-16`
      while `Q_top = 1.31e-20`. That gap is not an error; it is the
      difference between a flux and a volume integral. The region integral is
      in turn dominated by `IntrinsicCharge` = `kahan3(IntrinsicHoles,
      -IntrinsicElectrons, NetDoping)` = **-6.2e12**, with the mobile
      `NCharge`/`PCharge` = -1.33e-12/+1.33e-12 cancelling it to 8 digits.
      Doping is carried uncompensated in that node model; the 1e-12 residual
      is genuine catastrophic cancellation and is why the volume route is
      useless for charge-balance work at these scales.

      *IT CONVERGES.* Guarded solves (`_solve_at_bias` -> `_solve_converged`,
      which raises `EquilibriumNotReached`), fine ramp
      (0.01,0.02,0.04,0.06,0.08,0.10,0.15,0.20,0.25,0.30,0.35,0.40,0.45,0.50 V),
      n_r=2, measured at 0.35 V:

          n_z     Q_top (C)     Delta from previous
           50   3.150239e-20        --
          100   1.310276e-20    +1.840e-20
          200   9.301640e-21    +3.801e-21
          400   8.021586e-21    +1.280e-21
          800   7.514059e-21    +5.075e-22

      Q(n) = Q_inf + c/n fits the last three points EXACTLY (lstsq residual
      5e-45): **Q_inf(0.35 V) = 6.87e-21 C**. The n_z=100 -> 200 step the
      reviewer and lead saw is the visible tail; every n_z=100 value is
      uniformly **2.0x** its extrapolated limit, which is why 100-vs-200
      looked like a 29 % failure rather than a smooth law. A coarse ramp
      (0.05 V first step) DOES fail to converge on a fresh device -- that is
      where the earlier "RelError 1.00" lines came from, not from the mesh.

      *CAPACITANCE, NOW CONVERGED.* Same guarded ramp, C = dQ/dV over 0.10 V
      spans at the same fixed biases:

          n_z    C@0.25      C@0.35      C@0.45
          100  2.606075e-20 3.360726e-20 4.293633e-20
          200  1.855304e-20 2.397817e-20 3.069738e-20
          400  1.601185e-20 2.070591e-20 2.652258e-20
          800  1.500156e-20 1.940222e-20 2.485602e-20

      Extrapolated (Q_inf + c/n, rms error <= 8e-22):
      **C_inf = 1.289e-20 (0.25 V), 1.670e-20 (0.35 V), 2.142e-20 F (0.45 V)**.

      FIVE-POINT REFIT (lead's instruction, 2026-11-11 12:57Z), beside the
      three-point fit above rather than replacing it. Fitting ALL FIVE n_z
      points instead of the last three:

          quantity     3-point (last 3)    5-point (all)     spread
          Q_top@0.35   6.874e-21 C         3.927e-21 C       43 %
          C@0.25       1.373e-20 F         1.289e-20 F       6.1 %
          C@0.35       1.777e-20 F         1.670e-20 F       6.0 %
          C@0.45       2.277e-20 F         2.142e-20 F       5.9 %

      Computed with lstsq over n_z = 50/100/200/400/800 (Q), 100/200/400/800
      (C). >>> THE 2.13x RISE BELOW IS UNQUOTABLE (2026-11-12). It is a
      `get_contact_charge` measurement ratioed against a box-length
      parallel-plate constant; both parts were wrong. Corrected: against the
      depletion capacitance the converged half-device volume integral gives
      0.65-0.77x C_dep and is FLAT across bias (see the stop-point block at
      the end of 2.8 and `2.8-charge-probe.md`). The sentence is kept as the
      record of the reading, not as evidence. NOTE the 3-point C column here
      is 1.373/1.777/2.277e-20, which
      differs from the 1.289/1.670/2.142e-20 recorded above; the earlier
      figures came from a fit line whose provenance I did not keep, so the
      numbers in THIS table are the ones with a reproducible script, and the
      earlier ones should be treated as approximated.

      THE 5-POINT REFIT UNDERCUTS THE THREE-POINT CLAIM, and this is the
      point of doing it. The 5-point Q_top fit has rms residual 2.14e-21 on
      a 3.93e-21 answer -- 55 % of the value -- so the 1/n_z form does not
      hold across the full range (the n_z=50 point is far outside its
      asymptote). **Q_inf(0.35 V) is therefore UNESTABLISHED**: it lies
      somewhere in 3.9--6.9e-21 C depending on the fit, i.e. a factor 1.75.
      The earlier "fits the last three points EXACTLY (residual 5e-45)"
      sentence above is true only because three points and two parameters
      leave one degree of freedom -- it is arithmetic, not evidence.

      C_inf is far more robust: the 5-point and 3-point fits agree to ~6 %
      and the 5-point residuals are ~6e-22 on ~1.7e-20, i.e. 4 %. So
      **C_inf = 1.29/1.67/2.14e-20 F at 0.25/0.35/0.45 V, good to ~6 %**.
      The ratio gap against the geometric reference is UNESTABLISHED to
      that same ~6 % and is quoted below as a 20x--54x band, not a measured
      constant.
      The bias trend SURVIVES extrapolation -- C rises ~1.66x from 0.25 to
      0.45 V, the direction a forward-biased junction takes as the depletion
      width shrinks -- so that qualitative claim was never at risk. The
      MAGNITUDE was: every number recorded above the extrapolation block
      (2.286e-20 ... 4.838e-20 on the unguarded probe) is ~2-3x high, and the
      "4.32e-20 / 3.09e-20 / 2.71e-20 spread" is the same convergence tail,
      not three independent discretisations disagreeing.

      >>> ANNOTATION 2026-11-12 -- this whole block (through ~1924) is
      UNQUOTABLE. The quantity it measures, `get_contact_charge`, does not
      converge on this mesh (see the retraction at ~2176, factor ~9577 across
      the z sweep); the reviewer has withdrawn their `f3c9453`/`aa24d37`
      endorsement. Kept as the record of how the reading was arrived at, not
      as evidence. Pointer: ~2176.

      MECHANISM, WHY THE TWO CHARGES ARE NOT THE SAME OBJECT (the sentence
      the lead asked for): the terminal charge is a **surface flux** --
      DEVSIM assembles it from `contactcharge_edge = Permittivity *
      ElectricField` integrated over the contact's edges with an EdgeCouple
      (area-like) weight, i.e. a Gauss-law surface integral -- whereas
      `sum(NetCharge * CylindricalNodeVolume)` is a **volume integral of an
      uncompensated doping-minus-carrier density** dominated by
      IntrinsicCharge (-6.2e12 against mobile terms ~1.3e-12, a cancellation
      to 8 digits). Comparing them is comparing Gauss's law at a surface to
      the total space charge enclosed; they agree only if the volume truly
      encloses all of it. So the balance test must use the terminal charge
      against dQ/dt, and the volume integral is unusable at this scale.

      **>>> THE LAST SENTENCE OF THE ABOVE IS WITHDRAWN (lead + reviewer,
      2026-11-12).** The geometry sentence is right -- a contact flux is not a
      volume sum -- but its INSTRUCTION was "wire the balance to the terminal
      charge", and `get_contact_charge` is exactly the quantity that does not
      converge (retraction at ~2176; factor ~9577 across the z sweep). The
      reviewer verified `eps*E*A = 6.734e-18` and the non-convergence
      independently. So: the volume integral is dead as a target (the
      IntrinsicCharge/mobile cancellation is 8 digits) and the flux is dead as
      a target on this mesh too. What survives is only the negative claim --
      **there is no reliable electrode charge from either measurement yet** --
      and the balance must be wired to NEITHER until the C++ assembly is read.
      No test enforces the withdrawn reading (checked 2026-11-12: nothing in
      `tests/test_transient_pulse.py` ties `_contact_charge_coulombs` to
      `get_contact_charge`). One nearby risk is real and is recorded here so
      it is not mistaken for the same thing: the SKIPPED 2.8 test
      (`test_junction_capacitance_depends_on_radial_resolution`, body raises
      `AssertionError("UNFIXED 2.8")`)
      does assert that C differs by more than 5% between n_r=2 and n_r=4, and
      its probe uses `devsim.get_contact_charge`. Un-skipping it would demand
      that a NON-converging quantity move with n_r. It must stay skipped, and
      its 5% threshold must be re-derived on a converging measurement, before
      it is ever enabled.

      STILL OPEN, and it is the real question: C_inf ~ 1.7e-20 F against the
      parallel-plate reference -- CORRECTED, my earlier 4.43e-19 F was
      wrong. The mesh is a half-disk swept through 2*pi, so the electrode
      area is the FULL disk pi*r^2 = 5.0265e-11 cm^2 (not the half-disk
      2.51e-11). The reference is now PINNED by
      scripts/elec28_capacitance_fixture.py, which reproduces the recorded
      charges below to all seven digits and prints the geometry it used:
      r_max = 4.0e-6 cm, L = 6.0e-5 cm (its +/-3.0e-7 m box), so
      **C_pp = 8.678486e-19 F**. Measured ratios against that reference:
      0.0300 / 0.0387 / 0.0495 at 0.25 / 0.35 / 0.45 V (n_z = 100) and
      0.0185 / 0.0239 / 0.0306 (n_z = 400), i.e. **20x--54x LOW, and the
      deficit WIDENS with bias**. (A still earlier draft used L = 5.88e-5
      from a +/-2.94e-7 box, giving 8.8556e-19 F and a 19x--40x band; that
      does not match the pinned fixture and is superseded.) Not
      explained by n_z convergence (the extrapolation only moves the
      measurement ~2x), and not explained by a series neutral-region term
      either -- (1/C_j + 1/C_neutral)^-1 comes out 8.856e-19 F flat to 4
      digits at every bias because the neutral term dominates, whereas the
      measurement rises 2.13x over the same range [UNQUOTABLE -- see the
      marker above]. A real junction
      capacitance should approach the geometry-limited value from BELOW only
      where the depletion region fills the gap; here L = 588 nm with
      N_A = N_D = 1e17 cm^-3, so the depletion width at these biases is a
      small fraction of L and the series result should be dominated by the
      dielectric in series with the whole gap -- i.e. near the parallel-plate
      value, not the measured 20x-54x under it (this sentence said "26x"
      before the reference was pinned; the conclusion is unchanged).
      That discrepancy is the next defect to chase;
      it is NOT the mesh, and the capacitance entry must not be closed until
      it is understood.

      (5) TWO DIFFERENT CHARGE QUANTITIES WERE BEING COMPARED, and this is
      the answer to "which one is Q_top". Read from the code path
      (2026-11-12), not argued:

        * `scripts/elec28_capacitance_fixture.py:93` measures
          `devsim.get_contact_charge(contact="top", equation="PotentialEquation")`
          -- DEVSIM's C++ contact assembly of `contactcharge_edge` =
          `Permittivity*ElectricField` over the contact's edges, i.e. a
          SURFACE FLUX (Gauss law). Every Q_top and C=dQ/dV number in this
          entry came from that.
        * `mse_axisymmetric.py:1563 _contact_charge_coulombs`, used by
          `transient_pulse` at :1708 and :1728 for the balance series `q_out`,
          measures `sum q*(p-n)*CylindricalNodeVolume` over the whole
          silicon -- a VOLUME sum of MOBILE charge, with the fixed dopant
          deliberately excluded.

      So the capacitance work and the transient balance have been measuring
      different objects all day: a surface flux at one contact versus a
      volume-integrated mobile charge over the region. They need not agree,
      and the earlier "why do these not match" confusion (the 1e-15 C vs
      1e-20 C scale clash) was at least partly this, not physics. Any
      comparison or balance test must name which one it uses; the natural
      choice for a charge balance `I dt = dQ` is the CONTACT (surface) charge,
      since that is what enters the terminal current integral -- but
      `transient_pulse` currently uses the volume one, so making the balance
      use the same quantity as the fixture is a CODE CHANGE that has NOT been
      made. Recorded as the next action, not claimed as done.

      What a successor should NOT do: re-derive mesh convergence of Q_top or
      C. `scripts`-less probes for this are
      `probe_qconv.py` / `probe_cnz.py` (per n_z, guarded) and the fit is
      three lines of lstsq. Reproduce, do not re-argue.

      PINNED FIXTURE (in the repo, so this survives the scratch probes).
      `scripts/elec28_capacitance_fixture.py` rebuilds the device, ramps
      through `_solve_at_bias` (guarded), and prints Q_top and dQ/dV with
      the reference it computed. It REPRODUCES the table above exactly:
      at n_z=100 it gives Q_top(0.35) = 1.310276e-20 C and
      C(0.35) = 3.360726e-20 F; at n_z=400, 8.021586e-21 C and
      2.070591e-20 F. Same to all seven digits, which is what makes it a
      fixture rather than a re-enactment. Run it with the devsim
      interpreter plus the repo's numpy:

          DEVSIM_MATH_LIBS="libblas.so.3:liblapack.so.3" \
          PYTHONPATH=$PWD/.venv-mse/lib/python3.12/site-packages \
            /tmp/devsim-probe/bin/python scripts/elec28_capacitance_fixture.py 400

      THE TRAP THAT MADE THIS NECESSARY: the first draft of the fixture
      omitted `refine=1.0e-9, refine_halfwidth=5.0e-8` and used a
      +/-2.94e-7 box. It ran clean and gave C(0.45) = 6.76e-20 F against
      the record's 4.29e-20 F -- a ~1.6x different device that LOOKED like
      a reproduced result. The junction refinement changes the charge
      materially; a fixture that omits it is measuring something else. If
      a future run of this script disagrees with the numbers above, check
      the refinement FIRST.

      **SEED PROBE RE-RUN (the row asked for it: the reviewer accepted the
      correction on reasoning, not measurement).** `probe_seed8.py`, fine
      ramp to 0.30 V, guarded, seed offset parsed as float:
      dphi = 0.00 / +0.02 / -0.02 / +1.00 V all give
      intI = -4.6525e-27 A, dQ = 0.0000e+00 C, finalI = -2.3263e-15 A --
      identical to every digit. A seed offset of a volt does not move the
      transient solution, so the start state cannot be the defect and the
      earlier "wrong seed" run was the `int()`-parse bug, now measured rather
      than argued. NOTE for anyone re-running: the seed probe MUST use the
      fine ramp. A 0->0.30 V jump raises `EquilibriumNotReached` before the
      seeding code is reached, which reads as "the probe fails" when it is
      the drive that fails.

      **ANSWERED: the 1.7e-3 -> 4.3e-6 A decay is NOT PHYSICAL. It is a
      bdf1 half-step artefact.** The row asked: physical, or an integrator
      artefact -- try a finer dt and a higher-order integrator. Both were
      done (`probe_dtint.py`; step from a converged 0.30 V state to 0.32 V,
      six steps, `charge_error=0.2` so the step is accepted the same way the
      shipped function accepts it). `Iseries = 0.5*(I_top - I_bottom)` after
      each step:

          k     bdf1 2e-12    bdf1 2e-13    bdf1 1e-11    tr 2e-12
          0     1.7355e-03    4.9405e-03    4.5404e-04    2.6917e-03
          1     5.0666e-04    3.8344e-03    3.5275e-05   -2.9438e-04
          2     1.5277e-04    3.0280e-03    2.8278e-06    1.0161e-04
          3     4.6534e-05    2.4190e-03    2.2853e-07   -6.0958e-05
          4     1.4219e-05    1.9470e-03    1.8506e-08    3.9659e-05
          5     4.3492e-06    1.5745e-03    1.4994e-09   -2.6014e-05

      Two independent failures of the physical reading:
      (i) **dt-dependence.** Changing dt by 5x (2e-12 -> 2e-13) changes the
          FIRST-step current by 2.8x. A dielectric relaxation current is set
          by the device, not by the step size; if it were physical these
          columns would agree at k=0.
      (ii) **`transient_tr` OSCILLATES IN SIGN.** Trapezoidal steps give
          -2.94e-04, +1.02e-04, -6.10e-05, +3.97e-05, -2.60e-05 -- alternating,
          decaying ~2.5x per step. bdf1's smooth monotone decay to 4.3e-6 A
          is the BDF1 damping of exactly this oscillatory mode, not the decay
          of a physical current. A real relaxation does not change sign.

      Consequence: the "six orders apart" gap between `0.5*(I_top-I_bottom)`
      and `dQ` is NOT a conservation defect in the physics. It is the
      transient integrator on a 0.02 V hard step. So DEVSIM's
      `Charge Relative Error` = 8.9e-2 on that step is reporting a REAL
      integration problem, and the 1% balance test cannot close while the
      step is driven as a jump.

      This does NOT close the balance and must not be read as closing it. It
      relocates the problem: the item to fix is HOW the transient is driven,
      not the charge accounting. The untested cure remains small DC
      increments rather than a hard step -- untested is still true of a
      RAMPED TRANSIENT (every probe above still starts from a converged state
      and then steps the bias in one go). What is now excluded is the
      hypothesis that the device or the balance equation is wrong.

      **Two wrong baselines were raised and retracted in this same session;
      do not resurrect either.** (i) A "1e4x-too-small volume" came from
      comparing a HALF-DISK against a mesh whose lines span the full radius --
      `build_grid` uses `r_lines = linspace(0, r_max, n_r)`, so n_r=2 is the
      axis plus the outer edge and the half-disk IS the right baseline.
      (ii) A "1e6x" figure came from recomputing the geometry in SI metres
      while `_build_dd_device` builds the mesh in CENTIMETRES (`M_TO_CM=100`);
      r_max=4e-8 m is x=4e-6 in the mesh. Standalone DEVSIM cylindrical
      weighting was checked in isolation and is CORRECT: a bare `create_2d_mesh`
      cylinder gives sumCylindricalNodeVolume = 2.01e-15 against the analytic
      half-disk 1.51e-15, and the per-node ratio CylindricalNodeVolume/
      NodeVolume = 1.6755e-05 against 2*pi*r_max = 2.5133e-05, the 0.667 being
      the triangular-mesh deficit. **The cylindrical geometry is not a defect.**
      Read geometry back FROM DEVSIM whenever comparing volumes.

      **UNITS AND AXISYMMETRIC SCALING CHECKED FIRST (2026-11-11, lead's
      instruction: rule out units before suspecting physics).** Two of the
      three suspects are CLEARED, measured rather than argued:

      (1) PERMITTIVITY. `_build_dd_device` sets Permittivity from
      `eps_s * EPS0_CM` with EPS0_CM = 8.854e-14 F/cm against a CM mesh
      (`M_TO_CM = 100` converts `build_grid`'s metres). Read back from DEVSIM
      at eps_s = 11.7: **Permittivity = 1.0359399740976e-12 F/cm**, which is
      11.7 * 8.854e-14 to every digit. Correct, and on ONE unit system.

      (2) CONTACT/ELECTRODE AREA (the 2*pi*r weighting). The mesh is a
      half-disk (`r_lines = linspace(0, r_max, n_r)`) swept through 2*pi, so
      the analytic electrode area is the FULL disk pi*r^2 = 5.026548e-11 cm^2
      at r_max = 4e-6 cm. Measured as sum(CylindricalNodeVolume)/L, the
      discrete area converges to that reference from above as the radial
      direction is resolved:
        n_r   2 -> 6.483853e-11 (ratio 1.2899)
        n_r   3 -> 5.673371e-11 (1.1287)
        n_r   5 -> 5.268130e-11 (1.0481)
        n_r   9 -> 5.065510e-11 (1.0078)
        n_r  17 -> 4.964200e-11 (0.9876)
        n_r  33 -> 4.913545e-11 (0.9775)
      First order, converging to 1.0. **The cylindrical area weighting is not
      a defect either.** (The n_r=2 excess of 29 % is purely the one-column
      discretisation, not the gap defect. An earlier "26x" here is struck:
      it came from the wrong 4.43e-19 F reference, superseded above.)

      (3) THE REFERENCE ITSELF WAS WRONG. The "parallel-plate 4.43e-19 F" I
      quoted at the last handoff was a coincidence of two cancelling errors:
      the correct full-disk reference is eps0*eps_r*A/L =
      **8.855598e-19 F**, and I had halved it for a half-disk whose area does
      NOT get halved (the 2*pi sweep re-fills it). Recomputed properly and
      compared against a guarded, converged measurement at n_z=400, n_r=2:
        V       Q_top (C)      C=dQ/dV (F)   ratio to 8.856e-19
        0.10    5.858122e-21
        0.20    8.081424e-21   2.223302e-20  0.0250
        0.30    1.097154e-20   2.890116e-20  0.0325
        0.40    1.469070e-20   3.719162e-20  0.0418
        0.50    1.943393e-20   4.743230e-20  0.0533
      So the gap is low, and it WIDENS with bias. The units are right and the
      reference is now right; the deficit is real. SUPERSEDED ON THE
      MAGNITUDE: the 8.855598e-19 F used in this table came from an
      L = 5.88e-5 box that the pinned fixture does not use. The fixture pins
      L = 6.0e-5 and C_pp = 8.678486e-19 F, giving 20x-54x at these same
      biases (see the block above at ~1905, which is the authoritative one).

      (4) WHY PARALLEL-PLATE IS THE WRONG MODEL HERE, and it does not save the
      measurement. W(V) runs 94.0 -> 70.4 nm over 0.15-0.45 V against a 588 nm
      device, so most of the column is neutral series material. The series
      model C = (1/C_j + 1/C_neutral)^-1 with C_j = eps*A/W and
      C_neutral = eps*A/(L-W) gives series capacitance **8.856e-19 F at every
      bias** -- flat to 4 digits, because the neutral term dominates
      completely. The measurement RISES 2.13x over the same range. So the
      measurement does not match parallel-plate OR series; the bias dependence
      is unexplained by either textbook model. That is the open defect.
      >>> ANNOTATION 2026-11-12: the bias-slope and magnitude statements in
      (2)/(3)/(4) above are UNQUOTABLE -- they rest on `get_contact_charge`,
      which does not converge (retraction at ~2176). Kept, not deleted.

      (5) A PROBE OF MINE WAS INVALID AND IS WITHDRAWN. I built a synthetic
      `ymid` edge model to identify the contact's edges and read E = 0 on all
      7 "top-contact" edges; that was MY broken edge model
      (`edge_from_node_model` did not create the `y` edge model I then
      referenced), not a property of the device. Withdrawn, not recorded as a
      finding. Same error class as (3): a bad instrument read as a strange
      world.

      (6) STILL UNEXPLAINED, and the next thing to measure: C is BIT-IDENTICAL
      (3.90730e-20 F, 6 digits) for n_r = 2, 4, 8, 16 even though the mesh
      genuinely gains radial columns (verified: x takes 2/4/8/16 distinct
      values). A resolved physical quantity cannot be independent of the
      radial discretisation. That independence points at the CONTACT
      ASSEMBLY (which nodes the contact carries and how their edge charge is
      weighted) rather than at the silicon solution -- and it is the same
      place the balance work pointed. Not yet established.

      ONE BOUNDED CONTACT-ASSEMBLY PASS (2026-11-12, lead-authorised, spent).
      It did NOT explain (6), and it found a bigger, sharper defect. Records
      both so the next seat starts from the measurement, not the theory.

      (6a) THE INVARIANCE IS REAL, AND IT IS NOT A CONTACT-NODE ARTEFACT.
      The contact plane is built with `xl=x[0], xh=x[-1]` (the full radius), so
      it does gain nodes as n_r grows. DEVSIM's mesh log, top contact:
      n_r=2 -> 2 nodes; n_r=4 -> 4 nodes; n_r=8 -> 8 nodes. Equations 366 ->
      732 -> 1464. Every solve is guarded (`_solve_converged`) and converged,
      so the identical charge is not a stale or unconverged state.

      (6b) WHY: THE DEVICE IS EXACTLY ONE-DIMENSIONAL. Sampling Potential and
      Electrons at the same z on every radial column gives identically equal
      values at all printed digits, for every n_r. The radial direction is
      decoration; the solution genuinely depends on z alone. That is WHY a
      properly-weighted cylindrical integral comes out n_r-independent --
      (6a) is a symptom of the solution being 1-D, not of a broken contact.
      This retires the contact-assembly hypothesis for (6).

      (6c) THE ACTUAL DEFECT, AND IT IS THE ONE THAT MATTERS. On the same
      converged states, at V=0.35:

          z points    Emax (V/cm)     Q=get_contact_charge    eps*E*A
          84          1.2933e5        8.306e-17               6.73e-18
          168         1.2934e5        9.007e-19               6.73e-18
          336         1.2933e5        4.354e-20               6.73e-18
          672         1.2934e5        1.391e-20               6.73e-18
          1344        1.2933e5        8.673e-21               6.73e-18

      Emax is CONVERGED to 4 digits across a 16x mesh refinement -- the field
      and the silicon solution are right and stable. `Q` is NOT converged: it
      falls by a factor ~9577 from the coarsest to the finest mesh
      (8.306e-17 / 8.673e-21, n_z 84 -> 1344; an earlier draft of this block
      said 777, which is wrong -- lead correction 2026-11-12), still
      falling at n_z=1344, and shows no sign of a limit. Since A and
      permittivity are both verified correct (see the units check above), and
      E is converged, `Q = eps*E*A` MUST be converged. It is not. Therefore
      `get_contact_charge` is NOT returning the electrode charge on this mesh.
      THIS RETRACTS the "it converges as 1/n_z" reading in the phase-2 blocks
      above: the sequence was decreasing roughly like a power and the 5-point
      fit mistook the tail for a limit.

      (6d) WHAT `Q` IS NOT. Two candidate reconstructions were measured and
      both FAILED to reproduce it, which is itself useful:
        - edge_charge_model `EField` = (P@n0 - P@n1)*EdgeInverseLength is a
          FIELD, not a charge, and lives in `_build_dd_device`'s sibling
          builder (`DField = Permittivity*EField` is the D.n that a contact
          charge needs). Monkeypatching `DField` in changed `Q` by ZERO digits
          -- which proved the patch did not reach the call, not that the model
          is irrelevant. A no-op mutation is indistinguishable from a
          surviving one; this was checked, not assumed.
        - sum of `contactcharge_edge * EdgeCouple` over the silicon edges I
          could query is ANTI-CORRELATED with Q across n_z as first measured
          (EdgeCouple up x1.22, Q down x0.32). The Q-side factor here is
          the 777-era one and is unquotable; on the corrected Q the
          anti-correlation is far stronger, so the conclusion ("Q is not that
          sum") holds a fortiori. So Q is not that sum over those edges.
          Whatever DEVSIM sums is on objects `get_edge_model_values` does not
          expose.

      HANDED UP AS PARTIAL, per the lead's instruction at the top of this pass:
      if one bounded pass does not explain it, stop. It did not. The next move
      is a real one and is NOT another start-state theory: read the C++
      `contactcharge_edge` / `CreateContactEquation` assembly in the DEVSIM
      source (it is vendored in the solver image) to find which nodes and
      weights the contact integral actually uses, instead of reconstructing it
      from Python-side getters. Do not quote any absolute Q or C from this
      row until that is answered.

      >>> UNQUOTABLE MARKER, 2026-11-12 (lead, after reviewer FAIL on
      bookkeeping). REVIEWER POSITION, recorded so a later seat does not
      inherit false confidence: the reviewer verified `eps*E*A = 6.734e-18`
      independently and verified the non-convergence, so (6c)'s FINDING stands
      -- but the reviewer WITHDRAWS their earlier endorsement of `f3c9453` and
      `aa24d37`, the two commits that quoted absolute Q and C. Treat every
      absolute charge and capacitance in the phase-2 blocks above (including
      the 20x--54x gap against `C_pp` and the 2.13x bias slope) as UNQUOTABLE
      until the C++ contact assembly is read and the electrode charge is
      computed independently. This marker is the forward pointer: the blocks
      at ~1900--1924 (see the two inline ANNOTATION lines) saying "the deficit
      is real", "20x--54x LOW", and "RISES 2.13x" now point HERE. They are kept, not deleted (lead instruction),
      but they rest on a quantity this block shows does not converge, so they
      are the retracted reading and this block supersedes them. The reviewer's
      verification of `eps*E*A` and of the non-convergence is NOT withdrawn.

- [ ] 2.9 `scripts/dd_bench.py`. Prove the central-difference, dropped-2πr and
      table-priced refusal mutations.
      **PARTIAL 2026-11-12 (`qitem-20261112102258`, branch elec-sic-materials-fill).
      2 of 3 caught; the third SURVIVED and the survivor is a real defect, not
      a broken bench.** The box stays UNTICKED: the row's done-condition is
      "box ticked only if all three are caught".
      Script: `scripts/dd_bench.py`, one subprocess per case (DEVSIM's mesh
      registry is process-global), mutations applied by monkeypatch only.
      Every number below is from the script's printed output.

      | mutation | check that caught it | reference | mutated | verdict |
      |---|---|---|---|---|
      | central-difference flux | `_solve_converged` (`EquilibriumNotReached`) | `converged=True`, `I_top=4.850859e-13 A` | `converged=False`, hole-continuity residual 1.164e+03 | CAUGHT |
      | dropped 2πr | none — **survived** | `w_measured=8.770540e-08 m`, `NodeVolume sum=1.980132e-10` | bit-identical; `NodeVolume sum=1.980132e-10`, `CylindricalNodeVolume` ABSENT | SURVIVED |
      | table-priced refusal | `EstimateError` from `estimate_memory` | refused: "not been measured above 112,847 free unknowns" | returned `5.030064e+09` bytes | CAUGHT |

      Reproduce (solver image, tiny cases):
      `docker run --rm --cpus=2 --memory=2g -e DEVSIM_MATH_LIBS="libblas.so.3:liblapack.so.3"
      -e PYTHONPATH=/repo/dockerfiles/maxwell_solver:/opt/app -v "$PWD":/repo:ro
      --entrypoint python registry.example/mode-search-engine/mse-solver:devsim-2.1 /repo/scripts/dd_bench.py`
      (case 3 alone needs no DEVSIM: `python scripts/dd_bench.py --case memref`
      runs both sides in-process). Exit code is 1 when any mutation survives.

      **WHY THE 2πr MUTATION SURVIVED, measured:** `cylindrical_node_volume` and
      `cylindrical_edge_couple` do NOT overwrite `NodeVolume` / `EdgeCouple`.
      DEVSIM logs "Replacing Node Model CylindricalNodeVolume" and writes NEW
      models under the `Cylindrical*` names. Patching both calls out leaves
      `NodeVolume` bit-identical (1.980132e-10 in both columns) and the solve
      bit-identical to 16 digits. The quantity that does move is the model that
      disappears: `CylindricalNodeVolume` sums to 8.294358e-16 in the reference
      and is ABSENT in the mutant.

      **THE DEFECT THIS EXPOSES (pre-existing, not introduced here).** The
      equations and the integrators ask for DIFFERENT measures:
      - `PotentialEquation` is assembled with `edge_volume_model="EdgeCouple"`
        (mse_axisymmetric.py:832) — the BARE, PLANAR coupling;
      - `_contact_charge_coulombs` (:1604) and `_recombination_per_second`
        (:1633) integrate over `CylindricalNodeVolume` — the CYLINDRICAL one.
      On the 2.8 solve mesh the two differ by ~4 orders of magnitude:
      `NodeVolume` sum 7.263333e-10 against `CylindricalNodeVolume` sum
      1.216983e-14; and the mesh's own volume is 0.990063 x `r_max*L`, i.e. the
      planar strip, against a full-swept-disk volume of `pi*r^2*L`. So the
      Poisson solve has been PLANAR while the charge integral has been
      CYLINDRICAL, in every axisymmetric solve in this change.
      This is the best candidate yet for the 2.8 charge imbalance and for
      `get_contact_charge` not converging, because `Σ q(p-n)·V_cyl` cannot
      balance a solution whose Poisson equation used `EdgeCouple`.

      **NEEDS THE LEAD (`qitem-20261112102258`):** fixing it means changing which
      measure the equation uses, which moves EVERY solved number in 2.3--2.8 —
      V_bi, the depletion width, every charge and capacitance. 2.9's own limits
      forbid this bench from touching solver source, and the change is far
      outside 2.9's scope. The 2.8 UNQUOTABLE markers therefore stay in place:
      the numbers are not merely unverified, they were computed on a mixed
      measure. Recommend the lead open this as its own row against 2.3, before
      anything else in the electrical-simulation change quotes an absolute
      charge.
- [x] 2.11 Solvers read material parameters THROUGH the citing gate, not around
      it. Reviewer finding 1 (2026-11-10): `require_cited_parameter` checked that
      a cited value EXISTS in the library and returned None, so `sweep_diode_iv`,
      `solve_multi_terminal` and the other two callers went on using their own
      `eps_s` argument. A caller could pass a hand-typed eps_s and still clear
      the gate.
      **DONE 2026-11-11 (`qitem-20261111101126`, branch elec-materials-gate).**
      `require_cited_parameter` now RETURNS the cited value, and a new
      `material_value(material, name, override=None)` wraps it: it returns
      `(value, source)` where source is `"library: <material>.<name>"` or
      `"override(<material>.<name>)"`. All FIVE solvers that take a material
      (`solve_abrupt_junction_dd`, `solve_abrupt_junction`, `sweep_diode_iv`,
      `solve_multi_terminal`, `solve_layered_dd_3d`) now assign `eps_s` from it,
      their `eps_s` keyword defaults to None, and each returns `eps_s` and
      `eps_s_source` so an override is reported rather than inferred.
      A caller-supplied eps_s is therefore an EXPLICIT, recorded override; it
      can never again be a silent default. A gap or a refusal still raises
      even when the caller supplies a number (cite-or-refuse outranks the
      override) -- `test_a_gap_is_refused_even_when_the_caller_supplies_a_number`.
      Tests: `tests/test_material_value_gate.py` (9). Mutation-proved: restoring
      any one solver to a bare `require_cited_parameter` fails
      `test_every_solver_that_takes_a_material_reads_eps_s_through_the_gate`,
      naming that solver. The converse is asserted too: `_build_device` must NOT
      re-resolve, because a second gate would silently discard an entry-point
      override one level down.
      NOTE: the library's `resolve()` already returned `(values, sources)` and
      has no production caller; the defect was only in the solver path.
- [x] 2.12 `solve_abrupt_junction` (the potential-only path) does not converge. FIXED
      2026-11-11. The recorded cause above (single solve vs a staged ramp) was WRONG, and
      the fix it implied would not have worked: a 0.05 V-step bias ramp stalls at the same
      place. Measured stall was `AbsError 4.09097e-01`, which is exactly V_bi/2.
      REAL CAUSE: the fixed space charge was `q*NetDoping*1e6` under a comment claiming
      SI geometry; the `1e6` inflated the charge a millionfold. Dropping it converges in
      ~9 Newton steps to RelError 5e-14. The sweep, other things equal:
        Permittivity=F/m,  charge=q*N      -> converged, span 0.8334 V  <-- taken
        Permittivity=F/m,  charge=q*N*1e6  -> FAIL
        Permittivity=F/cm, charge=q*N      -> converged, span 36.98 V (wrong)
        Permittivity=F/cm, charge=q*N*1e6  -> FAIL
      Consequence recorded, not fixed: this builder sets Permittivity from `EPS0` (F/m)
      while `_build_dd_device` uses `EPS0_CM` (F/cm), so the two are not on one unit
      system. Unifying them means re-deriving the 2.3 calibration under `EPS0_CM`, which
      is a separate change with its own numbers to re-validate.
      V_bi now agrees with `solve_abrupt_junction_dd` to 0.14 % (0.833370 vs 0.834505 V).
      DEPLETION WIDTH IS NOT ACHIEVABLE BY THIS MODEL and no attempt was made: with no
      electron/hole continuity there are no carriers to screen the field, so the potential
      ramps across the whole domain (far-field slope 3.0e5 V/m, measured) and the 10-90 %
      transition reads 1.82e-6 m against the coupled solver's 8.77e-8 m on the same grid.
      The number is still returned, for the size-wiring test that uses it as a cheap
      fixture; its docstring and `tests/test_po_junction_convergence.py` both say it is
      not a physics result. A real depletion width needs the coupled path.
      Two unit bugs fixed alongside: the width was measured on the raw cm axis and
      compared against a metre-valued analytic width (a 1239x phantom error), and the
      result dict now returns `z` (metres) and `phi` like the coupled solver so the two
      can be compared sample-by-sample. Tests: 6 new, mutation-proved by restoring `1e6`
      (all fail with the original Convergence failure).
- [ ] 2.13 A memory-priced gate cannot refuse a mesh that is too ill-conditioned to
      factor. Found 2026-11-10 reproducing 2.7's 5.0e-8 failure locally: the coupled
      solve dies in `umfpack_di_numeric` ("umfpack numeric failed") at peak RSS
      3.08 GB, while `estimate_tet_job_bytes` prices the same mesh at 5.45 GiB — so
      the gate ADMITS a run that provably cannot factor, and the peak is BELOW its own
      price. Raising `resources.limits.memory` does nothing. Admission for this class
      needs a non-memory criterion: try the factorisation with a bounded retry at a
      coarser mesh, or gate on pivot growth / condition estimate, or move to UMFPACK's
      64-bit `dl` variant so the ceiling itself moves. None of these is implemented;
      2.7 records the gap rather than claiming the refusal path covers it.

      **INTERIM SHIPPED 2026-11-10 (lead decision):** a NODE-COUNT refusal,
      `TET_MAX_FACTORABLE_NODES = 18957`, raised in `_require_tet_job_memory`
      BEFORE the memory price. 18,957 is the largest measured to factor (edge
      6.0e-8, stage 1); 32,430 (edge 5.0e-8, coupled) failed. The true ceiling
      lies between those two sizes, so the constant takes the known-good end and
      refuses some meshes that might have solved — a refusal the user can act on
      beats a six-minute failure inside the numeric factor. The refusal message
      says "Coarsen the mesh" and states it is a solver-size limit, not a memory
      limit, so nobody tries raising the Job's memory.
      Tested twice: `test_a_mesh_over_the_factorable_ceiling_is_refused_before_solving`
      (mutation-verified — removing the guard fails it) and
      `test_the_node_ceiling_lies_between_the_two_measured_sizes`.
      The pre-existing memory-gate test was REPOINTED, not deleted: since this
      guard no mesh under 18,957 nodes exceeds the 14 GiB default, so it now
      names an explicit small `limit_bytes` to exercise the memory gate alone.
      STILL OPEN above, unclaimed: the 64-bit `dl` variant, pivot-growth /
      condition gating, and a coarser junction mesh. The node ceiling is a
      stop-gap that refuses without diagnosing.

**2.8 STOP POINT — Option B taken (lead decision, 2026-11-12).**
**CORRECTED 2026-11-12 after reviewer FAIL: the numbers this block first
carried (1.80e-19 F, 0.21 C_pp, "~5x low", "seam") are WITHDRAWN.** They came
from differencing across two n_z (a mesh difference, not a dQ/dV) on
mislabelled bias columns, against a box-length reference. See
`2.8-charge-probe.md`, which now shows the arithmetic row by row.

WHAT THE PROBE ACTUALLY ESTABLISHES (all from fixed-mesh dQ/dV):

- **`q_half_top`, the half-device volume sum of mobile charge, is the
  well-behaved quantity.** Its dQ/dV is 4.256e-18 F (the probe's sign
  convention makes it negative; the magnitude is the capacitance) and it
  moves 0.09 % from n_z=84 to 1344 and 0.00 % from 1344 to 5376.
- **Against the right reference it is 0.65–0.77 x `C_dep`.** `C_dep =
  eps_s*A/W(V)` is 5.539e-18 F at 0.15 V (W = 94.0 nm) and 6.586e-18 F at
  0.35 V (W = 79.1 nm), from the device's own N_A = N_D = 1e17, n_i = 1e10,
  V_bi = 0.833370 V. The measured value is FLAT where `C_dep` rises 19 %, so
  it does not reproduce the depletion slope. **Cause unknown.** That, not
  "5x low", is the residual statement.
- **`get_contact_charge` is a poor capacitance quantity** — 61x below the
  half-device sum and mesh-tracking — but its fixed-mesh dQ/dV is POSITIVE
  (+1.677e-20 F at n_z=1344, +1.633e-20 at 5376). The earlier "negative
  dQ/dV / a capacitance cannot be negative" reading was my arithmetic error
  and is retracted.
- **`q_dop_net` is +4.261067e-20 C bit-identically at both biases.** A
  neutral diode should have this near zero, and it is; but 0.2 V of bias
  moving NO net charge is an open solve/doping-sign observation for a later
  look. It is **not** a z = 0 seam and the seam reading is removed: charge
  neutrality explains the approach to zero, as the lead and reviewer both
  pointed out.
- **The parallel-plate constant `C_pp = 8.678486e-19 F` is arithmetically
  correct** (`eps_s·π·r²/L`, box length L = 6.0e-5 cm, verified line by
  line) **but is the wrong yardstick** — a 600 nm box against a ~80–95 nm
  depletion width. Kept only as a labelled mesh constant.

2.8 STILL CANNOT BE CLOSED: no charge identity is asserted anywhere; the
transient balance remains owed; `q` from `transient_pulse` is labelled a
STAND-IN in the code. The 20–54x, 5x, 2.13x, 0.207 and 1.80e-19 F figures are
dead as live claims and must not appear in any successor document.

OWED, unclaimed: (i) why the measured capacitance is flat in bias where
`C_dep` is not; (ii) the C++ `contactcharge_edge` / `CreateContactEquation`
assembly, read from the vendored DEVSIM source, to say what
`get_contact_charge` actually sums; (iii) the skipped 2.8 test's 5 % n_r
threshold, which still has no justification.

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

### 2.3 axisymmetric (r,z) drift-diffusion (in progress, 2026-11-09)

- [x] The 2πr weighting is available in DEVSIM, but only on a genuine 2-D
      mesh: ``create_2d_mesh`` + ``raxis_variable``/``raxis_zero``, then the
      **commands** ``cylindrical_node_volume``/``cylindrical_edge_couple``.
      They are commands, not expressions. Verified against an analytic disc
      volume.
- [x] A contact only registers when a **region of different material** sits
      under its box; a same-material box yields zero contacts with no error.
- [x] Every edge model needs its analytic Jacobian companions
      (``<model>:Potential@n0/@n1``) or the Newton matrix is singular.
- [x] A 1-D DEVSIM mesh has **no ``y`` coordinate** — it returns 0.0
      everywhere, so ``init_from="y"`` silently dopes a constant. One of my
      own probes was undoped this way and reported V_bi = 0.0000 with no error.
- [x] The coupled drift-diffusion solve converges on the (r,z) mesh, and
      **V_bi = 0.83450 V vs 0.83337 V analytic (0.136%)**, tested.
- [ ] The depletion **width** is not yet quotable, and the defect is **not**
      the carrier contact BC — that correction was tested and does not hold.

**Corrected diagnosis (2026-11-09, after the reviewer's finding 2):** I ran
the contact-BC hypothesis down and it is wrong, so recording what was
measured rather than what was assumed:

- The carrier contact BCs **are** satisfied exactly. All four
  ``Potential``/``Electrons``/``Holes``/``IntrinsicElectrons`` contact node
  models evaluate to a residual of 0.0 at every contact node. Losing none.
- The space charge **does** include the carriers. At a neutral node
  ``PotentialNodeCharge = 1.28e-18`` (e=1e3, h=1e17, nd=-1e17) — genuine
  cancellation. The model that would break neutrality
  (``PotentialIntrinsicCharge``, doping only) is not the one in use.
- The junction **does** screen. With the mesh in centimetres and
  DEVSIM's own F/cm constants, the whole 0.8345 V drop sits inside
  ±50 nm; it is localised, not a linear ramp. The earlier "linear ramp"
  readings were the **metre mesh**: DEVSIM's ``simple_physics`` is a
  cm-unit model, so a metre grid made the Debye length 1000x too long.
  That is the unit trap my own notes warned about and I walked into.
- The width is ~39 nm against 147 nm analytic (ratio 0.266, stable across
  charge thresholds 0.5/0.2/0.1/0.05/0.02 and across refinement windows).
  It still tracks the domain: 4.7 nm on ±0.3 um vs 31 nm on ±2 um.

So the open defect is narrower than "the contact BC": the space-charge
extent is ~3.75x too short and is not domain-independent. Unexplained.

**RESOLVED 2026-11-09 (the width question the lead blocked the merge on).**
Root cause: **a unit mismatch — the DEVSIM mesh was built in METRES while the
physics model it was fed is in CENTIMETRES.**

- ``devsim.python_packages.simple_physics`` is a centimetre-unit model
  (``eps_0 = 8.854e-14 F/cm``, doping in cm^-3). The reference
  ``diode_common.py`` builds its mesh at 0, 0.5e-5, 1e-5 **cm** for exactly
  this reason.
- ``_build_mesh`` was fed a metre grid verbatim into ``add_2d_mesh_line``, so
  ``EdgeInverseLength`` carried a per-metre scale while every charge term
  assumed per-cm. ``SetSiliconParameters`` then set ``eps_0`` in F/cm against
  that metre mesh, making the space charge 100x too weak: the Debye length
  came out sqrt(100) = 10x too long, 129 nm -> 1.29 um, the size of the box.
- **The result was not an error message — it was a beautifully convergent
  wrong answer.** The solve relaxed to a LINEAR potential ramp from contact to
  contact across the whole domain, with no junction in it. V_bi therefore
  looked perfect (0.8345 V, 0.14 % from analytic) because it is just the
  contact-to-contact difference, while W tracked the box because *the box was
  the entire solution*. Measured profile: flat -0.417 V, straight line, flat
  +0.417 V.
- **The fix** is one line: build the mesh in cm. Everything else in the module
  stays SI (public API, grids, widths) with conversion at the DEVSIM boundary
  (``_set_net_doping`` converts y cm->m before evaluating the profile; the
  readout converts z cm->m).~~ **Superseded on one point (2026-11-10):**
  leaving Permittivity alone is right about the UNIT (the F/cm value is the
  correct one for a cm mesh) but wrong about the MATERIAL. That block sets
  `eps_si = 11.1`, DEVSIM's generic silicon, so a caller's cited 11.7 was
  silently ignored. 2.4 now re-states `eps_s * 8.854e-14 F/cm` and the width
  moves 2.7 % (8.5404e-08 -> 8.7705e-08, exactly sqrt(11.7/11.1)). See the
  2.4 entry "WHY 2.4 MOVED A 2.3 NUMBER BY 2.7 %" below. Do not revert it
  thinking it is the old F/m bug.

**After the fix, measured on the real solve:**

| domain half-width | W_measured | W_analytic x 0.578 | error | V_bi |
|---|---|---|---|---|
| +-0.3 um | 8.5404e-08 m | 8.4887e-08 m | 0.6 % | 0.83450 V |
| +-1.0 um | 8.5404e-08 m | 8.4887e-08 m | 0.6 % | 0.83450 V |
| +-2.0 um | 8.5404e-08 m | 8.4887e-08 m | 0.6 % | 0.83450 V |
| +-5.0 um | 8.5404e-08 m | 8.4887e-08 m | 0.6 % | 0.83450 V |

These rows are the measurement as taken at c413e35 and are left as recorded.
**They are now 2.7 % low in W** (the table's 0.6 % agreement is with the 11.1
permittivity, not the cited 11.7): with the material value re-stated the same
solve gives 8.7705e-08 m, which is 3.3 % from the analytic 10-90 % line rather
than 0.6 %. Domain-invariance is unaffected. See the 2.4 entry below.

W is **identical to five significant figures across a 16.7x change in box
size** (+-0.3 um to +-5 um: 10/0.6 = 16.7, the same by half-width or full
width). That is the direct answer to "find why W tracks the box": it tracked
the box because of the unit bug, and with the unit fixed it does not track the
box at all. (The separate grid measurement below uses the +-0.3 um to +-2 um
pair, which is a 6.7x change -- two different comparisons, not one figure
reported two ways.)

**Two smaller defects found while confirming it (both fixed):**

- **The 10-90 % shape factor was wrong.** The solver's potential transition is
  LINEAR (constant field), not triangular, because the pinned-carrier DD solve
  gives a near-constant rho across the transition. Measured W_10-90/W_full =
  0.5817 at c413e35 (8.540e-08 / 1.468e-07 m, reviewer re-measured in the
  image), matching the linear value 0.5782 to 0.6 %, not the triangular
  0.4472. Using 0.4472 manufactured a stable, refinement-independent ~30 %
  "error" that read as a physics defect. (An earlier draft recorded 0.5927 and
  32.5 %; neither reproduces on any commit, so both are withdrawn.)
- **``build_grid``'s far regions had a fixed node count** (``max(2, n_z//3)``
  each), so their spacing scaled with the domain. That moved the measured
  width 3.8 % between a +-0.3 um and a +-2 um box *after* the units were right.
  Now sized by spacing, so node count scales with the region's length.

**Ruled out while chasing this — and one of these I had wrong:**
the mesh resolution itself (fine), the contact node models (identical in form
to DEVSIM's ``CreateSiliconPotentialOnlyContact``), and n*p = 1e20 exactly at
every node (DEVSIM's own built-in convention; its reference diode does the
same). **I previously recorded "the unit conversion was ruled out because the
1e6 in the charge term is consistent with F/m permittivity". That was wrong**
— the conversion was *internally* consistent and simultaneously inconsistent
with ``simple_physics``, which is what the defect was. A locally consistent
transcription of a unit bug still reads as consistent.

**A wrong "RESOLVED" note stood here for one wake.** The paragraph that
previously occupied this space claimed the width was fine, Debye-limited, and
that "W tracks the box is not a defect — it is the physics", citing the
reference diode reading 28.6 nm. Those *measurements* were real but were taken
through the metre-mesh bug, so they described a linear ramp, not a junction.
The correction: the Debye-width sweep was a description of the broken solve.
**Lesson: when one suspicion (the metric) is confirmed by comparing against an
external tool, check that the external tool comparison is not itself running
the same broken code.** Both sides of my comparison shared the defect.

- [x] Re-measure W on domains from +-0.3 to +-5 um; domain-invariant to 0.6 %.
- [x] State in the docstring which width is compared to which, and why.


- [x] The width test no longer "fails by design". At ``c146290`` the width
      assertion raised a ``KeyError`` inside an ``xfail(strict=True)`` and so
      passed as "expected failure". That is now real keys + a hard 10 %
      assertion, and the suite is 20 passed, 1 xfailed (the known 2.2
      uncited-parameter xfail). Verified non-vacuous by mutation, re-measured
      2026-11-09 on the merged tree:

      - metre mesh back (``M_TO_CM = 1.0``): **2 of 5 fail**, the width test
        and ``test_the_junction_is_not_just_the_box``. The three that survive
        are ``test_the_coupled_solve_reproduces_the_built_in_voltage``,
        ``test_the_built_in_voltage_does_not_depend_on_the_domain`` and
        ``test_the_potential_does_separate_the_two_doping_regions`` -- and
        they survive *because a linear ramp has the right V_bi too*: the ramp
        still spans the full drop from contact to contact, so V_bi and "the
        two sides have different potentials" are both satisfied by the broken
        solution. That is exactly why the defect hid for a wake: the tests
        that checked the *magnitude* of V_bi could not see it. Only a test of
        the width, or of whether the width is the box, can.
      - triangular shape factor (``0.4472`` instead of ``0.5782``): **1 of 5
        fails**, the width test, at 30.1 % (measured 8.540e-08 m against the
        triangular expectation 6.566e-08 m, as printed by the assertion). To
        keep the quantities apart, since they are easy to conflate: 30.1 % is
        the *observed failure against the triangular expectation*; 0.6 % is the
        agreement of the measured 0.5817 with the linear 0.5782; and 29.3 %
        (0.5782/0.4472 - 1) is the *ratio between the two shape factors*,
        which is a third number that never appears as a test error.

**Recorded against myself (2.3, wake 4→5):** I spent four wakes probing
DEVSIM's API by hypothesis when
``devsim_data/examples/diode/diode_common.py`` had the whole recipe in 60
lines. Worse, in wake 3 I reported "V_bi = 0.83337 V, 0.0000% error" from a
potential-only solve whose domain I had sized to about one depletion width —
a linear ramp of the right length is not evidence of agreement, and I
retracted it. The lead's two corrections (the reference exists; 1e10 is the
normal DD tolerance) are what moved this from stuck to working.

**Correction: a "reviewer finding 3" I reported does not exist (2026-11-09).**
After the 2.3 review I listed an open item -- "the potential error-correction
factor 300 giving 1.3 um with both contacts at 0 V, sweep ``PotentialError``
and compare the reference" -- and attributed it to the reviewer. **It is not
the reviewer's finding and it is not in this tree.** Checked: no
``PotentialError`` anywhere in ``dockerfiles/`` or ``openspec/``, none in the
reviewer's own worktree, and none across the last 40 revisions of that worktree
either. The only occurrence of the string anywhere is in my own post-review
summary, where I first wrote it.

So there is nothing to fix and no evidence to write down: I cannot say which
solve, which bias, or what the 300 multiplies, because I do not have a source
for any of it. Recorded here rather than silently dropped, because "carries an
unfounded open item in the repo notes" is itself a defect -- it would send a
later reader hunting for a bug that was never demonstrated. If a real
PotentialError concern surfaces it gets its own note with a measurement
attached; this one is withdrawn.
