## ADDED Requirements

### Requirement: Drift-diffusion SHALL solve Poisson and both carrier continuities through DEVSIM
`drift_diffusion.solve(mesh, regions, doping, contacts, biases, form)` SHALL build a DEVSIM
device and solve the coupled Poisson, electron-continuity and hole-continuity equations with
Scharfetter-Gummel edge currents, Boltzmann statistics, Shockley-Read-Hall and radiative
recombination, and ohmic contacts. The regions and contacts SHALL be general: any number of
doped semiconductor parts, any number of undoped semiconductor or insulator parts, and any
number of ohmic contacts, each at a fixed bias or swept. `form` SHALL be `"axisymmetric"` (a
2-D (r, z) mesh of an equal-area cylinder, each node and edge weighted by 2πr) or `"3d"` (the
tetrahedral mesh from `mse_meshing.tetrahedralize`). Material parameters (ε_s, n_i,
mobilities, lifetimes, B) SHALL come from the materials library or per-part overrides, each
with its cited source recorded in the module. It SHALL return, per bias, the terminal
currents, the potential and both carrier densities at every node, and the field sampled at
any requested points. It SHALL solve each bias by Newton from the previous one and raise
`RuntimeError` naming the bias when Newton does not converge.

#### Scenario: The built-in potential of an abrupt junction
- **WHEN** a 1-D-like abrupt p-n junction (a wide axisymmetric cylinder) at zero bias is solved
- **THEN** the potential step across it is (k_BT/q)·ln(N_A·N_D/n_i²) within 1 %

#### Scenario: The depletion width
- **WHEN** the same junction is solved at zero and at a reverse bias V_R
- **THEN** the depletion width matches √(2ε_s(V_bi + V_R)(N_A + N_D)/(q·N_A·N_D)) within 10 %
  (the depletion approximation is itself approximate at the edges)

#### Scenario: The ideal-diode slope
- **WHEN** a long p-n diode with only SRH recombination outside the depletion region is swept
  in forward bias at low injection
- **THEN** d(ln I)/dV over the low-injection range is q/(k_BT) within 3 % (ideality 1)

#### Scenario: Current is conserved
- **WHEN** any bias is solved
- **THEN** the currents of all contacts sum to zero within 1e-6 of the largest one

#### Scenario: A multi-terminal device is accepted
- **WHEN** a request carries three doped regions and four ohmic contacts
- **THEN** `solve` returns the currents of all four at every bias

### Requirement: The axisymmetric form SHALL be an option, and a non-round device SHALL be refused
`form = "axisymmetric"` SHALL build the (r, z) mesh from an equal-area cylinder of the
uploaded geometry's cross-section. It SHALL be offered when the device's cross-section is
round to within a stated tolerance (the circumradius and inradius within 2 %), measured from
the uploaded geometry. A non-round device SHALL be refused for the axisymmetric form with
`ValueError` naming the measured ratio and the tolerance, and the message SHALL say that the
3-D form is available. The refusal SHALL be at upload, not after a Job starts.

#### Scenario: A hexagonal wire is refused as axisymmetric
- **WHEN** a request asks for the axisymmetric form on a hexagonal cross-section
- **THEN** the upload is refused, naming the circumradius/inradius ratio and the tolerance

#### Scenario: A round pillar is accepted as axisymmetric
- **WHEN** a request asks for the axisymmetric form on a circular cross-section
- **THEN** the request is accepted and the (r, z) mesh is built

