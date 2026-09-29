**CLEAN**

# Review r20-B1: `plan-services.md` §3.3 part B1 (attached cluster hosting), delta round

## Scope
- **Snapshot:** `reviews/plan-services-m68b-r20-b1-snapshot.md`, identical to the plan at review time.
- **Delta read:** `git diff --no-index --word-diff reviews/plan-services-m68b-r19-b1-snapshot.md plan-services.md`, limited to B1 and the minimal context around it:
  - L490–492: the env merge and `http_server`'s `root`;
  - L548–565: the orphan rule, the one bounded reap, and the SIGTERM handler;
  - L721–722: the B1 rows' new legs;
  - L735–736: "Fails on (B1)".
- **Checked against:**
  - `probes/m68b/announce_proto.py` as it stands now (`reap`, `on_sigterm`, `main`);
  - CPython `subprocess.Popen._wait` and `_internal_poll` (3.10 to 3.13);
  - §3.1 L239 (`http_server(name, *, root=".")`, whose argv has no root);
  - `probe_r19_b1_orphan_reap.txt`;
  - the r19-B1 exit items.
- **Re-run:** `probes/m68b/probe_announce_rules.py` (python 3.11) reproduces the committed text:
  - L1–L12 unchanged;
  - L13: exit 0 8.6 s after start, orphaned at 3.6 s, child gone;
  - L14: exit 143 5.0 s after the SIGTERM, child gone;
  - L15: `from-job from-recipe`.
- **New evidence** is in scratch at `/tmp/claude-0/review-r20-b1/r20b1_results.txt`, with the scripts beside it. No pool was needed, and no container was started.

There are no design findings. Two exit items are appended under "## r20-B1 exit items" in `m68b-exit-items.md`.

## M37-B1: closed at its cause
- **Every exit path now uses one bounded reap.** L556–558 names the orphan (403 or no 200), SIGTERM, the start deadline and a failed start. The prototype's `reap()` does terminate, then `wait(5)`, then `kill` and `wait()`, and it is the only reap. Measured:
  - L13: the orphan reap of a SIGTERM-ignoring child exits 0 within `lease_s` + 5 s.
  - L14: a SIGTERM inside that reap exits within 5.0 s.
  - The old prototype failed both (`probe_r19_b1_orphan_reap.txt` A and B).
- **The handler is sound on each path asked about.**
  - **Out of `Popen.wait(timeout)`:** the timeout branch takes the waitpid lock with `acquire(False)` only around a `WNOHANG` waitpid, inside `try/finally`, and sleeps outside it. A raise from the sleep or the waitpid leaves the lock free.
  - **Out of the blocking `wait()`:** that branch uses `with self._waitpid_lock`. `os.waitpid` gets EINTR, runs the handler (PEP 475), and the `with` releases the lock.
  - **After a waitpid that already reaped the child:** if the raise lands after the waitpid succeeded but before `_handle_exitstatus`, the next `poll()` gets ECHILD and sets `returncode = 0`. The reap then returns at once, with no zombie and no signal sent to a reused pid.
  - **Out of `urlopen` or a socket call, and out of `time.sleep`:** both are PEP 475 retries that run the handler and propagate the exception. `post`'s `except OSError` and `self_check`'s `except Exception` do not catch a `BaseException`.
  - **A second SIGTERM** finds `SIG_IGN`, so it cannot interrupt main's reap.
  - **Threads:** `announce.py` is single-threaded, and Python runs signal handlers only in the main thread, so the raise always lands in the frame the plan means.
- **Stress:** 240 random-time SIGTERMs to the real prototype, all with a SIGTERM-ignoring child:
  - 120 while serving, with `beat_s` 0.001, so most of the time is spent in `urlopen`, `poll` and `sleep`;
  - 120 inside the orphan reap.
  - All exited 143, the latest 5.13 s after the SIGTERM, with no hang (`r20b1_stress.txt`).
  - A double SIGTERM inside the orphan reap, and a SIGTERM during start, each exit 143 5.0 s after the first SIGTERM, with the child gone.
- **One residual window remains.** It is measured and bounded, so it is an exit item, not a finding.
  - In `Popen._internal_poll` and in `_wait`'s timeout loop, `if self._waitpid_lock.acquire(False):` precedes the `try`. A raise at the eval-breaker check right after `acquire` returns leaks the lock. Main's reap then blocks in `wait()` after `kill`, because SIGTERM is now ignored.
  - In a tight `poll()` loop with an external sender, this happened 1, 2, 0 and 2 times per 300 trials on 3.10, 3.11, 3.12 and 3.13, and each leak hung the reap (`r20b1_lockleak.py`). In the prototype's real loops (the 240 trials above) it never happened.
  - A SIGTERM between `Popen` returning and `CHILD[0] = child` leaves that child unreferenced.
  - Both cases are bounded in production. A SIGTERM from condor is always a removal (L-02), and `job_max_vacate_time = 30` then SIGKILLs the whole family. The bound is therefore 30 s instead of 5 s, at a rate too small to measure, and the frozen L14-type leg's flake rate is negligible. See exit item 1.
- **`sys.exit(143)` does not conflict with D6.** D6's codes are the driver's (1 or 3). Nothing reads a removed service job's `ExitCode`: `host_service` names `ExitCode` only for a job that left before announcing.

## Env merge and `http_server` inputs: holding
- **Env merge.** `{**os.environ, **env}` at L490 matches the prototype (`announce_proto.py:136`), and L15 shows both variables reach the child.
  - The new leg ("a child records a job variable and a recipe `env` variable and sees both") fails a replace, as "Fails on" now says.
  - The job's environment carries `KRB5CCNAME`/`X509_USER_PROXY` paths to the child. That was already true, and it is not the served cwd, whose rule (only declared inputs) is unchanged.
- **`http_server`'s inputs.** "`root` is not an input … the spec has `inputs=()`" agrees with §3.1 L239, whose argv carries no root. The live row now names `inputs=()` and the empty `service/`. This closes r19 exit item 4 without touching the fixed §3.1.
- **The other r19-B1 exit items are applied:** `service` is relative to `initialdir` in the row, and `probe_r19_b1_history_times.txt` is cited in the live row.

## Checked and holding (no finding)
- **Fails on (B1)**, the orphan-path reap: the new leg fails the old prototype (`probe_r19_b1_orphan_reap.txt` A).
- **Fails on (B1)**, "a SIGTERM handler that waits": no listed leg discriminates it. A variant with the bounded reap and a handler that waits still exits 5.0 s after the L14-leg SIGTERM (`r20b1_double_waiting.py`). This is a test-precision item, not a code change, and is exit item 2.
- **The coverage save:** `sys.exit(143)` from the top level runs `atexit`, and announce.py's handler replaces coverage's `sigterm = true` handler (as r19 checked).
