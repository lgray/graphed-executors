# Review r13 — `plan-services.md`, unit m68a (delta vs `plan-services-r12-snapshot.md`)

**Verdict: NOT CLEAN — 1 design finding (N9).** N8 is closed at its cause for driver-hosted children. The same repair
also extended record-before-call to cluster-hosted names, which `start()` does not spawn; that makes
`release_service` run on names `host_service` never hosted. One clause in m68a and one sentence in D10 fix it; the
dispatch can carry both. The delta returned a design finding, so no whole-unit pass was run.

Probe: `probes/services-code/probe_cluster_record_r13.{py,txt}` (driverless `.venv` python,
`PYTHONDONTWRITEBYTECODE=1`, nothing written into any lane clone; executors head 386d65d).

## r12 findings
- **N8 closed for driver-hosted.** L260-262: the child is recorded "at `Popen`", before its check; any exception out
  of `start()` runs `close()` over everything recorded. L253-254 defines the failed poll as `ServiceUnavailable` with
  `legs["managed"]` naming the check. The frozen leg (L297, `sleep(60)`, `timeout_s=1`, pid gone without `close()`)
  matches probe_inflight_start_r12 (`register_at_popen=False` → `child_alive=True`; `True` → `False`).
- **D10 consistency (m68b/m70).** Every `host_service` mention returns `(endpoint, identity)`: L103, L252, L373-374,
  L423, L431.
- **D6** matches the owner ruling (plan `StageError` → 3; `KilledWorker` → 1, retried). **D7** keys on
  `load_params` (L85-88).

## Design findings

**N9 · Recording a cluster name before `host_service` is called sends `release_service` to names nothing hosted.**
- L261: "a cluster-hosted name before `host_service` is called". When `host_service` raises before hosting anything
  (m70 dask: "refused naming the worker table", L418; parsl: `gpus > 0` refused, L428), `close()` calls
  `release_service(name)` on that name.
- D10 (L101-110) does not say what `release_service` does with such a name. m70's rule (L415, "a stop never
  acknowledged is the refusal") makes it wait `timeout_s` and then raise. That raise leaves `start()` in place of the
  original refusal, so D6 would classify it as a plan error: exit 3, not retried.
- probe_cluster_record_r13: record-before gives `raised=RuntimeError(stop never acknowledged) exit=3
  release_calls=['svc']`; record-after gives `raised=ServiceUnavailable exit=1 release_calls=[]`.
- Cause: the r12 rule says the recorder is whoever spawned the child. `host_service` spawns the cluster service, and
  only `host_service` can reach it until it returns. The engine's early record of the name tells the backend nothing
  it did not already know.

**Closed by:**
1. L260-262: record a driver-hosted child at `Popen`, as now. Record a cluster-hosted name only once `host_service`
   returns.
2. D10: `host_service` either returns with the service up, or releases whatever it started and then raises. This is
   the same ownership rule one level down. m68b and m70 implement it and add no other text.
3. Frozen leg in `test_services_protocol.py`: give the two-host fake a `host_service` that raises
   `ServiceUnavailable`. `run` raises that same exception, and the fake's `release_service` spy records zero calls.
   The current text makes one call, so the leg discriminates.

## Exit-round constraints (to the implementer)
- **E14 still stands.** L265 says `graphed.bind_services`; use `graphed.services.bind_services`.
- **E15 still stands.** L288 says "`driver.log`, which holds the traceback". Point at `driver.log` without promising
  a traceback: an `ok=True` blob that fails to load has none.
- E16 and E1–E13 stand as r11 left them.
