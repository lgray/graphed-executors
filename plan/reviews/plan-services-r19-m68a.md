# plan-services r19: m68a delta review (r18 snapshot to plan)

**Verdict: NOT CLEAN. 1 design finding (H1).** r18's G1 and G2 are closed at their causes. H1 sits in the parsl `release_service` sentence that the G1 repair rewrote. The gap is older than r18: the r17 text did not await the actor either, and r18's "Closed when" did not name the await. Because the delta has a design finding, no whole-unit pass was run.

## r18 findings

- **G1 (parsl driver endpoint never closed): closed.**
  - The §3.4 release now pops the key's driver endpoint, sends `("stop",)` and closes the endpoint in a `finally`.
  - `EscalatingHttpTransport.close` suppresses its own errors (exec-main `common/http_plane.py` `close`), so the `finally` cannot replace the outcome.
  - The m70 parsl row gains two witnesses: after the two-run and overlap legs, each endpoint refuses connections and the thread count is restored; on the unacknowledged leg, the endpoint refuses.
  - Fails-on now names "a driver endpoint left open".
- **G2 (no `ServiceUnreachable -> 1` witness): closed.**
  - `_exit_code` is now parametrized over `ServiceUnavailable`, `ServiceUnreachable` and raw `WorkerLost` (each 1). The controls are `ValueError` and a task-`ValueError` `StageError` (each 3).
  - The controls discriminate. exec-main `htcondor_backend/driver.py` `_exit_code` returns 1 only for `StageError` with `cause_type == "KilledWorker"`. So m67 code fails the three legs that expect 1 and passes the two controls, and an implementation that leaves out any one of the three types fails that type's leg.

## Design findings

**H1: parsl `release_service(key)` returns once the stop is delivered, not once the actor has stopped. Two m70 legs cannot hold.**
- **Where:** §3.4 parsl, "`release_service(key)` pops that key's driver endpoint, sends `("stop",)` on it and closes it in a `finally`". Nothing in it waits on the actor.
  - `grep -o "[^.;]*await[^.;]*" plan-services.md` returns three sentences: the probe answer, the engine's "`release_service` is awaited with the spec's `timeout_s`", and dask's "sets that key's Event, awaits its actor's future". None of them is about parsl.
- **Code:** `EscalatingHttpTransport.send` is an inline, synchronous `POST /msg` into the peer's inbox (exec-main `common/http_plane.py` `send`, `urlopen(req, timeout=5)`). It returns when the inbox accepts the message, whether or not the actor ever `recv`s it.
- **Premise, already shown by existing evidence:** in `probes/services-code/probe_parsl_service.txt`, "SERVICE_STOPPED_BY_MESSAGE True child gone after 0.1s". The driver sent the stop, then polled `kill(pid,0)`, and the child was still alive on the first poll after `send` returned. The actor in `probe_parsl_service_tasks.py` `service_main` kills the child, waits for it and closes its endpoint, and only then returns. So its future's completion is the acknowledgement.
- **Harm:**
  1. "a stop that is never acknowledged … refuses at the timeout naming the actor": the injected actor that ignores stop still has an inbox that accepts the POST. `release_service` therefore returns at once, and neither a refusal nor a log record ever fires. The engine's "a stop never acknowledged is the refusal" has nothing to time out on for parsl.
  2. "the run's end ends the child (pid gone) and frees the port" races the actor's kill and close. The leg passes or fails on timing.
- **Closed when:** parsl `release_service(key)` sends `("stop",)` and then awaits that call's actor future up to the spec's `timeout_s`, which is dask's shape. It raises on timeout, naming the actor. The endpoint close stays in the `finally`, so it runs on both paths.
  - The existing m70 legs are the test that shows H1 closed. The unacknowledged-stop leg fails without the await, and the pid-gone/port-free leg becomes deterministic.
  - To keep that leg sharp, add a harness actor whose stop handler sleeps about 1 s before it kills the child. After `run` returns, its pid is gone. Without the await, the pid is still alive.

## Exit items (constraints for the implementer; no round)
- **`threading.active_count()` leg.** `ThreadingHTTPServer` handler threads can outlive the request by a moment. Assert the count within a short bounded wait, not at a single instant.
- **Stop-ignoring parsl actor.** After the timeout it still holds an HTEX slot. HTEX has no remote cancel (measured), so the harness's `stop_htex` is the only reclaim. Do not add a backstop in `release_service`.
- **Carried from r18, still open as constraints:**
  - Clearing the dask Event on release is optional.
  - Leave a late condor announce under a dropped key; add no sweep.
  - The warm recipe with `submit` must await futures inside the set's `with`.
  - The warm set on `HTCondorRunner` calls `wait_for_pilots()` first.
  - Status witnesses read the `graphed_executors.services` log record.
  - The m70 unacknowledged stop is witnessed by a log record naming the actor, and the run's value stands. m68a's releases log and never raise, so the frozen phrase "refuses at the timeout" means that `release_service` raises and the set logs it.
