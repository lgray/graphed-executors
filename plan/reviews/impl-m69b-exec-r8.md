# m69b executors implementation review, round 8 (PR #44: delta 7e6e9c5..ce39e42 and what it references)

## Verdict: APPROVE, with zero BLOCKING findings (Windows is left to CI)

**r7's H1 is closed.** The r7 probe at ce39e42 has both concurrent plans end with their values: x at 31.1 s, y at
46.5 s. This held on the pool and in B1's overlap.

**Probes found no job left in the queue, no unended wait, and no cycle:**
- the set-start lock in each frozen row-8 Ctrl-C form, with a second plan waiting its turn;
- the lock held behind a busy slot;
- a held or deferred pilot needed inside the lock;
- B1's overlap of a queued `submit` and a direct `run`.

There is one NON-BLOCKING doc item, N1. r7's N1 (the assert) and N2 (the refusal message) are still open as filed.

| Gate | Result | Evidence |
|---|---|---|
| frozen tree vs `freeze-m69b-fixup2` (22df587); m68a/m68b tags (eb8691d) | byte-equal: 0 of 256 files differ. No commit in 7e6e9c5..ce39e42 touches `tests/frozen`. Control: 67ba8f2 differs in `test_service_order.py` | `probes/m69b/frozen_exec_rv8.txt` |
| Linux pool, CI test-htcondor line | 543 passed, 10 skipped (dask, parsl, coffea, Triton; B1's file is not among them). The queue was empty afterwards. Per-file: lowest 98.80 % (`server.py`). diff-cover: 292 lines, 0 missing | `probes/m69b/gates_exec_rv8.txt` |
| macOS py3.12, frozen + extra, `--cov-branch` | 1165 passed, 43 skipped. Per-file: lowest 93.02 % (`local/shuffle.py`). diff-cover: 48 lines, 0 missing | same |
| ruff, ruff format, mypy (also win32), sphinx -W | clean | `probes/m69b/lint_integrity_exec_rv8.txt` |
| integrity `scan_diff` | `7e6e9c5..ce39e42`: 0 findings. `upstream/main...ce39e42`, with the frozen paths left to the tag check: the known `ci_config_modified` only | same |

## The judged items

1. **r7's probe at ce39e42** (`probe_cross_plan_exec_rv8.txt`).
   - **Concurrent leg:**
     - `x1` and `x2` run.
     - Plan x ends at 31.1 s with its value.
     - `y1` runs and `y2` waits briefly.
     - Plan y ends at 46.5 s with its value.
     - The queue is empty afterwards.
   - **Serial control:** the plans end at 26.0 s and 36.5 s.
2. **Can the set-start lock cycle or hang?** No probe produced either.
   - **A set holding the lock while its server waits on a busy pool** (`probe_turn_behind_busy_exec_rv8.txt`).
     - Setup: plan a's 2000 MiB server waits behind a blocker that leaves 1200 MiB free. Plan b's 512 MiB server
       would fit, but plan b waits its turn: no b server is submitted for the 40 s the blocker runs.
     - After the blocker is removed at 48.1 s, a ends at 63.1 s and b at 68.9 s, both with values.
     - b's wait lasts exactly as long as a's wait for its slot, and ends with it. Ctrl-C ends both (item 2d).
   - **`_probe` needing a deferred or held pilot.**
     - `starting_services` (the phase) is nested inside `starting_service_set` and ends before `_probe`. So the
       phase end releases a hold or runs a recorded need, and `_probe`'s own `n_workers()` moves the pilots.
     - Phases now run one at a time, so `_starting` is 0 at the probe.
     - **Measured:**
       - In the turn probe, plan a is a first plan. Its probe inside the lock submitted the deferred pilot, and a
         ended.
       - The r6 failed-set probe at ce39e42 shows the pilot at `JobStatus=1` right after plan B's refusal, and plan A
         done 6 s after the blocker leaves (`probe_failed_set_hold_exec_rv8.txt`).
       - Frozen row 1, the hold and release around a later plan's probe, passes in the pool line.
   - **B1's overlap of a queued `submit` beside a direct `run`, both with services.** Frozen m68b
     `test_cluster_services_live.py` passes in the pool line and on its own (2 passed, with the 3 sibling-room rows).
     The queue is empty afterwards.
   - **Ctrl-C in each frozen row-8 form while a second plan waits its turn** (`probe_ctrl_c_turn_exec_rv8.py`, output
     in `.txt`).
     - Setup: plan A's server waits behind a blocker. Plan B calls `runner.run` on a non-daemon thread, so a wait that
       never ended would keep the child alive. Then SIGINT is sent.
     - Results:

       | form | child exits | B ends with |
       |---|---|---|
       | `run` | 0.3 s after SIGINT | "service 'b1' (…) not submitted: the runner is closing" (B's turn came during the close) |
       | `result` | 1.8 s after SIGINT | "a plan's services still waited for another plan's to start when the runner closed" |
       | `close` | 1.8 s after SIGINT | same as `result` |

     - In every form, the only service job is A's: `JobStatus=3 NumJobStarts=0`. No pilot was submitted, and the queue
       is empty.
3. **Leaks.** None found.
   - A set whose turn comes during a close is refused under `_lock` before it submits. The `run` form measured this:
     B's server was never submitted.
   - A set refused after its submit removes the job on the way out, through its `ExitStack`.
   - `close()` removes every recorded job, and waits for a pilot submit in flight (r6).
   - The set lock submits nothing of its own.
4. **Gates:** see the table above.

## NON-BLOCKING (issue content)

### N1 — the docs do not say how long a plan waits for its turn

- **Defect.** htcondor.rst ("One plan's services start at a time") does not say that a plan waiting its turn waits as
  long as the starting plan's own wait for a slot. That holds even when the waiting plan's servers would fit now.
- **Probe.** `probe_turn_behind_busy_exec_rv8.py`, output in `.txt`:
  ```
  8.1s plan b calls run · 18.1–48.1s servers: 18(2000 MiB): JobStatus=1 (no b server)
  48.1s blocker removed · 63.1s a ends · 68.9s plan b ended: value ('mem://rv8-turn-b/0',)
  ```
- **Fix.** Add one clause to that bullet: "a plan waiting its turn waits as long as the starting plan's servers wait
  for their slots".
- **Where.** `reviews/impl-m69b-exec-r8.md`; commit 3cdff78.

### r7's NON-BLOCKING items, unchanged at ce39e42

- **r7 N1:** `services.py`'s `assert self.cluster is not None, "matched only once submitted"`.
- **r7 N2:** the refusal message's "until the run ends" for the pilots.

Both are as filed in `reviews/impl-m69b-exec-r7.md` (commit 1b3ba0f).
