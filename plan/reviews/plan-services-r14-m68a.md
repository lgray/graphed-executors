# Review r14 — `plan-services.md`, unit m68a (whole-unit pass after the class cut)

**Verdict: NOT CLEAN — 4 design findings (N10–N13).**
- (a) The cut closes N9, and every member the adjudication lists, at the cause. The new frozen legs fail on the r13 pre-cut text.
- (b) The ExitStack contract recurs twice more on failure paths. N12 is exception types that D6 misclassifies. N13 is `HTCondorBackend.close`. Under the adjudication's stop rule, both go to the owner with the three lines below. They do not go to a planner round.
- (c) Two findings sit outside that class: N10 (a success-path hop from job to submitter) and N11 (a PR-order dependency).

Code: exec-main b966a28 and graphed origin/main 6e9e55e. The probes are in `probes/class/*_r14.{py,txt}`. They were read-only, and no process outlived its run.

## (a) The cut against N9 and the listed members
- **N9 is closed.** L262-263 registers `release_service(name)` only once `host_service` returns. D10 (L110-112) makes `host_service` release what it started and then raise. The frozen fault "`host_service` raises" asserts that `release_service` ran exactly for the hosted names, which here means zero. The r12/r13 text recorded the name before the call and makes one call, so the leg discriminates.
- **N7 and N8 are closed.** `Popen` registers when it returns, before the check. The faults "a check never passes" and "a ready child, then a later spec refuses" assert the pid is reaped without `close()`.
- **Probe and bind refusals after `start()` are closed.** The run's stack is handed over only after the probe passes (L267-269). The fault "the probe refuses" fails on r13's "`start()` … runs `close()`" text, because that text left the child alive until `close()`.
- **Cleanup replacing the refusal is closed.** The fault "`release_service` raises, then a later spec refuses" asserts the injected type and exit 1. A plain ExitStack gives `RuntimeError`, which is exit 3 (`probe_exitstack_semantics.txt`, `probe_cleanup_replaces_refusal.txt` P2).
- **Terminate without reap is closed.** `os.kill(pid, 0)` answers for a zombie (`probe_cleanup_replaces_refusal.txt` P4), and the ladder is terminate, wait, kill, wait.
- **The `started` key across plans is closed.** The set is keyed by spec name, an unequal spec is refused, and a control leg covers a second plan's new spec.
- **The m66 acquirers are closed.** This covers the orphaned pilot, `launcher.stop` never called, cluster 4242 unrecorded, and `_runner` outside the `try`. The sites-row fault leg fails on b966a28 (`probe_acquire_record.txt`).
- D1/D2/D4/D6/D7 agree with §3.1.
- In m68b and m70, every `host_service` mention returns `(endpoint, identity)` (L103, L380, L429, L437).

## Design findings

**N10 · A driverless run's result cannot outlive the job's own services, and nothing in m68a resolves it before release.**
- The `test_driverless_endpoints.py` row (L307) requires that "`result.pkl` holds the snapshot" of an in-job histserv. The fat-slot variant in §5.2 (L589) depends on it.
- D8/§5.1 (L538, L549) make the reduce's value a `FillReceipt(snapshot=None)`. The receipt is resolved only at `unpack`, by dialling the server.
- `driver.main` pickles the result after `runner.close()` (`driver.py:106-122`). By then the set has released the server, and its `on_close` has run `delete`.
- `probe_result_after_close_r14.txt`: `events [('runner.close',), ('pickled', 'server_released')]`, `snapshot None`.
- No generic hook exists that could resolve the result in the job. graphed's `Plan` fields are process, combine, empty, tasks, next_tasks, stop, open_once and services (`core/execution.py`). Executors may not name histserv (the `test_services_packaging.py` grep).
- The submitter's `unpack` therefore dials `127.0.0.1:<port>` inside a job that has ended. The same lifetime applies to an attached `unpack` called after `close()`.
- **Decide one of:**
  - (a) A duck-typed resolve hook on the plan's process, called on the root value before the service stack is released. The caller is `SubmitRunner.run` before it returns, or `driver.main` before `runner.close()`. graphed-histogram implements it in m69b.
  - (b) An in-job driver-hosted service cannot back a returned result. Drop the snapshot clause from L307 and the fat-slot variant from L589.
- **Closed when:** a frozen leg loads `result.pkl` after the job's server is gone. Under (a), it unpacks equal to the local twin with zero connects. Under (b), it refuses at submit, naming the rule. The current text fails either leg, because it gives `snapshot=None` and a dial to a dead port.
- This is the hop authority, applied to the success payload. N5 and N6 applied it only to loadability. It is not a failure-path member of the ExitStack contract.

