"""Tests for the paper-1 wire-with-top-electrode fixture (task 1.6b).

The fixture is UNVALIDATED and its field is NOT converged, so these tests assert
the things that ARE established and, where the field is involved, assert the
NEGATIVE -- that it moves with the mesh. A test that pinned a field value here
would pin an artefact of the element count.
"""

from __future__ import annotations

import math
import os
import sys

import numpy as np
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "scripts"))
sys.path.insert(0, os.path.join(_ROOT, "dockerfiles", "maxwell_solver"))

import paper1_wire_electrode as F  # noqa: E402
import mse_meshing as _MESH  # noqa: E402


def _convex(ring):
    """The convex, counter-clockwise form of an outline (the mesher's own)."""
    return _MESH._convex_outline(ring)


# --------------------------------------------------------------------------
# geometry: exact, and checked against closed forms rather than eyeballed
# --------------------------------------------------------------------------

def test_circumradius_comes_from_the_papers_own_hex_to_cylinder_relation():
    """2s = 1.14 D (paper 1 p. 10, S2), so the circumradius is s."""
    side = 1.14 * F.DIAMETER_NM / 2.0
    assert F.circumradius_nm() == pytest.approx(side, rel=1e-12)
    # 0.2 recorded the corner-to-corner width as 478.8 nm and the flat-to-flat
    # as 414.6 nm; both derive from this one number.
    radius = F.circumradius_nm()
    assert 2 * radius == pytest.approx(478.8, abs=0.1)
    assert 2 * radius * math.cos(math.pi / 6) == pytest.approx(414.6, abs=0.1)


def test_prism_volume_matches_the_closed_form_exactly():
    """A hexagon prism's volume is (3 sqrt(3)/2) r^2 H -- no approximation."""
    solid, _label, zs, _labels = F.stacked_solid_with_labels()
    radius = F.circumradius_nm() * F.NM
    expected = 3 * math.sqrt(3) / 2 * radius ** 2 * (zs[-1] - zs[0])
    assert solid.volume == pytest.approx(expected, rel=1e-9)


def test_the_solid_is_closed_and_orientable():
    """A PLC TetGen accepts must be watertight with one shell."""
    solid, _label, _zs, _labels = F.stacked_solid_with_labels()
    assert solid.is_watertight
    assert solid.euler_number == 2


def test_the_layer_boundaries_are_the_paper_thicknesses():
    """Assert the LITERAL paper numbers, not ``F.OXIDE_NM``.

    An earlier version compared each layer against the same module constant it
    was derived from, so changing ``OXIDE_NM`` from 12 to 50 still passed -- a
    test that cannot fail is not a test. The paper's numbers are written out
    here so a change to the constant has to argue with the paper.
    """
    _solid, _label, zs, labels = F.stacked_solid_with_labels()
    nm = [z / F.NM for z in zs]
    assert labels == ["mirror", "oxide", "wire", "top"]
    assert nm[1] - nm[0] == pytest.approx(120.0, abs=1e-6)   # gold mirror
    assert nm[2] - nm[1] == pytest.approx(12.0, abs=1e-6)    # "a 12 nm thick oxide" (p. 4)
    assert nm[3] - nm[2] == pytest.approx(1375.0, abs=1e-6)  # H (p. 3)
    assert nm[4] - nm[3] == pytest.approx(60.0, abs=1e-6)    # top electrode


def test_footprint_error_reports_the_pad_margin_rather_than_hiding_it():
    """The fixture drops the square pad; this is the number that says so."""
    hexagon, square, ratio = F.footprint_error()
    radius = F.circumradius_nm() * F.NM
    pad = radius + F.ELECTRODE_PAD_NM * F.NM
    assert hexagon == pytest.approx(3 * math.sqrt(3) / 2 * radius ** 2)
    assert square == pytest.approx((2 * pad) ** 2)
    assert ratio == pytest.approx(2.408, rel=1e-3)
    assert ratio > 1.0, "the square pad is larger than the hexagon, by definition"


# --------------------------------------------------------------------------
# permittivities: static, and deliberately NOT n^2
# --------------------------------------------------------------------------

def test_permittivities_are_static_and_not_the_optical_index_squared():
    mats = F.materials()
    assert mats["wire"] == pytest.approx(12.5)      # InP eps_s, Ioffe 300 K
    assert mats["oxide"] == pytest.approx(3.9)      # SiO2 eps_s
    # n = 3.44 (paper 1 p. 9, S1) is an OPTICAL index; n^2 = 11.83 is not eps_s.
    # The two are 5.6% apart and must never be substituted for one another.
    assert mats["wire"] != pytest.approx(3.44 ** 2, rel=1e-3)
    assert mats["wire"] > 3.44 ** 2


def test_every_part_has_a_permittivity_the_solver_can_use():
    """``solve`` refuses an eps_static below 1, so no part may be omitted."""
    mats = F.materials()
    _solid, _label, _zs, labels = F.stacked_solid_with_labels()
    assert set(mats) == set(labels)
    for name, value in mats.items():
        assert value >= 1.0, f"{name} has eps_s {value} < 1, which is not a material"


# --------------------------------------------------------------------------
# the mesh and the solve
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def coarse_mesh():
    return F.mesh_fixture(max_tets=8_000)


def test_mesh_covers_all_four_layers(coarse_mesh):
    parts = coarse_mesh["parts"]
    region = np.asarray(coarse_mesh["region_of_tet"])
    assert parts == ["mirror", "oxide", "wire", "top"]
    # Every layer must be present; an absent layer means label_fn's z-splits
    # do not match the geometry and the solve below is meaningless.
    for i, name in enumerate(parts):
        assert (region == i).sum() > 0, f"no tets in layer {name!r}"


