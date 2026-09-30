**CLEAN**

# Review r25-B1: `plan-services.md` part B1, delta over the M41 fold (538fe62)

## Scope
- **Delta only** (owner 2026-09-29): `git diff cc09174 538fe62`, which touches `plan-services.md`, `condor_surface/RESULTS.md` Q-04, and `m68b-exit-items.md` "## decisions (round 19)".
- **Snapshot:** `reviews/plan-services-m68b-r25-b1-snapshot.md`. Its diff against the r24 snapshot is exactly the fold's `plan-services.md` hunks (L435–436, 455, 548–550, 571, 589, 745–746, 773).
- **Judged against:** M41-B1 in `plan-services-m68b-r24-b1.md`, and the five "## r24-B1 exit items".
- **Code:** executors 0e48380: `pyproject.toml`, `launch.py`, `ci.yml`, `tests/frozen/{m47,m67,m68a}`. Also the test-htcondor job log of CI run 36626770013 (job 109605661110).
- **Probe:** new `probes/m68b/probe_r25r_b1_history_mutants.{py,txt}`. Container `r25r-mini` (htcondor/mini:25.13.2-el9), now removed. No worktree was made.

## Design findings
None.

## Checked and holding
- **M41 is closed.** Run 2's bound is now `JobCurrentStartDate ≤ t` and `int(t) ≤ EnteredCurrentStatus`. Run 1's bound, `EnteredCurrentStatus < t`, is unchanged.
  - **Correct code passes.** The run-2 bound held in 7 of 7 sub-second trials in `probe_r24r_b1_history_seconds.txt`. In `probe_r25r_b1_history_mutants.txt`, "correct" (removed milliseconds after `t`) passes the int form and fails the float form.
  - **It still fails the mutant it guards.** In "removed ≥1 s before t", a run-2 service removed before its task's `t` fails with `E-int(t)=-1`.
  - **A leaked service is failed by run 1's bound.** In "leaked", a service kept past `t` fails `E<t`. The run-2 bound never guarded a leak, in either form: the leaked case passes both. A leak is caught by the row's polled "the run's end removes" clause and by "each run's end removes only its own".
  - **The resolution limit is history's, not the fold's.** A start after `t` or a removal before `t` that lands in `t`'s own second passes: "started after t" gives `S-int(t)=+0`, and "removed before t, same second" gives `E-int(t)=+0`. The start side was already like this before the fold. On the removal side, the float form caught the same-second case only by also failing correct code.
    - Neither case hides a wrong-service answer. The task can only GET an endpoint that `host_service` returned after run 2's service announced, and run 1's bound fails a run-1 service that is still alive at `t`.
- **Q-04 (RESULTS).** The truncation is measured: `frac(t)=0.79` with an immediate removal gives `ECS-int(t)=0` in r24r. The r19 and r24r probes are both cited.
- **The "+ margin" bounds.** A regex, `within (N s|a few seconds|lease_s)`, over `plan-services.md` matched seven bounds. The five 5 s bounds (L571, L589, and three in the L745 row) all carry "+ margin". The two "a few seconds" bounds are unchanged.
  - No leg became unable to fail. A reap without SIGKILL leaves the SIGTERM-ignoring child alive indefinitely, so it fails any finite margin.
  - L13 measures 5.0 s (orphaned at 3.6 s, exit at 8.6 s) and L14 5.0–5.1 s, matching the decision's figure.
- **Windows mypy (L548–550).** In 0e48380's `pyproject.toml`, `files` includes `tests`, `explicit_package_bases = true`, and the `tests.frozen.*` override disables `attr-defined`. The prek `mypy` hook runs with `pass_filenames: false`.
  - Existing precedent: `tests/frozen/m47/test_parsl_worker_death.py` already spells `signal.SIGKILL` bare.
- **`record_bindings` (missing-input leg).** At 0e48380, `CondorPilots.start` calls `_htcondor()` (`launch.py`, `start`). `record_bindings` is in `tests/frozen/m68a/services_harness.py`, beside `test_a_failed_spool_leaves_no_cluster_and_no_port`.
- **Sizes.** The prototype is 254 lines, so `announce.py` ~290 is plausible. Commit 1's figure moved from ~790 to ~950, which matches the announce.py change (+160). Commit 0 is ~750. Both are under 2k.
- **CI pool version.** Job 109605661110 at head `0e483803…` logs `$CondorVersion: 25.14.1 2026-09-23 … PackageID: 25.14.1-1+ubu24`. `ci.yml` installs HTCondor with `curl -fsSL https://get.htcondor.org | sudo /bin/bash -s -- --no-dry-run`, which is unpinned (exit item below).
