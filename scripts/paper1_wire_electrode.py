#!/usr/bin/env python3
"""Bench: paper 1's nanowire with a TOP ELECTRODE -- the electrostatic wire fixture.

**UNVALIDATED.** This fixture has no measured answer to be checked against. It
exists so that the field the gate applies to the paper-1 wire is a number we
computed on the paper's own geometry rather than a number we assumed. Nothing
downstream may quote its output as validated; see "Status" below.

What it builds
--------------
The same three parts as :mod:`paper1_nanowire` -- a gold mirror, a 12 nm SiO2
buffer and a hexagonal InP prism -- plus a top electrode that contacts the
wire's top facet. The geometry is imported from ``paper1_nanowire`` rather than
re-typed, so the two benches cannot drift apart: a change to the wire's
dimensions moves both.

Geometry, with its source in paper 1 (arXiv:2601.04440), as task 0.2 recorded it
---------------------------------------------------------------------------------
- **Wire:** wurtzite InP hexagonal prism, height H = 1375 nm, diameter
  D = 420 nm. "the optimal cavity dimensions (height of 1375 nm and width of
  420 nm) that we found" (p. 3, Results); the Fig. 1 caption agrees. We take
  these from p. 3 and NOT from the Fig. 5a caption, which swaps them
  ("D=1375 nm and H=420 nm", p. 8) and contradicts the rest of the paper.
- **The 1.14 factor** is the paper's own hex-to-cylinder relation: "A scaling
  factor of 1.14 was applied to the diameter as the nanowire has a hexagonal
  cross-section" (p. 10, S2). Applied as ``2s = 1.14 D`` -- s the hexagon's side
  -- it gives a corner-to-corner width of 478.8 nm, a circumradius of 239.4 nm
  and a flat-to-flat of 414.6 nm.
- **Oxide:** 12 nm SiO2 -- "a 12 nm thick oxide layer optimizes the Purcell
  enhancement and extraction efficiency" (p. 4), over a gold mirror.
- **Probe:** on-axis, 30 nm below the top -- "a QD emitter placed on-axis at
  30 nm below the top" (Fig. 2 caption, p. 5), at "the second antinode from the
  top" (p. 3).

Permittivities -- static, and NOT n^2
-------------------------------------
The paper states refractive indices and never a permittivity: "an index of
refraction n=3.44 ... to simulate the nanowire material (Wurtzite InP)" (p. 9,
S1). n^2 = 11.83 is a value at the optical band, not a static permittivity, so
it is used for NEITHER material here.

- **InP eps_s = 12.5** at 300 K (Ioffe, NSM archive, basic-parameters table;
  task 0.2, recorded in design.md).
- **SiO2 eps_s = 3.9** -- paper 1 gives no SiO2 value anywhere, so this is taken
  from a standard reference for thermal oxide. See :data:`EPS_SIO2` for the
  citation and its caveat.
- Gold is a conductor and is treated as an equipotential (it is an electrode,
  not a dielectric region).

Status: UNVALIDATED; the ONE-PART mesh does not resolve the oxide (the layered one does, 1.6c)
---------------------------------------------------------------------------------------------
There is no measurement of the field in this structure to compare against. The
paper reports a Purcell factor from an FDTD run, not a potential or a field.

Worse, and measured: **the field this fixture computes is not converged in the
mesh**, so it cannot be a gate for anything. Driving the only lever the one-part
mesher exposes (``n_modes``) from 20 to 120 changes ``|E|`` at the probe by
**40.1 %** and NOT monotonically (557, 780, 690 kV/m per volt). The cause is a
12 nm oxide inside a 1567 nm stack: every element must span both a 1375 nm wire
and a 12 nm layer, and the tet z-span only falls as roughly ``n^-1/3``. The
z-span spread is wide, so both ends of it matter: at ``n_modes=200`` (153k tets)
the MEDIAN element spans 20.4 nm in z while the WORST spans 51.7 nm (at
``n_modes=20`` the worst is 110.4 nm). Even the median is 1.7x the oxide and the
worst 4.3x, so resolution alone does not reach 12 nm; doing so would need on the
order of 10^6 tets, past tier 1 and past this rig's memory cap.

A single closed solid is used because it is the ONLY shape that reaches the
mesher: :class:`mse_parts.PartSet` refuses touching parts and requires one part
to enclose all others, and ``sizing=`` is refused on a one-part upload. So the
graded layered mesh this device needs has no path in the current mesher. Every
layer is labelled by the z of the tet's centroid, and at these resolutions tets
STRADDLE the layer boundaries (measured: at ``n_modes=20``, 1064 of 9775 tets,
10.9 %, cross z=120 nm or z=132 nm; a worst-case element has a 175 nm diagonal
spanning a 12 nm oxide), so the labels are applied to elements whose permittivity
is not uniform.
That, and not the physics, is what moves with resolution.

What this fixture therefore establishes, and what it does not:

- ESTABLISHED: the solver path works end to end on the paper's geometry, the
  result is exactly linear in the applied volts (max |dE| = 0 at 2V/2 vs 1V and
  at -1V vs 1V), and the prism's volume matches the closed form exactly.
- NOT ESTABLISHED: any field value. None may be quoted downstream.

**Task 1.6c (2026-11-05): the layered path.** :func:`mesh_fixture_layered`
meshes the stack with :func:`mse_meshing.tetrahedralize_layers`, which puts an
internal facet at every layer plane (and sub-slab facets in the oxide), so no
tet straddles an interface. On that mesh the field at the probe is the same to
8e-15 across 9.7k, 38k and 107k tets and equals the exact 1-D value
(:func:`field_per_volt_1d`, 707.483 kV/m per V) -- run ``--layered-convergence``.
That agreement is exact, not approximate, because this fixture IS a 1-D stack:
every layer has the wire's outline and both electrodes cover it, so the
potential is piecewise linear in z and lies in the P1 space. The 40 % spread
above was therefore entirely the centroid labels. The fixture is still
UNVALIDATED against the paper's device: the paper's pad is wider than the wire
(:func:`footprint_error`), and that 3-D fringing field is not modelled here.
:func:`mesh_fixture` (the one-part path) is kept, with its negative test, as
the record of what the one-part mesher does.

Usage
-----
    python scripts/paper1_wire_electrode.py            # layered mesh, prints E/V
    python scripts/paper1_wire_electrode.py --coarse   # a mesh small enough for tests
    python scripts/paper1_wire_electrode.py --layered-convergence   # task 1.6c check
    python scripts/paper1_wire_electrode.py --one-part --convergence  # the 1.6b negative

The script is also importable: :func:`mesh_fixture` and
:func:`wire_field_per_volt` are what ``tests/test_paper1_wire_electrode.py``
drives.
"""

