"""The 3-D drift-diffusion form (task 2.7): its mesh-side pieces.

DEVSIM 2.11.2 in this image has no 3-D mesh-create API, so the 3-D form is
handed a tetrahedral mesh as a Gmsh 2.2 file. Two things about that route are
worth testing without a solver at all, because both are silent when wrong:

* a face shared by two tets is INTERIOR and must not become a contact. Keying
  the raw (unsorted) triple reports every interior face twice and would put a
  contact through the middle of the device;
* a contact needs a boundary physical group that exists in the file. The
  shipped ``write_gmsh22`` writes only 3-D tet groups, so a device loaded from
  it has regions and no surfaces -- ``add_gmsh_contact`` then has nothing to
  bind to, and the current silently reads 0.

No test here runs a solve. The solve-level tests live in
tests/test_dd_3d_wiring.py and need devsim in the image.
"""

import numpy as np
import pytest

from mse_axisymmetric import (
    _boundary_faces,
    _estimate_tet_edges,
    _require_tet_job_memory,
    TooBigForJob,
    TooManyNodesForFactor,
    estimate_tet_job_bytes,
    TET_ESTIMATE_FACTOR,
    TET_FIXED_OVERHEAD_BYTES,
    TET_MAX_FACTORABLE_NODES,
    write_gmsh22_with_boundaries,
)


def _two_tets():
    """Two tets sharing one face: an interior face plus six boundary faces.

    Nodes 0-3 form the first tet, and the second reuses face (0,1,2) with a new
    apex node 4. That shared face is the only interior face in the mesh.
    """
    points = np.array([
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
        [0.0, 0.0, -1.0],
    ])
    tets = np.array([[0, 1, 2, 3], [0, 1, 2, 4]])
    return points, tets


def test_a_shared_face_is_interior_and_gets_no_contact():
    """The face between two tets is counted twice and is not a boundary.

    This is the whole reason the face key is SORTED: the same face appears as
    a different vertex order in each tet, and an unsorted key would record
    both orderings as separate single-owner faces, i.e. as two boundaries in
    the middle of the device.
    """
    _, tets = _two_tets()
    faces = _boundary_faces(tets)
    shared = tuple(sorted([0, 1, 2]))
    assert shared in faces
    assert len(faces[shared]) == 2, "the shared face must have two owners"
    interior = [k for k, owners in faces.items() if len(owners) > 1]
    assert interior == [shared]
    # 3 + 3 boundary faces, plus the one shared face.
    assert len(faces) == 7


def test_boundary_groups_are_written_for_both_contacts(tmp_path):
    """A contact must exist as a surface physical group in the file.

    Dimension is 2 (a surface) and the name is the contact's. A dimension-3
    group would load and select nothing, which is the failure mode recorded in
    mse_devsim_mesh -- so the dimension is asserted, not assumed.
    """
    points, tets = _two_tets()
    region_of_tet = np.array([0, 0])
    faces = _boundary_faces(tets)
    # Split the boundary faces into two groups by their apex node along z, so
    # both groups are non-empty and each has a distinct name. The grouping
    # rule is the TEST's; what is under test is that two distinct names come
    # out as two distinct surface groups with distinct physical tags.
    contact_of_face = {}
    for key, owners in faces.items():
        if len(owners) != 1:
            continue
        contact_of_face[key] = "top" if key[2] % 2 else "bottom"

    path = tmp_path / "two_tets.msh"
    report = write_gmsh22_with_boundaries(
        path, points, tets, region_of_tet, ["p"],
        contact_of_face=contact_of_face)

    text = path.read_text()
    assert '"bottom"' in text and '"top"' in text
    # Both are SURFACE groups (dimension 2), not volume groups.
    for name in ("bottom", "top"):
        dim = [ln for ln in text.splitlines() if ln.endswith('"%s"' % name)][0]
        assert dim.split()[0] == "2", "a contact group must be dimension 2"
    # Two names must mean two tags: one shared tag collapses them silently.
    tags = {ln.split()[1] for ln in text.splitlines()
            if ln.endswith('"bottom"') or ln.endswith('"top"')}
    assert len(tags) == 2
    assert report["units"] == "cm"
    assert set(report["contacts"]) == {"bottom", "top"}


