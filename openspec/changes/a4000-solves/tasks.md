# Tasks: run owner uploads' solves on the cluster A4000s

## 1. Routing

- [x] 1.1 `web/db.py`: add `CLUSTER_GPU = "cluster-gpu"` and extend `TARGETS`.
      The column already stores a plain string, so no migration is needed; note
      in the comment that old rows are unaffected.
- [x] 1.2 `web/config.py`: `gpu_route()` reading `MSE_GPU_ROUTE`, defaulting to
      `cluster`, and treating an unrecognised value as `cluster`.
- [x] 1.3 `web/app.py`: split the single comparison into "needs a GPU" and
      "which GPU machine", per `design.md`. Keep the CPU-cluster path unchanged.

**Done notes (1.x).** `next_queued()` takes a tuple of targets
(`CLUSTER_TARGETS`) so a `cluster-gpu` row is picked up by the same single Job
slot as a `cluster` one; a row's own `target` is what decides `gpu=` at launch,
so the queue cannot launch an A4000 Job as a CPU one. `GPU_ROUTE_FALLBACK` was
REMOVED from the config: its docstring described a quota-slot fallback that no
code implemented, and a route only an operator sets does not need a third
value. Unknown values still mean the default.

## 2. The GPU job

- [x] 2.1 `web/jobs.py`: `build_job_manifest(..., gpu=False)`. When true, add
      `nvidia.com/gpu: 1` to BOTH `requests` and `limits`, the
      `nodeSelector`, the four thread env vars set to the CPU limit, and keep
      `activeDeadlineSeconds`. Pure, as today.
- [x] 2.2 The GPU image: reuse `Dockerfile.bench-cuda`'s already-built image
      line; the solver image needs `MSE_SOLVER_BACKEND=cuda` in the manifest
      env, not a new image.
- [x] 2.3 `manifests/mse/power-cap.yaml`: `requests.nvidia.com/gpu: '1'`.
      Tracked only; the lead applies it.

**Done notes (2.x).** No new image was needed (2.2 was a check, not a build):
the manifest sets `MSE_SOLVER_BACKEND=cuda` and strips the CPU-only
`MSE_CPU_MAX_TETS`, which describes a machine the GPU Job is not running on.
The Job stays 4 vCPU / 14Gi, and the quota stays 5 CPU / 18Gi with only the GPU
count raised 0 -> 1. An earlier version of this change shrank the Job to 2.5
vCPU / 6Gi inside a 3 CPU / 7Gi quota, on the reasoning that 4/14Gi "only fitted
because the GPU count was 0". That reason is false: CPU and memory quota do not
depend on the GPU count. Job 4 + app 0.5 = 4.5 <= 5, and 14 + 1 = 15 <= 18Gi, so
the original size was already admissible -- and 3/7Gi left no headroom for an
app rollout beside a solve. Thread vars are the integer part of the CPU limit
(4), derived from the manifest's own limit rather than hardcoded.

## 3. The honest failure

- [x] 3.1 Confirm the existing GPU-OOM wording reaches a cluster GPU job's row.
      The Jetson path builds it in `worker/`; the cluster path reads the Job's
      failure output in `web/`. Route the A4000 case through the same sentence
      (spec: gpu-solves requirement 3).

**Done note (3.1).** It did NOT reach it honestly. `FAILURE_MESSAGES["OOMKilled"]`
said "Try a simpler object", which is false advice for a card that ran out of
memory -- and the A4000 is a tighter budget than the machine it replaced, so it
is the failure the owner meets first. The sentence now names the machine.

## 4. Tests (tier 1 only)

- [x] 4.1 A GPU manifest has `requests == limits` for cpu, memory and GPU, a
      positive `activeDeadlineSeconds`, and the A4000 nodeSelector.
- [x] 4.2 Thread env vars equal the CPU limit in the GPU manifest.
- [x] 4.3 `MSE_GPU_ROUTE`: `cluster` (and unset) -> cluster-gpu; `jetson` ->
      jetson; a nonsense value -> cluster-gpu.
