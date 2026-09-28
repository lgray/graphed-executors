# m68b redesign input held by the owner (journal excerpt, 2026-09-25)

- ~18:05Z D6 exit codes per owner ruling 2026-09-25 (plan-code StageError → 3, worker-loss KilledWorker StageError → 1, retried to JobMaxRetries); m68b DAG `UNLESS-EXIT 3` lines still hold. m68b redesign input (held): `DagmanProfile.dag_root` must read m67's `_SELF_SUBMIT_ROOT` (driverless.py:34, {"lxplus": "/afs"}) or vice versa; m67 fold adds a SiteProfile "jobs can submit" boolean (lpc False) — m68a/m68b build on it (name not yet in clone 9450e3d).

## Where these names stand on main (c2298d7)
- m67 merged `SiteProfile.jobs_can_submit` (`src/graphed_executors/htcondor_backend/sites.py`; lpc = False) and `_SELF_SUBMIT_ROOT = {"lxplus": "/afs"}` (`htcondor_backend/driverless.py`).
- The held input: m68b's planned `DagmanProfile.dag_root` and m67's `_SELF_SUBMIT_ROOT` answer the same per-site question, where a job-submitted DAG's files must live. Keep one source for it, on `SiteProfile` beside `jobs_can_submit`, and have both read it.
