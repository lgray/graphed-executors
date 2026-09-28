# Review r7 — `plan-services.md` §3.4 m70 (dask/parsl cluster hosting), reviewed alone

Scope: §3.4, D10, the §6/§7/§9 lines that name m70, and the r6→r7 delta
(`git diff --no-index --word-diff reviews/plan-services-r6-snapshot.md plan-services.md`). Code was read in
`~/vibe-coding/lanes/htcondor/graphed-executors` (lane/htcondor 613aaa7). Probes ran in a scratch venv
(distributed 2026.8.0, coverage) under this session's scratchpad. No lane clone or venv was touched.

## r6 findings: both closed
- **M8 (parsl actor announces before ready): closed.**
  - D10 now states the contract: `host_service` returns only after `check_ready` passed where the service runs.
  - The parsl actor now waits for `check_ready` before it announces.
  - Evidence: `probe_ready_identity.txt` has announce-then-bind at 0/5 first-GETs and wait-then-announce at 5/5.
  - The first-try GET row therefore discriminates.
- **M9, dask row: closed.**
  - The Variable carries `host_identity()`, and the row asserts that the probe passes on answers that carry the
    driver's identity.
  - D2's all-same rule passes on that answer iff the identity is the driver's.
  - `probe_ready_identity.txt` shows `DASK ... all equal: True`.

## Premises checked, all hold
- `pin_to_worker` forwarding: `dask_backend/backend.py:83-84`.
- The following all exist in the lane clone: `_open_driver_endpoint` (`transport_peer.py:334`), `HOST = "127.0.0.1"`
  (`:40`), `start_htex` (`launch.py:27`), and `n_workers` on the dask, parsl and condor backends.
- The m70 test basenames do not collide:
  - `find tests -name test_{hosted_service_attribute,dask_hosted_service,parsl_hosted_service}.py` returns 0 hits.
  - Control: `test_parsl_peer_reduce.py` is found.
- Stacking: m70 needs `recipes.http_server`, `ServiceSet` and `host_identity` (m68a) and condor `host_service`
  (m68b). All of them come earlier, and §7 orders m70 after m68b. Every commit is under 2k lines.

## Design findings

**M11: a hosted actor whose recipe never becomes ready keeps its worker slot and its child process after the run
fails.**
- Where: §3.4, both the dask and the parsl actor, plus D10.
- The r6 repair made each actor wait for `check_ready` before it announces.
  - That wait has no bound, and it does not listen on the stop channel. The dask actor reaches its `Event` loop and
    the parsl actor reaches its `recv` loop only after the service is ready.
  - The driver's wait gives up: dask `Variable.get(timeout)`, while parsl states no timeout at all.
  - Nothing then stops the actor. `release_service`/`close()` cannot stop it either, because the stop signal is never
    read.
- Measured with `scratchpad/m70p/probe.py`, the plan's dask actor shape with a never-binding child on
  `LocalCluster 2×1`:
  ```
  DRIVER_GET_TIMEOUT TimeoutError after 2.0s
  ACTOR_STILL_RUNNING pending {'tcp://127.0.0.1:61538': ('service:svc:n1',), 'tcp://127.0.0.1:61539': ()}
  CHILD_ALIVE 28503 True
  CHILD_ALIVE_AFTER_CANCEL True        # the plan's backstop client.cancel(force=True) leaves the child
  ```
- parsl: the plan's own `probe_parsl_service.txt` shows `CANCEL_IS_LOCAL_ONLY True ... child alive after cancel:
  True`. The stop message is the only mechanism, and a waiting actor never reads it.
- Result:
  - The run fails with a live child process and a held worker, which is exactly the "a service outliving `close`" that
    the Fails-on line names.
  - No frozen row covers the not-ready path.
- Closed by one sentence in D10 plus a frozen row:
  - D10: "`host_service` returns a checked endpoint or raises having released what it started."
  - Each actor's readiness wait is bounded by `spec.timeout_s` and polls its stop signal between attempts: dask
    `Event.is_set()`, parsl a short-timeout `recv`.
  - On timeout or stop, the actor kills the child and reports the last reason: dask sets the Variable to it, parsl
    announces a failure.
  - `host_service` raises that reason only after the actor's future has finished.
  - Frozen row in both hosted tests: a recipe that never binds (for example `{python} -c "import time;
    time.sleep(600)"`, `timeout_s=2`) is refused naming the managed leg and the check's reason. The child pid is gone,
    and the worker is free: both dask workers' `processing` is empty; on parsl a follow-on task runs.
- The same shape occurs outside this unit, for the m68a and m68b reviews. The D10/D2 sentence covers all three:
  - m68a L239: the driver-hosted `Popen` has "poll the check" with no bound and no terminate stated.
  - m68b L347: after the `wait_announce(name, spec.timeout_s)` timeout, the `ServiceJob` is not stated to be removed.

