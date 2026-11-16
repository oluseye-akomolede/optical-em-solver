"""Task 2.3: axisymmetric (r, z) drift-diffusion through DEVSIM.

A cylindrical device -- a nanowire, a pillar -- has no azimuthal dependence, so
we solve on one radial half-plane (r >= 0, z) and weight every control volume
and every edge by the 2*pi*r the full solid has there. That is DEVSIM's
"2D cylindrical" mode, and it is switched on in a specific order that is easy
to get wrong (measured 2026-11-09, DEVSIM 2.11.2):

  * ``set_parameter(CoordinateSystem="cylindrical")`` is ACCEPTED AND DOES
    NOTHING. Planar and cylindrical ``EdgeCouple`` come out identical
    (ratio exactly 1.0). It is not the switch.
  * The switch is a COMMAND: ``devsim.cylindrical_node_volume(device, region)``
    (and ``cylindrical_edge_couple``, ``cylindrical_surface_area``). It
    installs ``CylindricalNodeVolume`` and friends. It is not an expression
    and ``node_model(equation="cylindrical_node_volume")`` fails.
  * The command REFUSES a thin 3-D slab: it needs a genuine 2-D mesh, built
    with ``create_2d_mesh`` + ``add_2d_mesh_line(dir=...)`` +
    ``add_2d_region``. There is no ``add_2d_mesh_triangle``; the 2-D path is a
    structured axis-aligned grid.
  * Before the command, ``raxis_variable`` ("x" or "y") and ``raxis_zero`` (a
    float) must both be set, or it raises.

So this module carries its own structured (r, z) grid builder; the Gmsh writer
in ``mse_devsim_mesh`` is for the 3-D form.

WHAT IS CHECKED, AND WHY (spec: drift-diffusion/spec.md)
The point of solving a junction is that its behaviour is known independently
of us. A solver that gets the SHAPE right but the SCALE wrong -- a missing 2*pi
r, a permittivity off by eps0 -- still produces a plausible-looking band
diagram. The checks below are analytic results, so agreement is evidence and
disagreement is a bug.

  V_bi   = kT/q * ln(N_A N_D / n_i^2)                       (1 % in the spec)
  W      = sqrt(2 eps_s eps0 (V_bi + V_R) (N_A + N_D) / (q N_A N_D))  (10 %)

COMPARING ``W`` LIKE WITH LIKE
``analytic_depletion_width`` is the FULL space-charge width. The solve measures
the width between the 10 % and 90 % potential crossings, which for a triangular
potential is ``(2*sqrt(2) - 2)/2 = 0.447`` of it -- a fixed factor, not a
tolerance. Comparing the measured 10-90 % number straight against ``W``
under-reports by 2.2x and looks like a broken solver. Measured 2026-11-09:
DEVSIM's own reference diode reads 28.6 nm on this metric at 1e18 where the
correct comparison is 22.2 nm, so the artefact is in the metric, not the solve.
Use ``TEN_NINETY_OVER_FULL`` to convert, and know that the conversion only holds
while the charge is depletion-limited: a junction far enough from the contacts
to be Debye-screened is set by L_D instead (see tasks.md 2.3).

No value is read from memory: material parameters come from ``mse_materials``,
and a parameter that library records as a GAP is refused by name rather than
substituted (the spec's own rule, and task 2.3's "don't substitute a value").
"""

import math

__all__ = [
    "Q", "KB", "EPS0", "T0",
    "Grid", "build_grid",
    "MissingParameter", "require_cited_parameter",
    "solve_abrupt_junction", "analytic_v_bi", "analytic_depletion_width",
    "TEN_NINETY_OVER_FULL",
    "TooBigForJob", "estimate_job_bytes", "require_job_memory",
]

# Physical constants. These are definitions, not material data: exact by SI
# definition (q, EPS0) or measured to far more digits than any material
# parameter here (kB, as the adopted 2019 value).
Q = 1.602176634e-19       # C, exact (SI definition)
KB = 1.380649e-23         # J/K, exact (SI definition)
EPS0 = 8.8541878128e-12   # F/m, CODATA
# The same constant in F/cm, which is what DEVSIM's simple_physics is written
# in. EPS0 / 100: F/m -> F/cm is one factor of 100 (length), not 10^4.
EPS0_CM = EPS0 / 100.0
CM3_TO_M3 = 1.0e6         # cm^-3 -> m^-3
T0 = 300.0                # K, the temperature the library's values are cited at


class MissingParameter(ValueError):
    """A solve needs a material parameter the library records as a gap."""


def require_cited_parameter(material, name, library=None):
    """Refuse if ``material.name`` is a gap. Cite-or-refuse, nothing more.

    The rule from the spec is that an uncited number SHALL NOT ship, and task
    2.3 says to refuse rather than substitute. A parameter the library left as
    NaN (because no source gave it) stops the solve, naming the parameter and
    the material.

    It RETURNS the cited value, so a solver can use it. That return is the
    2.11 fix (reviewer finding 1, 2026-11-10): this function used to return
    None, so every caller cleared the gate and went on using its own
    ``eps_s`` argument -- a hand-typed number passed the check and the cited
    number never reached the solve. Use :func:`material_value`, which calls
    this and additionally records whether the number came from the library or
    from an explicit override.
    """
    if library is None:
        import mse_materials
        library = mse_materials
    params = library.get(material).params
    c = params.get(name)
    if c is None:
        raise MissingParameter(
            f"{material}.{name} is not a parameter in the library; "
            f"known parameters are {sorted(params)}")
    if not c.verified or c.value != c.value:  # NaN is the gap marker
        raise MissingParameter(
            f"{material}.{name} has no cited value (basis: {c.basis!r}). "
            f"Refusing rather than substituting a number from memory.")
    return c.value


def material_value(material, name, override=None, library=None):
    """The number a solve must USE, and where it came from.

    Returns ``(value, source)``. This is the 2.11 fix: the old gate checked
    that a cited value EXISTED and returned None, so every solver went on using
    its own ``eps_s`` argument -- a hand-typed number cleared the gate and the
    cited one never reached the solve. Now the library is the source, and a
    caller may override only by saying so here, where it is recorded.

    ``source`` is ``"library: <material>.<name>"`` or
    ``"override(<material>.<name>)"``. The override is allowed -- a per-part
    material really can differ from the library's bulk value under process
    variation -- but it is never silent: ``resolve()`` and the solve manifest
    surface this string, so a reader can see which numbers were ours.
    """
    cited = require_cited_parameter(material, name, library)  # raises on a gap
    if override is None:
        return cited, f"library: {material}.{name}"
    try:
        override = float(override)
    except (TypeError, ValueError):
        raise MissingParameter(
            f"{material}.{name} override {override!r} is not a number") from None
    if override != override:
        raise MissingParameter(
            f"{material}.{name} override is NaN; that is not an override")
    return override, f"override({material}.{name})"


def debye_length_m(doping_cm3, eps_s, temperature=T0):
    """Extrinsic Debye length in METRES, from the local doping magnitude.

    L_D = sqrt(eps_s * eps_0 * k_B T / (q^2 * N)), N in m^-3.

    This is the spec's own definition (electrical-simulation spec.md,
    "The mesh SHALL resolve the Debye length where carriers change"). N is
    taken as |net doping|: at a junction the relevant screening length is set
    by the majority-carrier density of the region being screened, and using
    the magnitude keeps the formula valid on both sides of the step.
    """
    n_m3 = abs(float(doping_cm3)) * CM3_TO_M3
    if n_m3 <= 0.0:
        # Undoped material has an unbounded Debye length; the mesh can never
        # "resolve" it, and returning 0 would make the gate refuse every
        # intrinsic region. Report infinity and let the caller decide.
        return float("inf")
    return math.sqrt(float(eps_s) * EPS0 * KB * float(temperature) / (Q * Q * n_m3))


class DebyeUnresolved(ValueError):
    """The mesh is too coarse to resolve the Debye length at a doping change.

    A ValueError (the spec asks for exactly that) and separate from
    ``MissingParameter`` so a caller can tell "the mesh is wrong" from "the
    library has a gap".
    """


def require_debye_resolved(grid, net_doping_cm3, eps_s, *,
                          junction_z=0.0, window=None, temperature=T0):
    """Refuse a mesh whose edge exceeds L_D/2 near a doping change.

    The spec's rule (spec.md, Debye requirement), implemented literally:

      * L_D is computed at every doped node from that node's own doping;
      * only nodes within ``window`` of a doping change are held to it --
        elsewhere the potential is flat and under-resolution costs nothing;
      * the refusal names the region, the WORST (smallest) L_D and the local
        edge, because those three are what a caller needs to re-mesh.

    ``window`` defaults to 10 L_D at the heaviest doping in the device: the
    transition is a few L_D wide either side, so 10 is generous and keeps the
    gate from passing a mesh that is only fine far from the junction.

    Returns the diagnosis dict on success so a caller can record it; raises
    ``DebyeUnresolved`` on failure. There is deliberately no
    ``allow_unresolved`` flag here -- the caveat-carrying escape lives in the
    solver that owns the result, so an unresolved run cannot be made to look
    like a resolved one by passing a keyword at the lowest layer.
    """
    import numpy as np
    z = np.asarray(grid.z_lines, dtype=float)
    if z.size < 2:
        raise ValueError("a grid needs at least two z lines to have an edge")
    edges = np.diff(z)

    # One doping value per node, from the caller's own profile function so the
    # gate and the solve cannot disagree about where the junction is.
    doping = np.array([float(net_doping_cm3(float(zz))) for zz in z])

    # A doping change is a node where the profile steps: compare each node to
    # its neighbour and treat a sign flip, or any jump of more than 2x, as a
    # change. Sampling the profile is cheaper and more honest than asking the
    # caller to also supply the junction list.
    changed = np.zeros_like(z, dtype=bool)
    if z.size > 1:
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.abs(doping[1:]) / np.abs(doping[:-1])
        jump = (np.sign(doping[1:]) != np.sign(doping[:-1])) | (ratio > 2.0) \
            | (ratio < 0.5)
        changed[1:] |= jump
        changed[:-1] |= jump

    # Worst-case L_D in the device sets the default window.
    finite = np.abs(doping[np.isfinite(doping) & (doping != 0.0)])
    if finite.size == 0:
        return {"worst_ld_m": float("inf"), "worst_edge_m": 0.0,
                "nodes_checked": 0, "window_m": float("inf")}
    heaviest = float(finite.max())
    worst_ld = debye_length_m(heaviest, eps_s, temperature)
    if window is None:
        window = 10.0 * worst_ld

    # A node is "near a doping change" if any change is within the window.
    near = np.zeros_like(z, dtype=bool)
    for zc in z[changed]:
        near |= np.abs(z - zc) <= window
    if not near.any():
        return {"worst_ld_m": worst_ld, "worst_edge_m": 0.0,
                "nodes_checked": 0, "window_m": float(window)}

    # Local edge for each node: the larger of the two edges touching it, so a
    # node with one coarse neighbour is judged by that coarse neighbour.
    local_edge = np.zeros_like(z)
    local_edge[:-1] = np.maximum(local_edge[:-1], edges)
    local_edge[1:] = np.maximum(local_edge[1:], edges)

    ld_at_node = np.array([debye_length_m(d, eps_s, temperature) for d in doping])
    # Refuse where the edge exceeds HALF the local Debye length, as specified.
    with np.errstate(invalid="ignore"):
        bad = near & np.isfinite(ld_at_node) & (local_edge > 0.5 * ld_at_node)
    if not bad.any():
        return {"worst_ld_m": float(ld_at_node[near].min()),
                "worst_edge_m": float(local_edge[near].max()),
                "nodes_checked": int(near.sum()), "window_m": float(window)}

    # Name the region, the worst L_D and the local edge -- all three.
    idx_bad = np.flatnonzero(bad)
    i_worst = idx_bad[int(np.argmin(ld_at_node[idx_bad]))]
    raise DebyeUnresolved(
        "mesh does not resolve the Debye length near the doping change in "
        "region 'silicon': worst L_D = {ld:.3e} m at z = {z:.3e} m, local "
        "edge = {edge:.3e} m, which exceeds L_D/2 = {half:.3e} m. "
        "{n} node(s) within {win:.3e} m of a change are unresolved; the "
        "finest edge there must be <= {need:.3e} m."
        .format(ld=float(ld_at_node[i_worst]), z=float(z[i_worst]),
                edge=float(local_edge[i_worst]),
                half=0.5 * float(ld_at_node[i_worst]),
                n=int(bad.sum()), win=float(window),
                need=0.5 * float(ld_at_node[i_worst])))


class Grid:
    """A structured (r, z) grid, refined about the junction.

    ``nodes`` are (r, z) pairs; the solver builds the same lines as DEVSIM
    mesh lines, so the node count and ordering here must match DEVSIM's.
    """

    def __init__(self, r_lines, z_lines):
        self.r_lines = list(r_lines)
        self.z_lines = list(z_lines)
        self.n_r = len(self.r_lines)
        self.n_z = len(self.z_lines)

    @property
    def n_nodes(self):
        return self.n_r * self.n_z

    def node(self, i_r, i_z):
        return (self.r_lines[i_r], self.z_lines[i_z])

    def describe(self):
        return (f"r: {self.n_r} lines {self.r_lines[0]:.3e}..{self.r_lines[-1]:.3e} m, "
                f"z: {self.n_z} lines {self.z_lines[0]:.3e}..{self.z_lines[-1]:.3e} m, "
                f"{self.n_nodes} nodes")


