# m68a implementer constraints from plan reviews r8–r10

Exit-round items (constraints, not review findings). E12/E13 are already folded into the plan.

- E8: For the in-job pilots=local backend, service_ports is None or absent, and the engine reads getattr(backend,'service_ports',None) or spec.ports. The engine must try-bind on advertise_host, because the task server already holds 127.0.0.1:10000 in the slot.
- E9: The in-job backend may either expose host_identity or leave it absent. Both give the module function; pick one.
- For the m68b reviewer: the announce_only in-job leg (L384) resolves from the announce, and the per-leg ServiceStatus.identity rule does not name its identity. It should be the announced identity.
- r7's E1-E7 still stand as constraints.
- E10: D6's '(owner ruling 2026-09-25)' covers only exit 3 for a StageError and exit 1 for worker loss. Exit 3 for an unwrapped task exception and exit 1 for a service refusal are this plan's decisions: label them as such in the driver.py docstring, and update that docstring, which still says '1 anything else'.
- E11: drop the history '(m67 maps them to 3)' at §3.1 L276 when carrying it into code or docs.
- Considered, not raised: a deterministic ServiceUnavailable (no leg configured, or a GPU recipe without host_service) exits 1 and uses the 2 retries. The plan chose this explicitly, the cost is bounded, and the reason still reaches result.pkl.
- r8 E8/E9 and r7 E1-E7 still stand.
- E12: in the text fallback, 'did not pickle' is also used for a blob that pickled but did not load; say 'did not round-trip through pickle' or similar
- E13: once N6 lands, the L306 Fails-on item should read 'a result.pkl the submitter cannot load'
- Considered, not raised: _result_blob(True, result) now loads the whole ExecResult a second time in the driver; the cost is one extra deserialization, and a success result that does not load still falls back to (False, RuntimeError) with exit 0, as m67 already does for a dump failure
- r9 E10/E11, r8 E8/E9 and r7 E1-E7 still stand

## r11–r13

- E14: in the §3.1 engine line, graphed.bind_services does not exist at the top level (graphed/__init__.py at origin/main cf4520d has no services or bind match; control: 16 import lines). Use graphed.services.bind_services.
- E15: the clause 'driver.log, which holds the traceback' is true only for a failed run, because driver.main prints the traceback only when error is not None. An ok=True blob that fails to load has no traceback there, so the RuntimeError message should point at driver.log without promising a traceback.
- E16: in the test_driverless_endpoints.py row, 'with no bindings' means under m67's record_bindings fake, because RunHandle.result() calls _located() -> launch._htcondor().
- Considered, not raised: graphed #61's require_bound is called only from SequentialRunner, and _PluginEvaluator.bind_services raises UnboundService for a name missing from the map. The engine binds every name in plan.services, so m68a's bind sees no refusal.
- r10's E12 and E13 are folded into the plan. r9's E10 and E11, r8's E8 and E9, and r7's E1-E7 still stand.
- E14 still stands: L263 says `graphed.bind_services`; use `graphed.services.bind_services`.
- E15 still stands: L285 says 'driver.log, which holds the traceback'. Point at driver.log without promising a traceback, because an ok=True blob that fails to load has none.
- E16 and E1–E13 stand as r11 left them.
- E14 still stands: L265 says graphed.bind_services; use graphed.services.bind_services.
- E15 still stands: L288 says driver.log 'holds the traceback'; point at driver.log without promising a traceback (an ok=True blob that fails to load has none).
- E16 and E1-E13 stand as r11 left them.

## r20 (whole-unit)
- Unanswered probe task: a timed-out probe submit stays queued and is leased ahead of the next run's first task (probes/lifetime/probe_stale_probe_task_r20.txt: abandoned leg leases ('probe',), cancelled leg leases ('next-run-task',)). Under m68a's own 'every acquisition registers its release' rule, register backend.cancel([fut]) for each probe submit, and have the 'probe no worker answers' fault case assert the cancel.
- m70 (for that unit): the parsl release_service owns its own await and timeout, while dask's 'awaits its actor's future' names no timeout. The engine's timed await of release_service is redundant for parsl and leaks a blocked thread for dask. Put the spec's timeout_s inside dask's release_service and have the engine call it plainly.
- Assert threading.active_count() within a bounded wait.
- A stop-ignoring parsl actor is reclaimed only by stop_htex; add no backstop in release_service.
- Clearing the dask Event on release is optional.
- Leave a late condor announce under a dropped key; add no sweep.
- The warm recipe with submit must await its futures inside the set's with.
- The warm set on HTCondorRunner calls wait_for_pilots() first.
- Status witnesses read the graphed_executors.services log record.
- The m70 unacknowledged stop is witnessed by a log record naming the actor, and the run's value stands; 'refuses at the timeout' means release_service raises and the set logs it.

## r22
- The overlap leg asserts that A's and B's `run_nonce`s differ.
- A user-held `ServiceSet` mints its scope as `uuid.uuid4().hex[:8]`.

## r23
- Wrapper registration follows `_RunLeaves` (`local/executors.py`): add under the lock, `add_done_callback` outside it; the stack's cancel snapshot is a `list` taken under the lock; reuse `_RunLeaves` if its `pending` set fits. (probe_live_set_race_r23: callback-before-add leaks one pin; callback-inside-lock deadlocks on ThreadBackend.)

## r24 (whole-unit, CLEAN)
- `run`'s stack registers the `ServiceSet` before the plan-task cancel, so the cancel runs first and no queued task reaches a stopped service.
- A plan with no services: the driver's `ServiceSet` submits no probe and starts nothing.
- `ThreadBackend.advertise_host` is a new attribute in `submit/threadpool.py`; add that file to commit 1's list.
