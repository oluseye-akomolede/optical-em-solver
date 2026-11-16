"""A pc job solved on the CLUSTER route shows its band diagram on the page.

This is the seam a live proof job fell through on 2026-11-12 (job 9ee91e75 on
gpu-node-b). Storage held a real diagram -- 30 k-points x 4 bands, Gamma-X-M-
Gamma, band 1 = 0 at Gamma -- the row was ``status=done, stage=pc``, and
``GET /jobs/<id>/status`` returned ``bands: null``.

The cause was not a bug in either half. Each half was reviewed and worked:

* the Jetson worker POSTs its bands back, ``worker_api`` validates them and
  ``finish_jetson_with_bands`` merges them into ``pcs`` -- the page reads that;
* a cluster Job runs the same solver in the image and writes ``result.json``.

Nothing joined them. A cluster pc Job never writes ``pcs.bands``, so the page's
only source of truth for that route was empty.

The test therefore drives the CLUSTER route end to end and asserts the page's
status payload carries the bands, with **no hand-written DB bands anywhere** --
that is the whole point. Writing ``pcs['bands']`` by hand would pass on the
broken code, because the broken code already reads that column.

What it does NOT prove: that the real image solves pc correctly, or that a pod
schedules. The result.json here is the payload shape ``worker/pc_solve.py``
returns, which ``tests/test_pc_solve.py`` pins.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))

import app as APP  # noqa: E402
import db as DB  # noqa: E402
import storage as STORE  # noqa: E402

from tests.test_web_routes import FakeDb, FakeLauncher, MemoryStore  # noqa: E402


PC_REQUEST = {"lattice": "square", "r_over_a": 0.2, "n_rod": 3.5,
              "n_bg": 1.0, "n_bands": 3, "divisions": 8,
              "polarisation": "tm"}

# Job ids are real UUIDs: the status route aborts 404 on anything that is not,
# so a readable string like "pc-cluster-1" tests the 404 path instead.
_PC_CLUSTER = "6f1c2e40-1d3a-4b7e-9c55-0a1b2c3d4e5f"
_PC_JETSON = "6f1c2e40-1d3a-4b7e-9c55-0a1b2c3d4e60"
_PC_NO_FILE = "6f1c2e40-1d3a-4b7e-9c55-0a1b2c3d4e61"

# The exact shape worker/pc_solve.py::solve_pc returns for pc: a JSON-ready
# dict with these five keys.
CLUSTER_PC_RESULT = {
    "lattice": "square",
    "polarisation": "tm",
    "labels": ["G", "X", "M", "G"],
    "k_points": [[0.0, 0.0], [0.5, 0.0], [0.5, 0.5], [0.0, 0.0]],
    "bands": [[0.0, 0.18, 0.26], [0.31, 0.29, 0.27],
              [0.42, 0.38, 0.35], [0.0, 0.18, 0.26]],
}


def _cluster_pc_job(db, job_id, request=None):
    """A pc row as a CLUSTER Job leaves it: request in ``pcs``, no bands."""
    db.create_job(job_id, "etch.obj", "mm", 1.0, 0,
                  kind=DB.PC, pcs=dict(request or PC_REQUEST))
    return job_id


def _done(job_id):
    """Mark the row done the way the solver's own DB client does."""
    return {job_id: DB.DONE}


def _app(tmp_path, db):
    # create_app returns (app, store, jobs_db, launcher); the tests want the app.
    app, _store, _db, _launcher = APP.create_app(
        {"TESTING": True, "MSE_LOCAL_STORE": str(tmp_path),
         "MSE_DB_MOCK": db, "MSE_JOB_LAUNCHER": FakeLauncher()})
    return app


@pytest.fixture()
def cluster_pc(tmp_path):
    """A store holding a CLUSTER pc Job's result.json, and a matching row.

    ``pcs`` holds ONLY the request -- what ``pc_form.request_json`` writes and
    what a cluster Job leaves behind, since the solver has no write path to
    that column. ``bands`` is deliberately absent from the row.
    """
    store = MemoryStore(str(tmp_path))
    db = FakeDb()
    job_id = _cluster_pc_job(db, _PC_CLUSTER)
    store.write(STORE.job_key(job_id, "result.json"),
                json.dumps(CLUSTER_PC_RESULT).encode())
    db.jobs[job_id].update(status=DB.DONE, stage=DB.DONE)
    return _app(tmp_path, db), store, db, job_id