def build_grid(junction_z, r_max, z_min, z_max, *, n_r=12, n_z=40,
               refine=None, refine_halfwidth=None):
    """Structured (r, z) grid with optional refinement about ``junction_z``.

    Refinement is geometric about the junction: ``refine`` is the first-cell
    spacing there and ``refine_halfwidth`` how far it is graded back to the
    uniform spacing. This gives a fine band where the depletion edge lives,
    which is what makes the width measurable, without refining the contacts.
    """
    import numpy as np
    if refine is None:
        z_lines = np.linspace(z_min, z_max, n_z)
    else:
        if refine_halfwidth is None:
            raise ValueError("refine_halfwidth is required when refine is given")
        # A scalar junction is a one-junction device; a SEQUENCE refines about
        # each. The multi-terminal check (task 2.4) has two junctions, and
        # refining only the first left the second at the coarse spacing --
        # the Debye gate refused it at z = 9.57e-7 m with a 20 nm edge against
        # a 2.04 nm requirement (measured 2026-11-09). Scalar callers are
        # unchanged.
        centres = ([float(junction_z)]
                   if np.isscalar(junction_z) else [float(c) for c in junction_z])
        if not centres:
            raise ValueError("build_grid needs at least one refinement centre")
        centres = sorted(centres)
        for a, b in zip(centres, centres[1:]):
            if b - a < 2.0 * refine_halfwidth:
                raise ValueError(
                    "refinement bands about %.3e and %.3e overlap "
                    "(halfwidth %.3e); merge them or narrow refine_halfwidth"
                    % (a, b, refine_halfwidth))
        # lo/hi get a FIXED NUMBER of points in the code this replaced
        # (max(2, n_z // 3) each). That makes their spacing scale with the
        # domain, so the same physical region is resolved differently on a
        # wide box than a narrow one -- a silent, domain-dependent grid.
        # Measured 2026-11-09: it moved the measured width by 3.8% between a
        # +-0.3um and a +-2um domain and looked like the width still tracking
        # the box. Size the far regions by SPACING instead: n points chosen so
        # their spacing matches the box's, and never coarser than the domain's
        # own (z_max - z_min) / (n_z - 1).
        coarse = (z_max - z_min) / max(1, n_z - 1)
        # Build the domain as alternating coarse stretches and fine bands, so
        # the far regions keep the domain's own spacing and each junction gets
        # the same geometric refinement.
        pieces = []
        cursor = z_min
        for c in centres:
            lo_edge = c - refine_halfwidth
            hi_edge = c + refine_halfwidth
            if lo_edge > cursor:
                span = lo_edge - cursor
                n = max(2, int(math.ceil(span / coarse)) + 1)
                pieces.append(np.linspace(cursor, lo_edge, n, endpoint=False))
            pieces.append(np.linspace(lo_edge, hi_edge,
                                      int(refine_halfwidth * 2 / refine) + 1))
            cursor = hi_edge
        if cursor < z_max:
            span = z_max - cursor
            n = max(2, int(math.ceil(span / coarse)) + 1)
            pieces.append(np.linspace(cursor, z_max, n))
        z_lines = np.unique(np.concatenate(pieces))
    r_lines = np.linspace(0.0, r_max, n_r)
    return Grid(r_lines.tolist(), z_lines.tolist())


def analytic_v_bi(n_a, n_d, n_i, temperature=T0):
    """kT/q * ln(N_A N_D / n_i^2), the abrupt-junction built-in voltage."""
    return KB * temperature / Q * math.log(n_a * n_d / (n_i ** 2))


def analytic_depletion_width(eps_s, n_a, n_d, v_bi, v_r=0.0):
    """sqrt(2 eps (V_bi + V_R) (N_A + N_D) / (q N_A N_D)), per metre.

    This is the FULL space-charge width. To compare it with the 10-90 %
    potential width the solvers measure, multiply by ``TEN_NINETY_OVER_FULL``
    (see the module docstring and tasks.md 2.3).

    N_A and N_D are DENSITIES IN cm^-3 (the library's and DEVSIM's unit), but
    EPS0 and Q here are SI, so the width only comes out in metres if the
    densities are converted to m^-3 first. Measured 2026-11-09: without the
    1e6 the analytic width is sqrt(1e6)=1e3 too small, and the solve then
    "disagrees" with theory by 100% while actually being right.
    """
    n_a = float(n_a) * CM3_TO_M3
    n_d = float(n_d) * CM3_TO_M3
    return math.sqrt(
        2.0 * eps_s * EPS0 * (v_bi + v_r) * (n_a + n_d) / (Q * n_a * n_d))


# 10-90 % width as a FRACTION of the full depletion width, for the profile
# shape this solver actually produces. The two textbook shapes differ enough
# that using the wrong one manufactures a 29 % "error" that is pure geometry:
#
#   triangular (full depletion, linear field, quadratic potential):
#       phi ~ z^2, so the 10 % and 90 % crossings sit at sqrt(0.1) and
#       sqrt(0.9) of the half-width -> (sqrt(1.8)-sqrt(0.2))/2 = 0.4472.
#   linear (flat-band / constant field): phi ~ z, crossings at 0.1 and 0.9
#       of the half-width -> (sqrt(0.8)-sqrt(0.1)) = 0.5782.
#
# Measured 2026-11-09 against the solved DEVSIM profile at N_A = N_D = 1e17,
# V_bi = 0.8345 V. THE SHIPPED PATH IS THE 11.7 ROW. That run used the cited
# eps_s = 11.7 (2.4 fixed the solver to read it rather than DEVSIM's default
# 11.1) and measures W_10-90 / W_full = 0.5974: 3.3 % from the linear 0.5782,
# and far from the triangular 0.4472.
#
# A second run at the OLD, uncited eps_s = 11.1 measured 0.5817, which is
# 0.6 % from 0.5782. That number is not what this solver produces any more
# and must not be quoted as its agreement: quoting it overstated the fit by
# a factor of five (0.6 % against the real 3.3 %). It is kept only because it
# identifies which run was secretly at 11.1, which is how 2.4's eps_s bug was
# found.
#
# Either way the linear shape stands against the triangular constant: with
# the triangular constant this test reported a stable, refinement-independent
# ~30 % error and looked like a physics defect. It was the shape assumption.
# Pinned to the measured shape.
TEN_NINETY_OVER_FULL = math.sqrt(0.8) - math.sqrt(0.1)


# ------------------------------------------------------- the size check (2.5)

class TooBigForJob(MemoryError):
    """A run whose estimated peak memory exceeds the solver Job's limit.

    A ``MemoryError`` so a caller that catches neither is still a crash rather
    than a silently-huge allocation, and carries the figures the message needs
    without the caller re-deriving them.
    """

    def __init__(self, estimate_bytes, limit_bytes, nodes, edges, hint=""):
        self.estimate_bytes = int(estimate_bytes)
        self.limit_bytes = int(limit_bytes)
        self.nodes = int(nodes)
        self.edges = int(edges)
        msg = ("this run would need about %.2f GiB, over the solver Job's "
               "%.2f GiB limit (%.0f nodes, %.0f edges; estimated before any "
               "solve)" % (self.estimate_bytes / GIB, self.limit_bytes / GIB,
                           self.nodes, self.edges))
        if hint:
            msg += ". " + hint
        super().__init__(msg)


class TooManyNodesForFactor(MemoryError):
    """A 3-D run larger than the biggest tet mesh measured to factor.

    A ``MemoryError`` for the same reason as :class:`TooBigForJob`: a caller
    that catches neither crashes rather than spending minutes failing inside
    ``umfpack_di_numeric``. The message says what the user can DO, because this
    refusal is actionable (coarsen the mesh) where a memory refusal is not.
    """

    def __init__(self, nodes, limit_nodes):
        self.nodes = int(nodes)
        self.limit_nodes = int(limit_nodes)
        super().__init__(
            "this 3-D run has %.0f mesh nodes, over the %.0f-node ceiling "
            "measured to factor (UMFPACK's direct solver failed between "
            "18,957 and 32,430 nodes). Coarsen the mesh -- increase edge_m -- "
            "so the junction is still resolved with fewer nodes. This is a "
            "solver-size limit, not a memory limit: raising the Job's memory "
            "will not help. Estimated before any solve."
            % (self.nodes, self.limit_nodes))


GIB = float(1024 ** 3)

#: Largest tet-mesh NODE COUNT measured to factor in UMFPACK.
#:
#: This is a ceiling on the direct solver, not on memory. Measured 2026-11-10 in
#: a tier-3 Job and reproduced locally in a 13 GiB container: the coupled
#: drift-diffusion solve at edge 5.0e-8 (32,430 nodes, 181,319 tets) raises
#: ``umfpack numeric failed`` after 360 s at PEAK RSS 3,079 MB -- it dies using
#: 3 GB of a 13 GB allowance, so no ``resources.limits.memory`` value admits it.
#: The largest size that factored is edge 6.0e-8 at 18,957 nodes / 104k tets
#: (stage 1 only). THE TRUE CEILING LIES SOMEWHERE BETWEEN those two sizes
#: (18,957 < N < 32,430); this constant takes the known-good end, so it refuses
#: some meshes that might have solved. That is the intended direction: a refusal
#: the user can act on beats a six-minute failure inside the numeric factor.
#:
#: Memory pricing cannot substitute for this. ``estimate_tet_job_bytes`` prices
#: the 32,430-node mesh at 5.45 GiB, UNDER the 14 GiB gate, while the failing run
#: peaked at 3.08 GB -- a mesh can be too ill-conditioned to factor while looking
#: cheap on every memory metric. The longer-term fixes (UMFPACK's 64-bit ``dl``
#: variant, a coarser junction mesh) stay open in task 2.13.
TET_MAX_FACTORABLE_NODES = 18957

#: Jacobian nonzeros per node. The coupled system solves three unknowns per
#: node (potential, electrons, holes), and a node couples to itself and to its
#: up-to-six structured neighbours, but the matrix is stored as a direct
#: (sparse) factorisation, not just the matrix: the LU fill on a 2-D
#: five-point stencil grows to roughly ``O(nodes * sqrt(nodes))`` entries.
#:
#: This number and the ``sqrt`` fill law in the estimate are calibrated
#: TOGETHER, as ONE conservative bound -- not as two independent physical
#: claims. Read on its own, neither is a measured fact: the three points in
#: tests/test_dd_size.py are 2-D axisymmetric grids whose peak RSS grows with a
#: measured slope of 0.83, while the estimator's slope is 1.5, so the 2-D bound
#: is pessimistic and the test prints how far apart they are rather than tuning
#: the factor to close the gap.
#:
#: This gate prices 2-D AXISYMMETRIC grids only. It priced 3-D until
#: 2026-11-10, when a tier-3 calibration Job measured the 3-D tet path at
#: ~2x this estimate plus a constant -- i.e. the opposite of the pessimism
#: claimed here, which would have admitted runs that then died. 3-D now has its
#: own calibrated path (TET_ESTIMATE_FACTOR, applied in
#: estimate_tet_job_bytes); do not read this constant as covering tet solves.
#: The axisymmetric slope in this function has NOT been measured the same way.
JACOBIAN_NONZEROS_PER_NODE = 40.0

#: bytes per sparse entry, int32 column index + float64 value, and int32 row
#: pointer per row. A direct factorisation is what DEVSIM's ``solver_type=
#: "direct"`` builds, which is what every solve in this module uses.
BYTES_PER_NONZERO = 12.0

#: bytes per node for the physics and solution arrays that live at peak.
#: DEVSIM keeps, per node: the solution (3 doubles), the node models it
#: evaluates (NetDoping, Electrons, Holes, Potential, and the contact models),
#: and the residual. Twelve doubles a node is a deliberate over-count of the
#: eight the reference models define, because a model added later should not
#: silently make the estimate optimistic.
BYTES_PER_NODE = 12.0 * 8.0

#: bytes per edge for the per-edge models. The edge models carry the current
#: densities, mobilities, fields and the cylindrical coupling; eight doubles an
#: edge is the same deliberate over-count.
BYTES_PER_EDGE = 8.0 * 8.0

#: Fixed process overhead above the per-node/edge terms, in bytes. MEASURED,
#: not modelled: the three tier-3 calibration points put ``peak - 2*raw`` at
#: 2.275e8 and 2.198e8 B for the two LARGEST sizes (4307 and 12157 nodes),
#: which agree to 3.5 % -- the signature of a genuine constant. NOTE: only the
#: 12157-node point is a CONVERGED run; the 4307-node point did not converge at
#: stage 3 (see tasks.md, task 3). Its residual is still a real high-water mark,
#: but this constant rests on one converged and one non-converged point. The
#: third point (1136 nodes) gives 8.56e7 B, lower because the interpreter
#: baseline is not fully amortised; using the larger figure over-prices that
#: size, which is the safe direction for a refusal gate.
TET_FIXED_OVERHEAD_BYTES = 2.20e8

#: Slope of peak RSS against the raw structured-grid estimate for a 3-D tet
#: solve. MEASURED at >=3 sizes (task 2.7 calibration Job, 2026-11-10, image
#: 7dbd3b4): ratios of 6.518 / 3.650 / 2.338 at 1136 / 4307 / 12157 nodes.
#: Those ratios fall with size, so the small-size figure is fixed overhead, not
#: a pricing law; fitted with the overhead held at TET_FIXED_OVERHEAD_BYTES, the
#: two largest points sit at 2.0x to within 1.5 % (again, only the largest of
#: those is a converged run).
#:
#: That the estimate UNDER-prices 3-D by ~2x is the opposite of the pessimism
#: this gate was originally built on, and is why the factor is applied only on
#: the tet path. ``estimate_job_bytes`` (axisymmetric) keeps its uncalibrated
#: 1.0 slope until 2-D RSS is measured the same way -- see the note there.
TET_ESTIMATE_FACTOR = 2.0


def estimate_job_bytes(grid, *, regions=1, contacts=2):
    """Peak bytes a coupled drift-diffusion solve on ``grid`` would hold.

    Derived from the mesh the solve WOULD build, never from a solve: this is
    called before anything is allocated, so the whole point is that it can
    refuse a run too big to attempt. ``Grid.n_nodes`` is the same count
    ``_build_mesh`` hands DEVSIM (the docstring there requires the ordering to
    match DEVSIM's), so the node figure is not a guess.

    A structured (r, z) tensor-product mesh has ``n_r * n_z`` nodes and
    ``(n_r-1)*n_z + n_r*(n_z-1)`` edges: each of the ``n_z`` rows is a path of
    ``n_r`` nodes, and each of the ``n_r`` columns a path of ``n_z``.

    ``regions`` and ``contacts`` are how many of each the device declares; each
    contact adds the Dirichlet row pinned in the matrix and its contact model
    arrays. They default to the two-terminal diode this module builds.

    The estimate is LINEAR in node and edge count apart from the factorisation
    fill, which is ``O(nodes * sqrt(nodes))``. It is therefore a model of the
    geometry, not a constant: two devices of different sizes give different
    estimates, which is what tests/test_dd_size.py's two-geometry test proves.
    """
    n_r, n_z = grid.n_r, grid.n_z
    nodes = n_r * n_z
    edges = (n_r - 1) * n_z + n_r * (n_z - 1)
    # Sparse matrix: the matrix itself scales with the graph, the direct
    # factorisation with its fill. Both are counted, the fill at the 2-D
    # square-root law.
    nonzeros = JACOBIAN_NONZEROS_PER_NODE * nodes * max(1.0, math.sqrt(nodes))
    total = 0.0
    total += nonzeros * BYTES_PER_NONZERO
    total += nodes * BYTES_PER_NODE
    total += edges * BYTES_PER_EDGE
    # Contact rows: a pinned Dirichlet row per contact, negligible per node but
    # counted so the number has every term the solver allocates.
    total += contacts * nodes * 8.0
    return int(total)


