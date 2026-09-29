**CLEAN**

# Review r19-B2: plan-services.md §3.3 part B2, whole-part read

Snapshot: `plan/reviews/plan-services-m68b-r19-b2-snapshot.md`, copied from `plan/plan-services.md` before reading.

**Scope read:**
- §3.3's preamble and the B2 ladder rows (L415–431).
- The shared "HTCondor behaviour relied on" subsection (L432–453).
- B2 (L580–695), its frozen rows, "Fails on (B2)" and commits (L696–743).
- §6's m68b CI lines, §7's m68b figures, §8, §9's m68b risks and site checks.
- D3, D4 and D6.

**Checked against:**
- `condor_surface/NEEDS.md` and `RESULTS.md`, including its appended section with S-19 and D-08a.
- `probe_dag_service.txt`, `probe_surface_dagman_strict.txt`, `probe_r17_b2_sigretry.txt` and `probe_placeholder.txt`.
- §3.1 (fixed) and executors `c2298d7`: `driverless.py`, `driver.py`, `sites.py`, `launch.py` and `server.py`.
- The frozen tests under `tests/frozen/m67` and m66's `test_htcondor_sites.py`.

## Verdict
There are no design findings. Five exit items are appended under "## r19-B2 exit items" in `m68b-exit-items.md`.

## What was verified (no finding)
- **Matrix coverage.** Each HTCondor or DAGMan behaviour B2 relies on is a matrix row that matches or pins it:
  - `from_dag` with `UseDagDir`/`AddToEnv`: D-01, D-03, D-S.
  - A fresh dir, so there is no `force`: D-02, D-04.
  - SERVICE nodes removed at the DAG's end, with the outcome independent of them: D-05, D-06.
  - `RETRY driver 2 UNLESS-EXIT 3`, a new cluster per try, and a signal death with the placeholder retried: D-08, D-08a.
  - The node attributes and `RemoveReason` on the success path only: D-11.
  - Held read from a node query, never from `DAG_*`: D-07, D-09.
  - A missing output holds the node, hence the placeholder: S-15.
  - `periodic_remove` as hygiene only: L-05.
  - `SendCredential` kept on lxplus and never added on generic: X-04.
  - `history(match=3)` in recorded order: Q-03.

  No not-assumable value is relied on: strictness is overridden per DAG, and the outcome is the driver's exit. The AFS, credential, unspooled-DAG and N-02 premises are named owner site checks (1)–(2), and D-12 is marked "site check" in the matrix.
- **m67's frozen tests stay unmodified and green under the text:**
  - `root == "/"` short-circuits on Windows for `test_driverless_payload.py:147`.
  - `worker_ports` is still refused before `job_root` (the `m67-noports` case, L201; its `pilots="local"` control has no root check).
  - lxplus is refused naming `/afs` (L225–237).
  - `driver.sh` is read by name only (L106–107), and the driver runs via `-m` in `test_driver_entry.py`.
  - The plain job keeps `log_dir`, so the `driver.log` assertion at `test_driverless_live.py:90` holds.
  - The exit-3 leg (d) still gives `NumJobStarts == 1` and `ExitCode 3`, because the driver overwrites the placeholder.
  - `RunHandle`'s new trailing `dag=False` keeps `save`/`load` round-tripping.
- **Agreement with §3.1:**
  - The outer `ServiceSet` in `driver.main` (outside the `run` try, so it exits 1) reaches the in-job `host_service`. A timeout there is therefore retried by `RETRY`.
  - The inner set re-checks the name as leg 1.
  - The in-job `service_hosts == ("driver",)` means B1's attached binding rule never fires in a job.
  - Status identity is the announced one, which settles the m68a exit item for the m68b reviewer.
- **Announce protocol across driver retries.** The secret is written before `driver.url`, a new secret is minted per start, and a stale url's server answers 403, which is retried.
  - Two runs on one EP keep separate dirs, secrets and ports.
  - `TaskServer` binds all interfaces on the first free port (`server.py:85-110`), so a SERVICE node and the driver sharing `worker_ports` on one EP do not collide.
- **Tests discriminate.** The frozen rows would each fail on a wrong implementation:
  - the ids sorted by name, with `0web` sorting first and getting no id;
  - `driver` sorted after `a b`;
  - the lpc leg-2 control;
  - the spool=True no-retrieve control;
  - the highest-`ClusterId` recorder order;
  - a DAGMan 5, and a DAGMan 2 with a held driver;
  - no `DAG_*` attribute read.
- **CI, partition and figures.** B2's commits total about 550 + 500 + 190. With B1's this matches §7's m68b figures (about 1.5k of source, CI and docs, and about 1.3k of tests), and every commit stays under 2k. §6 lists `test_driverless_dag` among the no-bindings files.

## Exit items (one line each; full text in `m68b-exit-items.md`)
1. The header's file list omits where the `driver.sh` placeholder is written (`launch.py`'s shared `_stage`).
2. The mode of the DAG dir's `graphed-secret` temporary file is unstated. On generic's local filesystem it should be 0600 via `write_secret`, and §9's "ACL, not mode" holds only on AFS.
3. The `job_root` check is lexical (`abspath`), so a symlinked input resolving outside the root passes. Also, "DAGMan waits on for ever" is true of a held driver node, not of a SERVICE node, which `periodic_remove` removes.
4. The DAG's `env.tgz` link for an image-less GPU SERVICE node needs `files()` to run after `_stage`.
5. The live file's SIGKILL run does not say whether it takes the DAG path or the plain path.

## Cleanup
No containers or processes were started. The scratch directory `/tmp/claude-0/review-r19-b2/` holds only the lexical check (`jr/`, `jr_lexical.txt`).