- [x] 4.4 The manifest states `requests.nvidia.com/gpu: '1'`.
- [x] 4.5 An out-of-memory GPU failure produces the plain sentence, not
      "contact support".
- [x] 4.6 The CPU manifest is unchanged by the GPU support (no card, no
      nodeSelector, `cpu` backend).

**Done notes (4.x).** Each new test was mutation-checked: dropping `gpu=` at
the launch site turns 4.1 red, and dropping `CLUSTER_GPU` from
`CLUSTER_TARGETS` turns 4.1 and 4.5 red. Two existing tests pinned the OLD
contract and were updated to state the new one rather than deleted: the 10 mm
box's default target (Jetson -> A4000) and the Job's resource size (now read
from `CFG`, so a future quota move does not fail them for the wrong reason).
The `FakeDb`/`FakeLauncher` doubles were corrected to the real signatures --
a fake `next_queued(target=str)` would never return a `cluster-gpu` row, so
every routing test above would have passed by launching nothing.

## 4b. The two blockers the lead found before deploy

- [x] 4b.1 `MSE_SOLVER_BACKEND` comes from `mse_backend.GPU`, not a literal.
      The test compares it with `mse_backend.BACKENDS`; mutating back to
      `"cuda"` turns it red.
- [x] 4b.2 A separate `MSE_SOLVER_GPU_IMAGE`, used for GPU jobs and never
      falling back to `MSE_SOLVER_IMAGE`; a GPU job with no CUDA image is
      refused before the Job is created. The app still starts without it.
- [x] 4b.3 The false comment ("The image is built with the CUDA stack") is
      gone.
- [x] 4b.4 `dockerfiles/maxwell_solver/Dockerfile.gpu` + `requirements-gpu.txt`:
      a CUDA 12.6.3 base matching the A4000 nodes, with a BUILD-TIME probe that
      calls the solver's own `mse_backend._missing_gpu_package()` so a GPU image
      missing the stack cannot reach Harbor.
- [x] 4b.5 `nvmath-python==0.9.0` **and** `nvidia-cudss-cu12==0.7.1.6` both
      pinned explicitly, read from the Jetson by the lead (04:18Z). The `cu12`
      extra is deliberately NOT used: it also drags in nvidia-cuda-runtime-cu12
      beside the base image's own CUDA 12.6.
- [x] 4b.6 `dockerfiles/maxwell_solver/gpu_stack_probe.py`, run by the build:
      the solver's own import probe, then a `ctypes` load of the cuDSS shared
      object. Loading needs no GPU, so a stackless image fails at BUILD time.
- [x] 4b.7 Probe mutation-checked in both directions on the dev VM: with the
      cuDSS distribution absent it refuses with the "pin it" message; with
      0.7.1.6 installed it locates the library and tries to load it.

**Measured fact that broke the first probe:** `nvidia-cudss-cu12` 0.7.1.6 is
DATA-ONLY -- it installs `nvidia/cu12/lib/libcudss.so.0` and no importable
`nvidia.cudss` package, so `find_spec("nvidia.cudss")` fails on a correct
install and the first probe would have refused a good image. The probe now
locates the library through the `nvidia-cudss-cu12` DISTRIBUTION instead. The
wheel also does not declare its `libcublas.so.12` dependency (the CUDA base
supplies it); because the probe actually LOADS the library, that class of miss
fails the build -- and did, locally, which is how the dependency was found.

**A second probe bug, caught by the first real image build.**
`import_probe()` asked `mse_backend._missing_gpu_package()` and treated any
non-empty return as a failure. But that helper returns the string `"the CUDA
stack"` as a LABEL for an error message when NOTHING is missing, so the probe
refused a correct image, with the self-contradicting line "the CUDA stack is not
importable". It now imports `mse_backend._GPU_PACKAGES` one name at a time and
reports the name that actually failed; both directions are tested on the dev VM.
The lesson generalises: a helper whose "nothing wrong" case shares a type with
its "something wrong" case cannot be used as a boolean.

