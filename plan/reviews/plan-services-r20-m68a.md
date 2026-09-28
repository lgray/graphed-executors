# plan-services r20: m68a whole-unit pass

**Verdict: NOT CLEAN. 1 m68a design finding (I1).** One more design finding (I2) belongs to unit m70. r19's H1 is closed.

I read all of m68a's text: D1, D2, D4, D6, D7 and D10, §3.1, and the §6–§9 lines that bind m68a.

## H1: closed
The §3.4 parsl `release_service(key)` now does the following:
- It sends `("stop",)`.
- It awaits that call's actor future up to the spec's `timeout_s`. The actor returns only after it has reaped its child, and a timeout raises naming the actor.
- It closes the endpoint in a `finally`.

The m70 parsl row adds the harness actor whose stop handler sleeps about 1 s. This matches r19's "Closed when".

The change also agrees with m68a. The registered release logs a raise and never raises itself, and the carried exit item already reads "refuses at the timeout" as "`release_service` raises and the set logs it".

## Design findings

**I1 (m68a): overlapping runs that start driver-hosted services pick the same port. One run then refuses spuriously, or it reads the other run's service.**
- **Where:** in the §3.1 `ServiceSet` bullet, leg 3 driver-hosted says "bind a free port from `backend.service_ports` … `Popen(argv)`". The recipe binds `{port}` itself, so the engine's scan finds a port and releases it before the child binds.
  - The engine line says "overlapping runs … each hold their own".
  - Per-run lifetime starts a new set for every run. `SubmitRunner` allows a `submit` to overlap a direct `run` (`probes/class/probe_concurrent_runs_r16.txt`).
  - The first-free scan is deterministic, so two starts that overlap both get the first free port.
- **Probe:** `probes/lifetime/probe_port_pick_race_r20.{py,txt}`. It runs the scan from the plan, then `Popen` of `http_server`'s argv, then the plan's own poll loop (check first, `proc.poll()` second).
  - In 10 of 10 trials both starts picked the same port.
  - In 5 trials, B's check passed while B's own child then died with rc=1. B was served by A's child, which A's run terminates when A ends.
  - In 4 trials, B refused with the early exit: a `ServiceUnavailable` on a healthy pool.
  - Control: a start that scans after the first child is ready gets a distinct port, and both children stay alive.
- **Harm:** this is the harm the arc's Fails-on lists name as "a run reading … another run's service" (m68b, m70). m68a creates it through the owner's per-run decision. The old held set, which started each name once under a lock, could not reach it.
- **Shape:** this is the second instance, after r17's F1. Something a run acquires is named from a namespace that overlapping runs share, and nothing reserves it per run. For F1 that was the rendezvous name; here it is the port. Neither D10 nor m68a states the reservation rule for the port.
- **Closed when:** a process-wide reservation covers the whole span from the port scan to readiness, so a concurrent start's scan skips the held port. For example, a module-level `threading.Lock` held from the scan until the check passes or the start fails. Readiness also requires `proc.poll() is None` after the check passes.
  - This reaches every same-process member, including m70's dask actors if they use m68a's start helper, since they share one worker process.
  - It does not reach picks made in different processes on one node: m68b's `ServiceJob` `<port>`, whose source §3.3 does not state, and parsl actors on sibling HTEX workers. Those units state their own port choice. One option is for the job side to pick and announce `host:port`, which the announce already carries.
- **Test that shows it closed:** in `test_services_protocol.py`, two `ServiceSet`s over the driver-hosted `http_server` spec are entered concurrently from two threads behind a `threading.Barrier`, 10 trials. In every trial:
  - the two endpoints carry distinct ports;
  - both children are alive while both sets are open.

  Without the reservation the probe shows the same port in 10 of 10 trials, so the test fails.