def require_job_memory(grid, *, limit_bytes=None, regions=1, contacts=2,
                       roundness_ratio=None):
    """Refuse, before any solve, a run that would not fit the solver Job.

    Returns the estimate in bytes when the run is admissible, so a caller that
    wants to log it does not recompute it. Raises :class:`TooBigForJob`
    otherwise.

    ``limit_bytes`` defaults to ``mse_common.DEFAULT_JOB_MEMORY_BYTES``, the
    same number the app builds the Job with. Read from there rather than
    restated: an estimate checked against a limit the Job does not actually
    have is worse than no check.

    ``roundness_ratio`` is ``circumradius / inradius`` (``mse_geometry``'s
    measure): at or below ``ROUNDNESS_TOLERANCE`` the device is round, and the
    message names the axisymmetric form as the way to solve it, because that
    form's grid is ONE-DIMENSIONAL and lands many orders of magnitude below
    this limit. Passing ``None`` omits the hint -- the caller measures
    roundness, this function does not re-derive it.
    """
    if limit_bytes is None:
        from mse_common import DEFAULT_JOB_MEMORY_BYTES
        limit_bytes = DEFAULT_JOB_MEMORY_BYTES
    estimate = estimate_job_bytes(grid, regions=regions, contacts=contacts)
    if estimate <= limit_bytes:
        return estimate
    hint = ""
    if roundness_ratio is not None:
        from mse_geometry import ROUNDNESS_TOLERANCE
        # ROUNDNESS_TOLERANCE is a RELATIVE spread (0.02 = within 2 %), while
        # roundness_ratio is circumradius/inradius, whose round value is 1.0.
        # Comparing the ratio straight against 0.02 would call every real
        # device non-round, so the tolerance widens 1.0 rather than bounding it.
        if roundness_ratio <= 1.0 + ROUNDNESS_TOLERANCE:
            hint = ("This device is round (circumradius/inradius %.5f, within the "
                    "%.0f per cent tolerance), so the axisymmetric (r, z) form "
                    "solves it on a one-dimensional grid instead of this "
                    "two-dimensional one."
                    % (roundness_ratio, ROUNDNESS_TOLERANCE * 100.0))
    raise TooBigForJob(estimate, limit_bytes, grid.n_nodes,
                       (grid.n_r - 1) * grid.n_z + grid.n_r * (grid.n_z - 1),
                       hint=hint)



# ------------------------------------------------------------ the DEVSIM solve

def _set_net_doping(devsim, net_doping_cm3, *, region="silicon", coord="y"):
    """Write the doping profile onto the solved nodes, by ``coord``.

    ``net_doping_cm3`` takes a position in METRES (the module's public unit),
    but the mesh is CM (see _build_mesh), so the coordinate read back here
    must be converted before the profile is evaluated. Getting this wrong
    silently moves the junction: with a profile of ``z > 0`` the sign is the
    same in either unit (both cross at 0), which is why it looked fine, but
    any junction at a nonzero position would land in the wrong place.

    ``region`` and ``coord`` are parameters because the 3-D gmsh form stacks
    its layers along z, not the axisymmetric mesh's y (task 2.7). The default
    reproduces the axisymmetric call exactly.
    """
    import numpy as np
    n = np.asarray(devsim.get_node_model_values(
        device="dd", region=region, name=coord))
    z_m = n * 1.0e-2
    doping = np.array([float(net_doping_cm3(zz)) for zz in z_m])
    devsim.node_model(device="dd", region=region, name="NetDoping",
                      equation="0")
    devsim.set_node_values(device="dd", region=region, name="NetDoping",
                           init_from=coord, values=doping.tolist())


def _build_mesh(grid, *, mesh_name, material="Si", contact_names=("top", "bottom"),
                extra_contacts=()):
    """Mesh + regions + contacts + the 2*pi*r weighting. No physics.

    THE MESH IS BUILT IN CENTIMETRES. ``grid`` is SI (metres) because that is
    the module's public unit, but DEVSIM's validated silicon model
    (``simple_physics``) is a cm-unit model: eps_0 = 8.854e-14 F/cm, doping
    in cm^-3, and ``diode_common.py`` -- DEVSIM's own working reference --
    builds its mesh at positions like 0.5e-5, i.e. cm. Mixing a metre mesh
    with that model is what broke the junction: every charge came out 100x
    weak, the Debye length 10x too long (1.29 um against a 1 um domain), and
    Poisson relaxed on a dead-straight line instead of depleting. V_bi still
    looked perfect, because a ramp's endpoint difference is also V_bi -- the
    defect was invisible in the one number the first tests checked.
    Measured 2026-11-09; see tasks.md 2.3.
    """
    import devsim
    import numpy as np

    M_TO_CM = 100.0
    devsim.create_2d_mesh(mesh=mesh_name)
    r = np.asarray(grid.r_lines) * M_TO_CM
    z = np.asarray(grid.z_lines) * M_TO_CM
    dr = float(r[1] - r[0]) if len(r) > 1 else r[0]
    for x in r:
        devsim.add_2d_mesh_line(mesh=mesh_name, pos=float(x), ns=dr, ps=dr, dir="x")
    for i, y in enumerate(z):
        lo = float(z[i] - z[i - 1]) if i else float(z[1] - z[0])
        hi = float(z[i + 1] - z[i]) if i < len(z) - 1 else lo
        devsim.add_2d_mesh_line(mesh=mesh_name, pos=float(y), ns=lo, ps=hi, dir="y")
    # Structure follows the shipped example examples/capacitance/cap2d.py,
    # which is the only working reference for contacts in this DEVSIM build:
    #   * ONE bulk region spans the whole device, terminal rows included;
    #   * the terminal rows are separate metal regions laid INSIDE that box,
    #     which is what makes the contacts register -- a contact creates
    #     nothing unless its box covers a region of a different material
    #     (same-material boxes give get_contact_list() == () with no error);
    #   * metal is pinned by a NODE MODEL (Potential = bias), not by an
    #     equation. Giving it an equation instead, or leaving its nodes
    #     unreferenced, makes the matrix singular ("umfpack symbolic failed").
    z0, z1 = float(z[0]), float(z[-1])
    # Contact naming is a parameter because the multi-terminal form (task 2.4)
    # uses four ohmic contacts on three doped regions; the geometry is the
    # same terminal-row layout, only the labels differ.
    name_hi, name_lo = contact_names
    # The bulk EXCLUDES the metal rows: metals carry no unknowns in this
    # formulation (cap2d.py: Potential is a node_solution only in the bulk,
    # and the metal is pinned with a plain node_model). Including the metal
    # rows in the bulk left their Potential unconstrained -> singular matrix.
    devsim.add_2d_region(
        mesh=mesh_name, region="silicon", material=material,
        xl=float(r[0]), xh=float(r[-1]), yl=float(z[1]), yh=float(z[-2]))
    devsim.add_2d_region(
        mesh=mesh_name, region="metal_top", material="metal",
        xl=float(r[0]), xh=float(r[-1]), yl=float(z[-2]), yh=z1)
    devsim.add_2d_region(
        mesh=mesh_name, region="metal_bottom", material="metal",
        xl=float(r[0]), xh=float(r[-1]), yl=z0, yh=float(z[1]))
    # CONTACT GEOMETRY (measured 2026-11-09). The contact must be a PLANE on
    # the silicon region's boundary, not a box spanning the metal rows. As a
    # box (yl=z[-2], yh=z1) it only catches the 2 corner nodes where that box
    # touches silicon, so every terminal current read 0.0000e+00 while the
    # solve "converged" to 9e-15 -- the contacts were attached to nothing.
    # yl == yh puts the contact on the plane y = z[-2] (top) / y = z[1]
    # (bottom), exactly as the validated 2-D example puts its contacts on
    # planes of constant x.
    devsim.add_2d_contact(
        name=name_hi, material="metal", mesh=mesh_name, region="silicon",
        xl=float(r[0]), xh=float(r[-1]), yl=float(z[-2]), yh=float(z[-2]))
    devsim.add_2d_contact(
        name=name_lo, material="metal", mesh=mesh_name, region="silicon",
        xl=float(r[0]), xh=float(r[-1]), yl=float(z[1]), yh=float(z[1]))
    # Interior taps (task 2.4's multi-terminal check) go in HERE, before
    # finalize_mesh. Adding a contact to a finalized mesh aborts with
    #   Mesh "mt" must not be finalized   (measured 2026-11-09).
    # z_pos arrives in METRES (the module's public unit) and the mesh is in
    # cm, so it must be converted exactly like the mesh lines above. Passing
    # it raw put a "1 um" tap at 1e-6 cm = 10 nm, inside the metal row, and
    # the contact never registered: "on Contact \"c1\" on Device \"dd\" does
    # not exist" (measured 2026-11-09).
    for name, z_pos in extra_contacts:
        y_tap = float(z_pos) * M_TO_CM
        devsim.add_2d_contact(
            name=name, material="metal", mesh=mesh_name, region="silicon",
            xl=float(r[0]), xh=float(r[-1]),
            yl=y_tap, yh=y_tap)

    devsim.finalize_mesh(mesh=mesh_name)
    devsim.create_device(mesh=mesh_name, device="dd")

    # The radial axis and its zero. Both are REQUIRED; omitting raxis_zero
    # raises "raxis_zero ... must be a valid number parameter".
    devsim.set_parameter(name="raxis_variable", value="x", device="dd",
                         region="silicon")
    devsim.set_parameter(name="raxis_zero", value=0.0, device="dd",
                         region="silicon")
    devsim.cylindrical_node_volume(device="dd", region="silicon")
    devsim.cylindrical_edge_couple(device="dd", region="silicon")
    return devsim


def _build_device(grid, *, material, net_doping_cm3, eps_s, mesh_name, n_i_cm3):
    """The potential-only (equilibrium) device: mesh, then Poisson alone.

    Order matters and is the whole lesson of this module: the mesh must be a
    genuine 2-D mesh, ``raxis_variable`` and ``raxis_zero`` must be set, and
    only then does ``cylindrical_node_volume`` install the weighted volume.
    """
    import devsim
    _build_mesh(grid, mesh_name=mesh_name, material=material)
    _set_net_doping(devsim, net_doping_cm3)

    # Potential is the SOLVED variable: a node_solution, not a node_model
    # (a node_model loads and builds, then aborts at assemble time with
    # "Potential is not a Node Solution").
    devsim.node_solution(device="dd", region="silicon", name="Potential")
    devsim.edge_from_node_model(device="dd", region="silicon",
                                node_model="Potential")
    # The potential's derivatives are REQUIRED. Without the analytic
    # Jacobian edge models the Newton matrix has no coupling between
    # unknowns and factorisation fails with "umfpack numeric failed" --
    # measured, and the single hardest part of this file to diagnose, because
    # the matrix assembles without complaint and only the solve reports it.
    devsim.set_parameter(device="dd", region="silicon", name="Permittivity",
                         value=float(eps_s) * EPS0)
    devsim.edge_model(device="dd", region="silicon", name="EField",
                      equation="(Potential@n0 - Potential@n1) * EdgeInverseLength")
    devsim.edge_model(device="dd", region="silicon", name="EField:Potential@n0",
                      equation="EdgeInverseLength")
    devsim.edge_model(device="dd", region="silicon", name="EField:Potential@n1",
                      equation="-EdgeInverseLength")
    devsim.edge_model(device="dd", region="silicon", name="DField",
                      equation="Permittivity * EField")
    devsim.edge_model(device="dd", region="silicon", name="DField:Potential@n0",
                      equation="diff(Permittivity * EField, Potential@n0)")
    devsim.edge_model(device="dd", region="silicon", name="DField:Potential@n1",
                      equation="-DField:Potential@n0")
    # CHARGE TERM AND SIGN (devsim.python_packages.simple_physics.
    # CreateSiliconPotentialOnly): the Poisson source is -q*(Holes - Electrons
    # - NetDoping). At equilibrium in the depletion approximation and with the
    # contacts pinning far from the junction, Holes-Electrons ~ 0 and the
    # source reduces to +q*NetDoping. Passing RAW NetDoping (no q) is the error
    # that produced V_bi ~ -2.4e11 V; the sign flip is what produced the
    # -0.097 V result. Both measured 2026-11-09.
    # CHARGE SCALE (measured 2026-11-11, task 2.12). This line carried a
    # `* 1.0e6` on the theory that NetDoping is cm^-3 while the geometry is
    # SI, so the volume charge density "must" be q*N*1e6 C/m^3. That term is
    # what made this solve fail to converge with its own defaults: DEVSIM
    # stalled at AbsError 4.09097e-01, which is exactly V_bi/2, and a bias
    # ramp at 0.05 V did not help either (so it was never a staging problem).
    #
    # Removing the 1e6 fixes it. Sweep over the two candidates, otherwise
    # identical, measured 2026-11-11:
    #   Permittivity=F/m, charge=q*N      -> CONVERGED, span 0.8334 V
    #   Permittivity=F/m, charge=q*N*1e6  -> FAIL
    #   Permittivity=F/cm, charge=q*N     -> CONVERGED, span 36.98 V  (WRONG)
    #   Permittivity=F/cm, charge=q*N*1e6 -> FAIL
    # Only (F/m, q*N) converges AND lands on the analytic V_bi. Because the
    # line ABOVE sets Permittivity from EPS0 (F/m, SI) while the coupled
    # _build_dd_device sets it from EPS0_CM (F/cm), these two builders are
    # not on one unit system; the potential-only one is self-consistent at
    # SI permittivity with q*NetDoping and nothing else. Unifying the two is
    # left to a task that can re-validate the coupled path's 2.3 numbers --
    # changing EPS0_CM here without that would risk the calibrated results.
    #
    # NetDoping is cm^-3; with q in C this is C/cm^3, which is the charge
    # density that pairs with the F/m permittivity above (the mesh is in cm,
    # so the gradient is V/cm, and the two length units cancel).
    devsim.node_model(device="dd", region="silicon", name="SpaceCharge",
                      equation="1.602176634e-19 * NetDoping")
    devsim.node_model(device="dd", region="silicon",
                      name="SpaceCharge:Potential", equation="0")
    devsim.equation(device="dd", region="silicon", name="PotentialEquation",
                    variable_name="Potential", edge_model="DField",
                    edge_volume_model="EdgeCouple",
                    node_model="SpaceCharge",
                    variable_update="log_damp")

    # Metal: pin the potential with a node model of each bias.
    devsim.node_model(device="dd", region="metal_top", name="Potential",
                      equation="top_bias")
    devsim.node_model(device="dd", region="metal_bottom", name="Potential",
                      equation="bottom_bias")

    # THE EQUILIBRIUM CONTACT CONDITION -- this is where V_bi comes from.
    # A contact pinned to "Potential = bias" alone is an ohmic pin with NO
    # built-in potential, so the solver returns an unbounded quadratic profile
    # (measured: 966 V, and the same ~1000x excess in a full CGS unit system,
    # so it was never a unit bug). DEVSIM's own model
    # (simple_physics.CreateSiliconPotentialOnlyContact) pins instead to
    #   Potential - bias + ifelse(NetDoping>0, -V_t*ln(n/n_i), V_t*ln(p/n_i))
    # i.e. the equilibrium Fermi-level offset between majority carriers and
    # n_i. That offset IS V_bi, and omitting it is the whole error.
    #
    # n and p here are the doping-derived majority carrier densities
    # (DEVSIM's celec_model/chole_model), not solved quantities: this is a
    # potential-only (equilibrium) solve.
    v_t = 0.025852  # k*T/q at 300 K, V
    n_i = float(n_i_cm3)
    majority = (f"ifelse(NetDoping > 0, "
                f"-{v_t}*log(0.5*(NetDoping + (NetDoping^2 + 4*{n_i}^2)^0.5)/{n_i}), "
                f"{v_t}*log(0.5*(-NetDoping + (NetDoping^2 + 4*{n_i}^2)^0.5)/{n_i}))")
    for c in ("top", "bottom"):
        devsim.contact_node_model(device="dd", contact=c, name=f"{c}_bc",
                                  equation=f"Potential - {c}_bias + {majority}")
        devsim.contact_node_model(device="dd", contact=c,
                                  name=f"{c}_bc:Potential", equation="1")
        devsim.contact_equation(device="dd", contact=c,
                                name="PotentialEquation",
                                node_model=f"{c}_bc",
                                edge_charge_model="EField")
    return "dd"


