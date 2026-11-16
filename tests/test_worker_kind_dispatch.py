"""The solver's ``--kind`` dispatch: a pc/td Job runs the worker's own code.

The network route is the Jetson worker (``test_worker.py``); this file covers
the OTHER route, where the same upload is solved as a Kubernetes Job on the
A4000 because the Jetson is offline. Both routes must run the SAME translation
layer, or a pc job's result depends on which machine happened to be up.

What is proved here:

* ``--kind pc`` and ``--kind td`` reach the worker modules and nothing else --
  the mesh options are never read, so a pc Job cannot be half-configured by
  ``--max-tets`` or ``--units``.
* the run is recorded at ``jobs/<id>/result.json`` with the payload keys the
  page expects. For pc that file is what the page reads. For td it is the run
  record: the page reads ``spectrum.json``/``trace.bin``, which ``solve_td``
  writes itself via ``write_results``.
* a translation error becomes a non-zero exit and a recorded failure, not a
  traceback with a zero exit.

pc is driven through a stub solver, so it checks the WIRING. td is deliberately
NOT stubbed -- it runs a real tiny solve through ``tests/test_td_solve.py``'s
own job, so it is evidence for the PORT: the worker module is reachable from
the image path, its store handles are passed correctly, and its payload encodes.
That last one is not hypothetical: this test caught ``solve_td``'s numpy trace
arrays being handed to a raw ``json.dumps``, which would have crashed every real
td Job on the A4000 AFTER the solve had finished.

What is NOT proved here, and must not be implied: that DEVSIM, cupy or a GPU
exists in the image, that ``pc.py``/``fdtd.py`` solve correctly at production
size, or that the manifest schedules. Those are deploy-time facts.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dockerfiles" / "maxwell_solver"))
sys.path.insert(0, str(ROOT / "worker"))

PC_REQUEST = {
    "lattice": "square",
    "r_over_a": 0.2,
    "n_rod": 3.5,
    "n_bg": 1.0,
    "n_bands": 3,
    "divisions": 8,
    "polarisation": "tm",
}


def _fake_pc_module(calls):
    """A stand-in for ``pc`` with the real call signature.

    Deliberately positional-and-keyword identical to ``pc.bands_from_mesh``: a
    stub with a looser signature would accept a wrong call and pass.
    """
    module = types.ModuleType("pc")
    module.high_symmetry_path = (
        lambda lattice, points_per_segment=10: (
            ["G", "X"], [[0.0, 0.0], [0.5, 0.0]])
    )

    def bands_from_mesh(lattice, divisions, r_over_a, n_rod, n_bg, k_points,
                        n_bands, polarisation=None):
        calls.append({"lattice": lattice, "polarisation": polarisation,
                      "r_over_a": r_over_a, "n_bands": n_bands})
        return k_points, [[0.4, 0.5, 0.6][:n_bands] for _ in k_points]

    module.bands_from_mesh = bands_from_mesh
    return module


def _write_job(root: Path, job_id: str, kind: str, request: dict) -> None:
    d = root / "jobs" / job_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "job.json").write_text(json.dumps({kind: request}))


def test_kind_pc_dispatches_to_the_worker_module_and_writes_result(
        tmp_path, monkeypatch):
    """The whole cluster-side pc path, with the solver stubbed.

    This is the claim the change exists to make: a pc upload can be solved on
    the A4000 by the SAME code the Jetson runs. Asserted on the result FILE and
    the call the stub received, not on the exit code alone -- a dispatch that
    returned 0 having solved nothing would also exit 0.
    """
    import mse_maxwell_solver as M

    calls = []
    monkeypatch.setitem(sys.modules, "pc", _fake_pc_module(calls))
    monkeypatch.delenv("MSE_MAX_TETS", raising=False)
    _write_job(tmp_path, "pc1", "pcs", PC_REQUEST)

    rc = M.main(["--job-id", "pc1", "--kind", "pc",
                 "--local-in", str(tmp_path), "--quiet"])

    assert rc == 0
    result = json.loads((tmp_path / "jobs" / "pc1" / "result.json").read_text())
    assert set(result) >= {"lattice", "polarisation", "labels",
                           "k_points", "bands"}, (
        f"result.json must carry what the job page reads, got {sorted(result)}")
    assert result["lattice"] == "square"
    assert result["polarisation"] == "tm"
    assert len(calls) == 1, "the solver must be called exactly once"
    assert calls[0]["r_over_a"] == 0.2, (
        "the request must reach the solver unmodified -- a lost field is a "
        "solve of a different crystal")


def test_a_pc_job_ignores_every_mesh_option(tmp_path, monkeypatch):
    """``--max-tets`` and friends must not reach a pc job.

    The dispatch happens before the mesh options are resolved. If they were
    read, ``max_tets()`` could refuse a pc job for a count that has no meaning
    for a band solve -- and the owner would be told their band diagram was too
    large.

    Proved by setting an impossible cap: if the pc path read it, the run would
    fail or the global would move.
    """
    import mse_maxwell_solver as M

    calls = []
    monkeypatch.setitem(sys.modules, "pc", _fake_pc_module(calls))
    _write_job(tmp_path, "pc2", "pcs", PC_REQUEST)

    before = M.max_tets()
    rc = M.main(["--job-id", "pc2", "--kind", "pc", "--max-tets", "7",
                 "--local-in", str(tmp_path), "--quiet"])

    assert rc == 0, "a pc job must not be refused by the tetrahedron cap"
    assert len(calls) == 1
    assert M.max_tets() == before, (
        "a pc job must not change the process-wide cap: set_max_tets writes a "
        "module global, and every later cavity solve in the process would "
        "inherit a pc job's limit")


def test_a_malformed_pc_request_fails_loudly_and_writes_no_result(
        tmp_path, monkeypatch):
    """A request the worker module refuses is a FAILED job, not an empty one.

    ``solve_pc`` validates by key. A row missing ``r_over_a`` must raise its own
    typed error, which this path turns into exit 1 -- and must NOT leave a
    result.json behind, because the page cannot tell an empty result from a
    solve that returned nothing.
    """
    import mse_maxwell_solver as M

    broken = dict(PC_REQUEST)
    del broken["r_over_a"]
    _write_job(tmp_path, "pc3", "pcs", broken)

    rc = M.main(["--job-id", "pc3", "--kind", "pc",
                 "--local-in", str(tmp_path), "--quiet"])

    assert rc != 0, "a request the worker module rejects must not exit 0"
    assert not (tmp_path / "jobs" / "pc3" / "result.json").exists(), (
        "a failed pc job must not write a result file -- the page would show "
        "an empty band diagram as a success")


def test_kind_td_dispatches_to_the_worker_module_and_writes_result(tmp_path):
    """The td half of the same claim, on a REAL tiny solve.

    Deliberately NOT stubbed. ``tests/test_td_solve.py`` already runs a tiny td
    job on this VM (``_job``/``_Store``/``PLENTY``), so the same request can go
    through the solver's own ``--kind td`` dispatch instead of a fake. That
    makes this test evidence for the PORT rather than the wiring: it fails if
    ``td_solve`` was not copied into the image, if its object-store handles are
    passed wrongly, or if the result the worker returns is not the dict the
    page reads.

    What it still does not prove: that the GPU image builds or that a pod
    schedules onto an A4000. The tiny job is sized for the VM, not the device.
    """
    import mse_maxwell_solver as M

    from tests.test_td_solve import _job, _Store

    job = _job()
    d = tmp_path / "jobs" / job["job_id"]
    d.mkdir(parents=True)
    (d / "job.json").write_text(json.dumps(job))
    (d / "input.obj").write_bytes(_Store().read("jobs/j1/input.obj"))

    rc = M.main(["--job-id", job["job_id"], "--kind", "td",
                 "--local-in", str(tmp_path), "--quiet"])

    assert rc == 0, "a well-formed tiny td job must exit 0"
    result = json.loads((d / "result.json").read_text())
    assert set(result) >= {"job_id", "kind", "modes", "result", "estimate",
                           "caveats", "files"}, (
        f"result.json must carry what the job page reads, got {sorted(result)}")
    assert result["kind"] == "td"
    assert result["modes"] == [], "a td job produces no modes"
    assert result["result"]["traces"], (
        "the probe must have seen the pulse: an empty trace set is a td run "
        "that solved nothing, which the page would show as a success")


def test_a_diverged_td_run_writes_strict_json_not_nan(tmp_path, monkeypatch):
    """Non-finite numbers must not reach ``result.json`` as bare NaN/Infinity.

    ``json.dumps`` emits ``NaN`` and ``Infinity`` by default, and neither is
    valid JSON -- a strict reader rejects the whole document. A diverged td run
    is exactly when a nan appears, so the failure would land on the run record
    of the job that most needed one: the solve finishes, the file is written,
    and nothing can parse it.

    The payload is the real shape ``solve_td`` returns (numpy arrays in
    ``result["traces"]``), with a diverged trace patched into the worker, so
    this exercises the dispatch and ``_report_worker_result`` both. The parse
    uses ``parse_constant`` to raise, because ``json.loads`` accepts bare NaN
    too -- parsing without it would pass on the very file this refuses.
    """
    import mse_maxwell_solver as M

    import td_solve

    real_solve_td = td_solve.solve_td

    def diverged(job, store_in, store_out=None, *args, **kwargs):
        payload = real_solve_td(job, store_in, store_out, *args, **kwargs)
        # fdtd's traces are a C-ordered (probe, step) array; the first sample of
        # probe 0 is where a diverged field would show first.
        traces = payload["result"]["traces"]
        assert getattr(traces, "ndim", 0) == 2 and traces.shape[1] > 0
        traces[0, 0] = np.float32("nan")
        payload["result"]["diverged"] = float("-inf")
        payload["result"]["nested"] = {"ratio": np.float32("nan")}
        return payload

    monkeypatch.setitem(sys.modules, "td_solve", td_solve)
    monkeypatch.setattr(td_solve, "solve_td", diverged)

    from tests.test_td_solve import _job, _Store

    job = _job()
    d = tmp_path / "jobs" / job["job_id"]
    d.mkdir(parents=True)
    (d / "job.json").write_text(json.dumps(job))
    (d / "input.obj").write_bytes(_Store().read("jobs/j1/input.obj"))

    rc = M.main(["--job-id", job["job_id"], "--kind", "td",
                 "--local-in", str(tmp_path), "--quiet"])
    assert rc == 0

    text = (d / "result.json").read_text()

    def refuse(name):
        raise AssertionError(
            f"result.json contains {name!r}: that is not valid JSON and a "
            f"strict reader rejects the whole run record")

    result = json.loads(text, parse_constant=refuse)

    traces = result["result"]["traces"]
    assert traces[0][0] is None, (
        "a nan must become null, not be dropped: the reader has to see that "
        "the number was not finite")
    assert result["result"]["diverged"] is None
    assert result["result"]["nested"]["ratio"] is None, (
        "a numpy scalar nan must be caught too -- np.float32 is not a float")


def test_kind_cavity_still_takes_the_mesh_path():
    """The dispatch is additive: cavity must not be diverted.

    A guard nobody feeds rots, and so does a dispatch whose only tested branch
    is the new one. ``--kind cavity`` is the default and every existing Job.
    """
    import mse_maxwell_solver as M

    args = M.build_parser().parse_args(["--job-id", "x"])
    assert args.kind == "cavity", (
        "the default must stay 'cavity': an omitted --kind is every Job that "
        "was launched before this flag existed")
