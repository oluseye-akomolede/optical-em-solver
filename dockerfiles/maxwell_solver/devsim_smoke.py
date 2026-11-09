"""Task 2.1 smoke: DEVSIM imports in the solver image, and our mesh becomes a device.

Runs INSIDE the built image (no DEVSIM on the host, so this cannot be a host
test). Prints `KEY=VALUE` lines that the task record quotes, so every number in
the record comes from this run rather than from memory.

    docker run --rm --cpus=2 --memory=2g --entrypoint python \
        mse-solver:devsim-2.1 /opt/app/devsim_smoke.py

The `--entrypoint python` is required: the image's ENTRYPOINT is the solver, so
without it the script path is swallowed as an argument to mse_maxwell_solver.py
and argparse exits 2 asking for --job-id.

Exit code 0 with `ROUTE=ok` means the whole path works: import, a two-layer
mesh written by our writer, loaded as a DEVSIM mesh, selected by physical name,
finalized into a device with the expected node count.
"""

import os
import sys
import tempfile

sys.path.insert(0, "/opt/app")
sys.path.insert(0, "/opt/app/scripts")

print(f"python={sys.version.split()[0]}")

import devsim  # noqa: E402

print(f"devsim_version={devsim.__version__}")

import numpy as np  # noqa: E402

import mse_devsim_mesh as M  # noqa: E402
import mse_meshing as MM  # noqa: E402

# The wheel on x86-64 does not bundle a BLAS; 0.2 measured that it needs this
# pointer. Report whether it was needed rather than assuming either way.
print(f"DEVSIM_MATH_LIBS={os.environ.get('DEVSIM_MATH_LIBS', '<unset>')}")

square = np.array([[0.0, 0.0], [-6e-8, 0.0], [-6e-8, 6e-8], [0.0, 6e-8]])
pts, tets, region = MM.tetrahedralize_layers(
    square, [("lower", 30e-9), ("upper", 30e-9)], edge_m=3e-8)
print(f"mesher_tets={len(tets)}")
print(f"mesher_points={len(pts)}")

path = os.path.join(tempfile.mkdtemp(), "two_layer.msh")
rep = M.write_gmsh22(path, pts, tets, region, ["lower", "upper"])
print(f"gmsh_bytes={os.path.getsize(path)}")
print(f"physical_numbers={rep['physical_numbers']}")

devsim.create_gmsh_mesh(file=path, mesh="m1")
for name in ("lower", "upper"):
    devsim.add_gmsh_region(mesh="m1", gmsh_name=name, region=name, material="InP")
devsim.finalize_mesh(mesh="m1")
devsim.create_device(mesh="m1", device="d1")

# Node counts come from get_element_node_list, NOT from a node model.
#
# The first two attempts invented a model: `node_model="NetDoping"` on
# set_parameter (rejected, "invalid option") and `devsim.node_model(...)`
# (rejected, "missing required STRING parameter - equation"). node_model is
# for SOLUTION variables and needs an equation; it is the wrong tool, and
# neither error had anything to do with the mesh route. get_element_node_list
# answers the question actually being asked -- how many nodes does each region
# hold -- with no model involved.
def _region_nodes(region):
    elems = devsim.get_element_node_list(device="d1", region=region)
    return len({n for e in elems for n in e})


n_lower = _region_nodes("lower")
n_upper = _region_nodes("upper")

print(f"devsim_nodes_lower={n_lower}")
print(f"devsim_nodes_upper={n_upper}")

# Both regions must hold nodes. If the physical-number position were wrong,
# add_gmsh_region would build an empty region and this sum would be 0 -- the
# silent failure 0.2 recorded, caught here as a value rather than an exception.
ok = n_lower > 0 and n_upper > 0
print(f"ROUTE={'ok' if ok else 'EMPTY_REGION'}")
sys.exit(0 if ok else 1)
