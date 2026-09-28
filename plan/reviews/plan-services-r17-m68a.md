# plan-services r17 — m68a whole-unit pass (owner lifetime decision applied)

**Verdict: NOT CLEAN. 2 design findings (F1, F2).** Both are new, and both come from the decision itself. Under per-run lifetime, every run starts and releases its services again. The held set used to start each name only once per runner, and it never re-probed a name it already held. Neither finding is a failure-path member of the adjudication's ExitStack contract, so the stop rule does not route them to the owner.

## (a) Decision applied; no runner-held service state remains
Counts in the plan, with the r16 snapshot as control:

| Pattern | Plan | r16 snapshot |
|---|---|---|
| `start_services` | 0 | 9 |
| `unequal` | 0 | 1 |
| `second plan` | 0 | 1 |
| runner `services()` → statuses | 0 | 1 |
| lock | 0 | 0 |

- The close-ordering hit left in the plan is at L286. It is the user's own `with` order in the warm recipe, not runner state.
- `SubmitRunner` keeps only the public `services` attribute. It is read once at the start of each run, which is the `monitor` precedent (engine.py L271).
- Driverless runs one plan per job, and its set belongs to that run.
- Premise probe `probes/lifetime/probe_lifetime.txt`:
  - A per-run child is gone after the run returns and after it raises. The control, a child not on a stack, stays alive.
  - A warm set serves two runs with 1 pid. Its child is gone when the set exits while the runner is still open.

## (b) Failure paths and frozen discrimination
- **Per-run path.** `run` enters `ServiceSet` on its own stack. Its fault list covers both entry points: `run` and `ServiceSet.start`, which is the warm `__enter__`. A raising `start` self-cleans, because `__exit__` is not called when `__enter__` raises.
- **Pre-decision text fails these frozen legs:**
  - "two runs of one plan start two pids" (the held set gives one);
  - "gone when `run` returns" (held until `close()`);
  - warm "gone when the set's `with` exits, the runner still open" (the held set had no user-held form).
- **Histserv deletion** stays per run in warm mode. m69b binds `on_close(delete)` on the `Endpoints` the runner binds, which belong to the per-run set, so deletion follows the run's `resolve_services`.

## (c) Consumers
- m69b uses per-run lifetime throughout: D8 "deletion when the run's services close", the `test_histserv_managed` and `test_hgg_live_pool` legs, and user-leg histserv.
- m68b and m70 now say "the run's end" everywhere.
- D10's key is where the consumers break per-run lifetime. That is F1.

## Design findings

**F1 · Backend hosting state is keyed by the service name. Per-run lifetime re-hosts the same name on the same backend on every run.**
- **Where:**
  - D10 L109: `release_service(name)`.
  - m68a L274: the release registered on the stack is `release_service(name)`.
  - m68b L415–419: `TaskServer` records `services[name]` and wakes `wait_announce(name, …)`, and `host_service` takes identity from `wait_announce(name, spec.timeout_s)`.
  - m70 L464–468: dask `Variable(f"svc:{nonce}:{name}")` and `Event(f"stop:{nonce}:{name}")`; parsl `_open_driver_endpoint(nonce)`. The plan does not say where `nonce` comes from. `release_service` receives only the name.
- **Defect:** the plan never clears or scopes the name's rendezvous record. `grep -n "wait_announce\|services\[name\]\|release_service" plan-services.md` returns only the lines above.
- **Harm:**
  - Sequential runs (the default path now). An announce can arrive before `wait_announce` starts waiting, so `wait_announce` must read the record. In run 2 of the same name, that record is run 1's dead announce. `host_service` returns a dead endpoint, and the probe refuses with `ServiceUnreachable`.
  - The same applies to a dask `Variable` keyed without a per-call nonce. This part is unmeasured, because `distributed` is not installed in `.venv-prep`.
  - Overlapping runs, which `SubmitRunner` allows (`probes/class/probe_concurrent_runs_r16.txt`: overlap True). Two runs hosting the same name share one record. One run's `release_service(name)` can stop the other run's service.
  - L283's claim "overlapping runs … each hold their own" is therefore false for cluster-hosted services.
- **Why this is new:** the held set hosted a name at most once per runner, and N16's lock ordered the runs.
- **Closed when:**
  - `host_service` scopes each call's rendezvous with a per-call key: the ServiceJob argument and announce key for condor, the `nonce` for dask and parsl.
  - `release_service` addresses that call, and the record is cleared when it is released.
  - The planner picks the handle, for example `release_service(endpoint)` or a returned token.
- **Test that shows it closed:**
  - m68b `test_cluster_services_live.py` (a), extended: two sequential runs of the cluster-hosted `http_server` plan on one runner. Each run's status carries its own ServiceJob cluster and pid. Run 2's task GET is answered by run 2's child. A queued `submit` overlapping a direct `run` gets two services, and each release removes only its own cluster.
  - The same two-run leg in m70's dask and parsl files.
  - In m68a's two-host fake, `release_service` is called with the handle `host_service` returned. Asserting on names alone is not enough.

**F2 · In the driver job, the service phase now runs a second time inside `runner.run`. A refusal there exits 3.**
- **Where:**
  - L310–313: `with ServiceSet(...) as eps: runner.services = eps; runner.run(plan)`, with "leg 1 for every name".
  - L278–283: every `run` enters its own `ServiceSet`. That per-run set re-checks and re-probes the leg-1 names inside the `runner.run` try.
  - m67's `_exit_code`, which the plan keeps unchanged at L314, maps every non-`KilledWorker` exception to 3.
- **Probe:** `probes/lifetime/probe_inner_phase_exit_r17.txt`: `inside runner.run, ServiceUnreachable -> 3`; the control, the phase before `runner.run`, gives `1`.
- **Harm:** with `pilots="condor"`, the pilots can be lost between the outer probe and the inner one. The inner probe then gets no answer within `timeout_s` and raises `ServiceUnreachable`. The job exits 3 and is not retried. D6 calls endpoints and placement environment (exit 1), and m68a's own Fails-on line names "a service-phase exception exiting 3".
- **Why this is new:** in r16, `run` started only the names it did not hold, so the driver's held names were never probed a second time.
- **Closed when:** a service-phase refusal inside `runner.run` exits 1. One way is for `_exit_code` to classify `ServiceUnavailable` and `ServiceUnreachable` as 1, which is a single line. The outer `with` stays for `OSError` from the bind and for arbitrary `host_service` errors.
- **Test:** in `test_driverless_endpoints.py`, a driver job whose in-run leg-1 re-check refuses must exit 1 with that exception in `result.pkl`. Against the current text it exits 3.

## Exit items (constraints for the implementer; no round)
- **Warm recipe with `submit`.** The set's `with` closes before `runner.close()` drains `PlanQueue`. The docs recipe must await every `runner.submit` future inside the set's `with`.
- **Warm set on `HTCondorRunner`.** The set's probe waits up to `timeout_s` (default 600 s) for pilots. The recipe should call `runner.wait_for_pilots()` before entering the set, as `driver.main` does, so that a pool with no pilots is refused promptly.
- **Status witnesses.** The runner's `services()` is gone. The m69b `test_histserv_managed` status legs and m70's "the status is `leg="managed", host="cluster"`" read the `graphed_executors.services` log record's `status`.
- **m70 unacknowledged stop (carried since r15).** m68a's rule is that a release logs and never raises. So the m70 leg "a stop that is never acknowledged … refuses at the timeout naming the actor" must witness a log record naming the actor, and the run's value stands.
