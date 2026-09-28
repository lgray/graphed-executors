# m68b redesign input held by the owner (journal excerpt, 2026-09-25)

- ~18:05Z D6 exit codes per owner ruling 2026-09-25 (plan-code StageError → 3, worker-loss KilledWorker StageError → 1, retried to JobMaxRetries); m68b DAG `UNLESS-EXIT 3` lines still hold. m68b redesign input (held): `DagmanProfile.dag_root` must read m67's `_SELF_SUBMIT_ROOT` (driverless.py:34, {"lxplus": "/afs"}) or vice versa; m67 fold adds a SiteProfile "jobs can submit" boolean (lpc False) — m68a/m68b build on it (name not yet in clone 9450e3d).
