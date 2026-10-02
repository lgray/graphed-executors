# m69b executors implementation review, round 6 (PR #44: delta 6877abc..245d0c6, then upstream/main...245d0c6)

## Verdict: REJECT

**Part 1, the delta: H1 is closed, with zero findings.** So Part 2, the whole-PR pass, ran. It found three design
findings that the delta rounds could not see. Each was probed:

- **D1 (Major).** A later plan's failed service start leaves the runner's queued pilots held. Nothing but a later
  need of a worker releases them. On a real pool, a concurrent plan with nothing left to submit sat with free room
  for 90 s, and one `n_workers()` let it finish 10 s later. The one-line cut was measured on the pool.
- **D3 (Major).** A plan whose servers each fit a slot, but not together, waits forever. The match subtracts the
  runner's running pilots but not the plan's own running servers. On a real pool, server 2 stayed idle for 120 s
  beside its running sibling. A normal `close()` would wait with it.
- **D2 (Minor).** In a driver job that has a SERVICE node, a service too big for the slot raises `ValueError`
  ("no SERVICE node") instead of the documented `ServiceUnavailable` naming the sizes.

D1 and D3 have one shape, stated under D3. There is no dead code: `stop_waiting` has one `src` caller
(`HTCondorRunner.__exit__`), no `_serving`/`_announcing` remains, and every Remove and Hold `act` passes a
`CondorReason`.

| Gate | Result | Evidence |
|---|---|---|
| frozen tree vs `freeze-m69b-fixup2` (22df587; m68a/m68b tags at eb8691d) | byte-equal: 0 of 256 files differ. df176a2 and 245d0c6 touch no `tests/frozen` (control: 67ba8f2 differs in `test_service_order.py`) | `probes/m69b/frozen_exec_rv6.txt` |
| macOS py3.12, frozen + extra, `--cov-branch` | 1161 passed, 39 skipped, 0 failed. Per-file gate: lowest 93.02 % (`local/shuffle.py`, 15 files in the macOS scope). diff-cover: 47 lines, 0 missing | `probes/m69b/gates_exec_rv6.txt` |
| Linux pool (graphed a51bee4), CI test-htcondor line | 535 passed, 10 skipped (dask, parsl, coffea, Triton), queue empty afterwards. htcondor scope per-file gate: lowest 98.80 % (`server.py`). diff-cover: 271 lines, 0 missing | same |
| test-hgg equivalent | 80 passed, 5 skipped (distributed and classad2 absent, plus the Linux-only bindings row) | same |
| ruff, ruff format, mypy (also win32), sphinx -W | clean | `probes/m69b/lint_integrity_exec_rv6.txt` |
| integrity `scan_diff` | `6877abc..245d0c6`: 0 findings. `upstream/main...245d0c6`: the known advisory `ci_config_modified`. Control: 2 | same |

## Part 1: H1 closed

- **The probe.** I re-ran `probe_start_close_exec_rv5.py` at 245d0c6 (`probe_start_close_exec_rv6.txt`). In both
  cases `close()` now waits out the in-flight submit and removes its cluster, and nothing is left queued:
  ```
  == direct        0.31s backend.close() · 1.50s submit-pilots 7001 · 21.66s act Remove ClusterId == 7001 · 22.07s close() returned
  == runner-close-sigint   1.51s submit-pilots 7001 · 21.67s act Remove ClusterId == 7001 · 22.06s KeyboardInterrupt left close()
  ```
- **The mutant.** `close-without-the-pilots-lock` (`close()` back to `with self._lock:`) is killed by
  `test_close_waits_for_a_pilot_submit_in_flight_and_removes_its_cluster`, with "close() returned with a pilot
  submit in flight". The control passes (`mutant_close_lock_exec_rv6.txt`).
- **The lock order.** `frozen_exec_rv6.txt` lists every acquisition with its enclosing `def`.
  - `_lock` is taken only in `_host_service`, at indent 12 inside `with ExitStack()`, after the `_pilots_lock`
    block (indent 8) has ended, and in `close()`, which takes `_pilots_lock` first.
  - Under `_pilots_lock` the code calls only `CondorPilots` methods (`start`, `release_held`, `hold_queued`,
    `running_claims`), and `launch.py` holds no reference to the backend.
  - So no path holds `_lock` while taking `_pilots_lock`.