def _build_dd_device(grid, *, net_doping_cm3, eps_s, mesh_name, T=300.0,
                    mu_n=None, mu_p=None, contact_names=("top", "bottom"),
                    extra_contacts=(), n_i_cm3):
    """Create the axisymmetric mesh, then DEVSIM's COUPLED drift-diffusion.

    The potential-only builder above solves Poisson with FIXED doping, which
    by construction cannot screen: there are no mobile carriers to move, so
    the built-in voltage ramps linearly across the whole domain whatever its
    length (measured 2026-11-09: +-V_bi/2 at the contacts on a 1 um domain,
    the same 0.833 V total on a 94 nm domain). A green V_bi on a domain sized
    by luck is NOT agreement; the width criterion cannot pass without carriers.

    This builder therefore installs Poisson + electron continuity + hole
    continuity, using DEVSIM's own validated silicon model
    (devsim.python_packages.simple_physics), rather than hand-rolling it.
    """
    import devsim
    import numpy as np
    from devsim.python_packages import simple_physics as sp

    # Reuse the proven mesh and 2*pi*r setup. _build_device returns as soon
    # as the mesh, regions, contacts and cylindrical weighting exist, BEFORE
    # it installs the potential-only physics, so the DD models below are the
    # only ones defined and nothing clashes.
    devsim = _build_mesh(grid, mesh_name=mesh_name, material="Si",
                         contact_names=tuple(contact_names),
                         extra_contacts=tuple(extra_contacts))
    _set_net_doping(devsim, net_doping_cm3)

    region = "silicon"
    # Every contact the mesh carries: the two ends the caller named plus any
    # interior taps. Both loops below must walk ALL of them; a tap without a
    # bias parameter or without its contact equation leaves a node the
    # solver treats as floating.
    all_contacts = tuple(contact_names) + tuple(n for n, _ in extra_contacts)
    # SetSiliconParameters assumes cm geometry: it sets
    #   Permittivity = eps_si * eps_0,  eps_0 = 8.854e-14 F/cm,
    #   ElectronCharge = 1.602e-19 C,   n_i = 1.0e10 cm^-3
    n_i_cm3 = float(n_i_cm3)

    sp.SetSiliconParameters(device="dd", region=region, T=T)
    # SetSiliconParameters writes ITS OWN module constants (n_i=1.0e10,
    # eps_si=11.7). We are called with a specific eps_s, and the contact
    # node models below are built from the same n_i. If the two disagree the
    # equilibrium carrier density at the contact is not the one Poisson's
    # charge term expects, and a biased solve need not converge.
    devsim.set_parameter(device="dd", region=region, name="n_i",
                         value=n_i_cm3)
    devsim.set_parameter(device="dd", region=region, name="Permittivity",
                         value=float(eps_s) * EPS0_CM)
    # n1/p1 are the SRH trap levels; SetSiliconParameters pins them to its
    # own n_i, so they need the same correction.
    for nm in ("n1", "p1"):
        devsim.set_parameter(device="dd", region=region, name=nm,
                             value=n_i_cm3)
    # UNITS: _build_mesh builds the mesh in CM, which is the unit this
    # cm-based model is validated in, so eps_0 = 8.854e-14 F/cm is CORRECT.
    # History (2026-11-09): this line used to set eps_s * EPS0 (F/m) against
    # a METRE mesh, and before that eps_s * 8.854e-14 against the same metre
    # mesh. Both were wrong in different ways; the real fix was the mesh
    # unit, not the permittivity constant.
    #
    # WHY THE MATERIAL VALUE IS RE-STATED (measured 2026-11-10). The line
    # above is not cosmetic. SetSiliconParameters writes Permittivity from
    # its OWN module constants, eps_si = 11.1 and eps_0 = 8.85e-14, i.e.
    # 9.8235e-13 -- and 11.1 is DEVSIM's generic silicon, not this
    # material's cited 11.7. Before this re-statement a caller passing
    # eps_s = 11.7 was silently solved at 11.1, which moved the 2.3
    # junction width W by 2.7 %: W ~ sqrt(eps_s), and
    # sqrt(11.7/11.1) = 1.0267 against a measured 8.770540e-08 /
    # 8.540402e-08 = 1.02695 (0.03 % apart). So the 2.7 % that 2.4 moved in
    # a 2.3 RESULT is this correction, and 2.4's width is the right one.
    # Ablation (2026-11-10): restoring only this line reproduces
    # 8.770540e-08 exactly; dropping it reproduces 8.540402e-08 exactly.
    # Re-stating n_i / n1 / p1 is NOT what moved the width (n_i is 1.0e10
    # both here and in the module) -- it is kept so the contact carrier
    # models and Poisson's charge term agree when a caller does vary n_i.
    if mu_n is not None:
        devsim.set_parameter(device="dd", region=region, name="mu_n",
                             value=float(mu_n))
    if mu_p is not None:
        devsim.set_parameter(device="dd", region=region, name="mu_p",
                             value=float(mu_p))

    _install_dd_physics(devsim, region=region, all_contacts=all_contacts,
                        n_i_cm3=n_i_cm3, eps_s=eps_s)
    return "dd"


def _install_dd_physics(devsim, *, region, all_contacts, n_i_cm3, eps_s,
                        maximum_iterations=30, relative_error=1.0e-10,
                        equilibrium_only=False):
    """Install DEVSIM's coupled drift-diffusion on an already-built device.

    This is the STAGED sequence lifted out of ``_build_dd_device`` unchanged so
    that the axisymmetric form and the 3-D gmsh form run the SAME physics. The
    two builders differ only in how the mesh, regions and contacts are made;
    every step below is mesh-shape agnostic and was validated on the
    axisymmetric path first.

    ``region`` is the silicon region's name -- "silicon" for the axisymmetric
    mesh, and whatever ``add_gmsh_region`` bound for a gmsh device.
    ``all_contacts`` lists every contact name the mesh carries.

    ``maximum_iterations`` and ``relative_error`` are parameters ONLY so a
    coarser or more irregular mesh can ask for a budget its conditioning
    needs. The defaults are the axisymmetric values, so that path is
    unchanged. They are not a place to relax a solve that is failing: an
    unconverged solve still raises, which is the whole point of routing every
    solve through ``_solve_converged``.

    ``equilibrium_only`` stops after STAGE 1 and installs no carriers. That
    is for callers that read an EQUILIBRIUM quantity -- the built-in voltage
    is fixed by stage 1 and nothing after it can change it. Running the
    coupled stages first and reporting V_bi from the result would gate a
    quantity stage 3 has no bearing on behind stage 3's convergence, which on
    a coarse tet mesh is a separate open problem (see tasks.md 2.7). It is
    NOT a way to skip a failing solve: stage 1 still goes through
    ``_solve_converged`` and still raises if it does not converge.
    """
    import devsim
    from devsim.python_packages import simple_physics as sp

    # ------------------------------------------------------------------
    # STAGE 1: equilibrium potential-only solve.
    # This is the sequence of DEVSIM's own validated 2-D diode example
    # (devsim_data/examples/diode/diode_common.py, InitialSolution +
    # DriftDiffusionInitialSolution). Copying it replaced four separate
    # guesses of mine that were each wrong -- see the notes below.
    #
    # ORDER IS REQUIRED (measured 2026-11-09): CreateSiliconDriftDiffusion
    # replaces the edge flux with "PotentialEdgeFlux", which only exists if
    # the equilibrium solution was built first. Without this call it aborts
    # with: -edge_model "PotentialEdgeFlux" ... does not exist.
    sp.CreateSolution(device="dd", region=region, name="Potential")
    sp.CreateSiliconPotentialOnly(device="dd", region=region)
    for c in all_contacts:
        devsim.set_parameter(device="dd", region=region,
                             name=sp.GetContactBiasName(c), value=0.0)
        # is_circuit stays False and MUST: True makes contact_equation bind
        # each contact to a circuit node named "<contact>_bias", and without
        # a circuit device that aborts with
        #   "Circuit node 'bottom_bias' does not exist"
        # (measured 2026-11-09). Supplying one would mean building a full
        # circuit device for a solver that has no external circuit.
        #
        # WITHDRAWN DIAGNOSIS (2026-11-09, corrected by the lead): I first
        # blamed the minority-current columns being exactly zero on this
        # is_circuit=False pinning, and called it the cause of the broken
        # I-V. That was wrong twice over. Pinning carriers to equilibrium
        # at an ohmic contact IS the standard boundary condition: the top
        # contact is n+ at 1e18, so Electrons=1e18 there at every bias is
        # correct, and the current comes from the interior rather than from
        # carriers moving at the contact. DEVSIM's own diode_1d has both
        # contacts on the silicon region with is_circuit False in this same
        # image and does conserve. The readout reason below still holds as a
        # description of the columns, but it is NOT the defect.
        sp.CreateSiliconPotentialOnlyContact(device="dd", region=region,
                                             contact=c, is_circuit=False)
    # relative_error 1e-10 is diode_1d.py's, matched deliberately (lead,
    # 2026-11-09). It is NOT the knob that fixed anything -- the real defect
    # was polarity -- but the reference's settings should not be second-
    # guessed without a measurement.
    _solve_converged(devsim, what="stage-1 equilibrium (potential only)",
                     absolute_error=1.0, relative_error=1.0e-10,
                     maximum_iterations=maximum_iterations)

    # An equilibrium-only caller reads Potential and stops here. Everything
    # below adds carriers and coupled equations, which cannot move a quantity
    # already fixed by the equilibrium solution.
    if equilibrium_only:
        return

    # ------------------------------------------------------------------
    # STAGE 2: the carriers, seeded from that equilibrium.
    # The carrier DENSITIES are unknowns in a coupled solve; the potential-
    # only model never created them, so CreatePE (called inside
    # CreateSiliconDriftDiffusion) aborts with "Electrons must exist".
    for c in ("Electrons", "Holes"):
        sp.CreateSolution(device="dd", region=region, name=c)
    # Carriers are solved in LOG form and must start strictly positive; a
    # zero or negative initial guess aborts with "Solution Variable has
    # negative or zero value before update". Seed from DEVSIM's own
    # equilibrium models -- NOT from a hand-computed formula and NOT with
    # init_from="y", which silently rebuilt the seed from the z coordinate
    # (values ~ -1e-6) and produced exactly that error.
    devsim.set_node_values(device="dd", region=region, name="Electrons",
                           init_from="IntrinsicElectrons")
    devsim.set_node_values(device="dd", region=region, name="Holes",
                           init_from="IntrinsicHoles")

    # ------------------------------------------------------------------
    # STAGE 3: the coupled equations, and one more solve to settle them.
    sp.CreateSiliconDriftDiffusion(device="dd", region=region,
                                   mu_n="mu_n", mu_p="mu_p")
    for c in all_contacts:
        sp.CreateSiliconDriftDiffusionAtContact(device="dd", region=region,
                                                contact=c, is_circuit=False)
    # abs_error 1e10 is DEVSIM's own setting for DD solves (diode_2d.py):
    # coupling the carrier equations makes the residual scale with the
    # doping, so a small absolute tolerance is not achievable or meaningful.
    _solve_converged(devsim, what="stage-3 coupled drift-diffusion",
                     absolute_error=1.0e10, relative_error=relative_error,
                     maximum_iterations=maximum_iterations)