from __future__ import annotations

import argparse
import math
import os
import sys

import numpy as np
import trimesh

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "..", "dockerfiles", "maxwell_solver"))

import paper1_nanowire as P1  # noqa: E402

import dot_material as DOT  # noqa: E402
import mse_electrostatics as E  # noqa: E402
import mse_meshing as MESH  # noqa: E402
import mse_parts as PARTS  # noqa: E402

NM = 1e-9

#: The paper's own hex-to-cylinder relation, re-exported so a caller reads the
#: same constant the wire was built from.
HEX_NW_RATIO = P1.HEX_NW_RATIO

#: Wire dimensions, from paper 1 p. 3 (see the module docstring for why p. 3
#: and not the Fig. 5a caption).
HEIGHT_NM = 1375.0
DIAMETER_NM = 420.0

#: The oxide's thickness, from p. 4.
OXIDE_NM = 12.0

#: The probe's depth below the wire's top facet, from the Fig. 2 caption (p. 5).
PROBE_BELOW_TOP_NM = 30.0

#: Static permittivity of InP at 300 K, from Ioffe's basic-parameters table
#: (task 0.2). NOT n^2 = 11.83, which is the optical-band value. Read from
#: :mod:`dot_material`, which owns the cited value, rather than re-typed here.
EPS_INP = DOT.INP_EPS_S.value

#: Static permittivity of SiO2. **Paper 1 states no SiO2 value** ("no SiO2 index
#: or eps is stated anywhere", design.md §1), so this is a standard-reference
#: value for thermally grown oxide, eps_r ~ 3.9 (the widely quoted figure for
#: thermal SiO2, e.g. Sze, "Physics of Semiconductor Devices", 3rd ed., ch. 4;
#: also the ITRS-era standard value). It is NOT read from paper 1 and it is NOT
#: n^2 (~2.1 for fused silica at the optical band, which is the wrong quantity
#: anyway). A 3.9 vs 2.1 difference in the oxide barely moves the wire's field
#: -- the wire is 114x taller than the oxide -- but the value is a reference
#: number, not a measurement of this stack.
EPS_SIO2 = 3.9

#: How far the top electrode extends beyond the wire, in nm. It is a planar
#: contact over the wire's top facet, so it is as wide as the wire plus a pad;
#: the pad exists so the electrode is a real volume in the mesh rather than a
#: zero-thickness sheet, which TetGen cannot make a region of.
ELECTRODE_PAD_NM = 60.0

#: The electrode's own thickness, in nm.
ELECTRODE_THICKNESS_NM = 60.0

#: How far the gold mirror extends below the wire, in nm. It is the back
#: electrode and must cover the oxide's footprint.
MIRROR_THICKNESS_NM = 120.0

#: Parts that are electrodes: their nodes are held at the applied potential.
ELECTRODE_PARTS = ("mirror", "top")


def circumradius_nm() -> float:
    """The wire's circumradius from its diameter, through the paper's 1.14 factor.

    The paper writes ``2s = 1.14 D`` (p. 10, S2) with s the hexagon's side, so
    the corner-to-corner width is ``1.14 D`` and the circumradius is half that.
    ``paper1_nanowire.scene`` applies exactly this relation for ``--hex paper``;
    this function is that one line, named so the fixture can print it.
    """
    return DIAMETER_NM * HEX_NW_RATIO / 2.0


def materials(ambient: str | None = None) -> dict:
    """Part -> static relative permittivity, for the dielectric parts only.

    The electrodes are held at fixed volts, so their permittivity is never
    used; they carry none here and :func:`mse_electrostatics.solve` is given
    ``eps_static`` for every part anyway because the assembler asks for it.
    A conductor's value is 1.0 by convention in that call and is inert.

    ``ambient`` adds the surrounding medium's two slabs at
    :data:`AMBIENT_EPS`\\ ``[ambient]``. ``None`` -- the four-layer device stack
    of 1.10c -- adds nothing, so a caller that meshes no medium is not handed a
    permittivity for a part it does not have.
    """
    eps = {"mirror": 1.0, "oxide": EPS_SIO2, "wire": EPS_INP, "top": 1.0}
    if ambient is not None:
        if ambient not in AMBIENT_EPS:
            raise ValueError(
                f"ambient must be one of {sorted(AMBIENT_EPS)}, got {ambient!r}")
        # The solve sees the medium as ONE part (:data:`AMBIENT_PART`); the three
        # meshed pieces are an implementation detail of the mesher's unique-name
        # rule and never reach ``eps_static``.
        eps[AMBIENT_PART] = AMBIENT_EPS[ambient]
    return eps


def probe_point() -> np.ndarray:
    """The probe, in metres: on the axis, 30 nm below the wire's top facet."""
    z_top = (MIRROR_THICKNESS_NM + OXIDE_NM + HEIGHT_NM) * NM
    return np.array([0.0, 0.0, z_top - PROBE_BELOW_TOP_NM * NM])


