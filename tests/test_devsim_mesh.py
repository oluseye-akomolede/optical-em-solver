"""Task 2.1: DEVSIM imports in the solver image, and our mesh becomes a device.

Two separate claims, tested separately:

1. ``import devsim`` works inside the built image and reports a version. This
   runs only where DEVSIM is installed, so it SKIPS (does not pass) when the
   module is absent -- a skip is not evidence, which is the point.
2. Our mesher's output can be handed to DEVSIM as a device. This is the mesh
   route from task 0.2, and it is tested on a tiny mesh here rather than
   asserted in prose.

The route test is the one that matters. 0.2 recorded that DEVSIM takes a Gmsh
2.2 4-node-tet file and selects regions by physical NUMBER at ``ilist[3]``; if
that sub-field moves, every element silently joins a group named after its own
element index. ``test_the_physical_number_is_where_the_reader_looks`` pins that
byte offset so the writer cannot drift from the reader without a failure.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "dockerfiles", "maxwell_solver"))

import mse_devsim_mesh as M  # noqa: E402

try:
    import devsim  # noqa: F401
    HAVE_DEVSIM = True
except Exception:  # pragma: no cover - depends on the interpreter
    HAVE_DEVSIM = False


# --------------------------------------------------------------------------
# the writer, which runs anywhere
# --------------------------------------------------------------------------

def _single_tet():
    pts = np.array([[0.0, 0.0, 0.0],
                    [1e-9, 0.0, 0.0],
                    [0.0, 1e-9, 0.0],
                    [0.0, 0.0, 1e-9]])
    tets = np.array([[0, 1, 2, 3]])
    return pts, tets, np.array([0])


def test_the_writer_emits_a_gmsh22_tet_file(tmp_path):
    pts, tets, region = _single_tet()
    path = tmp_path / "one.msh"
    rep = M.write_gmsh22(path, pts, tets, region, ["wire"])
    text = path.read_text()
    assert text.startswith("$MeshFormat\n2.2 0 8\n")
    assert "$PhysicalNames" in text and '"wire"' in text
    assert rep["n_tets"] == 1 and rep["n_points"] == 4
    assert rep["units"] == "m"


def test_the_physical_names_block_has_exactly_count_plus_names(tmp_path):
    """The block is a count line followed by ONE line per name -- nothing else.

    Measured failure this pins: an earlier writer emitted an extra bare `2`
    line between the count and the names (intended as the element dimension,
    which belongs on each name line instead). DEVSIM rejected the file with
    `line: 6: syntax error`, and every test here still passed, because they
    only asked whether "$PhysicalNames" appeared somewhere in the text. The
    in-image tests skip on the host, so nothing else read the block's shape.
    """
    pts, tets, region = _single_tet()
    path = tmp_path / "one.msh"
    M.write_gmsh22(path, pts, tets, region, ["wire", "oxide"])
    lines = path.read_text().splitlines()
    start = lines.index("$PhysicalNames")
    end = lines.index("$EndPhysicalNames")
    block = lines[start + 1:end]
    assert block[0] == "2", block                 # the count
    names = block[1:]
    assert len(names) == 2, block                 # exactly one line per name
    for i, line in enumerate(names, start=1):
        dim, tag, name = line.split()
        # Gmsh 2.2 order is DIMENSION then TAG. This assertion originally
        # read `(tag, dim) == (str(i), "3")`, which locked the transposed
        # order IN rather than catching it: the writer emitted `1 3 "wire"`
        # and the test agreed with it. The file loads either way, so only a
        # node COUNT in the image exposes it -- dimension 1 is a line, and
        # the group then selects zero tetrahedra.
        assert (dim, tag) == ("3", str(i)), line
        assert name.startswith('"') and name.endswith('"'), line


def test_every_number_in_the_file_parses_as_a_float(tmp_path):
    """Parse the file, don't grep it -- the defect this pins looked like data.

    Measured failure: the node lines were written with `!r`, which reprs a
    numpy scalar as `np.float64(0.0)`. The file still contained a `$Nodes`
    marker, the right count line and the right number of lines, so every
    string-matching test passed. DEVSIM rejected it as `line: 10: syntax
    error`. Two writer defects in a row (the stray `2` in $PhysicalNames, then
    this) survived a green host suite for the same reason: the tests asked
    whether text was present, never whether it was a number.
    """
    pts, tets, region = _single_tet()
    path = tmp_path / "one.msh"
    M.write_gmsh22(path, pts, tets, region, ["wire", "oxide"])
    lines = path.read_text().splitlines()

    def block(name):
        start = lines.index(f"${name}")
        end = lines.index(f"$End{name}")
        return lines[start + 1:end]

    nodes = block("Nodes")
    assert int(nodes[0]) == len(pts), nodes[0]
    for line in nodes[1:]:
        fields = line.split()
        assert len(fields) == 4, line
        int(fields[0])                      # node id
        for value in fields[1:]:            # x, y, z
            float(value)                    # raises on `np.float64(0.0)`
            assert "np.float64" not in line, line

    elements = block("Elements")
    assert int(elements[0]) == len(tets), elements[0]
    for line in elements[1:]:
        for value in line.split():
            int(value)                      # every element field is an int


def test_every_element_tag_is_positive(tmp_path):
    """Both tags must be > 0; a geometric tag of 0 loses the element silently.

    Measured failure: the physical tag was positive but the geometric tag was
    hardcoded 0. DEVSIM loaded the file without complaint -- it reported 144
    tetrahedra in each physical group -- and then said `Region lower has 0
    nodes` and failed to create NetDoping. Nothing distinguished a broken file
    from a working one until the region was asked for its nodes, which is why
    the smoke test asks for node counts rather than trusting the load message.
    """
    pts, tets, region = _single_tet()
    path = tmp_path / "one.msh"
    M.write_gmsh22(path, pts, tets, region, ["wire", "oxide"])
    lines = path.read_text().splitlines()
    start = lines.index("$Elements")
    end = lines.index("$EndElements")
    body = lines[start + 1:end]
    assert int(body[0]) == len(tets), body[0]   # the count, not an element
    for line in body[1:]:
        fields = line.split()
        physical, geometric = int(fields[3]), int(fields[4])
        assert physical > 0, line
        assert geometric > 0, line


def test_the_physical_number_is_where_the_reader_looks(tmp_path):
    # THE test for this module. DEVSIM reads ilist[3] as the physical number
    # (task 0.2), with ntags=2. So the element line must be
    #   id type ntags physical geometric ...
    # If a writer inserts an element index before the physical number, DEVSIM
    # puts every element in its own group and region lookup by name fails
    # WITHOUT an error -- the silent-wrong-answer failure 0.2 recorded.
    pts, tets, region = _single_tet()
    path = tmp_path / "one.msh"
    M.write_gmsh22(path, pts, tets, region, ["wire"])
    lines = path.read_text().splitlines()
    start = lines.index("$Elements")
    fields = lines[start + 2].split()
    assert len(fields) == 9, fields             # id, type, ntags, 2 tags, 4 nodes
    assert fields[1] == "4", fields             # 4-node tet
    assert fields[2] == "2", fields             # ntags
    assert fields[3] == "1", fields             # physical number, NOT 0, NOT an index


def test_each_part_gets_its_own_physical_number(tmp_path):
    pts = np.array([[0.0, 0, 0], [1e-9, 0, 0], [0, 1e-9, 0], [0, 0, 1e-9],
                    [2e-9, 0, 0], [3e-9, 0, 0], [2e-9, 1e-9, 0], [2e-9, 0, 1e-9]])
    tets = np.array([[0, 1, 2, 3], [4, 5, 6, 7]])
    region = np.array([0, 1])
    rep = M.write_gmsh22(tmp_path / "two.msh", pts, tets, region, ["wire", "oxide"])
    assert rep["physical_numbers"] == {"wire": 1, "oxide": 2}
    assert rep["tets_per_part"] == {"wire": 1, "oxide": 1}


def test_the_writer_refuses_a_region_with_no_part_name(tmp_path):
    pts, tets, _ = _single_tet()
    with pytest.raises(ValueError, match="no part name"):
        M.write_gmsh22(tmp_path / "bad.msh", pts, tets,
                       np.array([3]), ["wire"])


def test_the_writer_refuses_a_length_mismatch(tmp_path):
    pts, tets, _ = _single_tet()
    with pytest.raises(ValueError, match="regions for"):
        M.write_gmsh22(tmp_path / "bad.msh", pts, tets, np.array([0, 0]), ["wire"])


def test_a_real_two_layer_mesher_output_round_trips(tmp_path):
    """Not a synthetic box: the mesher's actual output, tagged and read back.

    A synthetic single tet proves the format; this proves the ROUTE, because it
    starts from ``tetrahedralize_layers`` and ends with physical numbers
    recovered from the file. Two layers is the smallest stack where a region
    mistake is visible -- with one layer, "every tet tagged 1" would pass.
    """
    import mse_meshing as MM

    square = np.array([[0.0, 0.0], [-6e-8, 0.0], [-6e-8, 6e-8], [0.0, 6e-8]])
    pts, tets, region = MM.tetrahedralize_layers(
        square, [("lower", 30e-9), ("upper", 30e-9)], edge_m=3e-8)
    path = tmp_path / "real.msh"
    rep = M.write_gmsh22(path, pts, tets, region, ["lower", "upper"])

    assert rep["n_tets"] == len(tets) > 0
    lines = path.read_text().splitlines()
    start = lines.index("$Elements")
    tags = {int(l.split()[3]) for l in lines[start + 2:start + 2 + len(tets)]}
    # Both layers present: a single-tag set means the region ids were flattened.
    assert tags == {1, 2}, tags
    assert set(rep["tets_per_part"]) == {"lower", "upper"}
    assert all(n > 0 for n in rep["tets_per_part"].values()), rep["tets_per_part"]


# --------------------------------------------------------------------------
# DEVSIM itself: skips without it, and says so rather than passing
# --------------------------------------------------------------------------
@pytest.mark.skipif(not HAVE_DEVSIM, reason="devsim not installed here; run in the image")
def test_devsim_imports_and_reports_a_version():
    import devsim
    assert devsim.__version__, "devsim imported but reported no version"
    assert devsim.__version__.startswith("2."), devsim.__version__


@pytest.mark.skipif(not HAVE_DEVSIM, reason="devsim not installed here; run in the image")
def test_our_mesh_becomes_a_devsim_device(tmp_path):
    """The whole route, on a tiny mesh: our arrays -> Gmsh 2.2 -> DEVSIM regions."""
    import devsim

    pts, tets, region = _single_tet()
    path = tmp_path / "one.msh"
    M.write_gmsh22(path, pts, tets, region, ["wire"])

    devsim.create_gmsh_mesh(file=str(path), mesh="m1")
    devsim.add_gmsh_region(mesh="m1", gmsh_name="wire", region="body",
                           material="InP")
    devsim.finalize_mesh(mesh="m1")
    devsim.create_device(mesh="m1", device="d1")

    # The region exists under the name we asked for; if the physical number
    # drifted, DEVSIM would have no region called "wire" (or silently none).
    devsim.set_parameter(device="d1", region="body", name="NetDoping", value=0.0)
    values = devsim.get_node_model_values(device="d1", region="body",
                                          name="NetDoping")
    # One value per node, read back from DEVSIM rather than assumed: the single
    # tet has 4 nodes, and a route that silently dropped nodes would not.
    assert len(values) == 4, len(values)