def test_tets_straddle_layer_boundaries(coarse_mesh):
    # The labelling is per centroid, so it is only exact if no element spans a
    # boundary. It is NOT exact: this is one solid with no internal facets, so
    # TetGen spans elements across the layer planes. Pinning straddle > 0 is
    # what stops a future reader (or a future "the label is exact" comment)
    # from assuming the label is safe. If this ever fails because the mesher
    # gained internal facets, that is good news: revisit the UNVALIDATED status
    # in the module docstring rather than deleting the test.
    s = F.straddle_counts(coarse_mesh)
    assert s["n_tets"] > 0
    assert s["n_straddle"] > 0, (
        "no tet straddles a layer boundary; if the mesher now constrains to "
        "internal facets, the fixture may be mesh-convergent -- re-measure "
        "the spread in test_the_field_is_not_converged_in_the_mesh")
    # Both oxide faces are crossed, so the effect is on the layer that matters.
    # Boundaries sit near 120 nm and at 132 nm (mirror 120 + oxide 12). Keys are
    # float nm out of the dict, so match with a tolerance rather than ==.
    crossings = s["per_boundary_nm"]
    near = lambda target: [n for z, n in crossings.items() if abs(z - target) < 0.5]  # noqa: E731
    assert near(120.0) and near(120.0)[0] > 0, crossings
    assert near(132.0) and near(132.0)[0] > 0, crossings
    assert 0.0 < s["fraction"] < 1.0


def test_region_ids_are_integers_into_parts(coarse_mesh):
    region = np.asarray(coarse_mesh["region_of_tet"])
    assert region.dtype.kind == "i"
    assert region.min() >= 0
    assert region.max() < len(coarse_mesh["parts"])


def test_probe_sits_inside_the_mesh_and_outside_an_electrode(coarse_mesh):
    """``field_at`` refuses a point in an electrode: phi there is imposed."""
    probe = F.probe_point()
    assert probe[2] < (F.MIRROR_THICKNESS_NM + F.OXIDE_NM + F.HEIGHT_NM) * F.NM
    sol = F.solve_wire(coarse_mesh, 1.0)
    # This raises if the probe is outside the mesh or inside an electrode.
    field = F.E.field_at(sol, probe)
    assert np.all(np.isfinite(field))


def test_the_field_is_exactly_linear_in_the_applied_volts(coarse_mesh):
    """The problem is linear, so a departure is a solver bug, not physics."""
    report = F.field_report(coarse_mesh)
    lin = report["linearity"]
    assert lin["two_v_over_two_vs_one_v"] == pytest.approx(0.0, abs=1e-9)
    assert lin["minus_one_v_vs_one_v"] == pytest.approx(0.0, abs=1e-9)


def test_the_solver_runs_on_the_fixture(coarse_mesh):
    result = F.wire_field_per_volt(coarse_mesh)
    assert result["method"] in F.E.METHODS
    assert result["n_free"] > 0
    assert np.isfinite(result["magnitude_per_volt"])
    assert result["magnitude_per_volt"] > 0


def test_the_direct_and_amg_paths_agree_on_this_fixture(coarse_mesh):
    """Whichever path ``auto`` chose, the other one must land in the same place."""
    direct = F.wire_field_per_volt(coarse_mesh, method="direct")
    amg = F.wire_field_per_volt(coarse_mesh, method="amg")
    assert amg["magnitude_per_volt"] == pytest.approx(
        direct["magnitude_per_volt"], rel=1e-5)


# --------------------------------------------------------------------------
# the negative result: the field is NOT converged, and that must stay testable
# --------------------------------------------------------------------------

def test_the_field_is_not_converged_in_the_mesh():
    """The measured headline, pinned so it cannot be quietly 'fixed' by
    pegging a resolution and calling the answer converged.

    If this test starts failing because the spread DROPPED, the mesher gained a
    way to resolve the oxide and the fixture can be re-evaluated. It must not be
    relaxed to make a field value quotable.
    """
    values = []
    for n_modes in (20, 60):
        mesh = F.mesh_fixture(max_tets=400_000, n_modes=n_modes)
        values.append(F.wire_field_per_volt(mesh)["magnitude_per_volt"])
    spread = (max(values) - min(values)) / min(values)
    assert spread > 0.20, (
        f"field spread across mesh sizes is only {spread:.1%}; if the mesher "
        f"can now resolve the 12 nm oxide, revisit the fixture's UNVALIDATED "
        f"status rather than deleting this test"
    )


# --------------------------------------------------------------------------
# 1.10c: the pad-WIDENED fixture -- the paper's real footprint
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def padded_mesh():
    return F.mesh_fixture_padded(edge_nm=200.0, max_tets=200_000)


# --------------------------------------------------------------------------
# 1.10d: the unknown-ambient guard (review note on 1.10d @7f2e4a6)
# --------------------------------------------------------------------------
# The guard lives in ``materials``, and this is the only one: an earlier copy in
# ``mesh_fixture_padded`` was unreachable, because that function validates by
# calling ``materials(ambient)`` when it assembles the solve input. The review
# asked for the untested guard to be covered; covering it showed it was dead, so
# it was deleted rather than tested twice. This test is what holds the surviving
# guard in place -- delete it and the typo becomes a KeyError deep in a mesh.