def stacked_solid_with_labels():
    """ONE closed solid for the whole dielectric stack, plus its layer labels.

    Why one solid and not four parts: :class:`mse_parts.PartSet` is the ONLY
    supported multi-part input, and :func:`mse_parts.load_parts` guarantees as a
    CONTRACT that no two parts intersect or touch and that one part ENCLOSES
    every other (the PEC wall). This stack violates both by construction: the
    layers share faces, and a 12 nm oxide cannot enclose a 1375 nm wire.
    :func:`mse_electrostatics.solve` does not need that contract -- it takes
    points, tets and a per-tet part array -- but a multi-part object can only
    reach the mesher through a ``PartSet``, so a stacked device cannot be
    expressed as parts here at all. A one-part solid can, so that is what this
    builds.

    Geometry: a hexagonal prism of circumradius :func:`circumradius_nm`, cut
    into four z-slabs by the layer boundaries. Every slab has the SAME hexagonal
    outline, so the solid is a prism and the mesh is exact: there is no
    cross-section step to triangulate and nothing to approximate.

    The electrode pad's margin (:data:`ELECTRODE_PAD_NM`) therefore does NOT
    widen the electrode -- it is folded into the outline of the whole stack
    instead, and :func:`footprint_error` reports how much area that adds around
    the wire. This is the one place the fixture departs from the paper's
    geometry, and it is reported rather than hidden. It changes the fringing
    field at the pad edge; it does not change which tets are "wire", because
    layers are separated by z, not by outline.

    Each tet is labelled by the layer its centroid falls in. The boundary
    planes are at known z, but **the mesh is not constrained to them**: this is
    a single solid with no internal facets, so TetGen is free to span an element
    across a boundary and the centroid then assigns the whole element to one
    layer. It does happen, and it is measured, not assumed -- at ``n_modes=20``
    about 10.9 % of tets straddle (see :func:`straddle_counts` and
    ``test_tets_straddle_layer_boundaries``). The label is therefore applied to
    elements whose permittivity is not uniform, which is why the field this
    fixture reports is not converged.
    """
    radius = circumradius_nm() * NM
    zs = [
        0.0,
        MIRROR_THICKNESS_NM * NM,
        (MIRROR_THICKNESS_NM + OXIDE_NM) * NM,
        (MIRROR_THICKNESS_NM + OXIDE_NM + HEIGHT_NM) * NM,
        (MIRROR_THICKNESS_NM + OXIDE_NM + HEIGHT_NM + ELECTRODE_THICKNESS_NM) * NM,
    ]
    labels = ["mirror", "oxide", "wire", "top"]
    assert len(zs) == len(labels) + 1

    hex_xy = [(radius * math.cos(math.pi / 6.0 + k * math.pi / 3.0),
               radius * math.sin(math.pi / 6.0 + k * math.pi / 3.0)) for k in range(6)]

    verts: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    rings = []
    for z in zs:
        ring = []
        for (x, y) in hex_xy:
            ring.append(len(verts))
            verts.append((x, y, z))
        rings.append(ring)

    # End caps: fan from vertex 0 of each ring. The bottom is wound to face -z
    # and the top to face +z.
    for k in range(1, len(rings[0]) - 1):
        faces.append((rings[0][0], rings[0][k + 1], rings[0][k]))
    for k in range(1, len(rings[-1]) - 1):
        faces.append((rings[-1][0], rings[-1][k], rings[-1][k + 1]))

    # Side walls: six quads per slab, each split into two triangles.
    for r in range(len(rings) - 1):
        lower, upper = rings[r], rings[r + 1]
        n = len(lower)
        for k in range(n):
            a, b = lower[k], lower[(k + 1) % n]
            c, d = upper[(k + 1) % n], upper[k]
            faces.append((a, b, c))
            faces.append((a, c, d))

    solid = trimesh.Trimesh(vertices=np.asarray(verts, dtype=np.float64),
                            faces=np.asarray(faces, dtype=np.int64), process=False)

    def label_fn(points, tets) -> np.ndarray:
        pts = np.asarray(points, dtype=np.float64)
        idx = np.asarray(tets)
        cent_z = pts[idx][:, :, 2].mean(axis=1)
        out = np.empty(cent_z.shape[0], dtype=object)
        for name, lo, hi in zip(labels, zs[:-1], zs[1:]):
            out[(cent_z >= lo) & (cent_z < hi)] = name
        # The top slab is closed at z_el_top, and a centroid can land exactly on
        # the last boundary only in a degenerate mesh; catch it rather than
        # leave it unlabelled.
        out[cent_z >= zs[-1]] = labels[-1]
        return out

    return solid, label_fn, zs, labels


def straddle_counts(mesh: dict) -> dict:
    """Measure how many tets cross a layer boundary, and by how much.

    The labelling in :func:`stacked_solid_with_labels` is per centroid, which
    is only exact if no element spans a boundary. This is the measurement that
    shows it does: an element "straddles" when its vertex z-values fall on both
    sides of a boundary plane.

    Returns the total, the straddling count and fraction, and per-boundary
    crossings, plus the widest z-span and the widest diagonal span overall.
    """
    if "planes_m" in mesh:
        zs = np.asarray(mesh["planes_m"], dtype=np.float64)
    else:
        # :func:`mesh_fixture` (the 1.6b lumpy fixture) predates planes_m and
        # carries only one outline, so its planes are the flat stack's.
        _s, _lf, zs, _l = stacked_solid_with_labels()
    pts = np.asarray(mesh["points_m"], dtype=np.float64)
    tets = np.asarray(mesh["tets"])
    z = pts[tets][:, :, 2]
    zlo, zhi = z.min(axis=1), z.max(axis=1)
    # Interior boundary planes only; the outer faces are not boundaries.
    inner = np.asarray(zs[1:-1], dtype=np.float64)
    straddles = (zlo[:, None] < inner[None, :]) & (zhi[:, None] > inner[None, :])
    n = int(tets.shape[0])
    n_straddle = int(np.any(straddles, axis=1).sum())
    span_z = zhi - zlo
    # Full diagonal extent of each element's bounding box.
    ext = pts[tets].max(axis=1) - pts[tets].min(axis=1)
    diag = np.linalg.norm(ext, axis=1)
    return {
        "n_tets": n,
        "n_straddle": n_straddle,
        "fraction": (n_straddle / n) if n else 0.0,
        "per_boundary_nm": {float(b / NM): int(straddles[:, i].sum())
                            for i, b in enumerate(inner)},
        "span_z_median_nm": float(np.median(span_z) / NM),
        "span_z_max_nm": float(span_z.max() / NM),
        "diag_max_nm": float(diag.max() / NM),
    }


def footprint_error():
    """Report the pad margin's effect on the outline area.

    The fixture gives every layer the wire's hexagonal outline, so the electrode
    is a hexagon of the wire's size rather than the paper's square pad with
    :data:`ELECTRODE_PAD_NM` of margin. This returns ``(hexagon_area,
    padded_square_area, ratio)`` -- the ratio is how much LARGER a square pad of
    that margin would have been. Reported so the departure is a number, not a
    silence.
    """
    radius = circumradius_nm() * NM
    pad = radius + ELECTRODE_PAD_NM * NM
    hexagon = 3 * math.sqrt(3) / 2 * radius ** 2
    square = (2 * pad) ** 2
    return hexagon, square, square / hexagon