#### Scenario: Roundness is measured per loop about the detected axis (task 2.6)
- **GIVEN** the uploaded surface (every part, through the solver's own split)
- **WHEN** it is sliced across each candidate axis (the eigenvectors of its area-weighted
  normal tensor and of its surface second moment, through its area-weighted centroid)
- **THEN** each closed loop of each slice gives a circumradius (its farthest point from the
  axis) and an inradius (the nearest point of its segments), the device's figure is the
  worst loop's ratio, and the axis is the candidate with the smallest such figure
- **AND** the limit is `mse_geometry.ROUNDNESS_TOLERANCE` (0.02), read by both the upload
  refusal and the solver, and a ratio above 1 + 0.02 is refused

#### Scenario: A faceted, tilted or offset cylinder is accepted
- **WHEN** the cylinder is a 24-sided prism (ratio 1/cos(π/24) = 1.0086), or is tilted and
  moved off the coordinate origin
- **THEN** it is accepted, measured about its own axis, not the coordinate z axis

#### Scenario: An elliptic cylinder straddles the limit
- **WHEN** the cross-section is an ellipse with a/b = 1.03
- **THEN** it is refused; at a/b = 1.015 it is accepted

#### Scenario: Every part is judged, loop by loop
- **WHEN** a round core sits inside a round tube
- **THEN** it is accepted (each loop is round on its own)
- **AND WHEN** a hexagonal part sits on the same axis beside a round wire
- **THEN** the upload is refused

### Requirement: The 3-D form SHALL be size-checked against the Job limit before it runs
Before building the 3-D mesh, the worker SHALL estimate the run's memory from the mesh it
would build — the node and edge counts of the actual geometry, at the requested edge lengths,
through the allocator's own array sizes (node coordinates, tet connectivity, one scalar per
node per unknown, the edge list and its couplings) — and SHALL refuse terminally, naming the
estimate and the Job's memory limit and pointing at the axisymmetric form when the device is
round, if the estimate exceeds that limit. The estimate SHALL NOT come from a table of typical
device sizes. The message SHALL name the estimated figure, the limit and how to proceed.

#### Scenario: A junction-resolving 3-D run is refused with both figures
- **WHEN** a 3-D request's estimated memory exceeds the Job's 16 GiB
- **THEN** the run is refused before meshing, naming the estimate, the limit, and the
  axisymmetric alternative when the device is round

#### Scenario: Two geometries of the same parts get different estimates
- **WHEN** two requests differ only in the uploaded geometry's size
- **THEN** their estimates differ, because each is priced from its own mesh's arrays


### Requirement: The mesh SHALL resolve the Debye length where carriers change, or the run SHALL be refused
Before solving, `solve` SHALL compute the extrinsic Debye length L_D = √(ε_s ε₀ k_BT/(q²N)) at
every doped node from its doping N, and SHALL refuse with `ValueError` (naming the region, the
worst L_D and the local edge) a mesh whose edge exceeds L_D/2 at any node within a stated
distance of a doping change. The refusal SHALL be the default; a coarse cross-check MAY pass
`allow_unresolved=True`, and its result SHALL then carry a caveat naming the unresolved regions.

#### Scenario: An unresolved junction is refused
- **WHEN** a 3-D mesh with a 20 nm junction edge is given 10¹⁸ cm⁻³ doping (L_D ≈ 4 nm)
- **THEN** `solve` raises `ValueError` naming the region and both lengths

### Requirement: The axisymmetric and coarse 3-D forms SHALL agree where both are resolved
For the p-i-n wire at a doping both forms resolve (design estimate ≤ 10¹⁶ cm⁻³), the
axisymmetric (r, z) form and the 3-D form SHALL give the same I-V.

#### Scenario: The two forms agree on a coarse p-i-n wire
- **WHEN** a small p-i-n hexagonal wire and its equal-area cylinder are solved at five forward
  biases
- **THEN** the currents agree within 5 % at every bias

#### Scenario: The cylinder's weight is the area
- **WHEN** a uniformly doped resistor cylinder of radius R is solved in the axisymmetric form
- **THEN** its current is the 1-D current density times πR² within 1 %

**[NOT MET ON THE 3-D PATH, 2026-11-10.]** The two scenarios above describe the axisymmetric
form, which meets them. The coarse 3-D tet form cannot yet produce a *biased* current at all:
any non-empty `biases` argument raises `EquilibriumNotReached`, because a bias solve runs the
stage-3 coupled DD solve and stage 3 does not converge on the tet mesh (see the change's
`2.7-feasibility.md` Finding 4 — it is a plateau, not a slow approach). Biased current has never
been produced on the 3-D path. This is an open gap, not a tolerance to relax, and it is tracked
as the refinement study in `tasks.md` 2.7. The 3-D path currently delivers the *equilibrium*
agreement in the requirement below.

### Requirement: The two forms SHALL agree on the built-in voltage and the depletion width at equilibrium
At equilibrium at a doping both forms resolve, the axisymmetric (r, z) form and the coarse 3-D
tet form SHALL agree on the built-in voltage AND on the depletion width. The built-in voltage
alone is insufficient: it is fixed by the contact boundary condition and the intrinsic carrier
concentration, so it is unchanged by a large error in the permittivity and proves only that both
forms are wired to the same junction. The depletion width is the quantity that comes out of the
Poisson solve.