**I2 (m70): the parsl overlap leg runs two hosted actors on `start_htex(workers=2)`. Each actor holds a worker slot for its run, so no slot is left for either run's probe or tasks.**
- **Where:** the §3.4 row `test_parsl_hosted_service.py`: "the same over `start_htex(workers=2)` … the same two-run and overlap legs as dask". The m70 engine sentence says "a hosted actor holds a worker slot for the run". `start_htex(workers=2)` gives two worker processes (exec-main `parsl_backend/launch.py` `start_htex`).
- **Harm:** consider a `submit` that overlaps a `run`. Once both actors are placed, any task submitted after that has no worker: run A's combines, which are queued once their inputs finish, and run B's probe. The run whose probe is pending waits the spec's `timeout_s` and raises `ServiceUnreachable`. After that the other run resumes. The leg's "each get their own actor pid" then either fails or depends on timing.
  - On dask, both actors are pinned to "the first [worker] whose resources cover", a single-thread worker. So they run one after the other, not side by side, and the leg passes only while run A is shorter than B's `host_service` timeout.
- **Premise:** from the plan's own text. The runtime is unmeasured, because `.venv-prep` has neither parsl nor distributed. Confirming it is the repair's first step.
- **Closed when:** the overlap legs run on a pool with at least one task slot beyond the hosted actors. For example, `start_htex(workers=3)`, and a `LocalCluster` whose first covering worker has two threads, or three workers. Then both overlapping runs complete, each with its own pid.

## Exit items (constraints for the implementer; no round)
- **Unanswered probe task.** A probe `submit` whose answer timed out stays queued. The next pilot to poll leases it ahead of the next run's first task (`probes/lifetime/probe_stale_probe_task_r20.txt`: abandoned leg leases `('probe',)`; `cancel`led leg leases `('next-run-task',)`).
  - m68a's own rule, "every acquisition in `start()` puts its release on the stack", covers it. Register `backend.cancel([fut])` for each probe submit.
  - In the "probe no worker answers within `timeout_s`" fault case, assert that the backend received the cancel for that future.
- **m70 release timeouts (for the m70 unit).** Parsl's `release_service` now owns its await and timeout. Dask's "awaits its actor's future" names no timeout. So the engine's "`release_service` is awaited with the spec's `timeout_s`" is redundant for parsl. For dask it leaves a blocked release thread whenever the engine's wait times out. Give dask's await the spec's `timeout_s` inside `release_service`, and have the engine call it plainly.
- **Carried from r19, still open as constraints:**
  - `threading.active_count()` is asserted within a bounded wait.
  - A stop-ignoring parsl actor is reclaimed only by `stop_htex`; add no backstop.
  - Clearing the dask Event is optional.
  - Leave a late condor announce under a dropped key; add no sweep.
  - The warm recipe with `submit` must await its futures inside the set's `with`.
  - The warm set on `HTCondorRunner` calls `wait_for_pilots()` first.
  - Status witnesses read the `graphed_executors.services` log record.
  - The m70 unacknowledged stop is witnessed by a log record naming the actor, and the run's value stands.

## Checked, no finding
- **D6 classification under every m68a failure path.**
  - Exceptions from the outer set's `__enter__` escape the `runner.run` try and exit 1.
  - The inner set sees every name as leg 1, because the outer `Endpoints` covers all of `plan.services`. So it can raise only `ServiceUnavailable`, `ServiceUnreachable`, or raw `WorkerLost`, and each maps to 1.
  - Releases log and never raise, so no close replaces the outcome.
  - Bind, task and `resolve_services` errors exit 3, which is the owner item in §9.
- **No runner-held state between runs.**
  - `bind_services` returns a new plan, and the original is unchanged (§3.2 `test_bind_services.py`).
  - `SubmitRunner.services` is read once per run.
  - `on_close` callbacks are registered on the per-run set's kept stack, so they run LIFO before the child's teardown.
- **`require_bound`** exists in graphed #61 and `SequentialRunner` calls it (r16). `grep -rnE 'def (run\(self, plan|[a-z_]*run_plan\()' src` in exec-main b966a28 returns the five runners the plan names.
