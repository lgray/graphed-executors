# m69b executors implementation review, round 5 (PR #44, delta 0008028..6877abc)

## Verdict: REJECT

G1, G2 and T1 are closed. The gate is one rule at `_move_pilots`, reading the plan's two states, and all 11 named
mutants die, as does r4's `release-on-any-need`. One design finding remains:

- **H1 (Major).** A pilot submit already running when `close()` starts is never removed by that `close()`.
  - The cause: `_move_pilots` checks `_closing` under `_pilots_lock`, but `close()` sets `_closing` under `_lock`
    alone and then stops the launcher. A submit that began before the close finishes after the launcher's stop.
  - Reachable through the runner: a Ctrl-C that lands in `close()`'s drain while the plan thread is in the first
    need's submit leaves the pilot cluster queued.
  - It is a member of r4 G1's class (a pilot submit that `close()` does not remove), and it is older than r4: it
    came in with the deferred submit and is already present at 67ba8f2.
  - The fix is one line, and it is the rule `ServiceJob` already keeps ("a stop waits for a submit in flight").

| Gate | Result | Evidence |
|---|---|---|
| frozen tree vs `freeze-m69b-fixup2` (22df587; m68a/m68b tags at eb8691d) | byte-equal: 0 of 256 files differ. 3a977ac and 6877abc touch no `tests/frozen` (control: 67ba8f2 differs in `test_service_order.py`) | `probes/m69b/frozen_exec_rv5.txt` |
| macOS py3.12, frozen + extra, `--cov-branch` | 1160 passed, 39 skipped. Lowest file 93.02 % (`local/shuffle.py`). diff-cover: 47 lines, 0 missing | `probes/m69b/gates_exec_rv5.txt` |
| Linux pool (graphed a51bee4), CI test-htcondor line | 534 passed, 10 skipped (dask, parsl, coffea, Triton), queue empty afterwards. htcondor scope per-file gate: lowest 98.80 % (`server.py`). diff-cover: 271 lines, 0 missing | same |
| test-hgg equivalent | 79 passed, 5 skipped | same |
| ruff, ruff format, mypy (also win32), sphinx -W | clean | `probes/m69b/lint_integrity_exec_rv5.txt` |
| integrity `scan_diff` | `0008028..6877abc`: 0 findings. `upstream/main...6877abc`: the known advisory `ci_config_modified`. Control: 2 | same |

## Closed

**G1.** I re-ran `probe_close_need_exec_rv4.py` at 6877abc (`probe_close_need_exec_rv5.txt`). None of the four
runner cases submits a pilot, and each with-need case now behaves like its control:

| case | r4 (0008028) | r5 (6877abc) |
|---|---|---|
| result-need | `submit-pilots 7002` at Ctrl-C; block left at 23.04 s | no pilot; block left at 3.01 s (control 3.01 s) |
| close-need | `7002` left in the queue after the block | no pilot; block left at 2.50 s (control 2.50 s) |

The waiting need threads raise "0 of 1 pilots connected when the runner closed; none was submitted".

**The direct case is correct under the ruled design. Not a finding.**
- The case calls `host_service` bare, which is not a plan starting its services. So the need submits at once
  (0.05 s), `close()` removes cluster 7002 (21.22 s), and nothing is left. The need thread ended, where at r4 it
  was still alive.
- `host_service` has exactly one call site in `src`, in `ServiceSet._managed` (`grep -rn 'host_service(' src`: that
  call and `def _host_service`), and it runs inside the phase.
- The 21.5 s is `CondorPilots.stop` draining idle pilots for `CLOSE_WAIT_S`. r3's trace shows the same wait
  (Remove at 22.2 s).
- r3's `probe_hold_release` (a bare `host_service` too) releases at the need for the same reason. The O2 row now
  drives a real `ServiceSet`.

**G2.** I re-ran `probe_set_gap_exec_rv4.py` (`probe_set_gap_exec_rv5.txt`). Inside the set there is one Hold and
one Release, and the Release (6.05 s) comes after service 2's announce (6.05 s). At r4 the same probe gave two Holds
and two Releases.

**O1 still holds.** `probe_driver_order_exec_rv3.py`: announce at 3.06 s, `submit-pilots` at 3.09 s, exit 0.

**One rule at the operation.**
- `_announcing` and `_serving` are gone: `grep -rn '_serving\|_announcing' src` finds 0 lines (`_starting`: 5).
- `_move_pilots` has two callers: `_need`, which every `n_workers()`/`submit()`/`wait_for_pilots()` poll reaches,
  and the `finally` of `starting_services`.
- `starting_services` is entered only by `ServiceSet.start`, around its `_resolve` loop, which is the one
  `_resolve` call site. The `_probe` runs outside it.
- So while a phase runs, pilots move in neither direction. Once `_closing` is set, nothing is submitted.
- The driverless DAG path resolves `_host_announced` inside the driver's `ServiceSet`, so it is inside the phase.
  `driver.main`'s `wait_for_pilots()` follows the set.

