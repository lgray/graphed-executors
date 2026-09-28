# plan-services r24: m68a whole-unit pass

**Verdict: CLEAN. m68a has no design findings, and K2 is closed.**

I read D1, D2, D4, D6, D7, D10, §3.1, and the §6–§9 lines that bind m68a. I also read the delta since r23 (`git diff --no-index --word-diff reviews/plan-services-r23-snapshot.md plan-services.md`), which has two hunks: the `test_scope_dask_memory.py` row and the §6 `test-dask` sentence. Greps ran against graphed-executors `origin/main` `b966a28` and `origin/lane/htcondor` `613aaa7`. I ran no probe, because the K2 row matches its r23 probe and no premise below needed a driven run.

## K2: closed
The row now reads: one batch of 40 leaves, `SubmitRunner(DaskBackend(LocalCluster 2×1), control=RunControl())`, a count of `-leaf-` keys whose `who_has` holder list is non-empty, and a bound of `backend.task_slots()`.

That is `probe_dask_memory_leg_r23.txt` row 3 (`windowed feed=bulk`):
- the not-done wrapper (`live`) gives a max held of 2, which equals `slots=2`;
- recording every future (`all`) gives 40.

So the row passes the repair and fails the K1 defect. `_run_adaptive_windowed` sizes its window from `_task_slots()`, which is `task_slots()` where the backend has one (`engine.py` `_task_slots`), and `DaskBackend.task_slots` exists (`dask_backend/backend.py`).

The §6 line now adds the file to `test-dask`'s explicit list, which is a list of named paths (`ci.yml` `test-dask`: `pytest tests/frozen/m42 … tests/frozen/m65/…`). The all-OS `test` job installs `.[dev]` without the `dask` extra (`ci.yml` `test`, and `pyproject.toml` `dask = ["dask[distributed]>=2026.6"]`), so the file's `importorskip` skips it there and on `test-htcondor`.

## Checked, no finding
- **Engine seams the text names exist at `b966a28`.**
  - `SubmitBackend.n_workers`, `.cancel(futures)`, and `.submit(fn, *args, key=…)` (`submit/protocol.py`) are what the probe bound `max(2, n_workers())`, the probe cancel, and the keyed probe submit rely on.
  - `SubmitRunner.__enter__`/`__exit__` exist (`engine.py`), which the warm recipe's `with SubmitRunner(backend) as runner` needs.
  - `run` mints `ctx` once per call, and its cancel check returns before any `_run_*` path, which is "after the cancel check".
  - `htcondor_backend/server.py` defines `WorkerLost` (`_exit_code`'s raw-`WorkerLost` leg).
- **D4 site data.** `origin/main` `sites.py` has `service_ports` and derives `service_hosts` from it: `("driver",) if self.service_ports`, then `("cluster",) if self.worker_ports`. lpc's `driver_ports=(10000, 10100)` (`origin/lane/htcondor`) supports D4's claim that the task server binds first, below the `(10001, 10100)` service range.
- **The driverless `test` job does not pick up the dask leg.** See K2 above.

## Exit items (constraints for the implementer; no round)
- **Stack order in `run`:** enter the `ServiceSet` on the run's `ExitStack` before registering the plan-task cancel. With LIFO, the cancel then runs before any service is released, so a queued task cannot be leased against a stopped service. No frozen leg pins this order.
- **Empty driver set:** `driver.main` enters its `ServiceSet` unconditionally. With `plan.services == ()`, `start()` submits no probe and starts nothing, as the engine does when it skips the set, so m67's service-free driverless runs gain no task.
- **`ThreadBackend.advertise_host = "127.0.0.1"`:** this is a new attribute in `submit/threadpool.py`, which commit 1's file list does not name. `ThreadBackend` has no such attribute at `b966a28`.