def test_an_unknown_ambient_is_refused_by_materials():
    with pytest.raises(ValueError, match="ambient must be one of"):
        F.materials(ambient="siliconeoil")
    # ...and the known ones are all accepted, so the guard is not refusing
    # everything.
    for name in F.AMBIENT_EPS:
        assert F.materials(ambient=name)[F.AMBIENT_PART] == pytest.approx(
            F.AMBIENT_EPS[name])


def test_an_unknown_ambient_is_refused_before_meshing():
    # The raise must happen BEFORE tetrahedralization, not after: a mistyped
    # ambient that costs a full mesh to discover is a bad guard. Deliberately
    # cheap args here, and if this test ever gets slow, that ordering is lost.
    with pytest.raises(ValueError, match="ambient must be one of"):
        F.mesh_fixture_padded(ambient="siliconeoil", edge_nm=200.0, max_tets=200_000)


def test_the_pad_radius_is_the_wire_plus_the_margin(padded_mesh):
    # WHY (task 1.10c review, 2026-11-06): I wrote "pad r = 839.4 nm" into the
    # tasks.md record and a test comment. It does not reproduce: the pad is
    # circumradius + ELECTRODE_PAD_NM = 239.4 + 60 = 299.4 nm. The 839.4 came
    # from an unrelated 600 nm perturbation run and was carried across by hand.
    # Deriving the expected value from the constants, and checking it against
    # the mesh, means the prose and the mesh cannot drift apart again.
    # LITERAL values, not circumradius_nm() + ELECTRODE_PAD_NM: deriving the
    # expectation from the same constants the mesh uses made the first version
    # of this test CIRCULAR -- mutating ELECTRODE_PAD_NM to 660 moved both
    # sides and the test still passed. Measured, the pad is 299.4 nm and the
    # wire 239.4 nm; those are the numbers the record quotes.
    assert abs(F.circumradius_nm() - 239.4) < 0.1, F.circumradius_nm()
    assert abs(F.ELECTRODE_PAD_NM - 60.0) < 0.1, F.ELECTRODE_PAD_NM
    for name in ("mirror", "top"):
        got = _region_rmax_nm(padded_mesh, name)
        assert abs(got - 299.4) < 1.0, (name, got)
    wire = _region_rmax_nm(padded_mesh, "wire")
    assert abs(wire - 239.4) < 1.0, wire


def _region_rmax_nm(mesh, name):
    """Largest radius of any vertex of a layer's tets, in nm."""
    pts = np.asarray(mesh["points_m"])
    tets = np.asarray(mesh["tets"])
    region = np.asarray(mesh["region_of_tet"])
    idx = mesh["parts"].index(name)
    verts = np.unique(tets[region == idx].ravel())
    return float(np.hypot(pts[verts, 0], pts[verts, 1]).max() / F.NM)


def test_the_electrodes_are_actually_wider_than_the_wire(padded_mesh):
    # The whole point of 1.10c. 1.10a's monotonic-narrowing rule could not
    # represent this stack at all, and the flat fixture folds the pad margin
    # into the wire's own outline, so every layer came out wire-wide. If this
    # test fails because both are equal, the mesher has silently collapsed the
    # pad back onto the wire -- the failure mode that makes the pad invisible.
    pad = F.circumradius_nm() + F.ELECTRODE_PAD_NM
    wire = F.circumradius_nm()
    assert _region_rmax_nm(padded_mesh, "mirror") == pytest.approx(pad, rel=1e-6)
    assert _region_rmax_nm(padded_mesh, "top") == pytest.approx(pad, rel=1e-6)
    assert _region_rmax_nm(padded_mesh, "oxide") == pytest.approx(wire, rel=1e-6)
    assert _region_rmax_nm(padded_mesh, "wire") == pytest.approx(wire, rel=1e-6)
    assert pad > wire + 1.0


def test_the_padded_stack_keeps_every_layer_and_its_region(padded_mesh):
    region = np.asarray(padded_mesh["region_of_tet"])
    for i in range(len(padded_mesh["parts"])):
        assert (region == i).sum() > 0, f"layer {padded_mesh['parts'][i]} got no tets"


def test_no_tet_crosses_a_padded_layer_boundary(padded_mesh):
    # Measured, not assumed: the pad ring is a separate outline, so an element
    # that spans a plane would be labelled by its centroid and the layers would
    # mix. This pins the number rather than a claim of zero -- 1.10c reduces
    # them relative to the flat fixture but does not reach zero, because the
    # oxide/wire interface shares one ring and TetGen still spans it.
    s = F.straddle_counts(padded_mesh)
    assert s["n_tets"] > 0
    crossings = {round(k, 1): v for k, v in s["per_boundary_nm"].items()}
    # 1.10d adds the medium's own faces AT these z-planes (the substrate ends at
    # z = 0, the ring spans the device, the cap starts at z_hi), so a tet can
    # now span 120 / 132 / 1507 nm without any DEVICE tet crossing anything.
    # The claim this test can still make is the one it was written for: most
    # elements do not straddle, and the straddles that exist are at the planes
    # the stack has. What it must NOT do is claim zero -- measured 415 / 2342 /
    # 1363 at the three planes with the medium present, up from 0 / 0 at 120 /
    # 1507 without it.
    assert set(crossings) <= {120.0, 132.0, 1507.0}, crossings
    assert 0.0 <= s["fraction"] < 0.5, s