**The corrected probe passed a real image build** (build VM, repo-root build
context): `GPU STACK IMPORTS OK`, then `cuDSS LOADS OK: libcudss.so.0`, image
tagged, exit 0. That is the probe's first clean run on the image it guards --
before it, the only observed run was the buggy one that refused a good build.
One build-context trap found on the way: the COPY paths are repo-root-relative,
so passing `dockerfiles/maxwell_solver/` as the context fails; it must be the
repo root.

**Done notes (4b).** The old test asserted `== "cuda"`: it encoded the bug
rather than catching it, so it was replaced by a membership check against
`mse_backend.BACKENDS`. A first attempt made `_launcher` read the GPU image
strictly, which failed an existing test that builds the app without one --
that was a real deployment risk (a missing GPU setting would stop the site
starting) and the read was made lenient, with the refusal left at the launch
boundary where the Job is created.

## 5. Deployment (the lead, not this seat)

- [ ] 5.1 Raise the live quota 0 -> 1 and apply the Job manifest.
- [ ] 5.2 Smoke a SMALL mesh on the A4000 and read the log; verify a real pod
      starts (a server dry-run is not admissibility).
- [ ] 5.3 Rollback: `MSE_GPU_ROUTE=jetson` and re-apply the quota at 0.

**Lead's red-path check (2026-11-03, merged image).** In the built image, run as root
(as the image's own user, `pip uninstall` is refused and the package silently stays, so
a non-root mutation proves nothing): with `nvidia-cudss-cu12` uninstalled the probe exits 1
with "no nvidia-cudss-cu12 distribution ..."; with `nvmath-python` uninstalled it fails with
"'nvmath' is not importable". The intact image prints both OK lines and exits 0.

## 6. pc and td uploads on the A4000 (Jetson offline, 2026-11-12)

**Context.** The Jetson is offline, so `photonic-bands` (pc) and `time-domain`
(td) uploads have no route. This section gives them one WITHOUT touching the
existing `mesh` FEM path, whose `--local-in`/`--local-out` contract and
`_write_results` DB path already work on the cluster and must keep working.

**Why not route pc/td through the FEM container.** `spark-fem-solver.py` solves
an eigenproblem on a tetrahedral mesh of an uploaded solid. pc is a
plane-wave-expansion band solve on a lattice, td is an FDTD march on a grid;
neither has a mesh, a stiffness matrix or a mode list, and both solvers already
exist in `dockerfiles/maxwell_solver/` (`pc.py`, `fdtd.py`, `fdtd_layout.py`)
and are ALREADY IN the GPU image. What is missing is only the translation layer
in `worker/` (`pc_solve.py`, `td_solve.py`): validation plus params->solver-call
plus solver-result->result-dict. Port that layer into the GPU image and call it
from a small entry point with the same `--local-in`/`--local-out` contract the
FEM container uses.

**The two layers are not the same shape, and the port must keep the difference.**
`worker/pc_solve.py::solve_pc(job, *, solver=None)` is pure translation: it
imports the solver lazily and returns a JSON-ready dict (`lattice`,
`polarisation`, `labels`, `k_points`, `bands`) with no I/O at all.
`worker/td_solve.py::solve_td(job, store_in, store_out=None, ...)` takes the
object store, because an FDTD run stages field output; it has its own OOM
detection (`is_out_of_memory`, `oom_message`) and an isolated child-process path
(`solve_td_isolated`). The pc port is a copy. The td port must also carry its
storage handles, and its OOM sentence, rather than being flattened into the pc
shape.

```mermaid
flowchart LR
  A[upload + params] --> B[MSE_GPU_ROUTE=cluster]
  B --> C[cluster-gpu Job: A4000]
  C --> D[entry.py: kind=pc|td]
  D --> E[worker logic ported into image]
  E --> F[pc.py / fdtd.py solver]
  F --> G[result JSON]
  G --> H[_write_results DB path - unchanged]
  B -.->|jetson| I[Jetson bench - offline]
```

**Constraints this section inherits and does not change.**
- The one-Job quota slot holds until raised by the lead (5.1); this section adds
  no second Job type to a live quota.