## Part 2: findings

### D1 — Major: a later plan's failed service start leaves the runner's pilots held until some later need

- **Defect.**
  - When the pilots are already submitted, `_host_service` holds the queued ones before it submits the service
    job, and so before `match_refusal`.
  - The hold is lifted only by `_move_pilots`. Its callers are a need (`_need`) and the end of the last phase, and
    the phase end only acts when a need was recorded (`if not self._starting and self._wanted`).
  - A set that fails (a refusal, an "ended before it announced", a timeout) has no probe after it, and so no need.
    The pilots stay held.
  - A concurrent plan that needs nothing more then waits on pilots that cannot start. `alive()` counts them, so
    the plan is not failed as pilot-less either. Such a plan has all its tasks in flight, nothing held in its
    window, and no running pilot.
  - With `min_pilots=0`, which the runner accepts, that is a one-task stage on a busy pool. With pilots running,
    the held ones still sit out until the next need.
  - §5.2's "released at that plan's next need of a worker" assumed every set ends in its own probe. A failed set
    has no next need.
- **Probe.** `probe_failed_set_hold_exec_rv6.py` on a minicondor pool.
  - Setup: a blocker keeps a 512 MiB pilot idle. Plan A (one task, `min_pilots=0`) is in flight. Plan B's service
    asks for 10⁷ MiB and is refused. Then the blocker is removed.
  - Output (`probe_failed_set_hold_exec_rv6.txt`, three legs):
  ```
  control      8.1s blocker removed · 10.1s plan A done=True; pilots 2: JobStatus=2
  failed-set  16.1s plan B refused · pilots 4: JobStatus=5 graphed: a service of this run waits for a slot (by user submituser)
             106.3s 90 s later: plan A done=False; pilots 4: JobStatus=5 …
             106.3s after one need: pilots 4: JobStatus=1 · 116.3s then: plan A done=True
  cut         11.1s plan B refused · pilots 12: JobStatus=1 · 13.1s plan A done=True
  ```
- **Cut (measured).** End the hold with the phase that placed it:
  `if not self._starting and (self._wanted or self._held):` in `starting_services`' `finally`.
  - `_held` implies the pilots were submitted, so `_move_pilots` only releases there. Submitting still needs a
    need.
  - The `cut` leg above ran with it on the pool.
  - With the cut, `tests/extra/m69b` and the frozen `test_service_order.py` pass on macOS
    (`cut_d1_suite_exec_rv6.txt`).
  - Frozen row 1 keeps its one Hold and one Release, the Release after the announce: the phase ends after the last
    announce, and the probe's need then finds nothing held.
- **Closed when** a recorder row passes in which a later plan's set holds the pilots and then fails (for example,
  the recorder ends the service job), with no need made; the Release is `act`ed when the set raises. The row fails
  at 245d0c6.

### D3 — Major: a plan whose servers each fit a slot, but not together, waits forever