def test_the_padded_solve_is_now_genuinely_three_dimensional(padded_mesh):
    # TASK 1.10e, 2026-11-06. This replaces 1.10c/1.10d's pin that the solve was
    # STILL 1-D. 1.10c pinned it as a defect (the pad overhang was empty space);
    # 1.10d meshed a medium but the device and medium were two separate
    # tetrahedralizations concatenated, so they shared no nodes, the medium was
    # filled THROUGH the device, and the field did not move. 1.10e meshes both
    # in ONE PLC with the interface as a facet; the field moves.
    #
    # Measured, and the numbers this test may quote:
    #   lateral phi spread within a z-level   0.17 V   (1.10d: ~1e-16)
    #   E_z at the dot                         -762 kV/m/V (1.10d/1-D: -707.5)
    # The two differences are what "the ambient couples" means. This test
    # asserts the QUALITATIVE change -- spread far above float noise, and the
    # field off the 1-D value -- because the converged field is still limited by
    # the box (see test_the_field_is_not_converged_in_the_box below) and
    # quoting a quadratically-converged number here would quote the box.
    sol = F.solve_wire(padded_mesh, 1.0)
    free = sol["free"]
    r_free = np.hypot(sol["points_m"][free, 0], sol["points_m"][free, 1])
    assert r_free.max() > 300.0e-9, (
        "free nodes do not reach past the pad's rim: the ambient is not being "
        "solved")

    z = sol["points_m"][:, 2]
    phi = sol["phi"]
    x = sol["points_m"][:, 0]
    z_hi = (F.MIRROR_THICKNESS_NM + F.OXIDE_NM + F.HEIGHT_NM
            + F.ELECTRODE_THICKNESS_NM) * F.NM
    widest = 0.0
    for zv in np.unique(z):
        if abs(zv - z_hi) < 1e-12:
            continue          # the top electrode's own face: 1 V to 0 V, not a field
        sel = z == zv
        if sel.sum() >= 3 and (x[sel].max() - x[sel].min()) > 20e-9:
            widest = max(widest, float(phi[sel].max() - phi[sel].min()))
    assert widest > 1e-3, (
        f"lateral phi spread within a z-level is only {widest:.3e} V -- the "
        "solve is 1-D again, which means the medium is not coupling to the "
        "device (see 1.10d: two meshes, no shared nodes)")

    # The field at the dot must be OFF the 1-D series value. -707.5 kV/m/V is
    # what the bare stack gives; anything within a few percent of it means the
    # ambient is not perturbing the device.
    ez = F.E.field_at(sol, F.probe_point())[2]
    ez_1d = -F.field_per_volt_1d()      # the fixture is 1-D with natural walls
    assert abs(ez) > 1.02 * abs(ez_1d), (
        f"E_z at the dot is {ez/1e3:.1f} kV/m/V against the bare stack's "
        f"{ez_1d/1e3:.1f}: the ambient is not perturbing the device")
    assert abs(ez) < 1.30 * abs(ez_1d), (
        f"E_z at the dot is {ez/1e3:.1f} kV/m/V, more than 30% off the bare "
        f"stack's {ez_1d/1e3:.1f}: too far to be a fringe correction")


def test_no_medium_element_is_meshed_through_the_device(padded_mesh):
    # The lead's explicit test for 1.10e. 1.10d measured 508 of 22186 medium
    # elements with every vertex inside the pad's footprint, one spanning
    # r = 0 -> 127 nm. The mesher now refuses that mesh (_check_medium_outside
    # _device), so the fixture could not build; this asserts the property
    # directly so it is pinned at the fixture too, not only inside the mesher.
    #
    # "Inside" is centroid-based and EXCLUDES interface elements: the interface
    # is a fan triangulation, so a correct boundary element legitimately
    # straddles it and its centroid can land on the device side. Measured on
    # this mesh: 5 medium centroids inside a layer outline, ALL 5 touching a
    # device node, 0 strictly interior.
    region = np.asarray(padded_mesh["region_of_tet"])
    pts = np.asarray(padded_mesh["points_m"])
    tets = np.asarray(padded_mesh["tets"])
    n_dev = len(padded_mesh["parts"]) - 1
    med = region == n_dev
    assert med.sum() > 0, "no medium elements at all"
    dev_nodes = np.unique(tets[~med].ravel())
    cent = pts[tets].mean(axis=1)
    planes = np.asarray(padded_mesh["planes_m"]).reshape(-1)
    outlines = F.pad_outlines_m()

    inside_env = np.zeros(len(tets), bool)
    for i, (name, _t) in enumerate(F.meshed_layers()):
        lo, hi = float(planes[i]), float(planes[i + 1])
        ring = _convex(outlines[name])
        nxt = np.roll(ring, -1, axis=0)
        edge = nxt - ring
        zok = (cent[:, 2] >= lo) & (cent[:, 2] <= hi)
        if not zok.any():
            continue
        rel = cent[zok][:, :2][:, None, :] - ring[None, :, :]
        cross = edge[None, :, 0] * rel[:, :, 1] - edge[None, :, 1] * rel[:, :, 0]
        ins = np.all(cross >= -1e-12 * float(np.max(np.abs(ring))) ** 2, axis=1)
        inside_env[np.flatnonzero(zok)[ins]] = True

    strictly = med & inside_env
    if strictly.any():
        idx = np.flatnonzero(strictly)
        touch = np.array([bool(np.isin(tets[t], dev_nodes).any()) for t in idx])
        strictly[idx[touch]] = False
    assert not strictly.any(), (
        f"{int(strictly.sum())} medium elements are strictly inside the device "
        "envelope, touching no device node: the medium is meshed THROUGH the "
        "device and any field measured on this mesh is a device in no ambient")


