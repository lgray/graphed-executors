# m69b executors implementation review, round 7 (PR #44: delta 245d0c6..7e6e9c5 and what it references)

## Verdict: REJECT, on one BLOCKING finding (a hang)

- **D1, D2 and D3 are closed.** Each r6 probe, re-run at 7e6e9c5, now shows the fixed behaviour. The fit controls
  still complete. Neither case the coordinator named makes the sibling subtraction refuse a set that would have run.
- **BLOCKING: H1, the run hangs.** Two plans of one runner whose services start at the same time wait for each other
  with no end. On the pool, all four servers held the same states from 20 s to 150 s, and neither plan ended until
  `stop_waiting` ran. A two-line cut is measured below. The hang is not new in this delta; see H1.
- **NON-BLOCKING: N1 and N2.** Issue content is given for each below.
- **No leak.** Every probe leg ended with the pool's queue empty. The refused server was removed unrun
  (`NumJobStarts=0`).

| Gate | Result | Evidence |
|---|---|---|
| frozen tree vs `freeze-m69b-fixup2` (22df587); m68a/m68b tags (eb8691d) | byte-equal: 0 of 256 files differ. No commit in 245d0c6..7e6e9c5 touches `tests/frozen`. Control: 67ba8f2 differs in `test_service_order.py` | `probes/m69b/frozen_exec_rv7.txt` |
| Linux pool, CI test-htcondor line | 540 passed, 10 skipped (dask, parsl, coffea, Triton); the queue was empty afterwards. Per-file: lowest 98.80 % (`server.py`). diff-cover: 282 lines, 0 missing | `probes/m69b/gates_exec_rv7.txt` |
| macOS py3.12, frozen + extra, `--cov-branch` | 1163 passed, 42 skipped. Per-file: lowest 93.02 % (`local/shuffle.py`). diff-cover: 47 lines, 0 missing | same |
| ruff, ruff format, mypy (also win32), sphinx -W | clean | `probes/m69b/lint_integrity_exec_rv7.txt` |
| integrity `scan_diff` | `245d0c6..7e6e9c5`: 0 findings. `upstream/main...7e6e9c5` with the frozen paths left to the tag check: the known `ci_config_modified` only, the same as at 245d0c6 | same |

## The r6 findings at 7e6e9c5

- **D3 is closed** (`probe_sibling_room_exec_rv7.txt`).
  - sum-over (2 × 9000 MiB, one 15973 MiB slot): `web2` is refused at 20 s, "beside its server 'web1' (cluster 14) …
    the largest slot memory beside them is 6885 MiB". Its job, cluster 15, shows `NumJobStarts=0 JobStatus=3`, and
    the queue is empty.
  - fit (2 × 6000 MiB): both servers ran, on `slot1_1` and `slot1_2`, and the plan was done at 40 s.
- **D1 is closed** (`probe_failed_set_hold_exec_rv7.txt`). After plan B's refusal the pilot is `JobStatus=1`, not
  held, and plan A is done 6 s after the blocker leaves. The control behaves the same.
- **D2 is closed** (`probe_driverjob_toobig_exec_rv7.txt`). With `announced={'gpu': 'svc0'}` the probe now raises
  `ServiceUnavailable`, and its `legs["managed"]` names 200 MiB against `driver_memory_mb` 100.

## Can the sibling subtraction refuse a set that would have run?

Not in either case named. I could not build another such case.

- **A sibling running on another slot.** On a pool configured with two 7986 MiB partitionable slots (`99-two-slots`),
  `web1` ran on `slot1_1` and `web2` (6000 MiB) ran on `slot2_1`, and the plan was done at 30 s. `_less_claim` takes
  the sibling's share only from its own parent slot, `slot1@…`.
- **`_as_whole` with partitionable slots.** The fit leg above: on one partitionable slot, the second 6000 MiB server
  is admitted next to its sibling and runs.