def _potential_transition_width(z, phi):
    """Width between the 10 % and 90 % crossings of the potential step.

    Module-level so the coupled and potential-only solvers measure the width
    with ONE implementation; two copies can drift apart and quietly disagree.
    z and phi must be sorted by z, both in the same length unit.

    The span runs contact to contact. That is only a valid width when the
    domain is sized near the depletion region; on a much wider box most of
    the span is flat and this reads a fraction of the BOX instead. Callers
    must therefore keep z_lo/z_hi near the depletion width -- see
    ``test_the_depletion_width_matches_the_abrupt_junction_formula``.

    History (2026-11-09), because this cost a whole round-trip with the lead:
    on a +-2 um box this reported 31 nm and on a +-0.3 um box 4.7 nm, and the
    width was called "tracking the box". It WAS tracking the box, but not
    because of this function: the mesh was built in metres while the physics
    model was in centimetres, so the solve produced a LINEAR potential ramp
    across the whole domain with no junction at all. Once the mesh was put
    in cm the profile became the correct flat-transition-flat shape and the
    domain-sized box gave the right answer. The docstring below about domain
    sizing is real and still applies, but it was a second, smaller effect
    sitting behind the unit bug.
    """
    z = [float(v) for v in z]
    phi = [float(v) for v in phi]
    p_side, n_side = phi[0], phi[-1]
    span = n_side - p_side
    if span == 0.0:
        return float("nan")

    def crossing(level):
        for i in range(1, len(z)):
            a, b = phi[i - 1], phi[i]
            if (a - level) * (b - level) <= 0.0 and a != b:
                return float(z[i - 1] + (level - a) / (b - a) * (z[i] - z[i - 1]))
        return float("nan")

    return abs(crossing(p_side + 0.90 * span) - crossing(p_side + 0.10 * span))


def solve_abrupt_junction_dd(*, n_a, n_d, n_i, eps_s=None, material="Si",
                              z_lo=-1.0e-6, z_hi=1.0e-6, junction_z=0.0,
                            n_r=8, n_z=80, refine=2.0e-9,
                            refine_halfwidth=None, library=None,
                            T=300.0, mu_n=None, mu_p=None):
    """Coupled drift-diffusion across an abrupt junction on an (r, z) mesh.

    Returns the built-in voltage between the two contacts and the measured
    depletion half-widths either side of the junction. This is the solve 2.3
    needs: potential-only Poisson cannot screen (see _build_dd_device).
    """
    import devsim
    import numpy as np
    # 2.11: the number the solve uses comes from the library. A caller may
    # still pass eps_s, but only as a recorded override -- never a silent
    # default that clears the citation gate and is then ignored.
    eps_s, eps_s_source = material_value(material, "eps_s", eps_s, library)
    for name in ("dd",):
        try:
            devsim.delete_device(device=name)
        except Exception:
            pass
    try:
        devsim.delete_mesh(mesh="axdd")
    except Exception:
        pass

    def net_doping(z):
        return float(n_d) if z > junction_z else -float(n_a)

    # The refined band must COVER the transition, or the 10 %/90 % crossings
    # land in the coarse region and the width is grid-limited. The transition
    # is the full space-charge width, which depends on the doping, so a fixed
    # 20 nm band is wrong at any doping other than one: at N=1e17 the width is
    # ~147 nm, so a +-20 nm band sits entirely INSIDE it. Default the band to
    # 1.5x the analytic width and let callers override.
    if refine_halfwidth is None:
        refine_halfwidth = 1.5 * analytic_depletion_width(
            eps_s, n_a, n_d, analytic_v_bi(n_a, n_d, n_i))

    g = build_grid(0.0, r_max=max(4.0 * refine, 1.0e-8), z_min=z_lo,
                   z_max=z_hi, n_r=n_r, n_z=n_z, refine=refine,
                   refine_halfwidth=refine_halfwidth)
    # Refuse BEFORE building the device or solving: pricing a run too big to
    # attempt is the entire point, and once DEVSIM has allocated there is
    # nothing left to refuse. The grid above is the one the solve would use,
    # so the estimate is this run's, not a guess about a similar one.
    require_job_memory(g)
    _build_dd_device(g, net_doping_cm3=net_doping, eps_s=eps_s,
                     mesh_name="axdd", T=T, mu_n=mu_n, mu_p=mu_p,
                     n_i_cm3=n_i)
    # No further solve here: _build_dd_device already ran the staged
    # equilibrium -> carriers -> coupled sequence and its final solve
    # converged. Re-solving with a stricter tolerance than DEVSIM's own DD
    # default (1e10 absolute) made the continuity equations' ~11 absolute
    # residue look like a failure, when their relative error was already
    # ~1e-15. The solve belongs in the builder, once.

    z = np.asarray(devsim.get_node_model_values(
        device="dd", region="silicon", name="y"))
    phi = np.asarray(devsim.get_node_model_values(
        device="dd", region="silicon", name="Potential"))
    order = np.argsort(z)
    z, phi = z[order], phi[order]
    v_bi = float(phi[-1] - phi[0])

    # The four keys below are the ones the tests read. The first version of
    # this function returned only {"v_bi", "z", "phi"}, so every test that
    # asked for v_bi_measured raised KeyError -- and the xfail on the width
    # test swallowed that KeyError as if it were the expected width
    # failure, so the suite reported a passing run that executed nothing.
    # Measured 2026-11-09; the reviewer caught it. Keys now match the file.
    v_bi_analytic = analytic_v_bi(n_a, n_d, n_i)
    w_analytic = analytic_depletion_width(eps_s, n_a, n_d, v_bi_analytic)
    # _build_mesh hands DEVSIM the grid in CENTIMETRES, so the y it returns is
    # in cm. Every public width in this module is SI (metres), so convert
    # here and nowhere else. Measured 2026-11-09: verify this against the
    # grid, don't assume it -- the unit of the readback follows the unit of
    # add_2d_mesh_line, and getting it wrong scales every width by 100.
    z_m = z * 1.0e-2
    w_measured = _potential_transition_width(z_m, phi)
    return {
        "eps_s": eps_s,
        "eps_s_source": eps_s_source,
        "v_bi_measured": v_bi,
        "v_bi_analytic": v_bi_analytic,
        "w_measured": w_measured,
        "w_analytic": w_analytic,
        "z": z_m,
        "phi": phi,
        "grid": g.describe(),
        "nodes": g.n_nodes,
    }


def solve_abrupt_junction(*, n_a, n_d, n_i, eps_s=None, material="Si",
                            z_lo=-1.0e-6, z_hi=1.0e-6, junction_z=0.0,
                          n_r=8, n_z=120, refine=2.0e-9,
                          refine_halfwidth=2.0e-8, library=None):
    """Solve an abrupt p-n junction on an axisymmetric (r, z) mesh at 0 V.

    EQUILIBRIUM ONLY: Poisson with FIXED charge, no electron or hole
    continuity equation. That makes it fast and robust -- it converges in
    ~9 Newton steps from a zero guess (measured 2026-11-11) -- and it makes
    V_bi exact, because V_bi is set entirely by the contact condition:

        V_bi_measured == V_bi_analytic   to 7 significant figures.

    What it CANNOT do is measure a depletion width. With no mobile carriers
    there is nothing to screen the field, so the potential ramps across the
    whole domain instead of flattening at the depletion edges. Measured
    2026-11-11 on the shared grid: the far-field slope is 3.0e5 V/m against
    the coupled solver's plateau, and w_measured reads 1.82e-6 m where
    solve_abrupt_junction_dd reads 8.77e-8 m on the same domain. The
    transition-width numbers are still RETURNED (callers use them as a
    cheap memory-gate fixture) but they are not a physics result; only
    compare w_measured between two solves that both have carriers.

    Returns a dict with the measured and analytic V_bi and width, the solved
    profile (z in metres, phi in volts) and the grid. The caller compares;
    this function does not decide pass/fail.
    """
    import devsim
    import numpy as np

    # Refuse a gap rather than substitute: the library owns the citation.
    # 2.11: the number the solve uses comes from the library. A caller may
    # still pass eps_s, but only as a recorded override -- never a silent
    # default that clears the citation gate and is then ignored.
    eps_s, eps_s_source = material_value(material, "eps_s", eps_s, library)

    # Clean up BOTH the device and its mesh. Deleting only the device leaves
    # "A mesh already exists with name mj", so a second call in one process
    # fails (measured 2026-11-09) -- which makes any parameter scan impossible.
    for name in ("dd",):
        try:
            devsim.delete_device(device=name)
        except Exception:
            pass
    try:
        devsim.delete_mesh(mesh="mj")
    except Exception:
        pass

    def net_doping(z):
        # N_D on the n-side, -N_A on the p-side. NOT (n_d - n_a): that gives
        # ZERO net doping on the n-side of a symmetric junction (n_a == n_d),
        # so the device comes out wholly p-type and the "junction" is a single
        # slab. Measured 2026-11-09: NetDoping max 0.0, V_bi a third of theory.
        return float(n_d) if z > junction_z else -float(n_a)

    grid = build_grid(junction_z, r_max=4e-8, z_min=z_lo, z_max=z_hi,
                      n_r=n_r, n_z=n_z, refine=refine,
                      refine_halfwidth=refine_halfwidth)
    # Refuse BEFORE building the device or solving: pricing a run too big to
    # attempt is the entire point, and once DEVSIM has allocated there is
    # nothing left to refuse. The grid above is the one the solve would use,
    # so the estimate is this run's, not a guess about a similar one.
    require_job_memory(grid)
    _build_device(grid, material=material, net_doping_cm3=net_doping,
                  eps_s=eps_s, mesh_name="mj", n_i_cm3=n_i)

    # The biases are REGION parameters: contact node models are evaluated in
    # the region, so a device-scope parameter alone raises "Value for
    # 'bottom_bias' not available" while assembling. Equilibrium = 0 V both.
    for c in ("top", "bottom"):
        devsim.set_parameter(device="dd", name=f"{c}_bias", value=0.0)
        for reg in ("silicon", "metal_top", "metal_bottom"):
            devsim.set_parameter(device="dd", region=reg,
                                 name=f"{c}_bias", value=0.0)
    # Tight tolerances. A loose absolute_error/relative_error (I once had 1e10
    # here while probing) makes DEVSIM declare convergence after ONE iteration:
    # it returns RelError 1.0 and an under-solved profile, with no error. The
    # V_bi error that produces is easy to mistake for a physics bug.
    devsim.solve(type="dc", solver_type="direct", absolute_error=1e-9,
                 relative_error=1e-12, maximum_iterations=800)

    phi = np.array(devsim.get_node_model_values(
        device="dd", region="silicon", name="Potential"))
    zz = np.array(devsim.get_node_model_values(
        device="dd", region="silicon", name="y"))

    order = np.argsort(zz)
    zz, phi = zz[order], phi[order]
    # V_bi is the potential DIFFERENCE BETWEEN THE CONTACTS. Taking it as a
    # mean over a band inside the contacts is wrong: that band sits in the
    # depleted region and has already relaxed toward the plateau, which
    # produced a spurious 12.6 % error on a solve that was exact (measured
    # 2026-11-09: endpoint span 0.83337 V vs 0.83337 V theory).
    n_side = float(phi[-1])
    p_side = float(phi[0])
    v_bi_measured = float(n_side - p_side)

    # _build_mesh hands DEVSIM the grid in CENTIMETRES, so the y it returns is
    # in cm. Every public width in this module is SI (metres). Convert here
    # and nowhere else, and measure with the SHARED helper so this solver and
    # the coupled one cannot drift apart. Measured 2026-11-11: this solver
    # used to hand-roll its own 10-90 % crossings on the RAW cm axis and
    # compare the result against a metre-valued analytic width, which read a
    # 1239x error on a solve whose V_bi was exact to 7 figures. The crossings
    # themselves were fine; the units were not.
    z_m = zz * 1.0e-2
    w_measured = _potential_transition_width(z_m, phi)

    v_bi_analytic = analytic_v_bi(n_a, n_d, n_i)
    w_analytic = analytic_depletion_width(eps_s, n_a, n_d, v_bi_analytic)

    return {
        "eps_s": eps_s,
        "eps_s_source": eps_s_source,
        "v_bi_measured": v_bi_measured,
        "v_bi_analytic": v_bi_analytic,
        "w_measured": w_measured,
        "w_analytic": w_analytic,
        "grid": grid.describe(),
        "nodes": grid.n_nodes,
        # The solved profile, in the SAME form solve_abrupt_junction_dd
        # returns it: z in metres, phi in volts. Without these the two
        # solvers' results cannot be compared sample-by-sample, which is
        # exactly what a V_bi-agreement check needs (task 2.12).
        "z": z_m,
        "phi": phi,
    }


# ------------------------------------------------ 2.4: bias, current, terminals

def _contact_currents(devsim, contact_names):
    """Total terminal current (A) at each contact, electron + hole.

    DEVSIM's own idiom (``diode_common.PrintCurrents``): the current is a
    per-EQUATION quantity, taken separately for the electron and hole
    continuity equations and summed. Reading only one equation would report
    half the current -- half the holes and electrons cross each terminal.
    """
    from devsim.python_packages import simple_physics as sp
    out = {}
    for c in tuple(contact_names):
        i_e = devsim.get_contact_current(
            device="dd", contact=c, equation=sp.ece_name)
        i_h = devsim.get_contact_current(
            device="dd", contact=c, equation=sp.hce_name)
        out[c] = float(i_e) + float(i_h)
    return out


