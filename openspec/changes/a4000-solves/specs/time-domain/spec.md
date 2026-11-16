# time-domain Specification (delta)

## MODIFIED Requirements

### Requirement: The worker SHALL run a time-domain job only with the memory it needs

The worker SHALL run at most one GPU job at a time when one of them is `td`.
Before starting a `td` job it SHALL check free device memory against the job's
estimate; when memory is short it SHALL leave the job queued with a status
saying the Jetson is busy, not fail it. A `td` job SHALL wait at most 60
minutes as "Jetson busy" and then fail with a readable message. A device
out-of-memory error during the run (another team's job started after the check)
SHALL fail the job with a readable message, not a generic error. A `td` job
SHALL be stopped after 45 minutes of run time (the 30-minute estimate limit plus
a margin) and fail with a message naming that limit.

WHERE a `td` job may run SHALL be chosen by the GPU route, and by nothing else.

- On the `jetson` route, `target = jetson`. No path that can change a job's
  routing (the unclaimed-GPU fallback, the abandoned-GPU reroute, the reaper and
  release) SHALL move it to the CPU cluster, which cannot run it.
- On the `cluster` route, `target = cluster-gpu`, solved as an A4000 Job whose
  entry point dispatches on `--kind td`. The GPU image carries `td_solve.py`
  and the solver under it.

The REFUSAL SHALL be on the (kind, target) pair, not on the kind alone:

- A `td` row aimed at the CPU `cluster` target SHALL be refused at creation.
  That image has no time-domain solver, so such a row would take the one quota
  slot and fail only after the wait.
- A `cluster-gpu` `td` row SHALL be visible to `next_queued`, or the upload
  would sit in a queue nothing reads.

A `td` job's refusal SHALL name the route it is allowed on. The requirement this
replaces said "never routed to the cluster" as a flat rule, written when the
Jetson was the only machine with a time-domain solver; it was true then and is
false now.

#### Scenario: a busy Jetson delays, not fails
- **WHEN** a `td` job's estimate exceeds the Jetson's free memory at start
- **THEN** the job stays queued with a "Jetson busy" status and runs once
  memory is free

#### Scenario: waiting for memory does not use up the retries
- **WHEN** the worker defers a `td` job because the Jetson is busy, any number
  of times within the 60 minutes
- **THEN** the job's release count is unchanged (a busy machine is no verdict
  on the job), the 60 minutes are counted from the FIRST deferral and later
  deferrals do not restart them, and the job is not handed out again for 60
  seconds after each deferral, so the worker does not claim it straight back
- **AND** only a `td` job can be deferred this way, and only by the worker that
  holds its lease
- **AND** a release or an expired lease requeues the job with a fresh wait: a
  deferral after that starts a new 60 minutes, so an old wait cannot fail it

#### Scenario: a Jetson that stays busy fails readably
- **WHEN** free memory stays short for 60 minutes
- **THEN** the job fails with a message saying the Jetson stayed busy
- **AND** it is finished like any failed job: its lease is released and its
  finish time is set
- **AND** on the `jetson` route it was never moved to the CPU cluster queue

#### Scenario: the upload's target follows the route setting
- **WHEN** a valid td form is uploaded, with `MSE_GPU_ROUTE` unset, set to
  `jetson`, set to `cluster`, or set to a value nothing recognises
- **THEN** the row's `target` is `cluster-gpu` for unset, `cluster`, and the
  unrecognised value, and `jetson` for `jetson`
- **AND** the row's `kind` is `td` in every case
- **AND** the stored request is the same in every case: the route decides the
  machine, never the parameters

#### Scenario: a td row on the CPU cluster is refused by name
- **WHEN** a `td` row is created with `target = cluster`
- **THEN** creation raises, naming the GPU targets it may use
- **AND** a `cluster-gpu` target is accepted for the same kind, so the refusal
  is about the CPU cluster and not about td

#### Scenario: a td row on cluster-gpu is picked up by the Job queue
- **WHEN** a queued `td` row has `target = cluster-gpu`
- **THEN** `next_queued` returns it
- **AND** a `td` row with `target = cluster` is still invisible to it, so the
  gate is on the pair and neither half alone

#### Scenario: the abandoned-GPU path respects the route
- **WHEN** a `td` row has waited past `MSE_GPU_WAIT_S` with no worker claiming it
- **THEN** on the `jetson` route it stays on the Jetson queue and the owner is
  not told it moved
- **AND** on the `cluster` route it is moved to `cluster-gpu`, and the message
  says that queue by name rather than "the cluster queue"

#### Scenario: memory taken mid-run fails readably
- **WHEN** the device runs out of memory during a `td` run
- **THEN** the job fails with a message naming the memory shortage

#### Scenario: a kernel out-of-memory kill fails the job once
- **WHEN** the kernel's OOM killer ends a `td` run with SIGKILL (on the Orin
  the GPU shares system RAM, so this, not an exception, is a common way to run
  out of memory)
- **THEN** the job fails once with the out-of-memory message, and is never
  requeued as a counted release
- **AND** this holds because the run solves in a spawned child process, with
  the worker (holding the lease) reading exit status -9 as out of memory; the
  child ignores SIGTERM and SIGINT, so a service stop does not end a run; an
  error raised in the child reaches the worker's classifier with its type (or
  its type's name, when it cannot be pickled) and its cause chain; and the
  worker's unit sets `OOMPolicy=continue`, so systemd does not stop the
  service when the child is killed
- **AND** only SIGKILL reads as out of memory: a child that exits non-zero or
  dies of another signal (SIGABRT, say) fails with the plain "stopped
  unexpectedly" message naming its exit status, never the out-of-memory one

#### Scenario: a run stuck inside one step is still stopped
- **WHEN** a `td` child is still running 5 minutes past the 45-minute limit
  (its own stop is checked only between steps, so it is stuck inside one)
- **THEN** the worker kills it and fails the job with the 45-minute message
- **AND** the worker times the run from when the child reports `solving`, the
  moment the child's own 45 minutes start, never from spawn, so a long setup
  does not eat into the run's time
- **AND** before `solving` arrives, setup is capped at 50 minutes from spawn;
  a child that reaches it is killed and the job fails with a plain message
  saying the setup took too long
- **AND** the worker reads every message the child has already sent before it
  looks at either clock, and an outcome found there wins over a deadline: a
  child that finished is never failed as too slow
- **AND** a child that has sent its outcome but has not exited within 60
  seconds is killed, and every child is reaped (no zombie) before the worker
  goes on

#### Scenario: an overlong run is stopped
- **WHEN** a `td` run passes 45 minutes of run time
- **THEN** it is stopped and the job fails with a message naming the limit
- **AND** the run time is checked before the first step and every 64 steps
  after it, on the host without reading any device value, so the stop comes at
  most 64 steps late and the check adds no device sync; the message names the
  step reached, the total, and the advice (increase dx or shorten the duration)

#### Scenario: free memory is what a new run can take on the Orin
- **WHEN** the worker checks free memory before a `td` run
- **THEN** it compares the estimate with the kernel's MemAvailable (the Orin's
  GPU shares system RAM) plus the blocks this process's cupy memory pool
  already holds free, and runs on numpy when no device is present

#### Scenario: a time-domain verdict is never retried
- **WHEN** a `td` job is refused (layout, mesh, estimate or limits) or stopped
  (out of memory, 45 minutes)
- **THEN** it is failed with that message shown to the owner unchanged, never
  released for another attempt, whatever error it was raised from; a device
  error the solver does not translate is classified like any other job's
