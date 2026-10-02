# m69b executors implementation review, round 3 (PR #44, delta 40470e6..67ba8f2)

## Verdict: REJECT

Two Major design findings are open, and both break §5.2 "Ordering"'s rule that a runner's own pilots never
hold room its servers need:
- **O1:** a DAG driver job submits its pilots before its SERVICE nodes announce.
- **O2:** one plan's need of a worker releases the pilots that another plan's waiting server held.

Each is a small change. Everything else is closed:
- **M3** is closed by 84e6fb7 and the LPC a51bee4 leg. The pilots on the `cmswn*` nodes wrote 4 parts to EOS, and
  all 14 histograms are bitwise equal (`lanes/htcondor/probes/site-lpc/m69-hgg.txt` "a51bee4 summary").
- **M4** is closed: both rows pass together (below).
- **CondorReason**, the new extra rows and the r2 exit items are closed.
- Every gate is green.

| Gate | Result | Evidence |
|---|---|---|
| frozen m69b/m68b/m68a vs `freeze-m69b-fixup`/`-m68b-fixup4`/`-m68a-fixup2`; m69a, m66, m67, m68c | byte-equal. 6811102, 04fb8b1, 8227fcf and 67ba8f2 touch no `tests/frozen`. 84e6fb7..eb8691d changes only the ruled m68a/m68b tests and READMEs (control: 8 files) | `probes/m69b/frozen_exec_rv3.txt` |
| macOS py3.12, frozen + extra, `--cov-branch` | 1148 passed, 39 skipped; lowest file 93.02 % (`local/shuffle.py`); diff-cover 44 lines, 0 missing | `probes/m69b/gates_exec_rv3.txt` |
| Linux pool (graphed a51bee4), CI test-htcondor line with `test_service_order.py` | 522 passed, 10 skipped, none of them an ordering id; htcondor scope lowest 98.69 % (`backend.py`); diff-cover 233 lines, 0 missing; queue empty afterwards | same |
| test-hgg equivalent | 67 passed, 5 skipped | same |
| ruff, ruff format, mypy (also win32), sphinx -W | clean | `probes/m69b/lint_integrity_exec_rv3.txt` |
| integrity `scan_diff`, `upstream/main...67ba8f2` | 1 advisory `ci_config_modified`: the test-htcondor list gains `test_service_order.py` (sanity F1); control 2 | same |

## Closed

**M4: both rows pass together.**
- **Row 1, free slot.** I re-ran `probe_close_pool_exec_rv2.py free 2` and `free` at 67ba8f2
  (`probe_close_free_exec_rv3.txt`).
  - At `POLL_S=2`, the job logged `waits for a slot: JobStatus=1` at 13.4 s, and `close()` returned `VALUE 1` after
    12.3 s. History shows `NumJobStarts 1` and the queue is empty. The same output was a `RuntimeError` at df4d059.
  - The frozen `test_close_at_once_finishes_a_plan_on_a_free_slot` passes in the pool run.
- **Row 2, idle forever.** The frozen `test_ctrl_c_removes_a_waiting_server_and_submits_no_pilot[run,result,close]`
  rows (a blocker, SIGINT) and `test_close_waits_for_a_waiting_server_and_an_error_in_the_block_ends_the_wait`
  pass in the same pool run.
- `htcondor.rst` "Closing" now states `design.rst`'s contract.
- The LPC run confirms the premise: its fresh service job logged one `waits for a slot: JobStatus=1` at 13:39:36Z,
  11 s after `QDate` (the a51bee4 summary).

**CondorReason.** Probe: `probe_reason_exec_rv3.py`, htcondor 25.13.2 in the pool. `Schedd.act`'s source
unpacks a tuple and passes `str(code)`. Output:
```
CondorReason  hold -> HoldReason 'graphed: a service of this run waits for a slot (by user submituser)', HoldReasonCode 1; release by prefix -> TotalSuccess=1
str           hold -> HoldReason '', HoldReasonCode 1; release by prefix -> TotalSuccess=0
CondorReason  removed -> RemoveReason 'graphed: run closed (by user submituser)'
```
- `(text, None)` is accepted, and the hold stays a user hold (code 1).
- The frozen recorder stamps `str(reason)` (`m69b_order.OrderSchedd.act`), so `CondorReason.__str__` gives it the
  text. No frozen or extra test compares a Remove reason as a str.
