# plan-services r23: m68a delta pass (K1 repair + `test_scope_dask_memory.py`)

**Verdict: NOT CLEAN. One design finding: K2 (m68a), the new frozen leg as written fails the repaired code and names a bound the engine it runs on does not keep. K1 is closed at its cause (check a).**

Delta: `git diff --no-index --word-diff reviews/plan-services-r22-snapshot.md plan-services.md` (the §3.1 engine bullet, one new m68a row, one Fails-on term, the `test-dask` CI line). Probes ran against graphed-executors origin/main `b966a28` (a detached worktree on `PYTHONPATH`, now removed) with distributed 2026.8.0 from `~/vibe-coding/lanes/htcondor/.venv`. That is the venv and distributed version r22 used. `graphed-workdir/.venv` has no `distributed`.

## (a) K1: closed at the cause; the discard is race-free if registration follows `_RunLeaves`
Probe: `probes/scope/probe_live_set_race_r23.{py,txt}`.
- **Held after run, all four paths.** Every run went through the not-done wrapper, on both `ThreadBackend` and `DaskBackend`. `_run_adaptive`, `_run_adaptive_windowed`, `_run_fixed` and `_run_fixed_windowed` all return value 66, and the held set is 0 after `run`. So the wrapper pins nothing once a run completes normally.
- **A callback on an already-done future:**
  - On `ThreadBackend`, it runs synchronously in the caller (`MainThread`). This is `concurrent.futures`, and parsl and htcondor futures behave the same way (`_ParslFuture.add_done_callback` wraps a raw `concurrent.futures.Future`).
  - On dask, it runs later, on `Dask-Callback-Thread_0`.
- **Registration order, with a future forced done before registration:**
  - "add under the lock, `add_done_callback` outside it": held = 0.
  - Callback before the add: held = 1, a leaked pin.
  - `add_done_callback` while holding the lock: a deadlock (submit had not returned after 2 s).
  - The repository already has the correct shape: `_RunLeaves.add`/`_done` in `local/executors.py` ("outside the lock: a done future calls back at once"). This goes to the implementer as an exit constraint, below.
- **Snapshot vs. cancel.** A stop run (`target_events=3`, one 3 s leaf) ends with 3 futures in the snapshot, all already `done()`. The engine's own `backend.cancel(list(outstanding))` ran, and the dask callbacks had not yet discarded them. The stack's `cancel` of that snapshot, plus one future that finished after the snapshot, raised nothing and left no `-leaf-`/`r4` key in `who_has`. Cancelling a done future is a no-op on concurrent.futures and a release on dask, so a completion between the snapshot and the cancel is harmless.

## (b) The new leg

Probes: `probes/scope/probe_dask_memory_leg_r23.{py,txt}` (one run of each cell) and `probe_dask_memory_repeat_r23.{py,txt}` (8 runs of each non-recording cell). Setup: 40 × 1 MB leaves, `LocalCluster(2, threads_per_worker=1, processes=True)`, `task_slots()` = 2, a count taken at every `next_tasks` call.

| engine path / feed | wrapper | who_has entries (any) | who_has with a holder (max; 8-run dist.) |
|---|---|---|---|
| `_run_adaptive`, one 40-leaf batch | none / all / live | 40 / 40 / 40 | 2 / **40** / 2 ({2:7, 3:1}) |
| `_run_adaptive`, slots then 1 per call | none / all / live | 3 / 40 / 3 | 2 / **40** / 2 ({1:2, 2:6}) |
| `_run_adaptive_windowed` (`control=RunControl()`), one 40-leaf batch | none / all / live | 2 / 40 / 3 | 1 / **40** / 2 ({1:3, 2:5}) |

Recording every future reaches 40 in every cell, so a leg built this way discriminates K1 by a wide margin. The row as written does not.

## Design finding

**K2 (m68a): `test_scope_dask_memory.py` counts the wrong set and asserts a bound on a path that keeps none.**
- **Where:** the new m68a row: "an adaptive plan of 40 leaves through `SubmitRunner(DaskBackend(LocalCluster 2×1))`: at each `next_tasks` call the count of this run's `-leaf-` keys in `client.who_has()` never exceeds the in-flight slots".
- **Why it changes code:**
  1. **The wrong set.** `client.who_has()` also lists queued and processing keys, with an empty holder list. On the repaired code that count is 40 (one batch) or 3 (windowed), both above 2. The leg fails correct code.
  2. **No slot bound on the plain path.** A runner without `control` runs `_run_adaptive`, which has no window. There, outstanding is whatever `next_tasks` has handed out minus what has been consumed. With one 40-leaf batch, the held count reached 3 in 1 of 8 runs of the repair.
  
  The bound the engine does keep is on `_run_adaptive_windowed`: outstanding ≤ `window.size` = `_task_slots()` = `DaskBackend.task_slots()` = Σ nthreads. So at a `next_tasks` call, at most `size` leaf results are in memory: `size − 1` still outstanding after the pop, plus the consumed one still bound to the loop's `fut`.
- **Measured:** the table above. With the repair, the windowed path with one batch and the slot-fed path held at most 2 in 16/16 runs, and recording every future gave 40. The literal "any entry" count is 40 or 3 on the repair.
- **Closed when:** the row builds the runner with `control=RunControl()` and one 40-leaf batch. The feed alternative is `task_slots()` leaves, then one per call. The row counts only `-leaf-` keys whose `who_has` holder list is non-empty, and the bound is `backend.task_slots()`.
- **Test that shows it closed:** `probe_dask_memory_leg_r23`, row 3. Recording every future gives max held 40 > 2, and the not-done wrapper gives ≤ 2 (`probe_dask_memory_repeat_r23`: 8/8).

## Exit items (constraints for the implementer; no round)
- **Wrapper shape:** use `_RunLeaves`'s registration order: add under the lock, then `add_done_callback` outside it. Take the stack's snapshot as a `list` under the lock. Reuse `_RunLeaves` if its `pending` set fits. Evidence: R2 above.
- **CI line:** the delta repeats "**`test-dask`**" in one sentence. Merge the new file into the existing `test-dask` `pytest` file list (`ci.yml`, job `test-dask`), which names files explicitly.
