"""Turn our tet mesh into a DEVSIM device (task 2.1).

Task 0.2 established the route: DEVSIM's ``create_gmsh_mesh`` reads a Gmsh 2.2
file, and ``add_gmsh_region`` selects a physical group by its *name*. It also
recorded the reader rule that costs time -- the physical number is
``ilist[3]``, so an extra element-index field shifts it and every element lands
in a group numbered by its own index, silently, with no error.

This module writes that file from what ``mse_meshing`` returns --
``(points_m, tets, region_of_tet)`` plus the part names -- and nothing else. It
is deliberately small: the mesh route is the deliverable, not a mesher.

Units: our tets are in METRES; the file is written in METRES too and the scale
is reported, because a silent mm/m mix-up in a device solver produces a
plausible-looking wrong answer rather than a failure.
"""

from __future__ import annotations

import numpy as np

# Gmsh 2.2 element type 4 is a 4-node tetrahedron.
_TET = 4
# Two tags per element (0.2 measured ntags=2: physical, then geometric).
_NTAGS = 2


def write_gmsh22(path, points_m, tets, region_of_tet, parts):
    """Write a 4-node-tet Gmsh 2.2 file. Returns a report dict.

    ``parts`` is the layer list; ``region_of_tet`` indexes it, and part ``i``
    becomes physical group ``i + 1`` named ``parts[i]``. Physical numbers start
    at 1 because the reader rejects 0 (0.2).
    """
    points_m = np.asarray(points_m, dtype=float)
    tets = np.asarray(tets, dtype=np.int64)
    region = np.asarray(region_of_tet, dtype=np.int64)
    if len(region) != len(tets):
        raise ValueError(f"{len(region)} regions for {len(tets)} tets")
    if region.size and region.min() < 0:
        raise ValueError("negative region id")
    if region.size and region.max() >= len(parts):
        raise ValueError(
            f"region id {region.max()} has no part name; there are {len(parts)}")

    names = list(parts)
    # Physical tag = part index + 1.
    phys_of_tet = region + 1

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("$MeshFormat\n2.2 0 8\n$EndMeshFormat\n")

        # Format is: one line holding the count, then one line PER NAME of
        # `tag dim "name"`. An earlier version wrote an extra bare `2` line
        # between the count and the names (I had intended it as the dimension),
        # which DEVSIM rejected as `line: 6: syntax error`. The dimension
        # belongs on each name line, as the `3` below.
        fh.write("$PhysicalNames\n")
        fh.write(f"{len(names)}\n")
        for i, name in enumerate(names):
            # Gmsh 2.2 order is DIMENSION then TAG: `3 <tag> "name"`. I first
            # wrote `{tag} 3 "name"`, transposing the two fields. It is not
            # rejected -- the reader takes dimension 1 (a line) and the group
            # then selects zero tetrahedra, so the file loads, the region
            # exists, and it holds no nodes. That silent mis-selection is
            # visible only by counting nodes, and cost a long bisection.
            fh.write(f'3 {i + 1} "{name}"\n')
        fh.write("$EndPhysicalNames\n")

        fh.write("$Nodes\n")
        fh.write(f"{len(points_m)}\n")
        for i, (x, y, z) in enumerate(points_m, start=1):
            # `.17g`, NOT `!r`: a numpy scalar reprs as `np.float64(0.0)`, which
            # is not a number to any parser -- DEVSIM rejected it as
            # `line: 10: syntax error`. `!r` looked like the exact choice and
            # produced an unparseable file. 17 significant digits round-trips a
            # float64 exactly, so nothing is lost.
            fh.write(f"{i} {float(x):.17g} {float(y):.17g} {float(z):.17g}\n")
        fh.write("$EndNodes\n")

        fh.write("$Elements\n")
        fh.write(f"{len(tets)}\n")
        for i, (tet, phys) in enumerate(zip(tets, phys_of_tet), start=1):
            a, b, c, d = (int(v) + 1 for v in tet)
            # id type ntags physical geometric nodes...
            # ntags MUST be 2 and physical MUST be ilist[3]: an inserted element
            # index here silently regroups every element (task 0.2).
            # The GEOMETRIC tag must also be positive. 0.2 recorded "tag 0 is
            # rejected" about the physical slot; I applied it only there and
            # hardcoded 0 here. Every element still parsed -- the counts were
            # right and both physical groups reported 144 tetrahedra -- but
            # `Region lower has 0 nodes` and NetDoping did not exist, i.e. the
            # elements were loaded and then discarded. Use the physical number
            # as the geometric tag too: it is positive and it keeps each
            # region's elements distinguishable.
            fh.write(f"{i} {_TET} {_NTAGS} {int(phys)} {int(phys)} {a} {b} {c} {d}\n")
        fh.write("$EndElements\n")

    return {
        "path": str(path),
        "n_points": int(len(points_m)),
        "n_tets": int(len(tets)),
        "parts": names,
        "units": "m",
        "physical_numbers": {n: i + 1 for i, n in enumerate(names)},
        "tets_per_part": {
            n: int((region == i).sum()) for i, n in enumerate(names)
        },
    }