def layers() -> list[tuple[str, float]]:
    """The stack as ``(name, thickness_m)`` bottom to top, for the layered mesher."""
    _solid, _label, zs, labels = stacked_solid_with_labels()
    return [(name, hi - lo) for name, lo, hi in zip(labels, zs[:-1], zs[1:])]


def hex_outline_m() -> list[tuple[float, float]]:
    """The wire's hexagon in metres, the same corners :func:`stacked_solid_with_labels` uses."""
    radius = circumradius_nm() * NM
    return [(radius * math.cos(math.pi / 6.0 + k * math.pi / 3.0),
             radius * math.sin(math.pi / 6.0 + k * math.pi / 3.0)) for k in range(6)]


def field_per_volt_1d() -> float:
    """The exact |E| in the wire per applied volt, for THIS fixture's geometry.

    Every layer has the same outline and both electrodes cover it, with natural
    (zero normal field) side walls, so the fixture is a 1-D series stack: the
    same displacement crosses oxide and wire and ``E_wire = V / (eps_wire *
    (t_ox/eps_ox + H/eps_wire))``. That is a property of the fixture's
    simplification (see :func:`footprint_error`), not of the paper's device,
    which has a pad wider than the wire and a 3-D fringing field.
    """
    s = OXIDE_NM * NM / EPS_SIO2 + HEIGHT_NM * NM / EPS_INP
    return 1.0 / (EPS_INP * s)


def mesh_fixture_layered(*, edge_nm: float = 200.0, n_across: int | None = None,
                         max_tets: int = 400_000, verbose: bool = False):
    """The stack meshed as CONFORMING layers (task 1.6c), same dict as :func:`mesh_fixture`.

    Every layer plane is an internal facet, so no tet straddles an interface
    and ``region_of_tet`` is TetGen's own region attribute, not a centroid
    guess; the oxide is split into ``n_across`` sub-slabs so it has at least
    that many elements across its 12 nm.
    """
    kw = {} if n_across is None else {"n_across": n_across}
    stack = layers()
    points_m, tets, region_of_tet = MESH.tetrahedralize_layers(
        hex_outline_m(), stack, edge_nm * NM, max_tets=max_tets,
        verbose=verbose, **kw)
    return {
        "points_m": points_m,
        "tets": tets,
        "parts": [name for name, _t in stack],
        "region_of_tet": region_of_tet,
        "eps_static": materials(),
        "probe": probe_point(),
        "planes_m": MESH.layer_planes(stack),
        "layers": stack,
    }


#: The layered convergence ladder: (bulk edge nm, oxide sub-slabs), coarse to
#: fine. Both levers refine together, the wire's edge and the oxide's.
LAYERED_LADDER = ((400.0, 1), (200.0, 2), (100.0, 3))


def pad_outline_m() -> list[tuple[float, float]]:
    """The ELECTRODE outline in metres: the wire's hexagon grown by the pad margin.

    Same 6-fold shape as :func:`hex_outline_m`, so the two rings nest exactly
    (same angles, larger radius) and the interface between them is an annulus.
    """
    radius = (circumradius_nm() + ELECTRODE_PAD_NM) * NM
    return [(radius * math.cos(math.pi / 6.0 + k * math.pi / 3.0),
             radius * math.sin(math.pi / 6.0 + k * math.pi / 3.0)) for k in range(6)]


#: Reference static permittivities for the surrounding medium (task 1.10d).
#:
#: ``"vacuum"`` is exactly 1.0 by definition. Paper 1's own simulation stands the
#: wire in AIR, so air (1.00059 at 300 K, ~1.0 to the precision this solver
#: carries) is used for the paper-1 check and is the DEFAULT. The value is a
#: property of vacuum/air, not a measurement of the device.
#:
#: ``"bcb"`` is benzocyclobutene, a common planarising polymer, eps_static ~= 2.65.
#: **This is a reference value, not a measurement**: the lead named 2.65 and no
#: datasheet was retrieved in this change, so treat it as a keyword, not a cited
#: number (unlike the InP and SiO2 values above, which carry their sources). It
#: exists to answer "what if the top contact sits on a real dielectric" -- it is a
#: SENSITIVITY case, not a claim about paper 1.
AMBIENT_EPS = {"vacuum": 1.0, "air": 1.0, "bcb": 2.65}

#: Default domain-box margin, as a multiple of the electrode pad radius: the box
#: half-width is ``DOMAIN_FACTOR * (circumradius + pad)``. 1.10d shows this
#: choice does not move the dot field (see the larger-box case in the bench).
DOMAIN_FACTOR = 3.0


def domain_half_width_nm(factor: float = DOMAIN_FACTOR) -> float:
    """Half-width of the surrounding domain box, in nm, measured from the axis.

    The box is a square in xy, not a hexagon: the medium is not a crystal
    facet, and a square's free rim is farther from the wire at its corners than
    its sides, which is the conservative choice for a natural boundary.
    """
    return factor * (circumradius_nm() + ELECTRODE_PAD_NM)


def ambient_outline_m(factor: float = DOMAIN_FACTOR) -> list[tuple[float, float]]:
    """The domain box as a 4-point outline in metres, for the per-region mesher."""
    h = domain_half_width_nm(factor) * NM
    return [(-h, -h), (h, -h), (h, h), (-h, h)]


def pad_outlines_m() -> list[list[tuple[float, float]]]:
    """One outline per layer for the pad-WIDENED stack (task 1.10c).

    Paper 1's device is a sandwich: gold mirror below, wire, top electrode
    above, with BOTH electrodes wider than the wire. That is a
    wide-narrow-wide stack, which 1.10a's monotonic-narrowing rule refused
    outright -- so the paper's own geometry could not be meshed at all until
    1.10c generalised the interface code.

    The electrodes get :func:`pad_outline_m`; the oxide and the wire keep the
    wire's own hexagon, because the oxide is grown ON the wire.
    """
    wire = hex_outline_m()
    pad = pad_outline_m()
    return {"mirror": pad, "oxide": wire, "wire": wire, "top": pad}