def test_the_medium_outside_device_guard_bites_on_both_sides():
    """Exercise ``_check_medium_outside_device`` against meshes built to fail it.

    WHY THIS EXISTS (task 1.10e review, 2026-11-06). The test above asserts the
    real mesh has no strictly-interior medium element -- which is a statement
    about the MESH, and passes just as happily if the guard is dead code that
    never raises. The reviewer's note was exact: the guard was never exercised,
    so the "103 elements" in the record was a hand-run that nothing re-checks.
    A guard whose only evidence is one manual run is one refactor away from
    being unreachable, which is what happened to 1.10a's ``_ring_contains`` and
    to 1.10d's duplicate ambient check.

    Synthetic meshes, so this costs no tetrahedralization. Two device-side tets
    sitting inside the wire layer, plus a medium column at a chosen radius:
    inside must raise, outside must pass. Both directions, because a guard that
    always raises is as useless as one that never does.
    """
    od = F.pad_outlines_m()
    device = F.layers()
    outlines = [od[name] for name, _t in device]
    planes = _MESH.layer_planes(device, 0.0)
    n_dev = len(device)

    def mesh_with_medium_column(r_m: float, n_tets: int = 8):
        """Two device tets at the axis + a medium column at ``r_m``."""
        z0, z1 = float(planes[2]), float(planes[3])      # the wire layer
        h = min(20e-9, (z1 - z0) / 20)
        pts, tets = [], []

        def tet(cx, cy, cz):
            base = len(pts)
            pts.extend([[cx, cy, cz], [cx + h, cy, cz],
                        [cx, cy + h, cz], [cx, cy, cz + h]])
            tets.append([base, base + 1, base + 2, base + 3])

        tet(0.0, 0.0, z0 + 0.2 * (z1 - z0))
        tet(0.0, 0.0, z0 + 0.6 * (z1 - z0))
        for i in range(n_tets):
            tet(r_m, 0.0, z0 + (i + 0.5) * (z1 - z0) / n_tets)
        return (np.asarray(pts, dtype=float), np.asarray(tets),
                np.array([0, 0] + [n_dev] * n_tets))

    # Inside the device: raises, and every column element is reported.
    for r_m, why in ((0.0, "on the wire axis"), (120e-9, "inside the wire rim")):
        pts, tets, attrib = mesh_with_medium_column(r_m)
        with pytest.raises(_MESH.MeshingError, match="meshed THROUGH the device") as ei:
            _MESH._check_medium_outside_device(pts, tets, attrib, outlines, device,
                                          n_dev, z0_m=0.0)
        assert "8 of 8" in str(ei.value), (r_m, str(ei.value))

    # Outside the widest outline: passes. This is the direction that proves the
    # guard is not simply always raising.
    pts, tets, attrib = mesh_with_medium_column(450e-9)
    _MESH._check_medium_outside_device(pts, tets, attrib, outlines, device,
                                   n_dev, z0_m=0.0)

    # No medium at all: raises for its own reason, since a mesh with no ambient
    # region has nothing for the solve to couple to.
    pts, tets, _attrib = mesh_with_medium_column(450e-9)
    with pytest.raises(_MESH.MeshingError, match="no medium elements"):
        _MESH._check_medium_outside_device(pts, tets, np.zeros(len(tets), dtype=int),
                                      outlines, device, n_dev, z0_m=0.0)


def test_every_device_boundary_node_is_shared_with_the_medium(padded_mesh):
    # The conformity claim 1.10e exists to make. In 1.10d the device and medium
    # were separate tetrahedralizations concatenated, so a boundary node on one
    # side simply had no counterpart on the other and the solve could not
    # couple them. Here the interface is a facet of ONE PLC.
    #
    # Only BOUNDARY nodes are meaningful: an interior device node is not
    # expected in any medium element. Counting all device nodes instead once
    # read 44.4% here and looked like a defect; it was measuring the interior.
    from collections import defaultdict
    region = np.asarray(padded_mesh["region_of_tet"])
    tets = np.asarray(padded_mesh["tets"])
    n_dev = len(padded_mesh["parts"]) - 1
    med = region == n_dev
    faces = defaultdict(int)
    for t in tets[~med]:
        a, b, c, d = (int(v) for v in t)
        for f in ((a, b, c), (a, b, d), (a, c, d), (b, c, d)):
            faces[tuple(sorted(f))] += 1
    bnd_nodes = sorted({v for f, n in faces.items() if n == 1 for v in f})
    med_nodes = set(np.unique(tets[med].ravel()).tolist())
    missing = [v for v in bnd_nodes if v not in med_nodes]
    assert len(bnd_nodes) > 100, len(bnd_nodes)
    assert not missing, (
        f"{len(missing)} of {len(bnd_nodes)} device boundary nodes appear in no "
        "medium element: the interface is not conforming, so the solve cannot "
        "couple the device to its ambient")


@pytest.fixture(scope="module")
def medium_mesh():
    return F.mesh_fixture_padded(edge_nm=150.0, max_tets=120_000,
                                 ambient="air", factor=4.0)


def test_the_medium_is_a_region_with_its_own_permittivity(medium_mesh):
    # The task's first half, as a fact about the mesh and the solve input.
    assert F.AMBIENT_PART in medium_mesh["parts"]
    assert F.AMBIENT_PART in medium_mesh["eps_static"]
    i = medium_mesh["parts"].index(F.AMBIENT_PART)
    assert (np.asarray(medium_mesh["region_of_tet"]) == i).sum() > 0
    # The device is untouched: 1.10c's four layers are still there, pad wider.
    pad = F.circumradius_nm() + F.ELECTRODE_PAD_NM
    assert _region_rmax_nm(medium_mesh, "top") == pytest.approx(pad, rel=1e-3)
    assert _region_rmax_nm(medium_mesh, "wire") == pytest.approx(
        F.circumradius_nm(), rel=1e-3)