**No hang under Ctrl-C or `close()`.**
- The phase is a context manager, so its counter goes back down on any exception.
- `_await_announce` ends on `_closing` within one `POLL_S`.
- A wait whose pilot was never submitted raises once the run ends. A wait on submitted pilots raises at the first
  poll after `close()`.
- Frozen row 8's three Ctrl-C forms pass in the pool run. In the probe, the runner forms leave the block when their
  controls do.

**After `stop_waiting()` alone: sound.** A wait on submitted pilots keeps going so the drain can finish plans, as
ruled. It cannot outlive `backend.close()`: `test_once_the_pilots_are_submitted_only_close_ends_a_wait_for_them`
passes, and `wait-ends-at-any-close` and `wait-ends-only-unsubmitted` both die. It can outlive a single Ctrl-C in
`result()` until the pilots connect or `N_WORKERS_WAIT_S` runs out. upstream/main does the same:
`SubmitRunner.__exit__` → `close()` → `PlanQueue.close()` waits for the plan's first-need wait. So this is not new.

**Mutants: 12 of 12 killed** (`mutants_exec_rv5.mac.txt`; the control passes, 9 selections):
- `phase-per-resolve`
- `no-phase`
- `probe-inside-the-phase` (the O1 row hangs, cut at 240 s)
- `release-on-any-need`
- `submit-while-closing`
- `wait-ignores-the-close`
- `no-release-while-closing`
- `last-phase-does-not-move`
- `wait-ends-only-unsubmitted`
- `wait-ends-at-any-close`
- `deadline-from-the-call`
- `deadline-from-the-submit`

The two deadline rows close T1. Under `deadline-from-the-call`, the raise came 0.05 s after the phase ended,
against at least 1.0 s.

## Findings

### H1 — Major: a pilot submit running when `close()` starts leaves its cluster queued

- **Defect.**
  - `_move_pilots` reads `_closing` and then calls `launcher.start`, all under `_pilots_lock`.
  - `close()` sets `_closing` under `_lock` only. It then removes the service jobs and closes the stack, and
    `CondorPilots.stop` finds `cluster is None`. A submit that began first then completes: `start` sets `cluster`
    and a fresh `_stack`, and nothing closes them.
  - What breaks:
    - the plan's "`close()` … An exception anywhere … removes every job the runner submitted before it leaves
      `close()`";
    - frozen row 8's "nothing of the child is left in the queue", in a form where Ctrl-C lands during the first
      need's submit.
  - The submit lasts one schedd round trip, or a spool on a spooling site.
  - The service jobs avoid exactly this race: `ServiceJob._lock`, "a stop waits for a submit in flight", and the
    record-before-submit under `_lock`. The pilots have no equivalent.
- **Probe.** `probe_start_close_exec_rv5.py`, over `OrderSchedd`, with the pilot submit taking 1.5 s. Output
  (`probe_start_close_exec_rv5.txt`):
  ```
  == direct need raised=['RuntimeError: 0 of 1 pilots connected when the runner closed']
      0.00s mark             pilot submit begins
      0.31s mark             backend.close()
      0.50s mark             close() returned
      1.51s submit-pilots   7001
    pilot clusters submitted=[7001] left in the queue=[7001]
  == runner-close-sigint          (a no-service plan's first need; a real SIGINT lands in the block's close())
      0.00s mark             pilot submit begins
      0.00s mark             block left normally: close() drains
      0.50s mark             KeyboardInterrupt left close()
      1.51s submit-pilots   7001
    pilot clusters submitted=[7001] left in the queue=[7001]
  ```
- **Cut (tested).** In `close()`, change `with self._lock:` to `with self._pilots_lock, self._lock:`.
  - An in-flight move then finishes first, and the launcher's stop removes its cluster. Every later move sees
    `_closing`.
  - The lock order is safe: `_host_service` takes the two locks in separate blocks, and no path holds `_lock`
    while taking `_pilots_lock` (`grep -n 'self._lock\b\|self._pilots_lock' src/graphed_executors/htcondor_backend/backend.py`).
  - With the cut, the same probe gives `act Remove ClusterId == 7001` before `close()` returns, in both cases, and
    nothing is left (`probe_start_close_exec_rv5.cut.txt`).
  - The 20 s before that Remove is the `CLOSE_WAIT_S` drain. A row can monkeypatch `launch.CLOSE_WAIT_S`, which
    `_drain` reads at call time.
- **Closed when** a recorder row passes: a pilot submit blocked on an `Event` when `backend.close()` is called on
  another thread; once the submit is let go, `close()` returns with that cluster's Remove `act`ed. The row fails
  at 6877abc (the probe above).

## Exit-round items (constraints for the next dispatch; no round needed)

1. **`stop_waiting()` may take `_pilots_lock` too, but needs no change.** The plan says "once its waits are stopped,
   no pilot is submitted". A submit that was in flight when `stop_waiting()` ran is the same outcome as one that
   finished just before it, and the later `close()` removes it.
2. **Docs.** "From then on no pilot is submitted" in "Closing" is true once H1 is fixed. No other doc edit is needed.