class EquilibriumNotReached(RuntimeError):
    """A drift-diffusion solve stopped without converging.

    Task 2.4's lesson (lead, 2026-11-09): a solve that exits on
    ``maximum_iterations`` has NOT reached equilibrium, and every downstream
    number inherits that. ``absolute_error`` does not save you: with
    absolute_error=1.0 the equilibrium solve below reached AbsError 2.3e-1
    after ONE iteration and DEVSIM called that done.

    The check is exact, not a heuristic: ``devsim.solve(..., info=True)``
    returns ``{'converged': bool, 'iterations': (...)}`` (measured
    2026-11-09 against the shipped reference diode, where it returned
    ``converged=True`` after 12 iterations). An earlier version of this
    guard re-solved and compared node values instead; that MISSED a
    non-converging stage-1 solve (1.0 -> 1.49 -> 0.47 -> 0.94 ... for 30
    iterations), because Newton revisits similar territory on a second call.
    Use the solver's own verdict.
    """

    def __init__(self, message, info=None):
        super().__init__(message)
        self.info = info


def _solve_converged(devsim, *, what="solve", **kwargs):
    """``devsim.solve`` that RAISES if the solver did not converge.

    Wrapping in place rather than checking afterwards is deliberate: nothing
    downstream can be trusted once a solve has stopped short, so the failure
    has to happen here.
    """
    kwargs.pop("info", None)
    # ``_solve_type`` lets the transient path reuse this guard's exact
    # convergence check rather than growing a second, weaker one. It was
    # hard-coded to "dc" until 2.8 needed "transient_dc".
    solve_type = kwargs.pop("_solve_type", "dc")
    result = devsim.solve(type=solve_type, solver_type="direct", info=True,
                          **kwargs)
    if not result or not result.get("converged"):
        iters = result.get("iterations") if result else None
        n = len(iters) if iters else "?"
        raise EquilibriumNotReached(
            "%s did not converge after %s iteration(s) "
            "(absolute_error=%r, relative_error=%r, maximum_iterations=%r); "
            "every result derived from this device would inherit a "
            "non-equilibrium state"
            % (what, n, kwargs.get("absolute_error"),
               kwargs.get("relative_error"), kwargs.get("maximum_iterations")),
            info=result)
    return result


def _solve_at_bias(devsim, contact_names, biases):
    """Set every terminal bias and re-solve the coupled system.

    ``biases`` maps contact name -> volts. Every terminal is set explicitly,
    including the reference one at 0 V: leaving a contact's bias at a stale
    value from the previous sweep point is how a "conservation" test passes
    while the device is being driven from the wrong place.
    """
    from devsim.python_packages import simple_physics as sp

    for c in tuple(contact_names):
        v = float(biases[c])
        name = sp.GetContactBiasName(c)
        # The DEVICE-scope value is what get_parameter reports back, but it
        # is the REGION-scope value that the contact node models evaluate --
        # setting only device scope leaves silicon:<c>_bias at whatever it
        # was and the solve silently ignores the bias (measured 2026-11-09:
        # 0 V and 0.4 V gave a potential identical to every printed digit).
        for reg in ("silicon", "metal_top", "metal_bottom"):
            devsim.set_parameter(device="dd", region=reg, name=name, value=v)
    _solve_converged(devsim, what="bias solve at %r V" % (dict(biases),),
                     absolute_error=1.0e10, relative_error=1.0e-10,
                     maximum_iterations=40)


def sweep_diode_iv(*, n_a, n_d, n_i, eps_s=None, biases, material="Si",
                   z_lo=-1.0e-6, z_hi=1.0e-6, n_r=2, n_z=200,
                   refine=1.0e-9, refine_halfwidth=None, library=None,
                   T=300.0, allow_unresolved=False):
    """Forward I-V across the abrupt junction, with contacts at each bias.

    Task 2.4. Returns one row per bias with the terminal currents and the
    conservation residual, so the caller can fit a slope and check that the
    current entering one contact leaves the other.

    The Debye gate runs first and refuses a mesh that cannot resolve the
    transition (spec.md:100). ``allow_unresolved=True`` is the spec's
    cross-check escape; when used, the result carries ``"debye_caveat"`` so a
    coarse run can never be mistaken for a resolved one.
    """
    import devsim
    import numpy as np
    # 2.11: the number the solve uses comes from the library. A caller may
    # still pass eps_s, but only as a recorded override -- never a silent
    # default that clears the citation gate and is then ignored.
    eps_s, eps_s_source = material_value(material, "eps_s", eps_s, library)

    def net_doping(z):
        return float(n_d) if z > 0.0 else -float(n_a)

    if refine_halfwidth is None:
        refine_halfwidth = 1.5 * analytic_depletion_width(
            eps_s, n_a, n_d, analytic_v_bi(n_a, n_d, n_i))

    g = build_grid(0.0, r_max=max(4.0 * refine, 1.0e-8), z_min=z_lo,
                   z_max=z_hi, n_r=n_r, n_z=n_z, refine=refine,
                   refine_halfwidth=refine_halfwidth)
    # Refuse BEFORE building the device or solving: pricing a run too big to
    # attempt is the entire point, and once DEVSIM has allocated there is
    # nothing left to refuse. The grid above is the one the solve would use,
    # so the estimate is this run's, not a guess about a similar one.
    require_job_memory(g)

    caveat = None
    try:
        require_debye_resolved(g, net_doping, eps_s)
    except DebyeUnresolved as exc:
        if not allow_unresolved:
            raise
        caveat = str(exc)

    for name in ("dd",):
        try:
            devsim.delete_device(device=name)
        except Exception:
            pass
    try:
        devsim.delete_mesh(mesh="axdd")
    except Exception:
        pass

    contacts = ("top", "bottom")
    _build_dd_device(g, net_doping_cm3=net_doping, eps_s=eps_s,
                     mesh_name="axdd", T=T, contact_names=contacts,
                     n_i_cm3=n_i)

    # POLARITY (measured 2026-11-09; this was the whole broken I-V).
    # The net doping above puts the n-side at z > 0, i.e. the TOP contact.
    # Forward bias means raising the p-side (bottom) above the n-side (top):
    # it narrows the barrier and makes n*p at the junction grow as
    # n_i^2 * exp(V/V_T). I had +V on the top contact, so every "forward"
    # point was REVERSE bias and n*p fell as exp(-V/V_T) -- which is what
    # made a perfectly converged solve look like uncoupled carriers.
    # Measured on this mesh, +V on the bottom: n*p = 1.000e20, 4.760e21,
    # 2.266e23 at 0/0.1/0.2 V against n_i^2*exp(V/V_T) = 1.000e20, 4.785e21,
    # 2.290e23 (0.5-2 %), and the terminal currents then cancel to ~1e-4 of
    # their own size. With +V on top, n*p was 1.000e20, 4.413e16 at 0.2 V:
    # n_i^2*exp(-V/V_T) to 0.3 %.
    # Probe the TWO CONTACT positions, not an arbitrary z inside the domain:
    # probing 1e-6 landed exactly on z_hi (the top contact, n-side) and so
    # picked "top" as the p contact -- the same inversion, one layer down.
    p_contact = "top" if net_doping(z_hi - 1.0e-12) < 0.0 else "bottom"
    n_contact = "bottom" if p_contact == "top" else "top"

    rows = []
    for v in biases:
        biases_by_contact = {p_contact: float(v), n_contact: 0.0}
        _solve_at_bias(devsim, contacts, biases_by_contact)
        currents = _contact_currents(devsim, contacts)
        total = sum(currents.values())
        scale = max(abs(x) for x in currents.values()) or 1.0
        rows.append({
            "bias_v": float(v),
            "i_top_a": currents["top"],
            "i_bottom_a": currents["bottom"],
            "i_total_a": total,
            # ABSOLUTE residual, and it is the one to judge on. The relative
            # form is meaningless below the round-off floor: measured
            # 2026-11-09 on the 1 um symmetric junction, |I| runs
            #   0.1 V 1.6e-16 A, 0.2 V 2.1e-14 A, 0.3 V 1.1e-12 A,
            #   0.4 V 5.3e-11 A, 0.5 V 2.5e-9 A,
            # while the absolute sum holds at 1.6e-16..6.6e-15 A at EVERY
            # bias (and stays put when maximum_iterations goes 40 -> 200).
            # That is solver round-off, ~1e-5 relative at 0.3 V and ~50 %
            # at 0.1 V, where the diode has not turned on and |I| is itself
            # only 1.6e-16 A. Dividing by a 1e-16 A current turns round-off
            # into a "0.5 residual" that reads as broken physics.
            "i_sum_residual_a": abs(total),
            "conservation_residual": abs(total) / scale,
            "contact_biases": biases_by_contact,
        })

    return {
        "eps_s": eps_s,
        "eps_s_source": eps_s_source,
        "rows": rows,
        "contacts": list(contacts),
        "v_bi_analytic": analytic_v_bi(n_a, n_d, n_i),
        "w_analytic": analytic_depletion_width(
            eps_s, n_a, n_d, analytic_v_bi(n_a, n_d, n_i)),
        "grid": g.describe(),
        "nodes": g.n_nodes,
        "debye_caveat": caveat,
    }


def _contact_charge_coulombs(devsim, region="silicon"):
    """Net mobile charge in the silicon, in coulombs, from node volumes.

    ``sum over nodes of q*(p - n)*CylindricalNodeVolume`` -- the 2*pi*r
    weighting is already inside ``CylindricalNodeVolume``, so this is the
    charge of the full solid, not of the 2-D half-plane. The FIXED dopant
    charge is deliberately NOT included: it does not move with the drive, so
    it cancels in any dQ between two states, and including it would make Q
    dominated by a ~1e17 term whose change is what we are trying to measure.

    Units: DEVSIM's cm-based model gives densities in cm^-3 and volumes in
    cm^3, so q*rho*V is coulombs with no further conversion.

    STAND-IN, NOT THE ELECTRODE CHARGE. This is a volume sum over the mobile
    carriers on EVERY node -- the whole device. That is the problem: on a
    neutral p/n diode the whole-device sum is the difference of two nearly
    equal half-device terms, so it is a cancellation rather than a
    measurement. The probe (``openspec/changes/
    electrical-simulation/2.8-charge-probe.md``) finds the HALF-device sum
    (``z > 0``) is the well-behaved quantity: a volume integral whose
    fixed-mesh dQ/dV is converged to 0.1 % across a 4x z refinement.

    DEVSIM's own ``get_contact_charge`` is a POOR capacitance quantity here
    (~61x below the half-device volume sum, and it tracks the mesh), but it
    is NOT sign-violating: its true fixed-mesh dQ/dV is +1.68e-20 F. An
    earlier version of this docstring claimed a negative capacitance, which
    came from differencing two DIFFERENT meshes at a fixed bias -- a
    difference of discretisations, not a dQ/dV. Corrected 2026-11-12.

    DO NOT quote this function's output as the stored electrode charge and do
    not close a charge identity on it: it is the whole-device cancellation.
    A charge balance, if one is ever closed, wants the half-device sum.
    Recorded rather than silently swapped, because swapping to
    ``get_contact_charge`` would be a worse quantity still.
    """
    import numpy as np
    en = np.asarray(devsim.get_node_model_values(device="dd", region=region,
                                                 name="Electrons"))
    hn = np.asarray(devsim.get_node_model_values(device="dd", region=region,
                                                 name="Holes"))
    vol = np.asarray(devsim.get_node_model_values(device="dd", region=region,
                                                  name="CylindricalNodeVolume"))
    return float(np.sum(Q * (hn - en) * vol))


def _recombination_per_second(devsim, region="silicon"):
    """Integral of the net electron-hole pair rate over the silicon, in 1/s.

    ``USRH`` is DEVSIM's net SRH pair rate in cm^-3 s^-1. Its sign follows
    ``np - n_i^2`` exactly (``simple_physics.CreateSRH`` line 257), so
    POSITIVE means net recombination and NEGATIVE means net generation. The
    model named ``ElectronGeneration`` is ``-q*USRH`` -- "generation" there
    is the electron continuity term's sign, not the sign of USRH itself.

    This was got backwards on the first pass (measured 2026-11-11): at 0.3 V
    forward the device had np/n_i^2 = 40.6, i.e. excess pairs and therefore
    recombination, while USRH was positive on 99.2% of nodes; the old
    ``-sum`` made it report generation. The docstring then said the
    opposite of the code. Anchor the sign at the formula, not at a model
    name.

    Returned with NO sign flip: positive = pairs recombine, s^-1. That is
    the quantity a charge balance needs. It is NOT phase 3's g(t): g(t) is
    the emissive (radiative) share, so callers must not read this as g(t).
    See ``transient_pulse``.
    """
    import numpy as np
    u = np.asarray(devsim.get_node_model_values(device="dd", region=region,
                                                name="USRH"))
    vol = np.asarray(devsim.get_node_model_values(device="dd", region=region,
                                                  name="CylindricalNodeVolume"))
    return float(np.sum(u * vol))