A width comparison SHALL be made only on a mesh that resolves the depletion region; at coarser
tet edges the 3-D width is set by the mesher's sub-slab structure rather than by the physics.

#### Scenario: The forms agree on the built-in voltage
- **WHEN** the same abrupt junction is solved to equilibrium by both forms at ≤ 10¹⁶ cm⁻³
- **THEN** the built-in voltages agree within 3 %, and each is within 1 % of the analytic value

#### Scenario: The forms agree on the depletion width
- **WHEN** the same junction is solved to equilibrium by both forms at a tet edge of 1e-7 m or
  finer, so the depletion region is resolved
- **THEN** the 10-90 % depletion widths agree within 5 %

#### Scenario: The width test is sensitive to doping, not to permittivity
- **WHEN** the acceptor or donor doping in the 3-D solve is doubled
- **THEN** the width test fails; a 5 % change in permittivity is NOT claimed to fail it, because
  the permittivity signal is smaller than the mesh discretisation error at any mesh that runs in
  a unit test, and permittivity is instead covered by the axisymmetric width test

### Requirement: A voltage pulse SHALL give the carrier arrival profile at the dot
`drift_diffusion.transient(..., waveform, dt, t_end)` SHALL step DEVSIM's transient solve from
a solved bias through a voltage waveform. It SHALL return g(t), the rate at which electron-hole
pairs recombine radiatively inside the dot's region, and the contact currents. The result SHALL
conserve charge.

#### Scenario: Charge balance in a transient
- **WHEN** a forward voltage step is applied
- **THEN** the time-integrated contact current equals the change in stored charge plus the
  integrated recombination within 1 %

#### Scenario: The junction capacitance
- **WHEN** a small reverse-bias step ΔV is applied
- **THEN** the change in stored charge over ΔV matches ε_s·A/W at that bias within 5 %

### Requirement: The drift-diffusion bench SHALL print its checks and exit nonzero on a failure
`scripts/dd_bench.py` SHALL run every check above (tier 1 for the 1-D-like and small cases,
tier 2 or 3 for the coarse 3-D wire), print the computed value, the reference, the tolerance
and the unknown count per check, and the peak RSS, and exit 1 when any check fails. It SHALL
record DEVSIM's version.

#### Scenario: A central-difference current fails the bench
- **WHEN** the Scharfetter-Gummel edge current is replaced by a central difference of n and ψ
- **THEN** the built-in potential or ideal-diode check fails, or Newton fails, and the bench
  exits 1

#### Scenario: A dropped 2πr weight fails the bench
- **WHEN** the axisymmetric form omits the 2πr weight
- **THEN** the cylinder-area check fails and the bench exits 1

### Requirement: A 3-D tetrahedral form SHALL run and be priced before it runs
`solve_layered_dd_3d(..., edge_m, max_tets)` SHALL build a tetrahedral mesh of a layer stack,
load it into DEVSIM as a Gmsh 2.2 file, and run the SAME staged drift-diffusion physics as the
axisymmetric form. DEVSIM 2.11.2 has no 3-D mesh-create API, so the Gmsh file route is the only
one; the array of contacts must come from surface physical groups written into that file, since
the shipped `write_gmsh22` emits only 3-D tet groups. The mesh SHALL be written in centimetres,
the unit `simple_physics` is validated in. The run SHALL be refused against the Job memory limit
BEFORE the device is built, through the same estimate the axisymmetric path uses, so a refusal
means the same thing whichever form is asking. It SHALL return the same keys as the
axisymmetric DD solver so an agreement test can compare the two through one interface.

#### Scenario: A 3-D device agrees with the axisymmetric one on the built-in voltage
- **WHEN** the same abrupt junction is solved by both forms at a doping where both are resolved
- **THEN** the measured built-in voltage agrees with the analytic value and with the other form

#### Scenario: An oversize 3-D mesh is refused before any solve
- **WHEN** the tetrahedral mesh would exceed the Job memory limit
- **THEN** the call raises before any device is created, naming the estimate and the limit

#### Scenario: A face shared by two tets does not become a contact
- **WHEN** boundary faces are collected for contact groups
- **THEN** a face with two owning tets is treated as interior and gets no group