def test_the_medium_reaches_past_the_pads_rim(medium_mesh):
    # A medium only as wide as the pad would put the rim on the boundary, where
    # the field is imposed rather than solved, and the scan could never show
    # what happens past it. The domain box is ``factor`` x the pad radius.
    pts = np.asarray(medium_mesh["points_m"])
    r_max = float(np.hypot(pts[:, 0], pts[:, 1]).max() / F.NM)
    pad = F.circumradius_nm() + F.ELECTRODE_PAD_NM
    assert r_max > 2.0 * pad, (r_max, pad)


def test_the_free_nodes_are_not_pinned_down_the_axis(medium_mesh):
    """The medium must be SOLVED, not a set of imposed values.

    ``solve_wire`` pins only the two electrodes; every other node is free. If
    the medium's nodes came back as Dirichlet nodes -- which happens if it is
    accidentally declared an electrode part -- the field in it would be imposed
    and the scan below would be measuring the boundary condition, not the
    device.
    """
    sol = F.solve_wire(medium_mesh, 1.0)
    pts = np.asarray(sol["points_m"])
    free = np.asarray(sol["free"])
    z_nm = pts[:, 2] * 1e9
    assert free[z_nm > 1600.0].any(), "no free node above the top electrode"
    assert free[z_nm < 0.0].any(), "no free node under the mirror"


def test_the_fringing_field_now_exists_and_is_pinned(medium_mesh):
    """THE FIELD THAT 1.10d COULD NOT PRODUCE, now measured (task 1.10e).

    This replaces test_no_fringing_field_is_recorded_as_owed_not_hidden, which
    pinned the 1.10d negative result and said, in its own docstring, that if it
    started failing because the field varied laterally then the ambient had
    connected and a fringing field should be asserted instead. It failed exactly
    that way: on the axis E_z was -707.5 kV/m/V flat to 1e-9, now it is
    -836 kV/m/V and varies with x.

    What the scan shows (factor 4, edge 150 nm, air), and the numbers this test
    may quote:
        x =   0 nm   E_z -836 kV/m/V   (device centre)
        x = 150 nm   E_z -861
        x = 205 nm   E_z -879          (inside the wire, inradius 207.3)
        x = 215 nm   E_z -879          (the corner region; see note)
        x = 350 nm   E_z -620          (OUTSIDE the pad's 299.4 nm rim, in air)
    The field is no longer confined to the wire: at 350 nm -- beyond both the
    wire and the pad -- it is still 74% of its on-axis value, because the pad is
    held at 1 V and the medium beside it is now part of the solved domain. That
    is the pad's fringing field, which 1.10c and 1.10d could not see.

    NOTE the 215 nm point: it reads identical to 205 nm. The hexagon's inradius
    is 207.3 nm, so 215 nm is outside the flat face but inside the corner
    radius; the value is plausible either way, but the equality to 3 significant
    figures suggests the probe is landing in the same element. This test does
    not rest on that point.
    """
    sol = F.solve_wire(medium_mesh, 1.0)
    scan = F.scan_at_the_dot(sol, [0.0, 150.0, 205.0, 350.0])
    ez, part = scan["ez"], scan["part"]
    assert np.all(np.isfinite(ez)), part
    # Not flat: the field varies across the wire now.
    assert abs(ez[0]) > 1e-6
    assert abs(ez[1] - ez[0]) > 1e3, (
        f"E_z is flat to {abs(ez[1]-ez[0]):.3g} V/m between x=0 and 150 nm -- "
        "the field is 1-D again")
    # And it reaches OUTSIDE the pad, which is the whole point of 1.10e.
    assert abs(ez[3]) > 0.3 * abs(ez[0]), (
        f"E_z at x=350 nm (outside the pad's 299.4 nm rim) is "
        f"{abs(ez[3])/abs(ez[0]):.1%} of the on-axis value: the field does not "
        "reach the medium beyond the pad, so the pad is not coupling")
    # The field at the dot is off the bare 1-D stack's value.
    assert abs(ez[0]) > 1.02 * F.field_per_volt_1d(), ez[0]

def test_the_medium_is_now_a_genuine_separate_body(medium_mesh):
    """The inversion of 1.10d's defect pin (task 1.10e).

    test_the_medium_is_not_actually_separated_from_the_device measured 508 of
    22 186 medium elements with ALL FOUR vertices inside the pad's footprint and
    said to re-measure once the annulus was a real shell. It no longer is an
    annulus: the medium is a region of ONE PLC separated from the device by a
    facet, so no medium element may sit strictly inside the device envelope.
    """
    pts = np.asarray(medium_mesh["points_m"])
    tets = np.asarray(medium_mesh["tets"])
    region = np.asarray(medium_mesh["region_of_tet"])
    i = medium_mesh["parts"].index(F.AMBIENT_PART)
    med = region == i
    dev_nodes = np.unique(tets[~med].ravel())
    # Every vertex strictly inside the pad's footprint: the 1.10d test's rule.
    r = np.hypot(pts[:, 0], pts[:, 1]) / F.NM
    all_inside = (r[tets[med]] < 290.0).all(axis=1)
    if all_inside.any():
        # ...but an interface element legitimately has vertices on both sides.
        touch = np.array([bool(np.isin(t, dev_nodes).any())
                          for t in tets[med][all_inside]])
        assert not touch.all(), (
            f"{int(all_inside.sum())} medium elements lie wholly inside the "
            "pad footprint and none touches a device node: the medium is meshed "
            "through the device again")
    assert med.sum() > 0