- No change to the `mesh` branch of `entry.py`; the CPU-cluster manifest is
  untouched.
- Bounded: the GPU manifest's cpu/memory limits stay as reviewed in 4.1/4.2;
  pc/td must fail with a plain sentence on OOM like the FEM path does (4.5).

### 6.1 OpenSpec first (this commit)

- [x] 6.1.1 Record the design above in this change, and amend the
      `photonic-bands` requirement that pc "SHALL run on the Jetson worker only,
      and the cluster SHALL refuse it". That wording is now wrong when the
      Jetson is offline. Scope checked: `time-domain` has NO routing requirement
      of its own -- td's cluster refusal lives in `web/db.py::next_queued`'s
      `kind = 'cavity'` whitelist and in `web/jobs.py::create`'s refusal -- so
      there is no td spec requirement to amend and none is invented here.

### 6.2 The entry point (landed: `--kind` on the solver itself)

The entry point is `dockerfiles/maxwell_solver/mse_maxwell_solver.py`, NOT an
`entry.py` -- there is no such file in this image, and 6.2.1 below originally
named one. Corrected here after reading the tree.

- [x] 6.2.1 `mse_maxwell_solver.py` gains `--kind` = `cavity` | `pc` | `td`,
      defaulting to `cavity` so every Job launched before the flag existed is
      unchanged. The dispatch is the FIRST thing `main()` does, before
      `max_tets()` is resolved and before `--units`/`--n-modes` are read, so a
      pc/td run cannot be half-configured by flags that do not apply to it.
- [x] 6.2.2 `worker/pc_solve.py` and `worker/td_solve.py` copied into the GPU
      image UNCHANGED (`COPY worker/<f>.py /opt/app/`), not re-implemented, so
      both routes run the same translation by construction. td keeps its
      `store_in`/`store_out` handles and its `solve_td_isolated` child path;
      pc takes the injectable-solver form. Neither pulls a new dependency in
      at module scope (`pc_solve` is stdlib-only; `td_solve` needs numpy, and
      imports `pc`/`fdtd`/`fdtd_layout`/`mse_common`/`mse_parts` lazily from
      the image tree, all five of which ship there).
- [x] 6.2.3 A plain sentence on failure: `_run_worker_kind` runs
      `owner_message(exc)` exactly as the cavity path does, records
      `db.fail(...)` with the peak RSS, and exits non-zero. It deliberately
      does NOT write `result.json` on failure -- an empty result file would be
      read by the page as a successful solve of nothing.

### 6.3 Tests (tier 1 only)

- [x] 6.3.1 `tests/test_worker_kind_dispatch.py::test_kind_pc_dispatches_to_the_worker_module_and_writes_result`
      -- a pc `--local-in`/`--local-out` round trip produces the result keys
      the Jetson path produces. The solver is a stub with `pc.bands_from_mesh`'s
      exact signature, so a wrong call is not silently accepted.
- [x] 6.3.2 `test_a_malformed_pc_request_fails_loudly_and_writes_no_result`
      -- the failure shape, which is the half the Jetson path gets from its
      service and this path has to build.
- [x] 6.3.3 `test_kind_cavity_still_takes_the_mesh_path` and
      `test_the_cavity_manifest_is_byte_identical_after_the_kind_dispatch`
      -- the FEM path is unchanged, asserted on the manifest byte-for-byte
      rather than on "it did not raise".
- [x] 6.3.4 Mutation-proved, not just passed: with the dispatch restored to
      `if False:` both 6.3.1 and the mesh-option test fail; with the dispatch
      moved BELOW the `max_tets()` resolution, `test_a_pc_job_ignores_every_mesh_option`
      fails on `assert 7 == 600000` -- a pc job leaking its cap into the
      process-wide global that every later cavity solve inherits.
- [x] 6.3.5 `test_kind_td_dispatches_to_the_worker_module_and_writes_result`
      -- the td half, deliberately NOT stubbed. It reuses
      `tests/test_td_solve.py`'s own tiny job (`_job`/`_Store`) and drives it
      through `--kind td`, so it is evidence for the PORT (the module is
      reachable from the image path, its store handles are passed correctly,
      its payload encodes) rather than the wiring.
