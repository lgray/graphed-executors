# m68a class adjudication (after r13)

**Verdict: apply.** One class, one cut, and it stays inside m68a.

## Class
Each time m68a acquires something on `run()`'s path (a child, a hosted name, a pilot, a backend), the plan describes what an exception at that point leaves behind in a per-case prose clause. The code already has three authorities for this, and the plan cites none of them (`grep -c 'ExitStack\|pop_all\|contextlib' plan-services.md` → 0; the control grep `host_service` → 20):

1. **Ownership of what was acquired.** `contextlib.ExitStack` with `pop_all()` at the acquirer: `backend.py` `HTCondorBackend.__init__`, the only ExitStack in the package, at lines 14/71/75.
2. **The outcome in flight.** From `driver.main`, around `runner.close()`: "the run's outcome stands; the close failure is only logged".
3. **The hop from job to submitter.** `pilot._run` falls back to text when dump fails; `TaskServer.result` guards the load. N5 and N6 already applied this pair.

The members are N7, N8 and N9 (the acquisition clauses) and N9's harm, where a cleanup exception replaces the refusal and turns exit 1 into exit 3. N4, N5 and N6 are the same exceptional exit at the classify and hop steps. They are closed, and their text stays. The non-members are N1, N2 and N3, and all r1–r6 items that are not r1 M1 or r6 M7. All three lenses agree on this split.

## Premises (measured, exec-main b966a28)
- A plain ExitStack still runs every later callback, but a raising callback replaces the in-flight exception. Wrapping each callback so it logs keeps the refusal. `probes/class/probe_exitstack_semantics.txt`: `logged=False → RuntimeError, calls [a,b]`; `logged=True → Refusal, calls [a,b]`. So the stack alone (rung 3) does not hold. Authority 2 is needed as well.
- Cleanup that is not isolated gives exit 3; isolated cleanup gives exit 1. `SubmitRunner.close` stops at `set.close`. A zombie answers `kill(pid,0)` until it is waited on, and a child that ignores SIGTERM survives terminate. Source: `probes/class/probe_cleanup_replaces_refusal.txt`.
- The m66 acquirers have the same gap. `LocalPilots` orphans pilot 1 when pilot 2 fails. `HTCondorBackend.__init__` never calls `launcher.stop`. When `CondorPilots` spool fails, it leaves cluster 4242 unrecorded and it cannot be removed. Source: `probes/class/probe_acquire_record.txt`.
- One runner runs many plans: `engine.py` `self._plans = PlanQueue(self.run, …)`.

## Cut (plan edits)
1. **§3.1 ServiceSet bullet.** Replace the sentence that starts "`start()` records each managed service…" with the following:
   "`start()` acquires under a `contextlib.ExitStack`, following the idiom of `HTCondorBackend.__init__`. Each release is registered once its acquiring call returns: `Popen` registers terminate, then `wait(grace)`, then kill, then wait; a returned `host_service` registers `release_service(name)`; `on_close` registers a stack callback. Each registered release logs its own failure and never raises (the `driver.main` rule), so the exception that ends the run is the first one raised. `close()` closes the stack that `pop_all()` handed over on success."
   Delete the ladder row "teardown … `Popen.terminate`" and the phrase "terminates subprocesses" from `close()`.
2. **§3.1 engine line.** `run(plan)` resolves under its own stack the specs of `plan.services` that the runner's set does not yet hold, keyed by name. A name that is held with an unequal spec is refused. The stack covers start, bind and probe. The runner's set takes the stack over only after the probe passes. This replaces the gate "and not started". `close()` closes the set, then the backend, and the set's close cannot raise.
3. **D10.** Add: "`host_service` returns with the service up, or it releases what it started and then raises. Inside it, each acquisition registers its release when the acquisition returns (condor: the cluster is registered when `schedd.submit` returns, before spool)."
4. **htcondor_backend bullet.** The m66 acquirers follow the same rule, and m68a already touches these files:
   - `HTCondorBackend.__init__` registers `launcher.stop`.
   - `LocalPilots.start` registers each child as it is spawned.
   - `CondorPilots.start` records the cluster before spool.
   - `driver._runner` holds the backend under a stack until the runner that owns it returns.
5. **Frozen table, `test_services_protocol.py`.** Replace the two per-case legs (the two-spec plan and `sleep 60`) with one parametrized fault-injection leg. Each case injects one fault:
   - a managed child whose check never passes;
   - a ready child, then a later spec refuses;
   - `host_service` returned, then a later spec refuses;
   - `host_service` raises;
   - the probe refuses;
   - a hosted spec whose `release_service` raises, then a later spec refuses.

   After `run` raises, and with no `close()` call, assert all of the following:
   - the raised type is the injected refusal;
   - `driver._exit_code` of it is 1;
   - every managed pid is reaped (`kill(pid,0)` raises);
   - every port is free;
   - `release_service` was called exactly for the names that were hosted.

   Add two more legs. In the first, `close()` with a raising `on_close` still reaps the child and calls `backend.close`. In the second (success control), the child is alive after `run` returns and gone after `runner.close()`, and a second plan with a new spec on the same runner resolves that spec.

## Predicted items
- Closed by the cut: cleanup replaces the refusal (taxonomy 1, structure 1); a raising teardown step skips later steps (taxonomy 2, structure 2); terminate without reap or escalation (taxonomy 3); a refusal from probe or bind after `start()` has returned (structure 3); the `started` key across plans (runtime 1); the unrecorded cluster when spool fails (runtime 2, structure 4); the partial starts in the m66 launchers (runtime 3); `_runner` outside the `finally` (runtime 4).
- Not in the class, carried as an implementer constraint: the readiness loop calls `proc.poll()`, and a child that exits early fails at once with a reason that names its returncode (runtime 5, one line).
- Left open: a service that dies mid-run surfaces as the task's own exception type and exits 3 (taxonomy 4). D6 classifies by type, which is the owner's ruling, and the type cannot tell this case apart from a plan's own error. Retrying it would need task errors to be wrapped. That is a new decision for the owner, not a defect in this class.

## Three lines
- Task: when any step that acquires a service raises, m68a's `run()` must leave nothing running and must surface the original refusal.
- By hand: `with ExitStack() as st:` around the steps, with each release registered right after its acquisition and wrapped to log, then `pop_all()` on success. This is what `backend.py` and `driver.main` already do.
- Rung (2): the repository already does it. Rung 1 fails because the frozen legs require the property. Rung 3 alone (a plain ExitStack) replaces the in-flight exception, as the probe shows.

## Stop rule
This is the one change of level for this mechanism. If a round finds another failure-path member against this contract, it goes to the owner with these three lines. It does not start another round of clauses.