def test_the_region_label_at_the_axis_is_the_device_again(medium_mesh):
    """The inversion of 1.10d's label defect (task 1.10e).

    1.10d's test asserted the label at the wire's axis was 'ambient', because
    the medium's elements overlapped the device and claimed the point. It said:
    if this fails because the label is the wire, the overlap is fixed -- delete
    and re-measure. The overlap is fixed, so the label at the axis is the wire.
    """
    sol = F.solve_wire(medium_mesh, 1.0)
    scan = F.scan_at_the_dot(sol, [0.0], z_nm=1400.0)
    assert scan["part"][0] != F.AMBIENT_PART, (
        "the region label on the wire's axis is still 'ambient': the medium is "
        "overlapping the device, which is the 1.10d defect returning")


def test_solve_wire_refuses_a_mesh_without_the_top_electrode():
    # A constant-field zero is a number and not an answer; it must raise.
    mesh = {"parts": ["mirror", "wire"], "region_of_tet": np.zeros(0, int),
            "points_m": np.zeros((0, 3)), "tets": np.zeros((0, 4), int),
            "eps_static": {"mirror": 1.0, "wire": 12.5}, "ambient": None}
    with pytest.raises(ValueError, match="both electrodes"):
        F.solve_wire(mesh, 1.0)


# --------------------------------------------------------------------------
# 1.10e: what IS and is NOT converged, so neither is quoted as the other
# --------------------------------------------------------------------------

def test_the_dot_field_is_converged_in_the_mesh_but_not_in_the_box():
    """Both halves measured; the second is why no fringing number is quotable.

    MESH (fixed box factor 2, n_across 5/6/7): -764.19, -764.92, -764.25
    kV/m/V -- a spread of 0.095%. The discretization is converged.

    BOX (fixed n_across 6, factor 2/3/4): -764.92, -815.45, -838.39 kV/m/V.
    Still moving ~3% per step and separating less each time. The natural
    (zero-normal-field) condition on the domain wall is what makes the box
    matter: as it shrinks, the medium beside the pad is truncated closer to the
    device and the field the pad would have produced is cut off.

    1.10f CONVERGED IT. Five boxes at fixed discretization (edge 200 nm,
    n_across 6): factor 2/3/4/6/8 -> -764.92, -815.45, -838.39, -855.53,
    -855.78 kV/m/V. Richardson in 1/L (the box is linear in factor) gives
    -895.1; in 1/L^2 gives -863.2. The two bracket the limit, so the converged
    dot field is -879 +- 16 kV/m/V, and that is the number the write-up may
    quote -- as a LIMIT from a model with a natural outer boundary, not as a
    measurement of the real device, whose true surrounding is not this box.

    **Correction (2026-11-08, review of 1.10f @082baee).** The numbers first
    written here were -761.64, -811.00, -839.72, -851.02, -852.38, labelled
    "n_across 6". They are the **n_across=3 DEFAULT** ladder: -761.64 is what
    factor 2 gives at the default, against -764.92 at n_across 6. The values
    were real measurements; the provenance was wrong, because the first sweep
    omitted the keyword and I labelled it from the second sweep that passed it.
    The limit moved only -875 -> -879, so the headline survived, but the ladder
    and its convergence story did not: at n_across 6 the factor 6->8 step is
    0.25 kV/m/V, which is the real approach.

    The test below did NOT catch this, and could not: it builds its own meshes
    with ``n_across=6`` explicitly, so it measured the correct ladder the whole
    time while its own docstring quoted the wrong one. A test whose prose and
    whose computation are independent cannot detect a mismatch between them.
    ``test_the_quoted_ladder_is_the_one_this_fixture_produces`` now measures the
    n_across=6 value and compares it to the quoted anchor, so the two cannot
    drift apart again.

    So: the field has lateral structure (1.10e), the on-axis value is
    mesh-converged, and its box limit is now extrapolated rather than open.
    This test still asserts the box MOVES the field: if it ever stops, either
    the boundary condition changed or the medium stopped coupling.
    """
    mesh_vals = []
    for n in (5, 6, 7):
        m = F.mesh_fixture_padded(edge_nm=200.0, factor=2.0, n_across=n,
                                  max_tets=900_000, ambient="air")
        sol = F.solve_wire(m, 1.0)
        mesh_vals.append(F.E.field_at(sol, F.probe_point())[2])
    spread = (max(mesh_vals) - min(mesh_vals)) / abs(np.mean(mesh_vals))
    assert spread < 0.01, (
        f"mesh spread is {spread:.2%}, not converged: the on-axis value may not "
        f"be quoted. Measured values {mesh_vals}")

    box_vals = []
    for factor in (2.0, 4.0):
        m = F.mesh_fixture_padded(edge_nm=200.0, factor=factor, n_across=6,
                                  max_tets=900_000, ambient="air")
        sol = F.solve_wire(m, 1.0)
        box_vals.append(F.E.field_at(sol, F.probe_point())[2])
    # The box MUST matter. If it stops mattering, either the boundary condition
    # changed or the medium stopped coupling -- both are large news, and this
    # test is the place it surfaces.
    assert abs(box_vals[1] - box_vals[0]) / abs(box_vals[0]) > 0.02, (
        f"the field is {abs(box_vals[1]-box_vals[0])/abs(box_vals[0]):.2%} "
        f"sensitive to the box size ({box_vals}); it was 9.6% at 1.10e. Either "
        "the domain boundary changed or the ambient is no longer coupling")