- **Leak and hang paths in the delta.**
  - A refusal removes the refused job and unwinds the set, and the queue is empty.
  - A failing sibling query happens before the submit, so no job exists yet. The pilots it held are released when the
    phase ends (D1's cut).
  - The one hang found, H1, comes from the D3 design's exclusion of other plans' servers.

## BLOCKING

### H1 — two plans of one runner that start their services together wait for each other with no end

- **Defect.**
  - A set's later server is matched against the slot less its own set's servers ("never another plan's", plan
    e546dfe). The stated reason is that another plan's servers leave when that plan ends. That reason fails when the
    other plan's set is itself still starting.
  - On one 15973 MiB slot, plans x and y each have two 6000 MiB servers. `x1` and `y1` run. Then `x2` is admitted
    (15973 MiB less `x1`'s share leaves at least 6000) and `y2` is admitted the same way. Each waits, with no deadline, for room that the other
    plan's first server keeps until that plan's set completes.
  - This was a hang before the delta too: at 245d0c6 there was no sibling subtraction at all. My r6 review recommended
    the exclusion with that reason; the reason is wrong for overlapping starts.
  - **How it is reached:**
    - `runner.run` from two threads, or `runner.submit(x)` plus `runner.run(y)`;
    - `docs/htcondor.rst` itself covers overlapping phases ("once no other plan's services are starting").
- **Probe.** `probe_cross_plan_exec_rv7.py` (output in `probe_cross_plan_exec_rv7.txt`):
  ```
  serial (control)   28.5s plan x ended: value ('mem://rv7-serial-x/0',) · 44.0s plan y ended: value (...)
  concurrent         20.0s servers: 21: JobStatus=2, 22: JobStatus=2, 23: JobStatus=1, 24: JobStatus=1
                    150.2s servers: (unchanged) · after 150s: plans ended []
                    150.4s plan x ended: RuntimeError: service 'x2' (...) still waited for a slot when the runner closed
  ```
  The run ended only through `stop_waiting`, which is the Ctrl-C/exception path. The submit-plus-`run` variant goes
  through the same match; I did not run it separately.
- **Cut (measured).** An `HTCondorRunner` runs one plan at a time.
  - `run`, which `submit`'s driver thread also calls, takes a runner lock: `with self._one_run: return
    super().run(plan)`, with the lock created in `__init__` (`cut_one_run_exec_rv7.py`).
  - This is rung 2 of the ladder. `local/executors.py` already does it with `_run_lock`. design.rst states the rule
    ("An executor runs one plan at a time: a second `run()` from another thread waits until the first returns").
    `PlanQueue` already keeps submitted plans one at a time.
  - **On the pool:** the concurrent leg completes. Plan x is done at 31.8 s, plan y at 47.3 s, and the queue is
    empty.
  - **On macOS with the cut:** `tests/extra/m69b`, the frozen `test_service_order.py` and the frozen and extra
    m68a/m68b rows pass (`cut_one_run_suite_exec_rv7.txt`). The one failure in its first run was my copy missing
    `.coveragerc-htcondor`; that row passes once it is restored.
  - **The narrower cut does not work.** I measured serializing only the service-start phases
    (`cut_one_start_exec_rv7.py`). It moves the wait instead of ending it: `y`'s phase holds the pilot that `x`'s
    probe waits for, and `y1` waits for `x`'s room, still unchanged at 150 s.
  - With one plan at a time, the "once no other plan's services are starting" clause and the other-plans exclusion
    become moot. They can stay.
- **Closed when** a pool row passes in which two plans, each with two servers that fit the slot only one plan at a
  time, are run from two threads and both return values. The row fails at 7e6e9c5.

## NON-BLOCKING (issue content)

### N1 — the assert added to `match_refusal` silences the scan; it narrows no type

- **Defect.** `assert self.cluster is not None, "matched only once submitted"` is a true precondition:
  - the only caller, `_host_service`, calls `match_refusal` after `job.submit()`;
  - `submit` sets `cluster` or raises.
  
  But it narrows nothing mypy needs. Its effect is to silence the scan's `assertion_removed` finding against the
  owner-mandated removal of `assert self.launcher.cluster is not None, "claims are the submitted pilots'"`. The rule
  passes a removed assert whenever any added line in the same file contains `assert`.
- **Probe.** `probes/m69b/assert_exec_rv7.txt`:
  - With the assert deleted, `mypy services.py` reports "Success". The control, a `self.launcher.cluster[1]` in the
    same spot, gets `error: Value of type "tuple[str, int] | None" is not indexable`.
  - `scan_diff` of 245d0c6..7e6e9c5 reports 0 findings as committed, and 1 `assertion_removed` with the added line
    dropped.
- **Fix.** Drop the assert and record the advisory against the owner ruling. Keeping it is harmless at runtime.
- **Where.** `reviews/impl-m69b-exec-r7.md`; commit 1b3ba0f.

### N2 — the refusal message says the runner's pilots keep their slots "until the run ends"

- **Defect.** `match_refusal` says all holders keep their slots "until the run ends". The pilots keep theirs until
  the runner closes. htcondor.rst ("the pilots keep their slots until the runner closes, the servers until the run
  ends") and the earlier message ("until it closes") both say so.
- **Evidence.**
  - `grep -n "until the run ends" src/graphed_executors/htcondor_backend/services.py` finds the message f-string in
    `match_refusal`.
  - The `_host_service` docstring ends with the same phrase.
- **Fix.** Name each holder's own lifetime, or drop the clause.
- **Where.** `reviews/impl-m69b-exec-r7.md`; commit 1b3ba0f.

## Exit-round items for the H1 dispatch

1. Once runs are one at a time, htcondor.rst's "(by the same rule, once no other plan's services are starting)" and
   §5.2's matching clause describe a state that no longer occurs. Delete or keep them in the same commit as the cut;
   nothing depends on them.