def transient_pulse(*, n_a, n_d, n_i, eps_s=None, material="Si",
                    waveform, dt, t_end, v_initial=0.0,
                    z_lo=-3.0e-7, z_hi=3.0e-7, n_r=2, n_z=200,
                    refine=1.0e-9, refine_halfwidth=5.0e-8,
                    library=None, T=300.0, ramp_steps=9,
                    maximum_iterations=60, charge_error=0.2):
    """Transient drift-diffusion from a solved bias, returning g(t).

    Task 2.8. ``waveform`` maps a time (seconds) to the forward-bias voltage
    on the p contact at that time; it is sampled once per ``dt``. The device
    is first ramped to ``v_initial`` in ``ramp_steps`` DC steps -- a single
    jump from 0 V lands on a different branch and the transient then starts
    from a state no physical ramp reaches (measured 2026-11-11: a direct
    0.4 V DC solve gives 4.2e-15 A where the ramped one gives 2.4e-8 A).

    WHY THE RAMP IS NOT OPTIONAL: the coupled I-V is exponentially sensitive
    to the contact bias, so a Newton solve seeded at the wrong branch
    "converges" to the low-injection solution. 2.4 found the same thing.

    Returns a dict with ``t``, ``v``, ``q`` (stored mobile charge, C),
    ``i_contact`` (the p-contact current, A, by DEVSIM's own per-equation
    sum) and ``recombination`` (integrated net pair rate, s^-1).

    ``g(t)`` is DELIBERATELY ABSENT as a direct output. DEVSIM's SRH model is
    non-radiative; the radiative pair rate the owner's emitter coupling needs
    is B*n*p integrated over the dot, which is a different quantity that this
    solver cannot produce without a radiative coefficient. ``transient_pulse``
    returns the total pair rate and the electron/hole densities so a caller
    can form B*n*p itself; inventing ``g(t)`` here would be a number with no
    model behind it.

    CHARGE IS NOT CONSERVED ON A STEPPED BIAS, and ``charge_error`` states
    the tolerance rather than hiding it. DEVSIM separates the equation
    residuals from a *charge* acceptance test ("the relative error between
    projected and solved charge during transient simulation") and prints it
    per step. On a genuinely driven step (0.30 -> 0.32 V, currents ~5e-4 A)
    that error starts at **1.08e-01** and the Newton iteration does not drive
    it down: asking for ``charge_error`` of 1e-2 or tighter does not converge
    at all. So the default is 0.2 -- tighter than the 1.0 this function
    shipped with (which accepted the very first iteration at 1.08e-1) and
    loose enough to describe what the solver actually achieves. CONSEQUENCE:
    ``integral(i_contact dt) != dq + q*integral(recombination dt)`` on this
    path, by roughly the printed charge error. That identity is NOT asserted
    anywhere, and must not be until the step starts from a charge-consistent
    state. ``q`` above is a volume sum of mobile carriers, a STAND-IN for the
    electrode charge -- see ``_contact_charge_coulombs`` for exactly what it
    is and what it is not. See the 2.8 entry and 2.8-charge-probe.md for the
    measurements, the two
    no-op control runs (device-parameter bias and circuit contacts both read
    2.3e-30 charge error because the device does not move at all), and the
    untested candidate fix.
    """
    import devsim
    import numpy as np
    from devsim.python_packages import simple_physics as sp

    if dt <= 0.0:
        raise ValueError("dt must be positive")
    if t_end <= 0.0:
        raise ValueError("t_end must be positive")
    if t_end <= dt:
        raise ValueError("t_end must exceed dt: a single step has no profile")

    eps_s, eps_s_source = material_value(material, "eps_s", eps_s, library)
    g = build_grid(0.0, r_max=max(4.0 * refine, 1.0e-8), z_min=z_lo,
                   z_max=z_hi, n_r=n_r, n_z=n_z, refine=refine,
                   refine_halfwidth=refine_halfwidth)
    # Refuse before allocating, exactly as the DC paths do.
    require_job_memory(g)
    net_doping = lambda z: float(n_d) if z > 0.0 else -float(n_a)
    _build_dd_device(g, net_doping_cm3=net_doping, eps_s=eps_s,
                     mesh_name="axtr", T=T, n_i_cm3=n_i)

    # transient_bdf1 needs DEVSIM's extended solver, and ``transient_dc``
    # must run once BEFORE any bdf1 step: without it the solve aborts in
    # TimeData.cc:100 with "UNEXPECTED missing time data" (measured
    # 2026-11-11, DEVSIM 2.11.2).
    for key in ("extended_solver", "extended_model", "extended_equation"):
        devsim.set_parameter(name=key, value=True)

    # The n-side is z > 0 (top contact); forward bias is +V on the p side.
    p_contact = "top" if net_doping(z_hi - 1.0e-12) < 0.0 else "bottom"
    n_contact = "bottom" if p_contact == "top" else "top"
    contacts = (p_contact, n_contact)

    for v in np.linspace(0.0, float(v_initial), int(ramp_steps))[1:]:
        _solve_at_bias(devsim, contacts, {p_contact: float(v), n_contact: 0.0})
    _solve_converged(devsim, what="transient initial transient_dc",
                     absolute_error=1.0e10, relative_error=1.0e-10,
                     maximum_iterations=maximum_iterations,
                     _solve_type="transient_dc")

    times = np.arange(0.0, float(t_end) + 0.5 * dt, dt)
    t_out, v_out, q_out, i_out, r_out = [], [], [], [], []
    t_out.append(0.0)
    v_out.append(float(v_initial))
    q_out.append(_contact_charge_coulombs(devsim))
    i_out.append(_contact_currents(devsim, contacts)[p_contact])
    r_out.append(_recombination_per_second(devsim))

    for t in times[1:]:
        v = float(waveform(t))
        for reg in ("silicon", "metal_top", "metal_bottom"):
            devsim.set_parameter(device="dd", region=reg,
                                 name=sp.GetContactBiasName(p_contact),
                                 value=v)
        result = devsim.solve(type="transient_bdf1", solver_type="direct",
                              tdelta=float(dt), charge_error=float(charge_error),
                              absolute_error=1.0e10, relative_error=1.0e-10,
                              maximum_iterations=maximum_iterations, info=True)
        if not result or not result.get("converged"):
            raise EquilibriumNotReached(
                "transient step at t=%g s did not converge; a partly stepped "
                "device is not a time series" % float(t), info=result)
        t_out.append(float(t))
        v_out.append(v)
        q_out.append(_contact_charge_coulombs(devsim))
        i_out.append(_contact_currents(devsim, contacts)[p_contact])
        r_out.append(_recombination_per_second(devsim))

    return {
        "t": np.asarray(t_out),
        "v": np.asarray(v_out),
        "q": np.asarray(q_out),
        "i_contact": np.asarray(i_out),
        "recombination": np.asarray(r_out),
        "eps_s": eps_s,
        "eps_s_source": eps_s_source,
        "p_contact": p_contact,
        "n_contact": n_contact,
        "grid": g.describe(),
        "nodes": g.n_nodes,
    }


def solve_multi_terminal(*, regions, contact_bias, n_i, eps_s=None,
                         material="Si", z_lo=-3.0e-6, z_hi=3.0e-6,
                         n_r=2, n_z=300, refine=1.0e-9, library=None,
                         T=300.0):
    """Three doped regions, four ohmic contacts, currents summing to zero.

    Task 2.4's multi-terminal check. ``regions`` is a list of
    ``(z_from, z_to, net_doping_cm3)`` spanning ``z_lo``..``z_hi`` in order;
    a p-n-p or n-p-n stack. Contacts are the two outer ends plus two
    interior taps at the region boundaries, so four terminals see the same
    device and the argument is that ALL currents sum to zero.

    Returns the per-contact currents and the residual of their sum.
    """
    import devsim
    import numpy as np
    # 2.11: the number the solve uses comes from the library. A caller may
    # still pass eps_s, but only as a recorded override -- never a silent
    # default that clears the citation gate and is then ignored.
    eps_s, eps_s_source = material_value(material, "eps_s", eps_s, library)

    # Validate the stack before building anything: an unspanned domain or an
    # overlapping set of regions would build a device whose doping silently
    # jumps and produce a "conservation" result for the wrong geometry.
    regions = [(float(a), float(b), float(d)) for a, b, d in regions]
    if not regions:
        raise ValueError("solve_multi_terminal needs at least one region")
    eps = 1.0e-12
    if abs(regions[0][0] - z_lo) > eps or abs(regions[-1][1] - z_hi) > eps:
        raise ValueError(
            "regions must span z_lo..z_hi exactly: got %.3e..%.3e, "
            "expected %.3e..%.3e"
            % (regions[0][0], regions[-1][1], z_lo, z_hi))
    for (a1, b1, _), (a2, b2, _) in zip(regions, regions[1:]):
        if abs(b1 - a2) > eps:
            raise ValueError(
                "regions overlap or leave a gap: %.3e..%.3e then %.3e..%.3e"
                % (a1, b1, a2, b2))

    def net_doping(z):
        for a, b, d in regions:
            if a <= z <= b:
                return d
        return regions[-1][2] if z > z_hi else regions[0][2]

    contacts = ("c0", "c1", "c2", "c3")
    # Terminals sit at the two ends and at the two interior boundaries.
    boundaries = [regions[0][0]] + [r[1] for r in regions]
    # Four contacts on three regions: c0 at z_lo, c3 at z_hi, and the two
    # interior taps at the first two region boundaries.
    taps = [boundaries[1], boundaries[2]] if len(boundaries) > 2 else []
    if len(taps) != 2:
        raise ValueError(
            "solve_multi_terminal wants three regions (four contacts); got %d "
            "region(s)" % len(regions))

    # BOTH junctions are refined. Refining only taps[0] left the second at
    # the coarse spacing and the Debye gate refused the device (measured
    # 2026-11-09: 20 nm edge against the 2.04 nm the gate requires).
    g = build_grid(taps, r_max=max(4.0 * refine, 1.0e-8), z_min=z_lo,
                   z_max=z_hi, n_r=n_r, n_z=n_z, refine=refine,
                   refine_halfwidth=1.5 * analytic_depletion_width(
                       eps_s, abs(regions[0][2]), abs(regions[1][2]),
                       analytic_v_bi(abs(regions[0][2]), abs(regions[1][2]), n_i)))

    require_debye_resolved(g, net_doping, eps_s)

    for name in ("dd",):
        try:
            devsim.delete_device(device=name)
        except Exception:
            pass
    try:
        devsim.delete_mesh(mesh="mt")
    except Exception:
        pass

    # All four contacts are created by the builder, the two interior taps
    # included: a contact cannot be added after the mesh is finalized
    # ("Mesh \"mt\" must not be finalized", measured 2026-11-09). The taps go
    # on the two junction planes, in METRES, converted inside _build_mesh.
    _build_dd_device(g, net_doping_cm3=net_doping, eps_s=eps_s,
                     mesh_name="mt", T=T, n_i_cm3=n_i,
                     contact_names=(contacts[3], contacts[0]),
                     extra_contacts=((contacts[1], taps[0]),
                                     (contacts[2], taps[1])))

    biases = {c: float(contact_bias.get(c, 0.0)) for c in contacts}
    _solve_at_bias(devsim, contacts, biases)
    currents = _contact_currents(devsim, contacts)
    total = sum(currents.values())
    scale = max(abs(x) for x in currents.values()) or 1.0
    return {
        "eps_s": eps_s,
        "eps_s_source": eps_s_source,
        "contacts": list(contacts),
        "regions": regions,
        "contact_bias": biases,
        "currents_a": currents,
        "i_total_a": total,
        "i_sum_residual_a": abs(total),
        "conservation_residual": abs(total) / scale,
    }


# ---------------------------------------------------------------------------
# 3-D drift-diffusion on a tetrahedral (gmsh) mesh -- task 2.7.
#
# DEVSIM 2.11.2 in this image has NO 3-D mesh-create API: only create_1d_mesh,
# create_2d_mesh and create_gmsh_mesh. A general 3-D form therefore has to be
# handed a tetrahedral mesh as a Gmsh 2.2 file and loaded with
# create_gmsh_mesh; there is no structured-grid route to fall back on.
#
# The physics is NOT re-implemented here. _install_dd_physics carries the exact
# staged sequence (equilibrium potential-only -> carriers -> coupled) that the
# axisymmetric form validated, and it is mesh-shape agnostic. What differs is
# only mesh, regions and contacts, which is what this section builds.
# ---------------------------------------------------------------------------

# Gmsh 2.2 element types. Type 2 is a 3-node triangle (a boundary face of a
# 4-node tet); type 4 is the tet itself.
_GMSH_TRIANGLE = 2


def _boundary_faces(tets):
    """Return {(a,b,c): [tet_index, ...]} for the outward faces of a tet set.

    A face shared by exactly one tet is a boundary face. Keyed by the SORTED
    node triple so the two orderings a shared face can appear in collapse to
    one key -- keying the raw triple instead would report every interior face
    as two separate boundaries.
    """
    import numpy as np
    faces = {}
    tet = np.asarray(tets, dtype=np.int64)
    # The four faces of a tet given as index corners (0,1,2,3): each face is
    # the triple left when one vertex is dropped.
    for corner in range(4):
        idx = [c for c in range(4) if c != corner]
        keys = np.sort(tet[:, idx], axis=1)
        for row, k in enumerate(map(tuple, keys.tolist())):
            faces.setdefault(k, []).append(row)
    return faces


def write_gmsh22_with_boundaries(path, points_cm, tets, region_of_tet, parts,
                                 contact_of_face=None):
    """Write a Gmsh 2.2 tet file WITH boundary-face physical groups.

    ``mse_devsim_mesh.write_gmsh22`` writes only the 3-D tet groups, so a
    device loaded from its output has regions but no surfaces to put a contact
    on -- ``add_gmsh_contact`` needs a boundary group that exists in the file.
    This variant writes those groups as well.

    UNITS: ``points_cm`` is in CENTIMETRES, deliberately. DEVSIM's validated
    silicon model (devsim.python_packages.simple_physics) is a cm-unit model
    -- eps_0 = 8.854e-14 F/cm, doping in cm^-3 -- and ``_build_mesh`` builds
    the axisymmetric mesh in cm for exactly that reason. Handing this model a
    metre mesh scales every charge by 100 and moves the Debye length by 10x.

    ``contact_of_face`` maps an outward face triple (sorted node ids) to a
    contact name; faces mapping to None are left ungrouped. Returns a report
    dict in the same spirit as ``write_gmsh22``.
    """
    import numpy as np
    points_cm = np.asarray(points_cm, dtype=float)
    tets = np.asarray(tets, dtype=np.int64)
    region = np.asarray(region_of_tet, dtype=np.int64)
    if len(region) != len(tets):
        raise ValueError(f"{len(region)} regions for {len(tets)} tets")

    names = list(parts)
    contact_of_face = contact_of_face or {}

    # Physical tags: region i -> i+1 (as write_gmsh22), then contacts continue
    # the numbering so no tag is reused across dimensions.
    phys_of_tet = region + 1
    contact_names = sorted({c for c in contact_of_face.values() if c})
    phys_of_contact = {c: len(names) + 1 + i for i, c in enumerate(contact_names)}

    # Collect outward faces and bucket them by contact. Only faces that a
    # contact actually claims are WRITTEN; the rest are counted nowhere,
    # because the element count in the header must match the element lines.
    faces = _boundary_faces(tets)
    boundary = []
    for key, owners in faces.items():
        if len(owners) != 1:
            continue
        contact = contact_of_face.get(key)
        if contact is not None:
            boundary.append((key, owners[0], contact))

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("$MeshFormat\n2.2 0 8\n$EndMeshFormat\n")
        fh.write("$PhysicalNames\n")
        fh.write(f"{len(names) + len(contact_names)}\n")
        for i, name in enumerate(names):
            fh.write(f'3 {i + 1} "{name}"\n')
        for c in contact_names:
            # Dimension 2 = a surface group, which is what add_gmsh_contact
            # selects. Writing dimension 3 here would load and select nothing.
            fh.write(f'2 {phys_of_contact[c]} "{c}"\n')
        fh.write("$EndPhysicalNames\n")

        fh.write("$Nodes\n")
        fh.write(f"{len(points_cm)}\n")
        for i, (x, y, z) in enumerate(points_cm, start=1):
            fh.write(f"{i} {float(x):.17g} {float(y):.17g} {float(z):.17g}\n")
        fh.write("$EndNodes\n")

        fh.write("$Elements\n")
        fh.write(f"{len(tets) + len(boundary)}\n")
        eid = 0
        for i, (tet, phys) in enumerate(zip(tets, phys_of_tet), start=1):
            a, b, c, d = (int(v) + 1 for v in tet)
            fh.write(f"{eid + 1} 4 2 {int(phys)} {int(phys)} {a} {b} {c} {d}\n")
            eid += 1
        for key, _, contact in boundary:
            a, b, c = (int(v) + 1 for v in key)
            phys = phys_of_contact[contact]
            fh.write(f"{eid + 1} 2 2 {phys} {phys} {a} {b} {c}\n")
            eid += 1
        fh.write("$EndElements\n")

    return {
        "path": str(path),
        "n_points": int(len(points_cm)),
        "n_tets": int(len(tets)),
        "n_boundary_faces": int(len(boundary)),
        "parts": names,
        "contacts": contact_names,
        "units": "cm",
    }


