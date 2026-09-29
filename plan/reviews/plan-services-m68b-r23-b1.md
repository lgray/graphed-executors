**CLEAN**

# Review r23-B1: `plan-services.md` §3.3 part B1, delta round

## Scope
- **Snapshot:** `reviews/plan-services-m68b-r23-b1-snapshot.md` (plan at 505cc9f), diffed against the r22-b1 snapshot.
  The delta covers:
  - the B1 heading (`launch.py +1`);
  - the `service/` link-target citation;
  - `recipes.http_server`'s `root`;
  - the `ServiceJob` `submit()`/`stop()` paragraphs (the absolute `log_dir` from `CondorPilots.start`, and the reuse
    of `_submit`/`_remove`);
  - the B1 `test_cluster_service_job.py` row (the A/B-cwd leg, and the in-process L16/L17/missing-input legs moved
    out of the win32-skipped group);
  - "Fails on (B1)" and B1 commit 1.
- **Also read, because the delta references it:** the rest of the `ServiceJob` bullet, the shared subsection's L-07,
  L-09 and S-04 rows, D10, and B2's DAG bullet where it calls `files()`.
- **Evidence read:**
  - `probe_r23_b1_{logdir_abs,base_claims,l17_nonposix}`;
  - "## decisions (round 17)";
  - r22-B1's M40-B1 and its two exit items.
- **Code:** executors 0e48380 (`code-m68b-main`) for `launch.py`, `backend.py`, `driverless.py`, `driver.py`,
  `submit/{services,recipes}.py`, `ci.yml`, and the m66/m67/m68a tests.
- **My probes:** a scratch worktree of 0e48380 with the round-17 line applied as the decision spells it, plus
  container `r23r-mini` (htcondor/mini:25.13.2-el9). Both are removed.

No design findings. Two exit items are appended under "## r23-B1 exit items" in `m68b-exit-items.md`.

## Design findings
None.

## Checked and holding
- **M40-B1 is closed at its cause.** `start` stores `log_dir` absolute at the cwd its own writes use, and every
  later reader (the `ServiceJob` dir, `initialdir`, `executable`, the `env.tgz` link, the pilots' secret) spells from
  that stored value.
  - The row's A/B-cwd leg fails the unrepaired tree on every clause:
    - `initialdir` lies under B, not A;
    - `samefile` raises `FileNotFoundError`;
    - the job is held with code 13;
    - `stop()` unlinks B's secret.
  - With the line in place, the same leg passes (`probe_r23_b1_logdir_abs.txt` R, base vs start).
- **The line introduces no ordering defect.** `_refuse` already judged `os.path.abspath(log_dir)` at the same cwd, so
  the stored path is the one the sandbox check accepted (`probe_r23r_b1_start_order.txt`):
  - O1: a relative `log_dir` inside the sandbox root is accepted and stored as abspath-at-start;
  - O2: the same from outside the root is refused, and nothing is created;
  - O3: an image refusal creates no `mkdtemp` directory;
  - O4: `None` gives a fresh absolute directory under `_sandbox()`.

  mypy `--strict` passes on the planned spelling. The control is a `str` assignment to the attribute: the same
  invocation flags `launch.py:216` (scratch run).
- **No reader relies on `log_dir` staying relative:**
  - condor records a relative `initialdir` as absolute anyway, both `Iwd` unspooled and `SUBMIT_Iwd` spooled
    (`probe_r23r_b1_remove_reuse.txt` I);
  - `driverless.py` never calls `start`: 0 matches for `.start(`, against 1 each for `_stage(` and `_submit(`. m67's
    plain job, `RunHandle` and the saved-handle format therefore keep driverless's own absolute `out`;
  - the frozen and extra suites give the same results on the base and patched trees
    (`probe_r23_b1_logdir_abs.txt`).
- **Reusing `_submit`/`_remove` for `ServiceJob` behaves as the text says.** On a spooled profile, a
  ServiceJob-shaped job on its own `ExitStack` (`with` + `pop_all`) that exited 3 still sat in the queue at
  JobStatus 4 with `counts_as_alive` False. `stack.close()` then:
  - retrieved `service.out`/`.err` into `service-<key>/` (`SUBMIT_Iwd`, absolute under A/logs, although the job was
    submitted from cwd B);
  - removed the job.

  Control: the same job ended by a bare `act(Remove)` returns nothing, as L-07 says
  (`probe_r23r_b1_remove_reuse.txt` S/control). `_remove`'s `reason=` is dropped by condor (L-09), and no B1 text reads it.
- **No `stop()` can race `host_service`'s failure path.** m68a's `ServiceSet._managed` registers `release_service`
  only after `host_service` returns (0e48380 `submit/services.py` `_managed`). No second closer exists for a key
  `host_service` has not returned.
- **`recipes.http_server` at 0e48380:** `root="."` gives `inputs=()`, and any other `root` gives
  `--directory <root>` with `inputs=(root,)` (`recipes.py` `http_server`). The plan's text matches.
- **The in-process legs hold on every OS.** mypy `--platform win32` is an instrument-generated population. It finds
  8 Unix-only uses in the prototype:
  - `hard_reap:123,126` (`WNOHANG`, `SIGKILL`);
  - `start:156–165` (`pthread_sigmask`, `SIG_BLOCK`/`SIG_UNBLOCK`).

  The linux leg of the same invocation finds 0. None of the 8 is at module level, and none is on the L16 path
  (`on_sigterm`) or on L17's reaped path (`main` → `hard_reap(None)` returns first). This is
  `probe_r23r_b1_win32_mypy.txt` P, and it agrees with `probe_r23_b1_l17_nonposix.txt`. L17's mutant (a reaped pid
  signalled) fails the leg on POSIX, because the spy sees a call. It also fails on Windows, where the leg gets an
  `AttributeError` instead of exit 143.

## B2 small check
B2's text and rows stay true, and none of its lines changed in the delta:
- **The in-job driver.** Its `log_dir` is already absolute before the new line runs: `run["log_dir"]` is
  `str(out / "pilots")` with `out = Path(os.path.abspath(…))` (0e48380 `driverless.py`; m67's frozen
  `test_driverless_payload.py` asserts `isabs`). `start()`ed from another cwd, the line leaves it unchanged for
  `logs`, `a/../logs2` and `./logs3/` (`probe_r23r_b1_remove_reuse.txt` N).
- **Watch-mode `ServiceJob`s.** B2 uses only `.files`: B2's text has 0 `ServiceJob…submit()/stop()` matches (control:
  B1's text has 1), and "a driver job starts no `ServiceJob`". The `_submit`/`_remove` reuse therefore never reaches
  B2.
- **The `env.tgz` link.** `files()` now spells the link from `launcher.log_dir` without `os.path.abspath`. B2's launcher
  gets that value assigned absolute by driverless, which never calls `start`, so the value is unchanged. The row's
  `isfile(<run dir>/service-svc0/env.tgz)` stands.
- **Untouched:** `announce.py`'s watch mode and `launch._stage`.