#: Thickness of each surrounding slab, in nm (task 1.10d). The medium exists
#: BELOW the mirror, ABOVE the top electrode and AROUND both -- on every side of
#: the device, because a medium that surrounds a device on three sides is a
#: different boundary condition pretending to be the same one.
AMBIENT_SLAB_NM = 400.0

#: The ambient is ONE region in three pieces (below, ring, above). The mesher
#: requires unique layer names, so the pieces are named; they are all
#: :data:`AMBIENT_PART`'s material.
AMBIENT_BELOW = "ambient_below"
AMBIENT_RING = "ambient_ring"
AMBIENT_ABOVE = "ambient_above"

#: Every meshed part that is the surrounding medium.
AMBIENT_PARTS = (AMBIENT_BELOW, AMBIENT_RING, AMBIENT_ABOVE)

#: How close two vertices must be, in nm, to be the same point across the
#: device/medium interface. The mesher's finest edge here is ~3 nm and the
#: smallest feature 12 nm, so this is far below any real separation; it is far
#: above the round-off of the canonical scaling (~1e-9 of the box size).
WELD_TOL_NM = 1e-4

#: The region label the SOLVE uses for the medium -- one label for the three
#: pieces, so "the ambient has one permittivity" is a property of the mesh
#: handed to the solver, not of a lookup that happens to agree three times.
AMBIENT_PART = "ambient"

def meshed_layers() -> list[tuple[str, float]]:
    """The meshed device stack, bottom to top -- four layers, no ambient.

    The device alone, with the paper's own thicknesses and the pad's outlines.
    The meshing of this device in a medium is :func:`mesh_fixture_padded`'s job;
    what matters here is that NOTHING about the device changed in 1.10d. Its
    geometry is 1.10c's, unchanged, and the medium is added around it.
    """
    return layers()


def mesh_fixture_padded(*, edge_nm: float = 200.0, n_across: int | None = None,
                        max_tets: int = 400_000, verbose: bool = False,
                        ambient: str = "air", factor: float = DOMAIN_FACTOR):
    """The paper's real footprint SURROUNDED by a medium (tasks 1.10c, 1.10d).

    ``ambient`` names the medium (:data:`AMBIENT_EPS`: ``"air"``, ``"vacuum"``,
    ``"bcb"``); ``factor`` sets the domain box (:func:`domain_half_width_nm`).

    Geometry. 1.10c meshed the device with each layer's own outline --
    electrodes at r = 299.4 nm over a wire of r = 239.4 nm -- but meshed NO
    medium around it: the pad overhang was empty space, the free nodes stopped
    at the wire's rim, and the solve was the 1-D series stack again. 1.10d adds
    the medium as an ordinary region with its own permittivity, like any part,
    because the owner's product is the general solver and not a paper-1 case.
    The device itself is untouched.

    How the medium is meshed, and why this way. The medium is ONE region in
    three pieces: a slab below the mirror, a ring around the device up to the
    pad's outline, and a slab above the top electrode -- so the device is
    enclosed on every side. Pieces nest inside the domain box, and the box's
    four side walls form one continuous rim through all of them; its top and
    bottom are the slabs' own caps.

    The alternative -- ambient slabs as the STACK'S outermost layers, as wide as
    the box -- was tried first and is not used. It is geometrically legal (the
    box contains the pad contains the wire, so every adjacent pair nests) but
    IT CRASHES TETGEN: the C library aborts with ``malloc(): invalid size``
    inside ``tetrahedralize``, reproducibly at 10506 tets for the device alone
    and at any size with the ambient slabs added. The crash is in TetGen, not in
    the PLC (which is closed and edge-manifold), so the fixture nests the medium
    inside the box instead of making it the box. Recorded rather than retried:
    a native abort is a tier-1 test's worst failure mode, and a shape that does
    not provoke it is available.

    Sizing the medium coarser than the device is NOT offered, and task 1.10f
    tried: per-region volumes through ``add_region`` are measured INERT
    (``mse_meshing`` records a nine-order sweep that left the mesh
    byte-identical), and this wrapper drops the keyword ``maxvolume``
    altogether -- only the ``switches`` string's ``-a`` reaches TetGen. What
    actually sets element size is the PLC's own facets (module docstring, claim
    2), so grading the medium needs COARSE AMBIENT FACETS, and the ambient
    outline is four points per box wall. Raising ``edge_nm`` barely moves the
    count for the same reason: the outlines are already the resolution. So the
    medium is meshed at the device's resolution and the convergence knob is the
    BOX SIZE, which is what ``bench_box_convergence`` sweeps.

    Boundary, stated because it was chosen: a NATURAL (zero-normal-field)
    condition on the domain box's sides and top and bottom. That is
    :func:`mse_electrostatics.solve`'s condition -- the absence of a boundary
    term, so nothing is imposed -- and it is the right one for a finitely biased
    device whose enclosing medium is large enough that the field left over at
    the wall is small. The bench's larger-box case is what says the box is large
    enough. It is NOT right for a device with a grounded enclosure; paper 1 has
    no such electrode.
    """
    # No ambient guard here: this function validates via ``materials(ambient)``
    # when it assembles the solve input, and that raises on an unknown name. A
    # second check was written here and then DELETED (task 1.10d review,
    # 2026-11-06) because deleting it broke no test: ``materials`` is called on
    # every path through this function, so the copy was unreachable. It also
    # would have been the weaker guard -- it ran AFTER tetrahedralization, so a
    # typo would have cost a full mesh to discover.
    kw = {} if n_across is None else {"n_across": n_across}
    edge = edge_nm * NM

    device = meshed_layers()
    by_name = pad_outlines_m()
    # ONE mesh for the device and its medium (task 1.10e). The 1.10d version
    # meshed them separately and distance-welded the seam; two independent
    # meshes share no elements, so the solve could not couple them, and the
    # medium's PLC was filled straight through the device. Here the
    # device/medium interface is a facet of a single PLC, so interface nodes are
    # shared by construction.
    z_lo, z_hi = 0.0, sum(t for _n, t in device)
    box = ambient_outline_m(factor)
    points, tets, region, n_dev = MESH.tetrahedralize_surrounded(
        [by_name[name] for name, _t in device], device, box, edge,
        pad_m=AMBIENT_SLAB_NM * NM, max_tets=max_tets, verbose=verbose, **kw)
    if n_dev != len(device):
        raise AssertionError(
            f"internal error: the mesher reported {n_dev} device layers for a "
            f"{len(device)}-layer stack")
    # No weld is needed or possible now: the medium's interface vertices ARE the
    # device's. ``_combined`` is kept as the assembler, with the join step gone.
    return _assembled(points, tets, region, device, ambient, factor=factor,
                      n_dev=n_dev, z_lo=z_lo, z_hi=z_hi)