**M12: m70's engine delta has no covering test in any job that gates `submit/`, so its diff-coverage gates fail.**
- Where: §3.4 Engine (`submit/services.py` +15), the frozen table, and the §6 `test-dask`/`test-parsl` line.
- Which jobs gate `submit/` diff lines at ≥98%, measured in `.github/workflows/ci.yml`, `pyproject.toml` and the
  `.coveragerc-*` files:
  - The main `test` job gates them: its diff-cover excludes only `dask_backend`, `common`, `parsl_backend` and
    `htcondor_backend`.
  - It installs `.[dev]`, and `dev` contains neither dask nor parsl.
  - `test-dask` gates them too: it includes `src/graphed_executors/submit/**/*.py`.
  - `test-parsl` does not: the `.coveragerc-parsl` source is `parsl_backend` plus two `common` modules, and its
    diff-cover includes only `parsl_backend/**`.
- The engine's stop-timeout refusal ("a stop never acknowledged is the refusal") is witnessed only in
  `test_parsl_hosted_service.py`, which runs in the one job that does not measure `submit/`.
- Every m70 row that reaches the engine needs real dask or parsl, so each one skips in the main job.
- Result: the m70 PR fails the diff-cover gate in `test` and in `test-dask`.
- `test_hosted_service_attribute.py` "(all OS)" also constructs `DaskBackend` and `ParslBackend(HTEX)` in a job where
  neither is installed. Parsl is also excluded on 3.14/3.14t.
- Closed by:
  - A frozen engine-level row that imports neither dask nor parsl and runs in the main matrix and `test-dask`: a fake
    hosting backend (`ThreadBackend` plus duck-typed `host_service`/`release_service` whose release never
    acknowledges).
  - That row covers the stop-timeout refusal, the hosted `{python}` rendering, and the `n_workers` accounting seen by
    the engine.
  - The attribute test importorskips each backend on its own.
- Out of unit, for the m68a review: `.coveragerc-dask` sources the whole `graphed_executors.submit` package and its
  per-file gate is ≥90%. Coverage reports an unimported file in a source package at 0%. Scratch probe:
  `pkg/unused.py 3 3 0%`, control `pkg/used.py 100%`.
  - So once m68a adds `submit/services.py`, `test-dask` fails its per-file gate unless m68a omits that file there or
    gates it in exactly one job.
  - m68a §6 changes only `.coveragerc-htcondor`.

## Exit-round constraints (for the dispatch, no round)
- **E1.**
  - The hosted-service subtraction goes in `DaskBackend.n_workers` and `ParslBackend.n_workers`.
  - Reason: `tasks_engine.py:290,386`, `relay_engine.py:84,189` and `transport_peer.py:344-346` all call
    `backend.n_workers()` directly.
  - So the §3.4 heading "Engine (`submit/services.py` +15)" misplaces it.
  - `task_slots()` (used only by the engine window, `engine.py:607`) stays unchanged.
- **E2. D10's condor clause.** For `grpc:`, `announce.py` self-checks by connect only (m68b §3.3), so D10's
  "`check_ready` passed where the service runs" is true of dask and parsl but not of condor `grpc:`. Say so in D10.
- **E3.**
  - The dask actor's endpoint host is its worker's contact host (the host part of `get_worker().address`), and its
    port comes from `spec.ports` (D1).
  - The parsl actor uses `HOST`.
  - Both go through the one mint helper (r6 C2).
- **E4.** Spell out `test_parsl_hosted_service.py`'s "the same". The probe passes on answers carrying the driver's
  identity, and a task GETs the endpoint at its first try. This is M8's witness on parsl.
- **E5.**
  - Name m70's harness with a unique basename, for example `hosted_harness.py`.
  - The frozen dirs have no `__init__.py`, so same-named helpers across dirs collide.
  - The "actor ignores stop" injection and M11's never-binding recipe both live in that harness.
- **E6. §6.** `_service.py` and `transport_peer.py` are already inside the `.coveragerc-dask` and `.coveragerc-parsl`
  package sources. The m70 CI edit is to add `tests/frozen/m70` to the explicit pytest path lists of `test-dask` and
  `test-parsl`, plus M12's main-matrix row.
- **E7.** `start_htex` takes a required keyword-only `run_dir`, so write `start_htex(workers=2, run_dir=…)`.

## Verdict
**m70: NOT CLEAN**, on M11 and M12.
- Both are new shapes: M11 comes from the r6 readiness repair, and M12 from the CI gate topology.
- Each closes with a sentence and a frozen row, as given above.
- The m70 design count is 2 at r6 and 2 at r7, which is not falling. That is the non-convergence signal for the issuer.
  M11's cause-level cut sits at D10/D2 and also covers m68a and m68b.
