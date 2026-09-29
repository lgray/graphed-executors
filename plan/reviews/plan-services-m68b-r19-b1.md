**NOT CLEAN**

# Review r19-B1: `plan-services.md` §3.3 part B1 (attached cluster hosting), whole-part read

## Scope
- **Snapshot:** `reviews/plan-services-m68b-r19-b1-snapshot.md`, identical to the plan at review time.
- **Read in full:**
  - the §3.3 preamble and its B1 ladder rows (L415–431);
  - the shared subsection "HTCondor behaviour relied on" (L432–453);
  - "#### B1 — attached cluster hosting" (L454–579);
  - the B1 frozen rows, the harness, "Fails on (B1)" and the B1 commits (L696–743);
  - D2, D3 and D10 (L15–122);
  - §3.1's `ServiceSet`, `recipes` and `htcondor_backend/` bullets where B1 consumes them.
- **Checked against:**
  - `condor_surface/NEEDS.md` and `RESULTS.md`, including its appended section;
  - `probes/m68b/announce_proto.py`;
  - graphed-executors `c2298d7`: `htcondor_backend/{launch,server,backend,sites}.py`, `.github/workflows/ci.yml` (`test-htcondor`), `.coveragerc-htcondor`, `submit/engine.py:299` (the `run_nonce` is hex).
- **New evidence:**
  - `probes/m68b/probe_r19_b1_orphan_reap.{py,txt}`: run locally, no pool needed.
  - `probes/m68b/probe_r19_b1_history_times.{py,txt}`: run on htcondor/mini 25.13.2 in container `r19b1-mini`, which has been removed.

There is one design finding, M37-B1. Four exit items are appended under "## r19-B1 exit items" in `m68b-exit-items.md`.

## Design findings

### M37-B1: the orphan reap is unbounded, so a driver that died leaves a SIGTERM-slow service holding its slot for ever
- **Where:**
  - L547–550, the attached orphan rule: "it terminates the child and exits 0, so a driver that died … frees the slot".
  - L553–555: only the SIGTERM path is bounded ("waits for it at most 5 s, then kills it").
  - The B1 row (L707) tests the bound only on the SIGTERM path ("a child that ignores SIGTERM is killed within 5 s of `announce.py`'s SIGTERM").
  - Its orphan legs ("`url` on a closed port … reaps the ready child and exits 0", 403, server shut down) all use `http.server`, which exits on SIGTERM at once.
  - "Fails on (B1)" (L721) lists "a reap that waits on a SIGTERM-ignoring child", but no leg can fail it on the orphan path.
- **Why it changes code:**
  - The orphan path is the one case where nothing outside the job will ever end it. The driver that would `act(Remove)` is dead, the job has no `periodic_remove`, and `job_max_vacate_time` applies only to an eviction or removal.
  - So the reap there must be bounded by `announce.py` itself.
  - The cited prototype (`announce_proto.py:183–186`) does `child.terminate(); child.wait()` with no bound. An implementation that follows it passes every B1 leg.
  - The same prototype's SIGTERM handler calls `child.wait(5)`, then `kill()`, then `child.wait()`. If SIGTERM arrives while the main thread is inside a `Popen.wait`, the handler blocks for good on `Popen`'s non-reentrant waitpid lock, which the interrupted wait still holds.
  - That can happen in normal release. `release_service` forgets the key first, so a beat can take 403 and start the orphan reap just as `stop()`'s `act(Remove)` delivers SIGTERM. The job then lingers until the 30 s `job_max_vacate_time` SIGKILL, instead of leaving at once.
  - The implementer therefore has to write the reap as one bounded routine used by every exit path: terminate, then at most 5 s, then kill. It must also not nest a `Popen.wait` inside the signal handler. Two ways to do that:
    - the handler only sets a flag or raises into the main loop, which reaps;
    - or the handler polls with `os.waitpid(pid, WNOHANG)`.