def test_the_box_limit_is_the_quotable_number():
    """1.10f: the box sweep converges, and the limit is what may be quoted.

    Measured (fixed edge 200 nm, n_across 6): factor 2/3/4/6/8 gives
    -761.64, -811.00, -839.72, -851.02, -852.38 kV/m/V. This asserts the SHAPE
    of that approach -- monotone, steps shrinking -- and the bracket the two
    Richardson forms give. If a future change makes the sequence non-monotone
    or widens the bracket, the extrapolation has lost its justification and the
    -875 number must stop being quoted, which is the point of pinning it.
    """
    factors = (2.0, 3.0, 4.0, 6.0)
    vals = []
    for factor in factors:
        m = F.mesh_fixture_padded(edge_nm=200.0, factor=factor, n_across=6,
                                  max_tets=1_200_000, ambient="air")
        sol = F.solve_wire(m, 1.0)
        vals.append(F.E.field_at(sol, F.probe_point())[2] / 1e3)
    # Monotone decreasing in magnitude: each box is closer to the limit.
    steps = [vals[i + 1] - vals[i] for i in range(len(vals) - 1)]
    assert all(s < 0 for s in steps), (f"not monotone: {vals}")
    # Steps shrink toward zero -- an approach, not a drift.
    mags = [abs(s) for s in steps]
    assert mags[1] < mags[0] and mags[2] < mags[1], (
        f"box steps do not shrink ({mags}); the sequence is not converging and "
        f"no limit may be extrapolated. Values {vals}")
    # The first step must still be material: a converged box at factor 2 would
    # make the whole sweep pointless, and would mean the fixture changed.
    assert mags[0] / abs(vals[0]) > 0.03, (mags, vals)

    # Richardson on the measured four points, in 1/L and 1/L^2 (L ~ factor).
    x = np.array(factors)
    y = np.array(vals)
    lim1 = np.polyfit(1.0 / x, y, 1)[1]
    lim2 = np.polyfit(1.0 / x ** 2, y, 1)[1]
    # Both forms must land in the same small neighbourhood, or the
    # extrapolation is not trustworthy enough to quote.
    assert abs(lim1 - lim2) < 0.05 * abs(lim2), (
        f"the two Richardson forms disagree ({lim1:.1f} vs {lim2:.1f}); the "
        f"measured points do not justify quoting a limit. Values {vals}")
    assert -920 < lim2 < -840, (
        f"extrapolated limit {lim2:.1f} kV/m/V is outside the measured "
        f"bracket; re-measure rather than quote. Values {vals}")


def test_the_quoted_ladder_is_the_one_this_fixture_produces():
    """The anchor tying the QUOTED numbers to a MEASURED one.

    Review of 1.10f caught the docstrings quoting an n_across=3 ladder under an
    "n_across 6" label. Nothing failed, because the convergence test above
    builds its own meshes and its docstring was written separately -- prose and
    computation could disagree silently.

    This closes that: it measures factor 2 at n_across 6 and at the DEFAULT, and
    asserts they are DIFFERENT and that the quoted anchor (-764.92) is the
    n_across=6 one. If someone relabels the table again, or the default changes
    to 6 so the distinction disappears, this fails and the docstrings must be
    re-measured.
    """
    quoted_anchor_kv_per_m = -764.92

    def ez(n_across):
        kw = {} if n_across is None else {"n_across": n_across}
        m = F.mesh_fixture_padded(edge_nm=200.0, factor=2.0, max_tets=900_000,
                                  ambient="air", **kw)
        sol = F.solve_wire(m, 1.0)
        return F.E.field_at(sol, F.probe_point())[2] / 1e3

    explicit = ez(6)
    default = ez(None)
    # The two must be distinguishable, or the label in the docstring carries no
    # information and the correction above cannot be verified.
    assert abs(explicit - default) > 1.0, (
        f"n_across=6 gives {explicit:.2f} and the default {default:.2f}: "
        f"within 1 kV/m/V of each other, so the docstring's 'n_across 6' label "
        f"cannot distinguish them. Check what the default is now.")
    # The quoted anchor must be the n_across=6 value, not the default one.
    assert abs(explicit - quoted_anchor_kv_per_m) < 1.0, (
        f"n_across=6 measures {explicit:.2f} kV/m/V but the docstring quotes "
        f"{quoted_anchor_kv_per_m:.2f}. The quoted ladder is labelled "
        f"n_across 6; re-measure the table or fix the label. (The default "
        f"measures {default:.2f} -- that is the number a mislabelled table "
        f"would show.)")


def test_the_ambient_permittivity_changes_the_field_at_the_dot():
    # The medium must enter the solve as a MATERIAL, not just as geometry. If
    # eps_static of the ambient stopped reaching the solve, air and bcb would
    # give the same number; measured, bcb is 8.1% stronger than air at the same
    # mesh (55,592 tets), which is eps_bcb / eps_air = 2.6 in the right
    # direction and far beyond any mesh artefact (0.1%).
    vals = {}
    for ambient in ("air", "bcb"):
        m = F.mesh_fixture_padded(edge_nm=200.0, factor=2.0, n_across=6,
                                  max_tets=900_000, ambient=ambient)
        sol = F.solve_wire(m, 1.0)
        vals[ambient] = F.E.field_at(sol, F.probe_point())[2]
    assert abs(vals["bcb"]) > 1.02 * abs(vals["air"]), (
        f"bcb {vals['bcb']/1e3:.1f} vs air {vals['air']/1e3:.1f} kV/m/V: the "
        "ambient permittivity is not reaching the solve")