**N11 · m68a's frozen suite needs graphed-histogram code that has not been built.**
- The L307 row declares `histserv_spec("hists")`, has pilot tasks fill it, and expects the snapshot. That needs `graphed_histogram.remote` (`histserv_spec`, `_RemoteProcess`, receipts, §5.1).
- graphed-histogram origin/main 4c4b79f has no `remote` or `histserv` path (`ls-tree | grep -c 'remote\|histserv'` → 0; control `boost.py` → 1). No PR is open for it.
- §7 (L624-625) orders the histogram PR only before *executors m69b*. m68a's freeze, which comes first in its arc, cannot collect.
- **Closed by** either of:
  - The L307 driverless leg uses `recipes.http_server` with a process whose task GETs it. This is D1's generic recipe, as `test_services_protocol.py` already does. The in-job histserv leg moves to m69b's table.
  - §7 puts the histogram PR before the m68a freeze.
- **Test:** `tests/frozen/m68a` collects and passes with released graphed-histogram 0.0.4 installed.

**N12 · The service phase can end in exception types that D6 sends to exit 3. [ExitStack-contract member → owner]**
- The cut keeps the first exception, but D6 classifies that exception by type. The fault list injects only the two refusal types.
- `probe_service_phase_types_r14.txt`:
  - A leg-3 bind with the range held gives `OSError`, exit 3.
  - A recipe `Popen` whose argv[0] is absent gives `FileNotFoundError`, exit 3.
  - A probe submission lost twice gives a raw `WorkerLost`, exit 3. The engine's `_translate` wraps only plan-task futures (`engine.py` `_result`).
- D2's "nothing left → `ServiceUnavailable` … why each failed" arguably covers the first two, but no leg pins them. Nothing covers the lost probe submission, and D6 names "every pilot preempted" as exit 1.
- The plan chose that every service refusal is retried, even a deterministic one (exit-items r10, "considered"). So the cut is one sentence at the service phase: any non-refusal exception from resolve becomes `ServiceUnavailable(legs[leg]=repr(exc))`, and any from the probe becomes `ServiceUnreachable(reason=repr(exc))`, each `from exc`.
- The fault list gains two cases: the port range held, and a probe `submit` raising the backend's worker-loss exception. Both assert exit 1. The current text gives 3.

**N13 · A raising `launcher.stop` skips `server.shutdown`. [ExitStack-contract member → owner]**
- `HTCondorBackend.close` is three bare calls (`backend.py:129-132`). The cut puts `launcher.stop` on `__init__`'s error stack, but `pop_all()` discards that stack on success.
- On the success path, a `CondorPilots.stop` that raises (a schedd query fails) therefore leaves the task server's port and thread held in an attached driver, and the secret file on disk.
- The adjudication's "a raising teardown step skips later steps" is closed for the set only.
- **Cut:** `__init__` keeps the popped stack and `close()` closes it. This is the ServiceSet idiom, one clause in a file m68a already touches.
- **Leg:** a raising `launcher.stop` still frees the server's port.

## For the owner (stop rule, N12 + N13)
- Task: every exception that leaves m68a's service phase or a teardown has to leave nothing running and be classified as environment.
- By hand: wrap the phase's non-refusal exceptions in the matching refusal, and have `close()` close the stack `pop_all()` returned. `driver.main` and `HTCondorBackend.__init__` already show both idioms.
- Rung (2): both are in the repository. Rung 1 fails because D6 names worker loss as exit 1 and the probes show exit 3.
- Still open from the adjudication: a service that dies mid-run exits 3.

## Exit-round constraints (to the implementer)
- **Stop-order.** Register `launcher.stop` so that LIFO reproduces `close()`'s order: `server.close`, then `launcher.stop`, then `server.shutdown`. Pilots exit on the 410. If `stop` runs before `server.close`, it waits `CLOSE_WAIT_S` before terminating.
- **Partial `start`.** `launcher.start` can fail partway through. Either register `launcher.stop` before calling it, or have `start` release its own partial state (D10's rule). Either passes the frozen leg.
- **Record `_schedd` too.** `CondorPilots.start` records `_schedd` together with `cluster` before spool, because `stop()` queries `self._schedd`.
- **Windows witness.** On Windows, `os.kill(pid, 0)` terminates a live process instead of probing it. It still fails correctly for a live child, but use `proc.poll()` for the Windows witness.
- **m70 wording.** L421 says "a stop never acknowledged is the refusal". Under m68a that failure is only logged.
- **E15 still stands.** L294 still says "which holds the traceback".
- E14 is moot (the text is gone). E16 and E1–E13 stand as r11 left them.