def _assembled(points, tets, region, device, ambient, *, factor, n_dev,
               z_lo, z_hi):
    """The solve input for a mesh that already contains the medium.

    Replaces 1.10d's ``_combined``. The two differences that matter: there is no
    distance weld (the interface is shared, so there is nothing to weld), and the
    medium's region label is ``n_dev`` as the MESHER produced it rather than a
    label the caller stamped on afterwards.
    """
    points = np.asarray(points, dtype=float)
    tets = np.asarray(tets, dtype=np.int64)
    region = np.asarray(region, dtype=np.int64)
    n_medium = int((region == n_dev).sum())
    if n_medium == 0:
        raise ValueError(
            "the mesh has no medium elements: the surrounding region was not "
            "seeded, and the solve would be a device in no ambient at all")
    used = np.unique(tets.ravel())
    if len(used) != len(points):
        compact = np.full(len(points), -1, dtype=np.int64)
        compact[used] = np.arange(len(used))
        points = points[used]
        tets = compact[tets]

    parts = [name for name, _t in device] + [AMBIENT_PART]
    layers = list(device) + [(AMBIENT_PART, None)]
    return {
        "points_m": points,
        "tets": tets,
        "parts": parts,
        "region_of_tet": region,
        "eps_static": materials(ambient),
        "probe": probe_point(),
        "planes_m": MESH.layer_planes(device),
        "layers": layers,
        "outlines": [pad_outlines_m()[name] for name, _t in device]
                    + [ambient_outline_m(factor)],
        "ambient": ambient,
        "n_medium_tets": n_medium,
        "device_z_m": (z_lo, z_hi),
        "dot": probe_point(),
    }


def inside(points_m, tets, p) -> bool:
    """Whether ``p`` lies inside the volume meshed by ``tets``.

    ``E.field_at`` is the judge of whether a point is inside the *solved* mesh,
    but it raises one message for inside-an-electrode, outside-the-solid and
    numerical failure alike. Moving a probe laterally and reading that message
    cannot tell "past the pad's rim" (a real edge, whose field should be shown)
    from "off the mesh" (an artefact). This asks the mesh, so a sweep can report
    where it walked off the device.

    A point inside a closed, positively oriented tetrahedralization is enclosed
    by the tets around it, so for those tets every face outward normal points
    AWAY from the point. Testing each candidate tet's four faces directly is
    exact; a signed-volume sum is not an adequate substitute here, because a
    mixed sign in the sum says the point is enclosed by OTHERS but not by this
    tet, which is precisely the discrimination needed.

    Candidates are the tets owning the ``k`` nearest vertices: a superset of the
    star around any point, cheap, and a cold fallback if nothing comes back.
    """
    from scipy.spatial import cKDTree
    pts = np.asarray(points_m, dtype=float)
    tets = np.asarray(tets)
    p = np.asarray(p, dtype=float)
    _d, vi = cKDTree(pts).query(p, k=min(16, len(pts)))
    vi = np.atleast_1d(vi)
    cand = np.nonzero(np.isin(tets, vi).any(axis=1))[0]
    if len(cand) == 0:
        cand = np.arange(len(tets))

    def enclosed(i):
        four = pts[tets[i]]
        faces = ((1, 2, 3, 0), (0, 2, 3, 1), (0, 1, 3, 2), (0, 1, 2, 3))
        for a, b, c, o in faces:
            n = np.cross(four[b] - four[a], four[c] - four[a])
            if np.dot(n, four[o] - four[a]) * np.dot(n, p - four[a]) < 0:
                return False
        return True

    return any(enclosed(i) for i in cand[:4000])


def field_at_the_dot(solution: dict) -> np.ndarray:
    """E at paper 1's dot, in V/m per applied volt.

    The dot's position is the paper's only positional fact about it: "a QD
    emitter placed on-axis at 30 nm below the top" (Fig. 2 caption, p. 5). That
    is :func:`probe_point`, so the dot and the probe are the same point and it
    would be wrong to give them different names -- the name here says what the
    measurement is FOR.

    ``field_at`` refuses a point that lies in an electrode, so this raises
    rather than returning a number if the pad or mirror ever engulfed the dot.
    """
    return E.field_at(solution, probe_point())


def field_at_the_dot_at(solution: dict, xy_nm) -> np.ndarray:
    """:func:`field_at_the_dot`, moved laterally: the same z, offset to ``xy_nm``.

    Used to show the field's SHAPE near the dot -- the axis against the pad's
    rim. ``E.field_at`` refuses a point it cannot sample rather than
    extrapolating, so this raises at the mesh's edge and :func:`scan_at_the_dot`
    is the caller that walks in from there.
    """
    x, y = (float(v) for v in xy_nm)
    p = probe_point()
    return E.field_at(solution, np.array([x * NM, y * NM, p[2]]))


