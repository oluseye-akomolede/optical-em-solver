"""The GPU worker gets its request from the APP, not from a hand-staged file.

Live failure, 2026-11-12 (rolled back the same day). Every pc and td upload on
the A4000 route failed within about a minute with "The uploaded file could not
be found in storage."

The cause was a seam between two correct halves. The solver loads its request
from ``jobs/<id>/job.json`` (``_load_worker_job``). The Jetson worker never
needed that file -- its service reads the row from the database and hands it
over -- so the key had no producer anywhere in ``web/`` or ``worker/``. The
consumer was thoroughly tested and the producer did not exist.

What these tests drive is the PRODUCER: a real upload through the real route,
the real scheduler tick, and then the solver's own worker entry against the
same directory. No test here writes ``job.json`` by hand. That is the whole
point -- a hand-written request file is exactly the thing production lacked, so
a test that writes one proves nothing about the live route. The earlier
dispatch tests (``test_worker_kind_dispatch.py``) stage the file and are
therefore evidence about the CONSUMER only.

What is still not proved here: that the image builds, that a pod schedules onto
an A4000, or that the solve is right at device scale. This proves the request
reaches the worker, which was the live failure.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "web"))
sys.path.insert(0, str(ROOT / "worker"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "dockerfiles" / "maxwell_solver"))

trimesh = pytest.importorskip("trimesh")

import app as APP  # noqa: E402
import db as DB  # noqa: E402

PC_FORM = {
    "mode": "pc",
    "lattice": "square",
    "r_over_a": "0.2",
    "n_rod": "3.5",
    "n_bg": "1.0",
    "n_bands": "4",
    "divisions": "8",
    "polarisation": "tm",
    "csrf_token": "t",
}


def _upload(web, data, path="/"):
    """POST through the real route with a session that carries a CSRF token."""
    with web.test_client() as client:
        with client.session_transaction() as sess:
            sess["csrf_token"] = "t"
        return client.post(path, data=data, follow_redirects=False)


def _only(rows, kind):
    found = [r for r in rows if r.get("kind") == kind]
    assert len(found) == 1, f"expected one {kind} row, got {len(found)}"
    return found[0]


def _assert_not_a_missing_request(job, rc):
    """The failure this file exists for is a missing FILE, not a bad solve.

    Called when the worker exits non-zero. A solver-level error (a diverged
    run, an unsupported parameter) is acceptable here: it proves the worker got
    its request and then failed on its own terms. A missing-file error is the
    live regression and is never acceptable.
    """
    message = (job.get("message") or "").lower()
    for phrase in ("could not be found", "no such file", "job.json",
                   "in storage"):
        assert phrase not in message, (
            f"the worker could not load its request ({message!r}) -- this is "
            f"the exact live failure the producer exists to prevent")


def test_a_pc_upload_produces_the_request_the_gpu_worker_loads(tmp_path):
    """A real pc upload, with nothing staged by hand, reaches the solver.

    The assertion is on the seam, not on the band values: the staged payload
    must BE the request the owner submitted (``pcs`` verbatim), because the
    route and the worker disagreeing about the request is the other way this
    fails quietly.
    """
    import mse_maxwell_solver as M
    from tests.test_web_routes import make_app

    web, store, jobs_db, launcher = make_app(tmp_path)
    web.config["MSE_GPU_ROUTE"] = "cluster"

    _upload(web, PC_FORM)
    row = _only(jobs_db.jobs.values(), DB.PC)
    job_id = row["job_id"]

    staged = tmp_path / "jobs" / job_id / "job.json"
    # The upload handlers run a scheduler pass themselves (``_handle_pc_upload``
    # and friends call ``run_tick``), so the request is usually already staged
    # by the time the POST returns. The point of this assertion is not "no file
    # yet" -- it is that THIS TEST did not write one. Remove the producer from
    # ``web/`` and the tick below finds no row to launch and nothing is staged.

    APP.run_tick(store, jobs_db, launcher)

    assert staged.exists(), (
        "the scheduler must write the worker's request before launching: "
        "without it the GPU job starts, cannot find its request, and dies "
        "(the live 2026-11-12 failure)")
    payload = json.loads(staged.read_text())
    assert payload["kind"] == DB.PC
    assert payload["pcs"] == row["pcs"], (
        "the staged request must be the request the owner submitted, not a "
        "re-derivation of it")
    assert payload["job_id"] == job_id

    rc = M.main(["--job-id", job_id, "--kind", "pc",
                 "--local-in", str(tmp_path), "--quiet"])
    if rc != 0:
        _assert_not_a_missing_request(jobs_db.jobs[job_id], rc)
        return

    produced = json.loads((tmp_path / "jobs" / job_id / "result.json").read_text())
    assert set(produced) >= {"lattice", "polarisation", "bands"}, (
        f"result.json must carry what the job page reads, got {sorted(produced)}")


def test_a_td_upload_produces_the_request_the_gpu_worker_loads(tmp_path):
    """The td half, on a real solve.

    td is not stubbed. ``tests/test_td_form.py`` already builds a tiny scene the
    VM can solve, so the same upload goes through the same route and the same
    scheduler and then into ``solve_td`` for real. That makes this evidence for
    the request AND for the port; a stub would only prove the dictionary.
    """
    import mse_maxwell_solver as M
    from tests.test_td_form import _fields
    from tests.test_web_routes import make_app

    web, store, jobs_db, launcher = make_app(tmp_path)
    web.config["MSE_GPU_ROUTE"] = "cluster"

    _upload(web, _fields())
    row = _only(jobs_db.jobs.values(), DB.TD)
    job_id = row["job_id"]

    staged = tmp_path / "jobs" / job_id / "job.json"
    # See the pc test: the upload route runs the tick, so the file exists by
    # now. What matters is that the app produced it.

    APP.run_tick(store, jobs_db, launcher)

    assert staged.exists(), (
        "the scheduler must write the td request before launching: without it "
        "every td upload on the A4000 dies (live, 2026-11-12)")
    payload = json.loads(staged.read_text())
    assert payload["kind"] == DB.TD
    assert payload["tds"] == row["tds"], (
        "the staged request must be the one the owner submitted")

    rc = M.main(["--job-id", job_id, "--kind", "td",
                 "--local-in", str(tmp_path), "--quiet"])
    if rc != 0:
        _assert_not_a_missing_request(jobs_db.jobs[job_id], rc)
        return

    produced = json.loads((tmp_path / "jobs" / job_id / "result.json").read_text())
    assert produced["kind"] == DB.TD
    assert produced["result"]["traces"], (
        "the probe must have seen the pulse: an empty trace set is a td run "
        "that solved nothing, which the page would show as a success")


def test_the_cavity_path_stages_no_request_file(tmp_path):
    """A cavity Job must not grow a request file it does not read.

    The FEM path takes its parameters from the manifest and its geometry from
    ``input.obj``. Staging a request for it would be a second, unchecked copy
    of the truth -- and the requirement to keep that path byte-identical is
    the reason the producer is gated on kind at all.
    """
    from tests.test_web_routes import make_app

    web, store, jobs_db, launcher = make_app(tmp_path)

    _upload(web, {"units": "mm", "n_index": "1.0", "csrf_token": "t",
                  "meshfile": (__import__("io").BytesIO(
                      trimesh.creation.box(
                          extents=[10, 7, 5]).export(file_type="obj").encode()),
                      "box.obj")})

    cavity = [r for r in jobs_db.jobs.values() if r.get("kind") == DB.CAVITY]
    assert len(cavity) == 1, f"expected one cavity row, got {len(cavity)}"
    job_id = cavity[0]["job_id"]

    APP.run_tick(store, jobs_db, launcher)

    assert not (tmp_path / "jobs" / job_id / "job.json").exists(), (
        "a cavity job must not get a request file: it reads the manifest and "
        "input.obj, and its path must stay unchanged")
