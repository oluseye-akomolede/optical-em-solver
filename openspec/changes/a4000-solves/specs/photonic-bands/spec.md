# photonic-bands Specification (delta)

## MODIFIED Requirements

### Requirement: A pc job SHALL be routed to the Jetson worker, and the cluster SHALL refuse it

The pc solver SHALL run on the Jetson worker only. A pc job SHALL therefore be
created with `target = jetson`, so the worker that can solve it is the worker
that claims it. The cluster queue SHALL NOT hand a pc row to the launcher: the
launcher builds exactly one Job shape, the cavity solver, so a pc row reaching
it would be cavity-solved and the row's `kind` would be lost. The cluster side
SHALL refuse a pc row by NAMING its kind, at both the queue and the launcher, so
a routing mistake is a loud failure rather than a band diagram that never
appears.

EXCEPTION (2026-11-12): while the Jetson is offline the operator sets
`MSE_GPU_ROUTE=cluster`, and a pc row MAY then be created with
`target = cluster-gpu` and solved on the cluster's A4000 by a Job whose entry
point dispatches on `kind = pc`. The default route is still `jetson`; a row that
reaches the cluster launcher on a route whose entry point cannot dispatch `pc`
SHALL still be refused by naming its kind, and a pc row SHALL never be
cavity-solved. The result dict SHALL carry the same keys on both routes
(`lattice`, `polarisation`, `labels`, `k_points`, `bands`), because `solve_pc`
is the one translation layer and both routes call it.

#### Scenario: the pc upload creates the row for the Jetson, not the cluster
- **WHEN** a valid pc form is uploaded
- **THEN** the created row's `target` is `jetson`
- **AND** its `kind` is `pc`
- **AND** the cluster worker never sees it

#### Scenario: the cluster queue skips a pc row
- **WHEN** a pc row with `target = cluster` is queued (a row that should not
  exist, but which the queue must not solve if it does)
- **THEN** `next_queued(cluster)` does not return it
- **AND** a cavity row for the cluster is still returned, so the filter removes
  only pc rows

#### Scenario: a pc row past the GPU wait stays on the GPU queue
- **WHEN** a pc row has waited longer than `MSE_GPU_WAIT_S` for a worker, and
  the GPU-abandon path runs over it
- **THEN** its `target` is still `jetson`, and `claim_jetson` still returns it
- **AND** it is not moved to the cluster, so it is never stranded with no queue
  that can see it
- **AND** the row does not tell the owner it was "moved to the cluster queue",
  because nothing moved
- **AND** `reroute_to_cluster` refuses a non-cavity row in its own SQL guard
  (`kind = 'cavity'`), so no caller can move one, not merely the one caller
  that skips pc rows today

#### Scenario: the cluster launcher refuses a pc row by name
- **WHEN** the cluster launcher is handed a job whose `kind` is `pc`
- **THEN** it raises, and the refusal names the kind and the Jetson
- **AND** it does not create a cavity Job for it

#### Scenario: the crossing is proven on the real store, not a double
- **WHEN** a pc row is created through the real upload route's store call on
  real Postgres
- **THEN** `claim_jetson` returns it
- **AND** `next_queued(cluster)` does not
- **AND** the check is red against the unfixed branch, failing as
  `claim_jetson -> None` because the row was created `target = cluster`

#### Scenario: a pc row runs on the A4000 while the Jetson is offline
- **WHEN** `MSE_GPU_ROUTE=cluster` and a valid pc form is uploaded
- **THEN** the created row's `target` is `cluster-gpu` and its `kind` is `pc`
- **AND** the cluster GPU launcher claims it and builds a Job whose entry point
  dispatches on `kind = pc`
- **AND** the Job's result carries the same keys the Jetson route produces, so
  the same page draws it
