**CLEAN**

# Review r20-B2 of plan-services.md (m68b part B2): delta check

- Snapshot: `plan/reviews/plan-services-m68b-r20-b2-snapshot.md`.
- Delta: `git diff --no-index --word-diff plan/reviews/plan-services-m68b-r19-b2-snapshot.md plan/plan-services.md`.
- Scope: the r19-B2 exit items as applied, plus the B1 changes the SERVICE node inherits: the one bounded reap, the SIGTERM handler that raises and exits 143, the recipe `env` laid over the job's, and `http_server` with `inputs=()`.
- Code: graphed-executors `c2298d7`.

## Design findings
There are none. The next number stays M46-B2.

## What was checked

### 1. The driver-only `_stage` argument (L590 header, L672–674)
- `_stage` has two callers: `launch.py:203` (`pilot.sh`) and `driverless.py:186` (`driver.sh`). No test under `tests/` calls `_stage` or overrides it (grep).
- m66 reads `pilot.sh` by name only (`test_htcondor_sites.py:149`). m67 reads `driver.sh` by name only (`test_driverless_payload.py:107`), and asserts only that `driver.log` exists (`test_driverless_live.py:90`, `test_driver_entry.py:112,144`).
- Prototype, in a scratch copy only: I added a keyword-only `placeholder: bytes | None = None` to `_stage` and passed it from `driverless.py` alone. It writes a `printf` of octal escapes to `result.pkl` and appends one line to `driver.log` before the existing `tar`/`exec` lines.
  - `tests/frozen/m66` and `tests/frozen/m67` gave the same result before and after the patch: all passed, with 2 skips (the live pool tests) each time.
  - `pilot.sh` came out byte-identical.
  - `driver.sh` run through `sh` with a missing module exits 1, leaves a `result.pkl` that loads as `(False, RuntimeError(...))`, and leaves the `driver.log` line.
- The plan's "`launch.py` +10" and "`pilot.sh` is unchanged" hold.

### 2. `files()` after `_stage` (L608)
- `submit_driverless` sets `launcher.log_dir = out` and then calls `_stage(out, …)` (`driverless.py:183–186`). In the DAG, `out` is the run dir, so the launcher's `env.tgz` is the run dir's.
- lxplus has `ship_env=True` (`sites.py:78`), so the new `os.path.isfile(<run dir>/service-svc0/env.tgz)` leg is meaningful with the fake venv the row already provides.

### 3. The 0600 temporary file and `os.replace` (L646–647), against the SERVICE node's reads
- `write_secret` does `touch(0o600)`, then `chmod`, then writes the hex text (`launch.py:52–55`). That is the format B1's watch loop reads.
- The SERVICE node's job and the driver's job run under the same owner, so 0600 does not block the read.
  - On AFS the owner mode bits allow `rw` and the ACL governs, which is what §9 now says.
  - On generic, 0600 closes the umask gap.
- A stale temporary file left by a killed driver try is re-chmodded and truncated by `write_secret`, and `os.replace` over the previous try's 0600 file is atomic.
- The watch loop already retries an absent or torn read (B1 L556–558).
- No new failure mode.

### 4. The lexical `job_root` statement (L613–617)
- This is the consequence r19 asked the plan to state.
- A held driver node stays `held`, which is D-09.
- A held SERVICE node is removed by `periodic_remove`, and the DAG then proceeds on the driver's outcome. `probe_r13_dag_held_service.txt`'s `_prm` variant shows this: the node is removed with the PeriodicRemove reason, and the DAGMan run ends with `ExitCode` 0. The driver then times out once per try.
- This is accurate. It is a stated limitation, not a new decision.

### 5. What B2 inherits from B1
- DAGMan's removal of the SERVICE node now ends `announce.py` with `sys.exit(143)` through the one reap.
- B2 reads neither the SERVICE node's exit nor DAGMan's `ExitCode`, so nothing in B2's status mapping changes.
- `http_server` with `inputs=()` in the live DAG leg serves an empty `service/`, and a GET still returns a body the plan can carry.
- The recipe `env` laid over the job's passes `KRB5CCNAME` to a watch-mode child. The cache file stays outside the served cwd, which is the property B2 claims.

## Exit items
Appended to `plan/reviews/m68b-exit-items.md` under "## r20-B2 exit items": three wording and test-precision items.

## Evidence
- Scratch: `/tmp/claude-0/review-r20-b2/`. It holds the patched copy of the code, a venv, and the pytest runs described above. Nothing was committed, and no docker was used.
