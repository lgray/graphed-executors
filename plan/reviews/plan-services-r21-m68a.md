# plan-services r21: m68a delta pass (I1, I2 closure)

**Verdict: NOT CLEAN. I1 is closed, and m68a has no design finding. I2 is closed on parsl but not on dask: J2 (unit m70, measured).**

Delta read: `git diff --no-index --word-diff reviews/plan-services-r20-snapshot.md plan-services.md` (3 hunks: the §3.1 driver-hosted bullet, the `test_services_protocol.py` row, and the m70 dask and parsl rows).

## I1: closed
- The §3.1 bullet holds one module-level `threading.Lock` from the scan until the check passes or the start fails. The frozen row adds r20's test (two `ServiceSet`s behind a `Barrier`, 10 trials, distinct ports, both children alive).
- **Measured** (`probes/lifetime/probe_port_lock_r21.{py,txt}`, the row's shape):
  - lock leg: `(distinct, both alive) -> 10/10`;
  - no-lock leg: `0/10`, with 5 early exits and 5 cases of "ready, dead after check".
  - So the test discriminates.
- r20's second clause ("`proc.poll() is None` after the check passes") was not applied. With the lock it matters only across processes, and it is a timing guard there, not a reservation. It goes forward as an exit item, not a round.

## Design finding

**J2 (m70): on dask, `LocalCluster 3×1` does not give the overlap leg a slot. `host_service` pins every actor to "the first [worker] whose `resources` cover", so both overlapping runs' actors land on one single-thread worker.**
- **Where:** the §3.4 dask `host_service` sentence and the `test_dask_hosted_service.py` row. The row's new "(a slot beyond the hosted actors, so overlapping runs both complete)" is false under that placement rule.
- **Measured** (`probes/lifetime/probe_dask_first_cover_r21.{py,txt}`, distributed 2026.8.0, `LocalCluster(n_workers=3, threads_per_worker=1)`, the plan's `submit(workers=[addr], allow_other_workers=False, pure=False)` plus a `Variable`/`Event` actor):
  - first-cover leg: A and B on the same address; "B not ready within 5s timeout". B's `host_service` waits for A's release, so the leg passes only while run A is shorter than B's `timeout_s` (r20's harm).
  - control leg (B on the first covering worker not already hosting): "B ready after 0.01s", and a plan task still ran.
  - The same serialization hits any production dask cluster with one thread per worker, which is the owner-ruled overlap case.
- **Closed when:** `host_service` picks the first covering worker that is not hosting one of this backend's live actors. The issuer decides what happens when every covering worker hosts: refuse naming the worker table, or fall back to the first covering worker. The 3×1 fixture then holds as written.
- **Test that shows it closed:** in the overlap leg of `test_dask_hosted_service.py`, the two actors' worker addresses differ and both runs' `host_service` return within the spec's `timeout_s`. Under the first-cover rule, the probe shows B not ready within the timeout.
- **Parsl half of I2:** closed. `start_htex(workers=3)` gives no placement, and each actor takes one worker process, so one is left. The runtime is unmeasured because parsl is not in `.venv-prep`.

## Exit items (constraints for the implementer; no round)
- **Readiness order (r20 I1, second clause).** Readiness is a passing check followed by `proc.poll() is None`, and failing this is the early-exit refusal naming the returncode.
  - This is the only m68a guard against a second driver process on one host. Line 637 runs leg 3 driver-hosted at the shared LPC login node, and every driver there scans the same profile `service_ports` from the same first port.
  - Measured in the no-lock leg of `probe_port_lock_r21.txt`: the post-check poll saw B's child dead in 5/5 wrong-service passes. It does not catch a listener that is already up before B's child starts, so no frozen test pins it.
- **Parenthetical.** "picks in other processes are m68b's and m70's" also covers another driver process on one host, which runs m68a's own leg and is reserved only by the guard above. Say so.
- **Lock wait.** The lock wait is not part of `timeout_s`: B's readiness clock starts after it acquires the lock, so a start queued behind a slow start does not time out spuriously. The lock is released in a `finally` on every start failure.