- [x] 6.3.6 **This test found a bug in the code it was testing.** `solve_td`
      returns numpy arrays in `payload["result"]` (the probe traces), and
      `_report_worker_result` passed the payload straight to `json.dumps`.
      Every real td Job on the A4000 would have solved the whole simulation and
      THEN crashed writing the result. Fixed with `_json_safe` (arrays become
      lists; anything else JSON cannot hold is reduced to `repr` rather than
      killing a finished solve). Mutation-proved: restoring the raw
      `json.dumps(payload)` fails 6.3.5 with
      `TypeError: Object of type ndarray is not JSON serializable`.
      A stub-based td test, as first proposed, would have missed this entirely
      -- the stub would have returned plain JSON-shaped values.
- [x] 6.3.7 The `_report_worker_result` docstring claimed `result.json` is
      "the same key the Jetson route writes" and the page "needs no branch".
      That is false for td: `web/app.py` reads `spectrum.json` and `trace.bin`
      for a td job, which `solve_td` already writes to the store itself via
      `write_results`. For td, `result.json` is the run record, not the
      product. Corrected in place.

### 6.4 The td route (found by the reviewer's read of 6.2)

- [x] 6.4.1 `web/db.py`: a td row was hardcoded to the Jetson in TWO places --
      `create_job`'s target refusal (which raised for any target but jetson) and
      `next_queued`'s kind whitelist (which was already kind-and-target pair
      based). Fixing only the first would have been worse, not better: the
      handler would then create a `cluster-gpu` td row that the queue still
      refused to see, and the owner's upload would sit in a queue nothing reads.
      The refusal is now on the PAIR: any GPU kind on the CPU `cluster` target
      raises, both GPU targets are accepted. `GPU_KINDS` names the set once so
      the two sites cannot drift.
- [x] 6.4.2 Both upload handlers already routed pc and td through the same
      `_gpu_target()` helper, but it had no test that drove it through the real
      upload for td. `test_a_td_upload_is_routed_by_the_setting_not_by_a_hardcoded_machine`
      runs the form four times (unset, `cluster`, `jetson`, nonsense) and checks
      the row's target each time.
- [x] 6.4.3 The abandoned-GPU reroute: a pc/td row now moves to `cluster-gpu`
      when the route says cluster, and stays put when the route says jetson.
      The owner's message names the queue it actually moved to; the old text
      said "the cluster queue" for every kind.
- [x] 6.4.4 Spec delta written for `time-domain`. The requirement said a td job
      "SHALL never be routed to the cluster" as a flat rule -- true when the
      Jetson was the only machine with a td solver, false now. It now says the
      route decides, and the refusal is on the (kind, target) pair.

**A test that pinned the old contract was updated, not deleted:**
`test_a_td_form_queues_a_jetson_td_row...` asserted `target == jetson`
unconditionally, which is exactly the hardcoding 6.4.1 removed. It now asserts
the target is one of the two GPU targets and the ROUTE MATRIX test pins which.
Its row-contents assertions (the worker's own reader and layout accept the
stored request) are unchanged and route-independent.

**Mutation-proved:** hardcoding `_gpu_target()` back to `return DB.JETSON`
fails three of the four route cases (`cluster`, unset, nonsense) and passes the
jetson one -- so the test fails for the reason it names, not for a reason common
to all four.

**Still not proved by these tests, and must not be implied:** that the GPU
image builds, that `pc.py`/`fdtd.py` solve correctly at production size, that a
pod schedules onto the A4000, and that a real pc upload returns a correct band
diagram. pc is driven through a stub solver, so that half proves the WIRING.
td runs a real (tiny, VM-sized) solve, so it proves the PORT but says nothing
about device scale. The image build and the A4000 smoke are the lead's (5.x).

**Not in this section.** The image rebuild and push, the quota raise, and the
smoke on a real A4000 pod: all the lead's (5.x). This seat commits and hands up.
