**NOT CLEAN**

# Review r24-B1: `plan-services.md` §3.3 part B1, whole-part read

## Scope
- **Snapshot:** `reviews/plan-services-m68b-r24-b1-snapshot.md` (plan at db19852).
- **Read in full, as implementer and test author:**
  - the §3.3 preamble and its B1 ladder rows, and "HTCondor behaviour relied on (both parts)";
  - "#### B1 — attached cluster hosting";
  - the frozen harness paragraph, the three B1 rows, "Fails on (B1)" and the B1 commits;
  - D2, D3, D10, and the §3.1, §6, §7 and §9 lines B1 consumes.
- **Checked against:**
  - `condor_surface/{NEEDS,RESULTS}.md`, including S-19, D-08a and Q-04;
  - `announce_proto.py` and the probes the text cites;
  - reviews r12–r23-B1 and `m68b-exit-items.md`.
- **Code:** executors 0e48380 (`code-m68b-main`), checked for `launch.py`, `backend.py`, `server.py`, `sites.py`, `driver.py`, `driverless.py`, `submit/{services,recipes}.py`, `ci.yml`, `.coveragerc-htcondor`, `pyproject.toml` (mypy, coverage), `tests/frozen/m68a/**`, and the test-htcondor log of CI run 36626770013.
- **Probes:** new `probes/m68b/probe_r24r_b1_{history_seconds,engine_gap,job_prototype}.{py,txt}` and `probe_r24r_b1_rules_py39.txt`.
  - Container `r24r-mini` (htcondor/mini:25.13.2-el9), now removed.
  - A scratch worktree of 0e48380, with a macOS py3.12 venv holding the graphed d0ad16b wheel. Both removed.

One design finding (M41-B1). Five exit items are appended under "## r24-B1 exit items".

## Design findings

### M41-B1: the live row's `t ≤ EnteredCurrentStatus` compares a float with condor's truncated seconds, and fails on correct code
- **Where:** the B1 row `test_cluster_services_live.py` (a), plan L744: "run 2's (…) has `JobCurrentStartDate` ≤ `t` ≤ its `EnteredCurrentStatus`", with `t` = `time.time()` at run 2's task GET.
- **Why it changes a line the test author writes:**
  - Condor stamps `EnteredCurrentStatus` as whole seconds, truncated. The r19 probe already shows `EnteredCurrentStatus - int(t_rm) = 0`.
  - Run 2's service is removed at run 2's end. That is `release_service` → `_remove`'s query and act, milliseconds after the last task's GET. So `t` and the removal usually fall in the same second, and then `EnteredCurrentStatus = int(t) < t`.
  - Q-04's evidence (`probe_r19_b1_history_times.txt`) walked only a 2.4 s gap between `t` and the removal. The row applies it to a gap of milliseconds.