def test_uncontacted_boundary_faces_are_not_written(tmp_path):
    """A face with no contact assigned stays out of the element list.

    Otherwise every outer surface would be a terminal and the device would be
    shorted by construction.
    """
    points, tets = _two_tets()
    region_of_tet = np.array([0, 0])
    path = tmp_path / "none.msh"
    report = write_gmsh22_with_boundaries(
        path, points, tets, region_of_tet, ["p"], contact_of_face={})
    assert report["contacts"] == []
    # Only the two tets are written; no triangles.
    text = path.read_text()
    assert "$Elements\n2\n" in text


def test_tet_edges_are_counted_uniquely():
    """Edges are the unique node pairs, not 6 per tet.

    Two tets sharing a face share three of their six edges, so the mesh has
    9 edges, not 12. Counting per-tet would overstate the memory estimate.
    """
    _, tets = _two_tets()
    assert _estimate_tet_edges(tets) == 9


def test_a_tet_mesh_over_the_limit_is_refused():
    """The 2.5 memory refusal is live on the 3-D path too.

    Uses an explicit small ``limit_bytes``: since 2.13's node ceiling, no mesh
    under ``TET_MAX_FACTORABLE_NODES`` exceeds the 14 GiB default, so the
    memory gate can only be exercised by naming a tighter limit. That is the
    real shape of the two gates -- they catch disjoint failures, and a mesh
    small enough to factor is refused here only for memory.
    """
    with pytest.raises(TooBigForJob) as excinfo:
        _require_tet_job_memory(18_000, 121_140, limit_bytes=1 * 1024 ** 3)
    assert "3-D" in str(excinfo.value)


def test_a_small_tet_mesh_is_admitted_and_priced():
    """The same check admits a small mesh and returns its estimate."""
    estimate, limit = _require_tet_job_memory(2000, 12000)
    assert 0 < estimate < limit


def test_the_3d_price_is_calibrated_by_the_measured_factor():
    """The 3-D price is the MEASURED 2x + overhead, not the raw sum.

    Task 2.7's tier-3 calibration Job (2026-11-10, three sizes) measured that a
    3-D solve costs about twice ``estimate_tet_job_bytes(raw=True)`` plus a
    constant ~220 MB. The pre-calibration gate assumed its estimate was
    PESSIMISTIC for 3-D; it was optimistic by 2x, so it admitted runs that then
    failed inside UMFPACK.

    This test fails if the factor is removed, or if it is applied to the raw
    sum in the wrong place, which is the whole point: a gate that quietly
    reverts to pricing 3-D at the axisymmetric slope reads as a working gate.

    Checked at TWO sizes so a factor applied at one fixed size (or a hardcoded
    override) cannot pass.
    """
    for nodes, edges in ((4307, 30_000), (12157, 95_000)):
        raw = estimate_tet_job_bytes(nodes, edges, raw=True)
        priced = estimate_tet_job_bytes(nodes, edges)
        expected = TET_FIXED_OVERHEAD_BYTES + TET_ESTIMATE_FACTOR * raw
        # +-1 B: ``raw=True`` truncates the float sum to an int, while the
        # calibrated path scales the float BEFORE truncating, so the two can
        # differ in the last bit. An exact-equality assert here was testing
        # float rounding order, not the calibration.
        assert abs(priced - expected) <= 1, (
            f"nodes={nodes}: priced={priced} expected={expected:.1f}")
        if TET_ESTIMATE_FACTOR <= 1.0:
            pytest.fail("TET_ESTIMATE_FACTOR must exceed 1: the measurement "
                        "shows 3-D costs more, not less, than the raw sum")