- `grep -rn 'JobAction|\.act(' src`: every Remove and Hold passes a `CondorReason`. The one Release passes no
  reason (htcondor2's default).
- Pool mutants `hold-str-reason` and `release-any-hold` are killed by `test_a_real_schedd_releases_graphed_s_hold_and_not_the_user_s`
  (`mutants_exec_rv3.pool.txt`).

**The claim's share.** `probe_claims_exec_rv3.py` runs a real 3000 MiB × 2-CPU job and reads it with
`running_claims`'s projection:
- `*Provisioned` is present 3 s after the start.
- `RequestDisk` is `MAX({1024, (TransferInputSizeMB + 1) * 1.25}) * 1024` and evaluates to `1048576.0` without
  `TransferInputSizeMB`.
- `_less_claim` leaves `slot1` at Memory 12901, Cpus 8 (15973/10 whole).

**The new extra rows: 8 of 8 mutants killed** (`mutants_exec_rv3.mac.txt`; control passes):
- `backend-close-no-remove` (r2 exit item 1, now closed)
- `stop-unserialized`
- `stopped-check-gone`
- `closing-submit-check-gone`
- `alive-held-not-counted`
- `alive-any-hold`
- `claim-parent-lost`
- `claim-request-first`

**The three decisions you named.**
- **The `_closing` check before the alive check.** Sound: a job that `close()` removed reports the close. Its
  mutant only changes the message (exit item 1).
- **`wait_for_pilots(n >= min_pilots)` as the first need's wait.** Sound. Neither direction's mutant is killed,
  including by m66/m67 (exit item 2).
- **`ServiceJob` recorded before its submit, under `_lock`.**
  - Read against `close()`: `close()` sets `_closing` and snapshots `_services` under the same lock.
  - A job recorded before that snapshot is stopped. If its submit has not yet run, `submit()` raises "stopped
    before it was submitted" under the job's lock.
  - A job not yet recorded is refused.
  - So no job is submitted that `close()` does not remove in its own thread.
  - `record-after-submit` survives, because the window needs an injected interleaving (exit item 3).

**r2 exit items.**
- Item 1 is closed (the `backend-close-no-remove` row).
- Item 2 is closed: "Closing" names Ctrl-C in the `with` block and in `close()`.
- Item 4 is closed: `attempts.md` iterations 8–10.
- Item 5 is closed by 84e6fb7.

## Findings

### O1 — Major: a DAG driver job with `pilots="condor"` submits its pilots before its SERVICE nodes announce

- **Defect.**
  - §5.2 "Ordering", Driverless: "with `pilots="condor"` the driver job's backend (`announced`) defers its pilots
    as above, so they follow the SERVICE nodes' announces."
  - The backend does defer.
  - But `driver.main` calls `runner.wait_for_pilots()` before it enters `ServiceSet(plan.services, …)`, and that
    call is a need of a worker. So the pilots go to the schedd before `_host_announced` waits.
  - A SERVICE node that is still idle then competes with its own driver's pilots. That is the plan's case C
    (`probe_order_fifo.txt`): pilots queued behind a server that cannot yet match take the holes it cannot use,
    and keep them.
  - `_host_announced` bounds this by `timeout_s`, so the run fails (exit 1, DAGMan retries) rather than hangs.
    The ruling's order would have run it.
  - `htcondor.rst`'s "The runner's own pilots never hold that room" is false for this form.
- **Probe.** `probe_driver_order_exec_rv3.py` runs `driver.main` over the frozen `OrderSchedd`. The SERVICE node
  announces 3 s after the driver publishes its url. Output (`…driver_order_exec_rv3.txt`):
  ```
    0.00s submit-pilots
    0.04s mark           driver published its url
    0.23s mark           ServiceSet asks for the SERVICE node's announce
    3.06s announce       svc0
  pilots submitted BEFORE the SERVICE node's announce
  ```
- **Closed when** a recorder row over `driver.main` (DAG form, `pilots="condor"`, an announce posted N s after the
  url) shows two things:
  - the pilots' `submit` follows the announce, and the driver exits 0;
  - with the pilots never starting, the driver still exits 1 (`EXIT_FAILED`), not 3, both for that plan and for a
    plan with no services.

  Today's `driver.py` fails the first condition.

  Deleting the explicit wait is not enough. For a plan with no services, the first need would then be the first
  task submit inside `runner.run`, whose `except` maps a `RuntimeError` to 3. Instead, move the wait into the
  `with ServiceSet(…)` block, before `runner.run`:
  - with services, the set's probe from a worker has already submitted the pilots after the announces;
  - with none, the wait submits them;
  - either way a failure leaves through `main`'s outer `except` as exit 1.

### O2 — Major: one plan's need of a worker releases the pilots that another plan's waiting server held

- **Defect.**
  - §5.2 "Later plans": the queued pilots "stay held across all of that plan's services and are released at that
    plan's next need of a worker", hence "no pilot of its runner is matchable while it waits".
  - `_submit_pilots` releases on any `n_workers()`, `submit()` or `wait_for_pilots()`, from any thread.
  - Two plans on one runner at once (a `submit()`ted plan beside a direct `run()`, as frozen m68b
    `test_a_cluster_hosted_http_server_serves_its_run_and_leaves_with_it` does): the running plan's next task
    submit releases the queued pilots while the other plan's server still waits.
  - Released pilots that take the room keep it until `close()`. The claims-aware match never counted them, since
    they were queued at match time. So the server waits on its own runner's pilots with no deadline. If its plan
    was `submit()`ted, `close()` waits for it until Ctrl-C: the M1 hang again, by another route.
  - "Released when that plan next needs a worker" in `htcondor.rst` is false in this case.
- **Probe.** `probe_hold_release_exec_rv3.py`, over `OrderSchedd`: pilots submitted and both queued; plan B's
  `host_service` waits on an idle service job; plan A then submits one task. Output (`…hold_release_exec_rv3.txt`):
  ```
    0.00s act             7001 Hold ClusterId == 7001 && JobStatus == 1 graphed: a service of this run waits for a slot
    0.00s submit-service  7002 planB-69009d1a028a7c82
    1.06s mark             plan B's server waits; plan A submits a task
    1.06s act             7001 Release ClusterId == 7001 && JobStatus == 5 && substr(HoldReason, 0, 47) == "graphed: …
    2.07s mark             plan B's server still waiting: True
  ```
- **Closed when** a recorder row passes in which:
  - plan B's `host_service` waits on a thread while plan A's `backend.submit()` runs;
  - no `Release` is `act`ed until B's wait has ended (its announce, refusal or raise);
  - the next need of a worker after that releases.

  The row fails on 67ba8f2. One way to pass it: count the `_host_service` calls in progress, and release only when
  that count is zero. Frozen row 1, which is serial, keeps its one Hold and one Release per plan.

## Exit-round items (constraints for the next dispatch; no round needed)

1. **The close message is the only thing guarding the order of the `_closing` check.** Mutant
   `closing-after-ad-check` survives the extra suite and the frozen close row. Under it, a job `close()` removed
   reports "ended before it announced: JobStatus=3 …". Assert the message in `test_backend_close_removes_a_waiting_service_job_before_it_returns`:
   `"when the runner closed"`.
2. **`wait_for_pilots`'s `_waited` update has no row in either direction.** `any-wait-is-the-first-need` and
   `no-wait-is-the-first-need` survive the extra suite, the recorder rows and m66/m67. A row should call
   `backend.wait_for_pilots(0)` with `min_pilots=1`, then `n_workers()`, and check that it still waits for one
   pilot.
3. **No row pins "recorded before submit".** `record-after-submit` survives. The `ServiceJob`-level row covers the
   stop-before-submit half. If a row is wanted, it can block `schedd.submit` on an `Event`, call `backend.close()`,
   and check that the Remove is `act`ed by `close()`, not by the waiter.
4. **The docs sentences that O1 and O2 falsify** ("The runner's own pilots never hold that room"; "released when
   that plan next needs a worker") become true with those fixes. No separate edit is needed.