- **Measurement:**
  - `probe_r24r_b1_history_seconds.{py,txt}` (r24r-mini): a running job, `t = time.time()`, a gap `g`, then query + act Remove, then history.
    - With `g` < 1 s, the plan's predicate failed 6 of 7 trials (`g=0.0` 4/4, `g=0.3` 2/3).
    - `JobCurrentStartDate ≤ t` and `int(t) ≤ EnteredCurrentStatus` failed 0 of 7.
    - Control, `g=1.2`: both forms pass.
  - `probe_r24r_b1_engine_gap.{py,txt}` (m68a's engine, ThreadBackend, a driver-hosted `http_server`): the last task's GET to the service's release takes 0.1–0.2 ms in 10 of 10 runs. A condor run adds the pilot's `/result` POST and `_remove`'s query and act, milliseconds each.
  - In `probe_r24r_b1_job_prototype.txt` J2, a real ServiceJob started, announced, was GET'd and was removed within one second (`JobCurrentStartDate == EnteredCurrentStatus`).
- **Closed when:** the row compares at condor's resolution: `JobCurrentStartDate ≤ t` and `int(t) ≤ EnteredCurrentStatus` for run 2. Run 1's "removed before `t`" (`EnteredCurrentStatus < t`) stays: `int(R1) ≤ R1 < t` holds for correct code, and it is still the bound a leaked run-1 service fails.
- **Test:** the row's clause as repaired passes the sub-second trials of `probe_r24r_b1_history_seconds.txt` (7/7), where the current clause fails 6/7. A mutant that keeps run 1's service until the runner closes still fails run 1's bound, because its `EnteredCurrentStatus` then lies after `t`.

## Checked and holding
- **The current prototype in a real ServiceJob.** It had not run on the pool since r8 (`probe_service_job.txt`), before `service/`, the secret unlink, the sigmask and the pid reap. `probe_r24r_b1_job_prototype.txt` runs it with B1's keys (absolute `service.sh`, `arguments=service.json`, relative inputs, `job_max_vacate_time=30`):
  - **J1:** the child runs in `service/`. `GET /` returns 200, and `/service.json`, `/graphed-secret` and `/announce.py` return 404. The child saw no `../graphed-secret`, and its SigBlk excludes SIGTERM. With the receiver stopped, the orphan rule exits 0 and the job leaves the queue in 5.2 s.
  - **J2:** a removal leaves the queue in 0.3 s, the child is gone, and history has JobStatus 3.
  - **J3:** with a SIGTERM-ignoring child, the job leaves in 5.1 s, well inside the 30 s vacate time.
  - **J4:** a 403 gives exit 0.
- **`probe_announce_rules.py` on 3.9.25:** L1–L17 reproduce in r24r-mini (`probe_r24r_b1_rules_py39.txt`). The L-lines match the committed output except for L14's time, 5.1 s against 5.0 s.
- **Surface reliance.** Each condor behaviour B1 relies on maps to a matching NEEDS/RESULTS row or to the "not assumed" table: S-03/04/05/08/09/12/15/18/19, L-02/05/07/09, Q-04, X-01/04/05/08, N-02. N-02 is a named site check.
- **Code premises at 0e48380:**
  - `write_secret` writes hex, as the prototype reads it.
  - `_submit` registers the removal before spool, and `_remove` retrieves status 4 before `act`.
  - `counts_as_alive` exempts code 16.
  - `RunHandle._poll` uses `history(match=1)`.
  - `recipes.http_server`'s `root` is as the plan states.
  - `ServiceSet._managed` registers `release_service` only after `host_service` returns.
  - `.coveragerc-htcondor` sources include `graphed_executors.htcondor_backend`. The main matrix omits `*/htcondor_backend/*`, so `announce.py`'s gate is test-htcondor's alone.
  - m68a's frozen packaging pins stay true when m68b adds `tests/frozen/m68b` to test-htcondor (`re.search(r"tests/frozen/m68a\b")`) and adds files under `htcondor_backend/` (exit item E2 already binds the name search).
- **CI pool capacity** (test-htcondor log, run 36626770013): one slot with 4 CPUs and 15989 MB. Two pilots plus the two service clusters of the overlapping-runs leg fit, at 1 CPU and 2048 MB each.
- **Commit sizes:** B1 commit 0 is ~750 lines and commit 1 ~790, both under 2k.

## B2 small check
B2's text and rows still hold:
- **The shared changes to `announce.py`.** The `sys.platform` guards in `start` and `hard_reap` are no-ops on Linux, where watch mode runs. L1–L17 on 3.9.25 and J1–J4 in a real job exercise that shared `start` and reap.
- **§2's `run.json` line.** It now says m68a writes `endpoints` and m68b adds `announce_only` and `dag_dir`. At 0e48380, `driverless.py` writes only `endpoints`, and m68a's hand-built run dict (`test_services_sites.py`) has `endpoints` and no `announce_only`. So B2's "`run.get("announce_only") or {}` … lack them" and its "run dict lacking both new keys" row agree.
- **The docs exit table.** In 0e48380 `docs/htcondor.rst`, 279–298 spans the table's lead-in sentence through its last row.