def scan_at_the_dot(solution: dict, xs_nm, y_nm: float = 0.0,
                    *, z_nm: float | None = None) -> dict:
    """E_z at the dot's z along ``xs_nm``, recording WHERE EACH SAMPLE COMES FROM.

    Returns ``xs_nm``, ``ez``, ``inside`` (the device volume covers the point),
    ``part`` (the region whose element the sample was taken in) and
    ``edge_nm`` (first x the mesh refuses).

    The ``part`` column is the point of this function. A lateral sweep at a
    fixed z crosses the top pad, then the gap beyond its rim, then the ambient,
    and E is piecewise CONSTANT within each region because ``phi`` is linear on
    an element. A number quoted without its region is therefore ambiguous:
    measured on this fixture, E_z at the dot is -707.5 kV/m/V on the axis and
    -0.000 kV/m/V at x = 210 nm -- the second is inside the ambient, not a field
    the device does not have. The rim is where the part changes, so the part is
    read from the containing element and reported instead of being guessed from
    the value.
    """
    from mse_electrostatics import _barycentric, BARY_EPS

    xs = np.asarray(xs_nm, dtype=float)
    pts_m = np.asarray(solution["points_m"])
    tets = np.asarray(solution["tets"])
    names = solution["tet_part_name"]   # a list, not an array
    ez = np.full(len(xs), np.nan)
    part = np.empty(len(xs), dtype=object)
    cov = np.zeros(len(xs), dtype=bool)
    p0 = probe_point()
    z_m = p0[2] if z_nm is None else float(z_nm) * NM
    for i, x in enumerate(xs):
        p = np.array([x * NM, y_nm * NM, z_m])
        cov[i] = inside(pts_m, tets, p)
        lam = _barycentric(pts_m, tets, p)
        hit = np.flatnonzero(np.all(lam >= -BARY_EPS, axis=1))
        if hit.size:
            # A point ON an interface lies in tets on BOTH sides of it. Taking
            # the lowest index reported the 60 nm top plate as 'wire' whenever
            # the two met exactly -- measured at x = 0..205, z = 1477 nm, where
            # the reported part was 'wire' and E the wire's. Prefer the
            # CONTAINING tet with the largest barycentric minimum (the point is
            # most interior to it), which resolves an exact interface to the
            # region the point is unambiguously inside rather than by numbering.
            part[i] = names[int(hit[np.argmax(lam[hit].min(axis=1))])]
        else:
            part[i] = None
        try:
            ez[i] = E.field_at(solution, p)[2]
        except ValueError:
            continue
    finite = np.isfinite(ez)
    edge = float(xs[~finite].min()) if not finite.all() else float("nan")
    return {"xs_nm": xs, "ez": ez, "inside": cov, "part": part, "edge_nm": edge}


def mesh_fixture(*, max_tets: int = 60_000, n_modes: int = 4, verbose: bool = False):
    """Tetrahedralise the stack and return the solver's own arguments.

    Returns a dict of exactly the keyword arguments :func:`solve_wire` passes to
    :func:`mse_electrostatics.solve`, plus ``probe``.

    ``n_index=1.0`` because the electrical solver has no refractive index and
    the optical edge rule must not drive this mesh.
    """
    solid, label_fn, _zs, labels = stacked_solid_with_labels()
    points_m, tets, _ = MESH.tetrahedralize(
        solid, "m", n_modes=n_modes, n_index=1.0,
        max_tets=max_tets, verbose=verbose,
    )
    # ``solve`` wants a per-tet integer region id, not a name: part names live in
    # ``parts`` and ``region_of_tet`` indexes into it.
    named = label_fn(points_m, tets)
    index_of = {name: i for i, name in enumerate(labels)}
    region_of_tet = np.asarray([index_of[n] for n in named], dtype=np.int64)
    return {
        "points_m": points_m,
        "tets": tets,
        "parts": list(labels),
        "region_of_tet": region_of_tet,
        "eps_static": materials(),
        "probe": probe_point(),
    }


def solve_wire(mesh: dict, volts: float, *, method: str = "auto", budget=None) -> dict:
    """Solve the fixture with ``top`` at ``volts`` and the mirror at 0 V.

    The mirror is the back electrode and is held at 0; the top electrode takes
    the applied potential. That is the gate configuration design.md describes
    ("the gold mirror is the back electrode ... plus a top electrode. The field
    at the dot is set by V_G").
    """
    electrodes = {name: 0.0 for name in ELECTRODE_PARTS if name in mesh["parts"]}
    if "top" in electrodes:
        electrodes["top"] = volts
    if "top" not in electrodes or len(electrodes) < 2:
        # Without the top electrode the potentials below are all the same value
        # and the solve returns a constant field of zero -- a number, not an
        # answer. Measured: with the top pad missing from ``parts`` the solve
        # ran happily and every node came back at 0 V.
        raise ValueError(
            f"solve_wire needs both electrodes; mesh parts are {mesh['parts']}"
        )
    result = E.solve(
        mesh["points_m"], mesh["tets"], mesh["parts"], mesh["region_of_tet"],
        mesh["eps_static"], electrodes, method=method, budget=budget,
    )
    # The medium's outer walls carry no Dirichlet value of their own, and a
    # solve with no value set on them leaves the medium floating: the free set
    # then comes back at ~0 V everywhere (measured: 87% of free nodes at
    # exactly 0.0), which reads as a field-free medium rather than as a solve
    # that never propagated the applied potential past the pad's rim.
    if mesh.get("ambient") is not None:
        expected = volts
        got = float(np.max(np.abs(np.asarray(result["phi"]) - expected)))
        if got < 0.5 * abs(expected) and abs(expected) > 0:
            raise RuntimeError(
                "the solved potential never reaches the applied value anywhere "
                f"(max |phi - {expected}| = {got:.3e}): the medium is floating, "
                "which makes a zero field outside the pad an artefact of the "
                "boundary condition rather than a result"
            )
    return result


def wire_field_per_volt(mesh: dict, *, method: str = "auto", budget=None) -> dict:
    """The field at the probe, per applied volt, in V/m per V.

    Solved once at 1 V and divided by 1 V: the problem is linear, and solving at
    1 V keeps the number a pure geometry-and-permittivity quantity that does not
    depend on the voltage chosen. :func:`field_report` checks the linearity
    separately rather than assuming it.

    Returns ``field_per_volt`` (the vector, V/m per V), ``magnitude_per_volt``,
    ``component_z_per_volt`` and the solve's own diagnostics.
    """
    sol = solve_wire(mesh, 1.0, method=method, budget=budget)
    field = E.field_at(sol, mesh["probe"])
    return {
        "field_per_volt": field,
        "magnitude_per_volt": float(np.linalg.norm(field)),
        "component_z_per_volt": float(field[2]),
        "method": sol["method"],
        "n_free": int(sol["n_free"]),
        "residual": sol["residual"],
    }