def solve_layered_dd_3d(*, n_a, n_d, n_i, eps_s=None, material="Si",
                        radius_m=1.0e-6, z_lo=-1.0e-6, z_hi=1.0e-6,
                        junction_z=0.0, edge_m=2.5e-7,
                        max_tets=None, limit_bytes=None, library=None, T=300.0,
                        mu_n=None, mu_p=None, biases=(),
                        maximum_iterations=120, relative_error=1.0e-10,
                        equilibrium_only=False):
    """Coupled drift-diffusion on a 3-D tetrahedral mesh (task 2.7).

    The general-solver form: rather than assume the device is round and
    build an (r, z) grid, this tetrahedralizes a real 3-D layer stack and
    runs the SAME staged physics as the axisymmetric path. Returns the same
    keys the axisymmetric DD solver does (v_bi_measured, w_measured, ...) so
    an agreement test can compare two solves through one interface.

    REFUSAL FIRST. ``require_job_memory`` is called on the node/edge count
    the tet mesh would actually produce, BEFORE any device is built or any
    solve runs. That is 2.5's check, and it must stay live on this path: a
    3-D DD solve is the most memory-hungry thing this module does.

    ``edge_m`` is the target tet edge in METRES. It, not a node count, is the
    resolution knob -- the node count falls out of it.
    """
    import os
    import tempfile

    import devsim
    import numpy as np

    from mse_common import DEFAULT_MAX_TETS

    import mse_devsim_mesh  # noqa: F401  (kept for the shared Gmsh conventions)
    from mse_meshing import tetrahedralize_layers

    # 2.11: the number the solve uses comes from the library. A caller may
    # still pass eps_s, but only as a recorded override -- never a silent
    # default that clears the citation gate and is then ignored.
    eps_s, eps_s_source = material_value(material, "eps_s", eps_s, library)
    if max_tets is None:
        max_tets = DEFAULT_MAX_TETS

    for name in ("dd",):
        try:
            devsim.delete_device(device=name)
        except Exception:
            pass
    for mesh in ("g3d",):
        try:
            devsim.delete_mesh(mesh=mesh)
        except Exception:
            pass

    def net_doping(z):
        return float(n_d) if z > junction_z else -float(n_a)

    # Two layers, p below and n above, split at junction_z.
    z_lo, z_hi = float(z_lo), float(z_hi)
    junction_z = float(junction_z)
    if not (z_lo < junction_z < z_hi):
        raise ValueError(
            f"junction_z={junction_z!r} must lie strictly inside "
            f"[{z_lo!r}, {z_hi!r}]")
    layers = [("p", junction_z - z_lo), ("n", z_hi - junction_z)]

    # AN EQUAL-ASPECT OUTLINE: a square whose half-diagonal is radius_m, so the
    # 3-D device occupies roughly the same volume as the axisymmetric one it
    # is compared against. The mesher takes an (x, y) outline; a square is the
    # simplest that does not bias the field in one transverse direction.
    half = float(radius_m) / np.sqrt(2.0)
    outline = [(-half, -half), (half, -half), (half, half), (-half, half)]

    points_m, tets, region_of_tet = tetrahedralize_layers(
        outline, layers, float(edge_m), z0_m=z_lo, max_tets=int(max_tets))

    # REFUSE BEFORE BUILDING ANYTHING. Price the mesh we are about to solve.
    # The structured estimator takes a Grid; a tet mesh has no (r, z) lines,
    # so price it from the counts the tet mesh actually produced.
    n_nodes = int(len(points_m))
    n_edges = _estimate_tet_edges(tets)
    estimate_bytes, limit_bytes = _require_tet_job_memory(
        n_nodes, n_edges, limit_bytes=limit_bytes)

    # ---------------------------------------------------------------- gmsh
    # Boundary faces become contacts. The p/n interface is an interior plane
    # and gets no group: only the two outer ends are terminals.
    z_all = np.asarray(points_m, dtype=float)[:, 2]
    z_min, z_max = float(z_all.min()), float(z_all.max())
    tol = 1e-9 * max(1.0, abs(z_max - z_min))

    faces = _boundary_faces(tets)
    contact_of_face = {}
    for key, owners in faces.items():
        if len(owners) != 1:
            continue
        zf = z_all[list(key)]
        if np.all(np.abs(zf - z_min) <= tol):
            contact_of_face[key] = "bottom"
        elif np.all(np.abs(zf - z_max) <= tol):
            contact_of_face[key] = "top"

    # The file is written in CM; the mesher works in metres.
    M_TO_CM = 100.0
    points_cm = np.asarray(points_m, dtype=float) * M_TO_CM

    tmpdir = tempfile.mkdtemp(prefix="mse-dd3d-")
    path = os.path.join(tmpdir, "layers.msh")
    report = write_gmsh22_with_boundaries(
        path, points_cm, tets, region_of_tet, [n for n, _ in layers],
        contact_of_face=contact_of_face)

    devsim.create_gmsh_mesh(file=path, mesh="g3d")
    # ONE silicon region spanning both layers: the doping is a FUNCTION of z
    # (net_doping), exactly as the axisymmetric form does it. Two separate
    # regions would put the p/n interface on a region boundary, and there the
    # doping profile is not applied continuously across the junction.
    devsim.add_gmsh_region(mesh="g3d", gmsh_name=layers[0][0],
                           region="silicon", material=material)
    devsim.add_gmsh_region(mesh="g3d", gmsh_name=layers[1][0],
                           region="silicon", material=material)
    contact_names = ("top", "bottom")
    for c in contact_names:
        if c not in report["contacts"]:
            raise RuntimeError(
                f"gmsh file has no boundary group named {c!r}; got "
                f"{report['contacts']!r}. Contacts need a surface physical "
                f"group written by write_gmsh22_with_boundaries.")
        devsim.add_gmsh_contact(mesh="g3d", region="silicon", name=c,
                                gmsh_name=c, material=material)
    devsim.finalize_mesh(mesh="g3d")
    devsim.create_device(mesh="g3d", device="dd")

    _set_net_doping(devsim, net_doping, region="silicon", coord="z")
    n_i_cm3 = float(n_i)
    from devsim.python_packages import simple_physics as sp
    sp.SetSiliconParameters(device="dd", region="silicon", T=T)
    devsim.set_parameter(device="dd", region="silicon", name="n_i",
                         value=n_i_cm3)
    devsim.set_parameter(device="dd", region="silicon", name="Permittivity",
                         value=float(eps_s) * EPS0_CM)
    for nm in ("n1", "p1"):
        devsim.set_parameter(device="dd", region="silicon", name=nm,
                             value=n_i_cm3)
    if mu_n is not None:
        devsim.set_parameter(device="dd", region="silicon", name="mu_n",
                             value=float(mu_n))
    if mu_p is not None:
        devsim.set_parameter(device="dd", region="silicon", name="mu_p",
                             value=float(mu_p))

    _install_dd_physics(devsim, region="silicon",
                        all_contacts=tuple(contact_names),
                        n_i_cm3=n_i_cm3, eps_s=eps_s,
                        maximum_iterations=maximum_iterations,
                        relative_error=relative_error,
                        equilibrium_only=equilibrium_only)

    z = np.asarray(devsim.get_node_model_values(
        device="dd", region="silicon", name="z"))
    phi = np.asarray(devsim.get_node_model_values(
        device="dd", region="silicon", name="Potential"))
    order = np.argsort(z)
    z, phi = z[order], phi[order]
    v_bi = float(phi[-1] - phi[0])

    v_bi_analytic = analytic_v_bi(n_a, n_d, n_i)
    w_analytic = analytic_depletion_width(eps_s, n_a, n_d, v_bi_analytic)
    # The mesh is CM, so z comes back in cm; every public width is SI.
    z_m = z * 1.0e-2
    w_measured = _potential_transition_width(z_m, phi)

    iv = {}
    if biases:
        iv = _solve_at_bias(devsim, contact_names, biases)
        # Re-read the equilibrium potential after the biased sweep so the
        # widths above are not mixed with a biased state.
        z = np.asarray(devsim.get_node_model_values(
            device="dd", region="silicon", name="z"))
        phi = np.asarray(devsim.get_node_model_values(
            device="dd", region="silicon", name="Potential"))

    return {
        "v_bi_measured": v_bi,
        "v_bi_analytic": v_bi_analytic,
        "w_measured": w_measured,
        "w_analytic": w_analytic,
        "z": z_m,
        "phi": phi,
        "n_nodes": n_nodes,
        "n_edges": n_edges,
        "n_tets": int(len(tets)),
        "eps_s": eps_s,
        "eps_s_source": eps_s_source,
        "estimate_bytes": estimate_bytes,
        "limit_bytes": limit_bytes,
        "gmsh_report": report,
        "iv": iv,
    }


def _estimate_tet_edges(tets):
    """Count the unique edges of a tet mesh."""
    import numpy as np
    edges = set()
    for a, b, c, d in np.asarray(tets, dtype=np.int64).tolist():
        for u, v in ((a, b), (a, c), (a, d), (b, c), (b, d), (c, d)):
            edges.add((u, v) if u < v else (v, u))
    return len(edges)


def estimate_tet_job_bytes(n_nodes, n_edges, *, contacts=2, raw=False):
    """Peak bytes a tet-mesh solve would hold, from the tet mesh's own counts.

    ``estimate_job_bytes`` prices a structured (r, z) grid from its line
    counts. A tet mesh has no lines, so the SAME per-node, per-edge and
    per-nonzero costs are applied to the node and edge counts the tet mesh
    actually produced. Keeping ONE set of costs means a refusal means the same
    thing whichever solver is asking.

    CALIBRATED against measurement, unlike the axisymmetric estimator. A tier-3
    calibration Job (2026-11-10, image 7dbd3b4, three sizes) measured peak RSS
    against the RAW sum below and found 3-D runs cost about
    ``TET_ESTIMATE_FACTOR x raw + TET_FIXED_OVERHEAD_BYTES``. Both corrections
    are applied here, so this function returns the number the gate refuses on.

    That direction matters: the pre-calibration gate assumed its estimate was
    pessimistic for 3-D. It was optimistic by a factor of two, which means it
    would have ADMITTED runs that then died. See TET_ESTIMATE_FACTOR.

    Public and pure so an RSS calibration (``scripts/dd_3d_rss.py``) can price
    the very mesh it just solved without re-deriving the formula, or worse,
    transcribing it. A transposed formula in the calibration script would
    compute a ratio between the estimator and *another* estimator.

    ``raw=True`` returns the uncalibrated sum. The calibration script uses it
    to report the ratio the correction is made of, rather than a ratio of the
    correction to itself.
    """
    nodes = max(1, int(n_nodes))
    edges = int(n_edges)
    nonzeros = JACOBIAN_NONZEROS_PER_NODE * nodes * max(1.0, math.sqrt(nodes))
    total = 0.0
    total += nonzeros * BYTES_PER_NONZERO
    total += nodes * BYTES_PER_NODE
    total += edges * BYTES_PER_EDGE
    total += contacts * nodes * 8.0
    if raw:
        return int(total)
    return int(TET_FIXED_OVERHEAD_BYTES + TET_ESTIMATE_FACTOR * total)


def _require_tet_job_memory(n_nodes, n_edges, *, limit_bytes=None,
                            contacts=2):
    """2.5's refusal plus 2.13's factorisation ceiling, on a TET mesh's counts.

    Two independent refusals, because they catch disjoint failures:

    * the NODE ceiling (:data:`TET_MAX_FACTORABLE_NODES`) catches meshes that
      ``umfpack_di_numeric`` cannot factor at ANY memory limit;
    * the memory price (:func:`estimate_tet_job_bytes`) catches meshes that
      would fit the factorisation but not the Job's allowance.

    The node check runs FIRST: it is the cheaper check and the one whose remedy
    (coarsen the mesh) is actionable, so it should win when both apply. The
    pricing lives in ``estimate_tet_job_bytes``; this function only adds the
    limits and the refusals, so a caller reading a price cannot disagree with
    the caller enforcing it.
    """
    if limit_bytes is None:
        from mse_common import DEFAULT_JOB_MEMORY_BYTES
        limit_bytes = DEFAULT_JOB_MEMORY_BYTES
    limit_bytes = int(limit_bytes)
    if n_nodes > TET_MAX_FACTORABLE_NODES:
        raise TooManyNodesForFactor(n_nodes, TET_MAX_FACTORABLE_NODES)
    total = estimate_tet_job_bytes(n_nodes, n_edges, contacts=contacts)
    if total > limit_bytes:
        raise TooBigForJob(total, limit_bytes, n_nodes, n_edges,
                           hint="the 3-D form is the general solver and is "
                                "the easiest way to exceed the Job limit")
    return total, limit_bytes
