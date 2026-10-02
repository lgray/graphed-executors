# m69b executors implementation review, round 2 (PR #44, delta d3f2820..40470e6)

## Verdict: REJECT

One Major finding is open: M4, a decision for the dispatcher.

- B1, M1, M2, m1 and m2 are closed. Each fix has a test that my own mutant fails.
- M3 was out of scope. 40470e6 reverts d536f04's output route; its default `root://` `--out` waits on graphed's
  fsspec writer. CI's `GRAPHED` is still 7e048bf, so M3 stays open until that writer lands and the pin moves.
- Every local gate is green.
- The delta pass found one design finding (M4), so no whole-PR pass was run.

| Gate | Result | Evidence |
|---|---|---|
| frozen m69b/m69a/m68c/m66/m67/m68a; m68b at `freeze-m68b-fixup3` and main | byte-equal; d8f6923, d536f04, df4d059 and 40470e6 touch no `tests/frozen` (control: the freeze commit shows 2 files) | `probes/m69b/frozen_exec_rv2.txt` |
| macOS py3.12, frozen + extra, `--cov-branch` | 1138 passed, 33 skipped; lowest file 93.02 % (`local/shuffle.py`); diff-cover 44 lines, 0 missing | `probes/m69b/gates_exec_rv2.txt` |
| Linux pool, CI test-htcondor line | 506 passed, 10 skipped; htcondor scope lowest 98.39 % (`backend.py`); diff-cover 110 lines, 0 missing; queue empty afterwards | same |
| test-dask equivalent (`.venv-m69b-dask`, the job's list, `.coveragerc-dask`, its `--include`) | 406 passed, 1 skipped; per-file gate 0; diff-cover 44 lines, 0 missing | same |
| test-hgg equivalent (`GRAPHED_HGG_REQUIRED=1`) | df4d059: 63 passed; 40470e6: 62 passed (the root-`--out` refusal row left with the revert) | same |
| ruff, ruff format, mypy (also `--platform win32`), sphinx -W, at df4d059 and 40470e6 | clean | same |
| integrity `scan_diff`, `upstream/main...40470e6` | 1 advisory `ci_config_modified` (test-dask adds two test files; no gate relaxed); control 2 | `probes/m69b/integrity_exec_rv2.txt` |

## Round-1 findings, closed

Mutants: `probes/m69b/mutants_exec_rv2.py`, outputs in `mutants_exec_rv2.{mac,pool,hgg,dask}.txt`. Each control run
(no mutation, same selections) passes.

| r1 | Fix | Mutant → killed by |
|---|---|---|
| B1 | test-dask runs `test_m69b_schedulable.py` and the new `test_m69b_dask_driver_check.py` | diff-cover 100 % locally. `driver-limit-ignored` and `driver-fit-strict` → the dask file |
| M1 | `HTCondorRunner.close()` → `stop_waiting()`; the wait raises `RuntimeError` naming the key | `runner-close-no-stop` and `closing-check-gone` → `test_close_ends_a_wait_for_a_slot_removing_the_job` ("close() still waits for the slot"). r1's self-starve probe in the pool: close returned (the whole process took 101 s, 90 s of it the watch), the run raised naming the key, the service history shows `NumJobStarts 0`, and the queue was empty (`probe_self_starve_exec_rv2.txt`) |
| M2 | `_as_whole` reads `TotalSlotDisk` as `Disk` | `disk-not-whole` → the totals unit row (mac); `disk-not-whole-live` → the classad2 row (pool). r1's probe: "match as shipped: True" (`probe_disk_match_exec_rv2.txt`) |
| m1 | `ServerTimes` formatter (kept by 40470e6) | `servertimes-gone` and `servertimes-ready-dropped` → the status-line row, at df4d059 and at 40470e6 |
| m2 | the empty-ads guard moved into `match_refusal` | `no-ads-guard-gone` → `test_a_pool_whose_collector_lists_no_slot_submits_and_waits` (`ValueError: max() iterable argument is empty`) |

## The implementer's probes

**(a) close() during spooling.** Probe: `probe_close_standin_exec_rv2.py`, a stand-in pool built on the extra
row's `Pool`. Output in `…standin_exec_rv2.txt`:
```
(a) spooling 5/16: logged-wait=True close-returned-after=0.28 s removes=2 secrets-left={} | RuntimeError: service 'a-spooling 5/16' (6029d36e-…) still waited for a slot when the runner closed: JobStatus=5, HoldReasonCode=16
(a) JobStatus 6: … close-returned-after=0.5 s … | RuntimeError: service 'a-JobStatus 6' (a3f6fe5d-…) ended before it announced: JobStatus=6; …
```
- Status 6 is not alive (`counts_as_alive`), so it raises at once, with or without close().
- A live 5/16 needs a spooled submit. The stand-in reaches the same `deadline is None` branch.

**(b) One runner, one plan running and one waiting.** Probe: `probe_close_pool_exec_rv2.py` in the pool.
- R has gated tasks and its server is up.
- W asks for 12 000 MiB: the slot holds that whole, but the pilots and R's server leave only 10 853 MiB free.

Output in `…pool_exec_rv2.txt`:
```
submitted R, direct W: close() 6.6s
  R (running, submitted): VALUE 1
  W (waiting, direct): ('raised', "RuntimeError: service 'web' (526d7469-…) ended before it announced: JobStatus=4, ExitCode=0; …")
direct R, submitted W, gate opens 60 s after close(): close() 30.5s
  R (running, direct): ('raised', 'RuntimeError: task graphed-fff20b7ea1dd-c54bb56f-leaf-0 unfinished when the HTCondor backend closed')
  W (waiting, submitted): RuntimeError: service 'web' (8b4b1c41-…) still waited for a slot when the runner closed: JobStatus=1
queue after: []
```
- Nothing hangs, and R's outcome is truthful in both arrangements.
- On the first line, W's job started once R released its room. It then exited when the backend closed. See exit
  item 3.

**Ctrl-C, for `run_lpc`'s form.** In `with htcondor_runner(...) as runner: runner.run(plan)`, nothing can call
close() while the run waits. Probe: `probe_sigint_exec_rv2.py` and `pool_sigint_exec_rv2.sh`, using r1's
self-starve sizes. Output:
```
wait logged after 20s; SIGINT to 9840
exit=0 3s after SIGINT (2s)
19.8s: KeyboardInterrupt
Total for all users: 0 jobs; …
62 graphed-service-5876b5da-354186341e24367c 3 0
```

**M1's design.**
- No frozen row conflicts with it:
  - The fixup3 rows (`…_fails_a_gone_held_or_late_job…[idle,spooling]`) answer idle, then 2, and never close during
    a wait.
  - The m69b busy-pool row closes only after the blocker leaves and the run completes.
  - All of these pass in the pool run.
- §5.2's text names no close behaviour, and the wait still sets no deadline. So the change does not contradict
  §5.2.
- The conflict is with the runners' documented `close()` contract. That is M4.

## Findings

### M4 — Major (the dispatcher decides): close() also ends waits that are only a fresh job's negotiation, so `submit()` followed by leaving the `with` block kills plans a free pool would run

- **Defect.**
  - `stop_waiting()` sets one flag before `_plans.close()`. Every wait with no deadline yet then raises at its
    next poll. A job has no deadline until an ad answers `JobStatus == 2`.
  - Every freshly submitted service job is idle, or 5/16 on a spooled site, until a negotiation cycle matches it.
    The flag cannot tell that job from one starved by the run's own pilots.
  - So a plan submitted shortly before close(), and every plan queued behind it, raises "still waited for a slot
    when the runner closed".
  - That breaks `design.rst` ("`close()`, or leaving the `with` block, waits for every submitted plan … the local
    pools and `SubmitRunner` on any backend"). `HTCondorRunner` is a `SubmitRunner`.
  - The new `htcondor.rst` sentence ("`runner.close()` ends the wait") now contradicts that paragraph.
  - Measured timings:
    - In the minicondor pool a job starts 5 s after `QDate`.
    - At the LPC, service jobs started 10–11 s after `QDate` (`lanes/htcondor/probes/site-lpc/m69-hgg.txt`).
    - The first poll comes `POLL_S` = 10 s after the wait begins.
- **Probe.** Pool, a free slot, `fut = runner.submit(one-server plan)`, then `runner.close()` at once.
  `POLL_S = 2` puts the first poll before minicondor's 5 s start, as 10 s does against the LPC's 10–11 s.
  Command: `pool_close_exec_rv2.sh <src> free [POLL_S]`. Output:
  ```
  src=/work/src (df4d059), POLL_S=10.0: close() 6.7s; plan: VALUE 1          history (45, QDate …478, start …483, NumJobStarts 1)
  src=/work/src (df4d059), POLL_S=2.0:  close() 3.5s; plan: RuntimeError: service 'web' (f1f95724-…) still waited for a slot when the runner closed: JobStatus=1
                                                                              history (47, QDate …494, start None, NumJobStarts 0)
  src=/work-d536 (d536f04), POLL_S=2.0: close() 6.9s; plan: VALUE 1          history (49, QDate …508, start …513, NumJobStarts 1)
  ```
  The stand-in shows the same at the logic level (`…standin_exec_rv2.txt` (c)): a job idle at its first poll and
  running 0.5 s later. With `stop_waiting()` it raises; without it, it returns `endpoint=tcp://127.0.0.1:10007`.
- **Closed when** both of these rows pass on one tree:
  1. A plan whose service job is idle at its first poll and runs at a later one, submitted and followed at once by
     `runner.close()`, returns the twin's value. On 40470e6 this row fails with "still waited for a slot when the
     runner closed".
  2. The existing `test_close_ends_a_wait_for_a_slot_removing_the_job` (a job idle forever): close() returns, the
     plan raises naming the key, and the job is removed.

  `design.rst` and `htcondor.rst` must then state the same `close()` contract.

  If the dispatcher rules the current semantics intended, M4 reduces to a docs repair: `design.rst`'s contract
  names the exception (a plan whose cluster service has not started when close() is called raises).

## Exit-round items (constraints for the next dispatch; no round needed)

1. **`HTCondorBackend.close()`'s own `stop_waiting()` call is never shown to change an outcome.** Mutant
   `backend-close-no-stop` survives `test_m69b_schedulable.py`.
   - `HTCondorRunner.close` sets the flag first.
   - `SubmitRunner.close` drains submitted plans before `backend.close()`.
   - The call matters only for a plain `SubmitRunner(HTCondorBackend(...))` with a direct `run()` waiting. Give it
     a row, or drop it.
2. **Name Ctrl-C as the way out in `htcondor.rst`.** In the documented "An H→γγ run" form (`with … runner.run`),
   nothing can call `close()` during the wait. The measured way out is Ctrl-C: 2–3 s, job and pilots removed. Say
   so beside "`runner.close()` ends the wait".
3. **When the backend closes under a direct `run()` whose service job started after close(), the run raises
   "ended before it announced: JobStatus=4".** That message points at `service.out`, not at the close. The path
   predates this delta (close() drains only submitted plans). Recorded only.
4. **`.graphed/m69b/attempts.md` has no iteration for 40470e6.**
5. **40470e6's message says graphed's writer "now" opens `root://`. It does not at the pinned `GRAPHED` 7e048bf.**
   M3's site evidence waits on that PR and the pin bump.