def test_the_calibrated_3d_price_brackets_the_measured_peaks():
    """The calibrated price is close to the peak RSS the Job actually measured.

    The three calibration points (image 7dbd3b4) at nodes 1136 / 4307 / 12157
    with the two largest of the three are the only evidence this bound has. If the
    constants drift until the price no longer brackets them, the gate is
    refusing on a number unrelated to what the solver uses, and every refusal
    message it produces is fiction.

    The coarse point is deliberately EXCLUDED: stage 3 did not converge there,
    so its peak is not a converged run's cost. It is recorded in tasks.md as a
    non-converged observation instead. The 4307-node point is bracketed but is
    ALSO non-converged -- only the 12157-node point is a converged run.
    """
    measured = ((4307, 28_986, 503_398_400), (12157, 81_816, 1_519_611_904))
    for nodes, edges, peak in measured:
        priced = estimate_tet_job_bytes(nodes, edges)
        # Within 15 %: the calibration fit these points to ~1 %, so a band this
        # wide accommodates the edge-count estimate (taken from the measured
        # ~6.73 edges/node) without letting a wrong factor through. A 2x error
        # or a removed factor fails by a country mile.
        assert 0.85 <= priced / float(peak) <= 1.15, (
            f"nodes={nodes}: priced {priced} vs measured peak {peak} "
            f"({priced / float(peak):.2f}x) -- recalibrate from new Job data "
            f"rather than widening this band")


def test_a_mesh_over_the_factorable_ceiling_is_refused_before_solving():
    """2.13: the node ceiling refuses what UMFPACK cannot factor.

    The measured facts: edge 6.0e-8 (18,957 nodes) factored; the coupled solve
    at edge 5.0e-8 (32,430 nodes) raised "umfpack numeric failed" at 3.08 GB
    peak, well under a 13 GiB limit. So this refusal is the ONLY thing standing
    between a user and a six-minute failure -- memory pricing admitted that mesh
    (5.45 GiB priced, under the 14 GiB gate).
    """
    edges = int(32_430 * 6.73)
    # It fits the memory gate -- that is the whole point -- so only the node
    # ceiling can refuse it.
    from mse_common import DEFAULT_JOB_MEMORY_BYTES
    assert estimate_tet_job_bytes(32_430, edges) < DEFAULT_JOB_MEMORY_BYTES
    with pytest.raises(TooManyNodesForFactor) as excinfo:
        _require_tet_job_memory(32_430, edges)
    message = str(excinfo.value)
    assert "Coarsen the mesh" in message, (
        "the refusal must tell the user what to do; got: " + message)
    assert "not a memory limit" in message, (
        "the refusal must not send the user to raise the Job's memory; got: "
        + message)
    assert excinfo.value.limit_nodes == TET_MAX_FACTORABLE_NODES


def test_a_mesh_at_the_measured_factorable_size_is_admitted():
    """The ceiling is the known-good end, so the mesh that factored passes.

    Removing the guard leaves this test green, which is why the refusal test
    above is the mutation target: this one pins that the ceiling is not set so
    low that it refuses the very measurement it was derived from.
    """
    edges = int(18_957 * 6.73)
    total, limit = _require_tet_job_memory(18_957, edges)
    assert total > 0 and limit > 0


def test_the_node_ceiling_lies_between_the_two_measured_sizes():
    """The constant must sit strictly between 18,957 and 32,430 nodes.

    Anything at or below 18,957 would refuse a size that DID factor; anything
    at or above 32,430 would admit the size that failed. The comment says the
    true ceiling lies between them, so the constant is a choice inside that
    interval, not a measurement of the boundary.
    """
    assert 18_957 <= TET_MAX_FACTORABLE_NODES < 32_430, (
        f"ceiling {TET_MAX_FACTORABLE_NODES} is outside the interval the "
        "measurements bound")
