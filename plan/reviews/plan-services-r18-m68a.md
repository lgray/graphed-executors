# plan-services r18 — m68a delta review (r17 snapshot → plan)

**Verdict: NOT CLEAN. 2 design findings (G1, G2).** Both are unfinished members of the r17 repairs' own classes. Neither is a new mechanism, and each fix is about one line plus one test leg. r17's F1 and F2 are closed at their causes (D10 per-call key; `_exit_code` type set) for every member except the two below. The delta had design findings, so no whole-unit pass was run.

## r17 findings

- **F1 (name-keyed rendezvous) — closed at D10 for condor, dask and the m68a fake. Parsl is open (G1).**
  - D10 now reads `host_service(spec) -> (endpoint, identity, key)`, with `key = secrets.token_hex(8)` per call and `release_service(key)`.
  - condor: the key is carried by the `ServiceJob` argument, the announce and `services[key]`, and `wait_announce(key)` pops the record. The frozen leg "a second `wait_announce` of that key times out" was added.
  - dask: `Variable/Event(f"…:{key}")`, and release deletes the Variable.
  - Tests: the m68a fake asserts release by the returned key and covers the sequential and overlap legs. The same legs were added to m68b live (a) and to m70 dask and parsl.
  - The premise holds in `probes/lifetime/probe_percall_key_r17.txt`: a name key returns run 1's dead value; a per-call key times out.
  - The DAG SERVICE node's key is its name. That is sound: `driver.main`'s outer set pops it once, and the inner set sees it as leg 1.
- **F2 (in-run service phase exits 3) — closed in `_exit_code`. The test does not witness the member that motivated it (G2).**
  - D6 and §3.1 map `ServiceUnavailable`, `ServiceUnreachable` and raw `WorkerLost` to 1.
  - `WorkerLost` is htcondor's own (`htcondor_backend/server.py:45`), and `_exit_code` is only used in `driver.py:85`, so that member is correctly scoped.
  - No plan-code producer of the two service types exists: they live in `submit/services.py`, which plan code does not import. Mapping them by type therefore does not reclassify a plan error.

## Design findings

**G1 · parsl `release_service(key)` stops the actor but never closes that call's driver endpoint. Each run leaks one listener and one thread.**
- **Where:** m70 §3.4 L483: "`release_service(key)` = stop on that key's endpoint only". The delta added "`_open_driver_endpoint(key)`, one epoch per call".
- **Code:** `_open_driver_endpoint` returns `EscalatingHttpTransport(DRIVER, epoch=…, host=HOST)` (exec-main `parsl_backend/transport_peer.py:334`). That object runs a `ThreadingHTTPServer` with a serving thread (`common/http_plane.py:206-235`) until `close()` (`:355`). `parsl_run_plan` closes its own endpoint (`transport_peer.py:419`).
- **Probe:** `probes/lifetime/probe_parsl_endpoint_close_r18.txt`:
  - After two opens with no close: +2 threads, and the endpoint accepts connections on its port.
  - After `close()`: +0 threads, and `ConnectionRefusedError`.
- **Harm:** under per-run lifetime every run of a hosted service opens one endpoint, and nothing closes it. A long-lived runner accumulates listeners and threads. This matches the unit's own "a service outliving its run". It is also D10's "drops its record" left undone for the parsl member of F1's class.
- **Closed when:** parsl `release_service(key)` sends `("stop",)` and then closes that key's endpoint. The endpoint closes whether or not the stop is acknowledged, so it is closed on every path.
- **Test:** in `test_parsl_hosted_service.py`, after two sequential runs, the driver endpoint of each run's key refuses connections, and `threading.active_count()` is back to its value before the runs.

**G2 · the frozen legs do not witness `ServiceUnreachable → 1`, the member r17 F2 was raised for.**
- **Where:** the `test_driverless_endpoints.py` row (§3.1) has these exit-code legs:
  - the in-run re-check refusal, which exits 1 with `ServiceUnavailable`;
  - `_exit_code(raw WorkerLost) == 1`.
- **Search:** `grep -o "exits 1 with [^;]*\|_exit_code\` of [^,;]*" plan-services.md` finds no `ServiceUnreachable` leg.
- **Harm:** an implementation whose `_exit_code` tuple omits `ServiceUnreachable` passes every listed leg. It still exits 3 on r17 F2's scenario: pilots lost between the outer probe and the inner one, the inner probe unanswered, then `ServiceUnreachable`. That exit is never retried.
- **Closed when:** in the same file, `driver._exit_code` is parametrized over `ServiceUnavailable`, `ServiceUnreachable` and raw `WorkerLost` and asserts 1 for each. The control is `ValueError` → 3, and a `StageError` from a task's `ValueError` → 3. The repair is test text only; the `_exit_code` design stands.

## Exit items (constraints for the implementer; no round)
- **dask release.** Clearing the stop `Event` on release is optional. The r17 probe cleared it; the plan only sets it. The key is unique per call, so a set Event is never read again.
- **condor late announce.** A record that arrives after `release_service(key)` has dropped that key sits under a key that is never read. Leave it; do not add a sweep for it.
- **Carried from r17, still open as constraints:**
  - The warm recipe with `submit` must await futures inside the set's `with`.
  - The warm set on `HTCondorRunner` calls `wait_for_pilots()` first.
  - Status witnesses read the `graphed_executors.services` log record.
  - The m70 unacknowledged stop is witnessed by a log record, and the run's value stands.