def field_report(mesh: dict, *, method: str = "auto", budget=None) -> dict:
    """The per-volt field plus the two linearity checks that make it trustworthy.

    A single solve at 1 V is only meaningful if the operator really is linear in
    the boundary values. This solves at 2 V and at -1 V and asserts the ratios,
    so the report carries its own evidence rather than asking the reader to
    assume linearity.
    """
    base = wire_field_per_volt(mesh, method=method, budget=budget)
    two = E.field_at(solve_wire(mesh, 2.0, method=method, budget=budget),
                     mesh["probe"]) / 2.0
    neg = E.field_at(solve_wire(mesh, -1.0, method=method, budget=budget),
                     mesh["probe"]) / -1.0
    out = dict(base)
    out["linearity"] = {
        "two_v_over_two_vs_one_v": float(np.max(np.abs(two - base["field_per_volt"]))),
        "minus_one_v_vs_one_v": float(np.max(np.abs(neg - base["field_per_volt"]))),
    }
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--coarse", action="store_true",
                    help="a mesh small enough for a tier-1 test")
    ap.add_argument("--max-tets", type=int, default=None)
    ap.add_argument("--method", default="auto", choices=sorted(E.METHODS))
    ap.add_argument("--convergence", action="store_true",
                    help="run at n_modes 20/60/120 and report the spread (the "
                         "number that says whether any value here is usable)")
    ap.add_argument("--one-part", action="store_true",
                    help="mesh with the old one-part, centroid-labelled path (1.6b)")
    ap.add_argument("--layered-convergence", action="store_true",
                    help="the same check on the conforming layered mesh (task 1.6c)")
    ap.add_argument("--budget", type=float, default=None,
                    help="memory budget in GiB; refused before assembly if over")
    args = ap.parse_args(argv)

    max_tets = args.max_tets if args.max_tets is not None else (8_000 if args.coarse else 60_000)
    budget = None if args.budget is None else int(args.budget * 2**30)

    print(f"UNVALIDATED fixture -- paper 1's wire with a top electrode")
    print(f"  wire    H = {HEIGHT_NM:.0f} nm, D = {DIAMETER_NM:.0f} nm "
          f"(paper 1 p. 3); circumradius {circumradius_nm():.1f} nm via 2s = 1.14 D")
    print(f"  oxide   {OXIDE_NM:.0f} nm SiO2, eps_s = {EPS_SIO2}")
    print(f"  wire    eps_s = {EPS_INP} (Ioffe, 300 K) -- NOT n^2 = 11.83")
    print(f"  probe   on axis, {PROBE_BELOW_TOP_NM:.0f} nm below the top (Fig. 2 caption)")

    if args.layered_convergence:
        # Task 1.6c: the same check on the CONFORMING layered mesh.
        print()
        print("  convergence on the LAYERED mesh (internal facets at every plane):")
        exact = field_per_volt_1d()
        values = []
        for edge_nm, k in LAYERED_LADDER:
            m = mesh_fixture_layered(edge_nm=edge_nm, n_across=k)
            st = MESH.layer_straddles(m["points_m"], m["tets"], m["region_of_tet"],
                                      m["planes_m"])
            r = wire_field_per_volt(m, method=args.method, budget=budget)
            values.append(r["magnitude_per_volt"])
            print(f"    edge {edge_nm:5.0f} nm, oxide x{k}: {len(m['tets']):7d} tets, "
                  f"straddling {st['crossing']}  |E| = "
                  f"{r['magnitude_per_volt']:.9g} V/m per V  "
                  f"(rel to 1-D {r['magnitude_per_volt'] / exact - 1:+.2e})")
        lo, hi = min(values), max(values)
        print(f"    spread {(hi - lo) / lo:.3e}; exact 1-D value for this fixture's "
              f"geometry {exact:.9g} V/m per V")
        return 0

    if args.convergence:
        # The measured headline of this fixture: the answer moves with the mesh,
        # and not monotonically, because a 12 nm oxide inside a 1567 nm stack
        # cannot be resolved by a one-part mesh. Printed as a RANGE so nobody
        # can lift a single figure out of it.
        print()
        print("  convergence in n_modes (the only lever a one-part mesh has):")
        values = []
        for nm in (20, 60, 120):
            m = mesh_fixture(max_tets=400_000, n_modes=nm)
            r = wire_field_per_volt(m, method=args.method, budget=budget)
            values.append(r["magnitude_per_volt"])
            print(f"    n_modes {nm:4d}: {len(np.asarray(m['tets'])):7d} tets  "
                  f"|E| = {r['magnitude_per_volt']:.6g} V/m per V")
        lo, hi = min(values), max(values)
        print(f"    spread {(hi - lo) / lo:.1%}  -- NOT converged, so no single "
              f"value above is quotable")
        return 0

    if args.one_part:
        mesh = mesh_fixture(max_tets=max_tets)
    else:
        mesh = mesh_fixture_layered(edge_nm=400.0 if args.coarse else 200.0)
    n_tets = int(np.asarray(mesh["tets"]).shape[0])
    print(f"  mesh    {int(np.asarray(mesh['points_m']).shape[0])} nodes, {n_tets} tets")

    rep = field_report(mesh, method=args.method, budget=budget)
    print()
    print(f"  E at the probe, per volt:  |E| = {rep['magnitude_per_volt']:.6g} V/m per V")
    print(f"                             Ez  = {rep['component_z_per_volt']:.6g} V/m per V")
    print(f"  solver: {rep['method']}, {rep['n_free']} free nodes")
    lin = rep["linearity"]
    print(f"  linearity: 2V/2 vs 1V max|dE| = {lin['two_v_over_two_vs_one_v']:.3g}; "
          f"-1V vs 1V = {lin['minus_one_v_vs_one_v']:.3g}")
    print()
    if args.one_part:
        print("  NOT CONVERGED: this one-part mesh cannot resolve the 12 nm oxide, and the")
        print("  value above moves ~40% across mesh sizes (run --convergence). Do not quote it.")
    else:
        print(f"  layered mesh: converged (run --layered-convergence); exact 1-D value "
              f"{field_per_volt_1d():.9g} V/m per V")
        print("  UNVALIDATED against the paper's device: every layer has the wire's")
        print("  outline (footprint_error), so this is a 1-D stack, not the 3-D pad.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