- **Measurement:** `probes/m68b/probe_r19_b1_orphan_reap.txt`. The prototype runs with the url on a closed port, `lease_s=3`, and a child that ignores SIGTERM.
  - **A:** 12 s after "orphaned", `announce.py` is still running and the child is alive (state S).
  - **B:** 10 s after a SIGTERM to `announce.py`, the child has been SIGKILLed (a zombie, Z), but `announce.py` has not exited. An earlier ad-hoc run of the same setup showed it waiting in `futex_do_wait` indefinitely.
  - **Positive control:** the probe's "orphaned" line fires after 3.6 s, so the orphan path was entered and the hang is inside its reap, not before it.
  - `probe_announce_rules.txt` L4–L6 exit 0 only because their child is `http.server`, which exits on SIGTERM.
- **Closed when:**
  - L547–550 says the orphan path reaps as SIGTERM does (terminate, at most 5 s, kill, exit 0).
  - L553–555 says the SIGTERM handler does not re-enter a wait that the main thread may be holding.
  - The prototype is fixed, or the plan stops citing it for the reap.
- **Test:** add to `test_cluster_service_job.py`'s subprocess legs, with `lease_s` shortened:
  1. A SIGTERM-ignoring child with `url` on a closed port: `announce.py` exits 0 within `lease_s` + 5 s + margin, and the child's pid is gone.
  2. The same, with SIGTERM sent to `announce.py` about 1 s after its "orphaned" log line (inside the reap): it exits within 5 s + margin.

  The unpatched prototype fails both legs (probe A and B).

## Checked and holding (no finding)
- **Surface reliance.** Every HTCondor behaviour B1 relies on maps to a matrix row that matches it, or is covered by the "not assumed" table:
  - **Submit description:** S-01 (absolute executable), S-03/S-04 (`initialdir` made first; `service.out` not assumed), S-05 (`sys.executable` never used), S-08/S-09/S-19 (mirror, relative entries, `env.tgz` link), S-12 (`.machine.ad` inside `service/`), S-18 (a 2-GPU request idles).
  - **Lifecycle:** L-01/Q-03 (history after leaving), L-02 (family SIGTERM, `job_max_vacate_time=30`), L-07 (spooled retrieve before remove), L-08, L-09 (no reason read back).
  - **Scratch and network:** X-01/X-02/X-08 (paths from the cwd), X-04 (attached drops `SendCredential`), N-01 and N-02 (site check).
  - **One test-only reliance was unpinned:** the live witness's history attributes. It is now measured (exit item 2).
- **m66 code seams:**
  - `CondorPilots._submit` submits and spools in one call (`launch.py:226-230`). The pre-spool registration comes from m68a's hook (§3.1 L311; exit item at `m68b-exit-items.md:36`).
  - `CLOSE_WAIT_S = 2*POLL_S` is 20 s (`launch.py:31`).
  - `counts_as_alive` treats a held job with code 16 as alive (`sites.py:335`).
  - The task server verifies the signature before `pickle.loads` today (`server.py:575-586`), so routing `/announce` first is a real change.
  - `LEASE_S`/`POLL_S` are read at call time (`server.py:337-340`).
- **Keys and wire:**
  - `key = f"{run_nonce}-{token_hex(8)}"` carries no whitespace (`engine.py:299`), so the three-field body parses.
  - `beat_s` (`POLL_S`, 10 s) is below `lease_s` (30 s).
  - `job_max_vacate_time=30` bounds removal below any larger `MachineMaxVacateTime`, since the job's shorter value wins.
- **CI:**
  - `test-htcondor` is a personal HTCondor with `MOUNT_UNDER_SCRATCH` empty. `sigterm = true` in `.coveragerc-htcondor` installs coverage's handler at process start, and `announce.py`'s own handler replaces it, so its `sys.exit` saves the data.
  - macOS (`ps -o args=`) and Linux run the subprocess legs, and Windows skips them.
- **Commit sizes:** B1 commit 0 is ~750 lines and commit 1 ~790, both within 2k.