def test_a_cluster_pc_job_shows_its_bands_on_the_status_payload(cluster_pc):
    """THE regression: a done cluster pc job returns its diagram, not null.

    Fails on ed15a3a with ``bands is None``: that code reads only
    ``pcs.get('bands')``, which a cluster Job never fills. Passes once the
    status route falls back to the solver's own ``result.json``.
    """
    app, store, db, job_id = cluster_pc
    resp = app.test_client().get(f"/jobs/{job_id}/status")
    assert resp.status_code == 200
    payload = resp.get_json()

    assert payload["status"] == DB.DONE
    assert payload["kind"] == DB.PC
    assert payload["bands"] is not None, (
        "a cluster pc job that wrote a real band diagram to result.json must "
        "show it; null here is the live regression (job 9ee91e75)")
    assert payload["bands"]["bands"] == CLUSTER_PC_RESULT["bands"]
    assert payload["bands"]["k_points"] == CLUSTER_PC_RESULT["k_points"]
    assert payload["bands"]["labels"] == CLUSTER_PC_RESULT["labels"]


def test_the_bridge_stays_out_of_the_way_of_the_jetson_shape(tmp_path):
    """A row that ALREADY has pcs.bands is served from the row, unchanged.

    The Jetson route is the reviewed, validated path; the cluster fallback must
    not override or reshape what it stored. This is the guard against "fix the
    cluster by changing what every route returns".
    """
    store = MemoryStore(str(tmp_path))
    db = FakeDb()
    jetson_bands = {"labels": ["G", "X"], "k_points": [[0.0, 0.0], [0.5, 0.0]],
                    "bands": [[0.0, 1.0], [0.2, 0.9]]}
    job_id = _cluster_pc_job(db, _PC_JETSON,
                             request={"lattice": "square"})
    db.jobs[job_id]["pcs"] = dict(PC_REQUEST, bands=jetson_bands)
    db.jobs[job_id].update(status=DB.DONE, stage=DB.DONE)
    # A DIFFERENT diagram in storage, to prove the row wins.
    store.write(STORE.job_key(job_id, "result.json"),
                json.dumps(CLUSTER_PC_RESULT).encode())

    payload = _app(tmp_path, db).test_client().get(
        f"/jobs/{job_id}/status").get_json()

    assert payload["bands"] == jetson_bands, (
        "the row's validated bands must win; the cluster fallback is only for "
        "a row that has none")


def test_a_malformed_cluster_result_reads_as_no_diagram(cluster_pc):
    """A ragged result.json must not blank the page or raise.

    The status poll is what draws the page, and it runs on a timer. An exception
    here is an empty page with no message, so a bad file degrades to
    ``bands: null`` -- the behaviour a job with no diagram already has.
    """
    app, store, db, job_id = cluster_pc
    bad = dict(CLUSTER_PC_RESULT)
    bad["bands"] = [[0.0, 1.0], [0.2]]  # ragged: only two vectors, one short
    store.write(STORE.job_key(job_id, "result.json"), json.dumps(bad).encode())

    resp = app.test_client().get(f"/jobs/{job_id}/status")
    assert resp.status_code == 200, "a status poll must never 500 on bad storage"
    assert resp.get_json()["bands"] is None


def test_a_non_finite_band_is_refused_like_a_ragged_one(cluster_pc):
    """NaN/Infinity are refused by the bridge, not passed to the plot.

    ``json.loads`` accepts bare ``NaN``/``Infinity`` and ``isinstance(nan,
    float)`` is True, so a type check alone would serve a NaN to the plot --
    the same trap ``_band_payload`` documents for the worker body, and the same
    one the reviewer found in a4000's ``_json_safe``.
    """
    app, store, db, job_id = cluster_pc
    bad = dict(CLUSTER_PC_RESULT)
    bad["bands"] = [[0.0, float("nan")], [0.2, 0.3],
                    [0.4, 0.5], [0.6, 0.7]]
    store.write(STORE.job_key(job_id, "result.json"),
                json.dumps(bad).encode())  # allow_nan=True: emits bare NaN

    resp = app.test_client().get(f"/jobs/{job_id}/status")
    assert resp.status_code == 200
    assert resp.get_json()["bands"] is None


def test_a_cluster_pc_job_with_no_result_file_still_shows_null(tmp_path):
    """A done pc row whose file is missing keeps the old null, not a 500.

    The fallback reads storage on every poll for a done cluster pc job, so the
    absent-file case is the ordinary one for a job that failed after being
    marked done, or was solved before this bridge existed.
    """
    db = FakeDb()
    job_id = _cluster_pc_job(db, _PC_NO_FILE)
    db.jobs[job_id].update(status=DB.DONE, stage=DB.DONE)

    resp = _app(tmp_path, db).test_client().get(f"/jobs/{job_id}/status")
    assert resp.status_code == 200
    assert resp.get_json()["bands"] is None