- **Defect.**
  - `_host_service`'s match subtracts `self.launcher.running_claims()`, which covers the pilots' cluster only.
  - A set resolves its specs one after another, and server 1 runs (announced) when server 2 is matched. If only
    the room server 1 holds could fit server 2, server 2 is admitted (the whole slot matches) and waits for a slot
    with no deadline.
  - Server 1 leaves only when the set closes, and the set closes only after server 2 is up. So the run never
    ends, and a normal `close()` waits for it ("close() finishes every submitted plan, a server's wait for a slot
    included"). Only Ctrl-C or an exception ends it.
  - §5.2's reason for subtracting pilots, "room only they hold is room the job can never get: it is removed unrun
    and refused", applies word for word to the set's earlier servers. The plan does not name them.
  - Reachable whenever a set's servers do not fit the pool together: for example, histserv servers of the offered
    sizes on a small pool.
- **Probe.** `probe_sibling_room_exec_rv6.py` on minicondor (one partitionable slot of 15973 MiB) runs two
  cluster-hosted `recipes.http_server` specs. Output (`probe_sibling_room_exec_rv6.txt`):
  ```
  fit (2 × 6000)       10.0s 6: JobStatus=2, 7: JobStatus=1 · 20.0s done=True
  sum-over (2 × 9000)  10.0s … 120.1s 10: JobStatus=1 RequestMemory=9000, 9: JobStatus=2 RequestMemory=9000
                       120.1s after 120s: done=False
                       121.6s closed; … 'web2' … still waited for a slot when the runner closed: JobStatus=1
  ```
- **Cut (needs the plan's decision).** In `_host_service`, add to `claims` the running ads of this set's earlier
  service jobs: the keys in `_services` that start with `f"{scope}-"`, queried with `running_claims`' projection.
  - The refusal then names those servers beside the pilots.
  - A real running job's ad already subtracts correctly through `_less_claim` (r3's `probe_claims_exec_rv3.txt`,
    a 3000 MiB × 2-CPU job), so that premise is bought.
  - Other plans' servers stay out of the subtraction, since they leave when their plans end.
- **Closed when** the `sum-over` leg, as a pool row, raises `ServiceUnavailable` for server 2 with its job removed
  unrun (`NumJobStarts == 0`), and the `fit` leg still completes.

**The shape of D1 and D3.** A no-deadline wait (a server's wait for a slot, a plan's wait on queued pilots) is safe
only when what it waits on is outside the run. The run's own holders must be counted at admission or released with
the phase that placed them. r3 counted the run's running pilots. The set's own running servers (D3) and the set's
own hold (D1) are the two members it left. Each cut is at its operation: the match's claims, and the phase end.

### D2 — Minor: a too-big service in a driver job with a SERVICE node raises `ValueError`, not `ServiceUnavailable`

- **Defect.**
  - `ServiceSet._managed` falls through from a driver-side refusal to `host_service` whenever `host_service` is
    callable.
  - In a driver job whose DAG has a SERVICE node for another spec, `host_service` is `_host_announced`, which can
    host only SERVICE nodes. An image-less spec never has one (`driverless._service_nodes` takes only images and
    GPUs).
  - So the size reason is lost, and `_host_announced` raises `ValueError` "has no SERVICE node in this run's DAG".
  - htcondor.rst "Schedulability" says a backend with no cluster host "refuses it with `ServiceUnavailable`, whose
    `legs["managed"]` names the sizes and the limit". The driver still exits 1 either way (`driver.main`).
- **Probe.** `probe_driverjob_toobig_exec_rv6.py` uses an in-job backend whose slot `Memory` is 100 MiB and a
  200 MiB image-less spec (`probe_driverjob_toobig_exec_rv6.txt`):
  ```
  announced={}               ServiceUnavailable … managed: its 200 MiB would bring the services beside the driver to 200 MiB, above the backend's driver_memory_mb of 100 MiB
  announced={'gpu': 'svc0'}  ValueError: service 'small' has no SERVICE node in this run's DAG (announce_only={'gpu': 'svc0'}), and a driver job submits no service job
  ```
- **Cut.** Fall through only to a cluster host, as the docs say:
  `if not callable(host_service) or "cluster" not in hosts: raise ServiceUnavailable(...)` in the too-big branch.
  - An attached runner with `"cluster"` still falls through.
  - A driver job (`("driver",)`) and a `("driver",)`-narrowed runner refuse with the sizes.
- **Closed when** the `announced={'gpu': 'svc0'}` case raises `ServiceUnavailable` whose `legs["managed"]` names
  the sizes.

## Checked, no finding

- **`service_hosts` narrowing** is refused before the task server starts, in the order the docs give.
- **The driver-memory check** sums the set's services beside the driver and falls through on an attached runner.
- **`run_lpc`'s `driverless_memory_mb`** covers the driver, its local pilots and the servers, so the in-job check
  passes.
- **design.rst's "`close()` … waits for every submitted plan"** holds for `HTCondorRunner`: on an exception, the
  plans waiting for a slot end by raising.
- **htcondor.rst's "Closing" and "A run's service jobs go before its pilots"** match the code. "Released … at the
  next need of a worker" matches the code too; D1 is that this rule leaves a failed set's hold in place.

## Exit-round items (constraints for the next dispatch; no round needed)

1. **Docs.** htcondor.rst "A later plan's servers wait with the runner's queued pilots held … released … at the
   next need of a worker" becomes "released once that plan's services have started or failed" with D1's cut. The
   claims sentence in "On the cluster, a slot must match" gains the set's own servers with D3's. Make both edits in
   the same commits.
2. **The plan.** §5.2's "Later plans" release clause and the sentence about subtracting pilots need the same two
   edits: an owner ruling, for D3's decision.
