**NOT CLEAN**

# Review r8 — `plan-services.md` §3.3 executors m68b, whole unit

Scope: §3.3, plus the lines of the §3 preamble, D1–D10, §6, §7, §8 and §9 that bind m68b. §3.1 (m68a) is taken as
given. Snapshot: `reviews/plan-services-m68b-r8-snapshot.md`. Code: graphed-executors main `c2298d7`.

Probes:
- Re-run on `htcondor/mini` (25.13.2): `probe_service_job` (legs A–D) and `probe_dag_service` (R, X). Both
  reproduce their `.txt`. The only difference is D's `TotalGPUs [0]`, because this pool had no `sim_gpu.config`.
- New for this review, in `probes/m68b/`: `probe_r8_paths.{py,txt}`, `probe_r8_fromdag_force.txt` and
  `probe_r8_announce_loop.txt`. The last one comes from running `announce_proto.py` locally.
- The container is removed.

## r7 items
- **M11: closed.**
  - D10 now reads `host_service(spec, scope) -> (endpoint, identity, key)`.
  - `wait_announce` returns `(host:port, identity)`. The DAG in-job `host_service` returns the announced identity.
  - `test_announce_route` asserts the returned pair, and `test_driverless_dag` asserts the logged identity.
- **M12: closed.**
  - `announce.py` scans `service.json.ports` (`= profile.worker_ports`) in the job.
  - `test_cluster_service_job` pins `ports` and has a leg where the first port is held.
  - `probe_service_job.txt` A announces 10002, reproduced.
- **M13: closed.**
  - `host_service` removes the job and raises `TimeoutError` naming the timeout and `JobStatus`.
  - Live (b) runs `gpus=2`, `timeout_s=20` and checks for an empty queue. The pool has one simulated GPU
    (`probe_sim_gpu.txt` G2).
- **M14: closed.**
  - Each driver start writes `graphed-secret` and then `driver.url` by `os.replace`.
  - DAG-mode `announce.py` re-announces whenever the pair changes, which covers `probe_dag_service` R's same-url
    rebind.
  - `test_cluster_service_job` has a DAG-mode leg for this, including the secret-only change.
- **M15: closed.** Live (a) and (b) run on a generic copy with `service_ports=None`. The DAG leg (c) uses a GPU
  recipe, which a driver job cannot host.
- **M16: closed.** `SiteProfile.job_root` has generic `"/"` and is the one source, as the owner input asked
  (`notes-m68b.md`). The Windows `"/"` rule is measured (`probe_code_premises.txt` W).
- **M17: closed.** The lxplus run uses `model_repository="models"`. `probe_service_job.txt` C is reproduced.
- **X1: applied** (D10 L115-116).
- **X2: applied** (L472, and the `test_announce_route` row).
- **X3: applied** (§7 L756).
- **X4: applied** (§9 L775-778).

## Design findings

**M18 · §3.3 L438 `ServiceJob` keys `executable=service.sh` · a relative executable resolves against the
submitter's cwd, not `initialdir`.**
- The measurement, positive and negative:
  - `probe_r8_paths.txt` E submits with `executable=svc.sh` and `initialdir=<d>` from another cwd. The job is held
    with `Cmd: /home/submituser/svc.sh` and "reading from file /home/submituser/svc.sh: No such file or directory".
  - m66 already knows this. `launch.py:204-205` has "a relative executable resolves against our cwd, not
    initialdir" and passes `str(script)`, and m67 does the same (`driverless.py:192`).
- Why it changes code:
  - `test_cluster_service_job` pins the `ServiceJob` keys. A test author who pins `executable == "service.sh"`
    makes the live test impossible: the job is held, and `host_service` raises `RuntimeError`.
  - The DAG `<name>.sub` inherits the same key.
- Closed when: the keys read `executable=<initialdir>/service.sh` (absolute), as `CondorPilots.start` does.
- Test: `test_cluster_service_job` asserts `os.path.isabs(desc["executable"])` and that it names `service.sh` in
  the fresh `service-<key>/` dir. Live (a) is the witness that the job runs.

**M19 · §3.3 L499-500 `run.dag` = `JOB driver driver.sub` / `SERVICE <name> <name>.sub`, submitted as
`Submit.from_dag(<run.dag>, {})` · the DAG runs only when the submitting process's cwd is the DAG dir, and
`from_dag` refuses a `log_dir` that a previous DAG used.**
- The measurement:
  - `probe_dag_service.py` itself calls `os.chdir(d)` before `from_dag`, which the plan does not carry.
  - `probe_r8_paths.txt` D1 submits the same shape from `~`. DAGMan exits 1 with zero nodes and logs "ERROR:
    submit attempt failed, errno=2 No such file or directory".
  - Positive controls: D2 (`{"usedagdir": True}`) and D3 (an absolute node `.sub` path) each run the node, and
    DAGMan exits 0.
  - `probe_r8_fromdag_force.txt`: `from_dag(..., {})` on a dir that already holds `run.dag.condor.sub`,
    `.lib.out` and the other DAGMan files raises `HTCondorException: Unable to write condor_dagman output
    files`. `{"force": True}` is accepted and adds `-force`.
  - m67 lets a user reuse `log_dir` (`driverless.py:180-183`, `exist_ok=True`).
- Why it changes code:
  - Live leg (c) runs from pytest's cwd, so it fails as the plan is written.
  - The only in-library fix left to the implementer would be `os.chdir`, which is process-global and not
    thread-safe.
  - `data/from_dag-generic.txt` (the fixture of the stock description) changes with the chosen options.
- Closed when the plan fixes both of these:
  - Either absolute node-submit paths in `run.dag` or `{"usedagdir": True}`.
  - For an already-used `log_dir`, either `{"force": True}` or a refusal before any bindings call naming the stale
    `run.dag.*` files.
- Tests:
  - `test_driverless_dag` asserts the chosen `run.dag` text and `from_dag` options, and regenerates the fixture
    under those options.
  - Live (c) runs with a cwd other than `log_dir`, using `monkeypatch.chdir(tmp_path)`.
  - A second `submit_driverless` into the same `log_dir` either submits (with `force`) or is refused with the
    recorder empty.

**M20 · §3.3 L496/L500-501 DAG refusal and "never spooled" · transferred inputs outside `job_root` are not
refused.**
- The measurement:
  - `driverless.py:187` puts `*launcher.user_modules` (absolute, anywhere) into `transfer_input_files`.
  - §3.3 L440 makes recipe `inputs` absolute against the driver's cwd.
  - The DAG check tests only `log_dir` (L496).
  - The plan's own premise is that the schedd reads `job_root` directly (L427, L501). That is why lxplus is
    `spool=True` (`sites.py` lxplus row).
- Why it changes code:
  - On lxplus, a user module or a `models` dir outside `/afs` (for example a cwd in `/tmp` or `/eos`) makes the
    unspooled driver or SERVICE node fail input transfer and go held.
  - DAGMan waits on a held node, so `RunHandle.wait()` never ends. This is a "dropped input" from the Fails-on
    list, reached through a path the refusal step does not see.
- Closed when, in DAG mode, `submit_driverless` refuses before any bindings call every `user_modules` path and
  every `announce_only` recipe input that `job_root` does not hold, naming the path and `job_root`. The
  alternative is to copy those paths into the DAG dir; the plan picks one.
- Test: `test_driverless_dag` builds a profile copy with `job_root=<tmp>/root` and `log_dir` under it. A user
  module outside it is refused naming `job_root`, with the recorder empty. The control, the same module under the
  root, submits.

**M21 · §3.3 L462-465 attached `announce.py` · no orphan rule before the first 200.**
- The measurement:
  - The text is "POSTs … retried each second until 200. Attached mode *then* re-POSTs … a 403 … or no answer for
    `lease_s` … is an orphaned service". Nothing bounds the loop before the first 200.
  - Positive control: the pilot's orphan clock starts at construction (`pilot.py:32`, `last_ok =
    time.monotonic()`), and `/hello` itself is subject to it (`pilot.py:50-53`, `87`).
- Why it changes code: suppose the driver dies hard (SIGKILL, or the login session is lost) while a GPU
  `ServiceJob` is still idle. The ExitStack never runs. The job starts later, the child comes up, and `announce.py`
  retries a dead URL, or gets 403 from a new server, until the walltime. It holds a GPU all that time. This is the
  M13 leak again, through a window the plan's lease rule does not cover.
- Closed when the lease clock starts when the child is ready. Having no 200 within `lease_s`, or a 403 on any
  POST, terminates the child and exits 0, as for a pilot.
- Test: `test_cluster_service_job` runs attached mode with `url` pointing at a closed port and `lease_s`
  shortened. `announce.py` reaps the child and exits 0.

**M22 · §3.3 L455-458 `announce.py` port loop · what ends it is unspecified.**
- The measurement (`probe_r8_announce_loop.txt`):
  - The prototype restarts a child that exits at once on every port: 101 starts, 51 s, then exit 3.
  - It gives a live but never-ready child a full `timeout_s` on each port: 3 ports × 2 s = 6.1 s. At the default
    range and `timeout_s=600`, that is 101 × 600 s.
  - The plan says "poll … until `timeout_s`" inside "for each port", and "a child that exits … moves to the next
    port". It does not say what happens to an alive, not-ready child at the deadline, or whether `timeout_s` is
    per port or total.
- Why it changes code:
  - A Triton that exits on a bad model is restarted up to 101 times, each start being a GPU init. `host_service`
    then reports `TimeoutError` instead of the child's exit code.
  - The frozen legs "an `http:` spec on a server answering 200 `application/grpc` never announces and exits 3",
    "a child that exits at once → exit 3" and live (b) "`RuntimeError` … before `timeout_s`" have durations the
    test author cannot bound without this rule.
- Closed when the plan states both rules:
  - `timeout_s` is the total budget. An alive child not ready at the deadline is killed, and the script exits 3
    naming the last reason.
  - A child that exits moves the loop to the next port only when its port is no longer free (another process took
    it). Otherwise the script exits 3 at once, naming the returncode.
- Tests:
  - `test_cluster_service_job`: the exits-at-once leg over a ≥10-port range exits 3 within a few seconds, naming
    the returncode. The `application/grpc` leg exits 3 within `timeout_s` plus a small margin over a multi-port
    range. The existing held-port leg still announces the next port.

**M23 · §3.3 L530 `test_cluster_service_job.py (all OS)` "SIGTERM reaps the child", with §6 L742-745 · the leg
cannot pass on `windows-latest`.**
- The measurement:
  - The all-OS job runs `pytest tests/frozen tests/extra` on `windows-latest` (`ci.yml:41`, `:61`). Positive
    control: frozen m66 already branches on `win32` (`test_htcondor_sites.py:287`).
  - Python's `os.kill` and `Popen.send_signal`/`terminate` on Windows call `TerminateProcess` for `SIGTERM`, so
    `announce.py`'s handler never runs and its `http.server` child is orphaned.
  - In the DAG-mode leg, the test's `os.replace` of `driver.url` can fail with `PermissionError` while
    `announce.py` has the file open, which gives a flake.
- Why it changes code: the test author has to invent a platform rule. `announce.py` only ever runs in a Linux
  job.
- Closed when the plan marks the subprocess legs of `test_cluster_service_job` (SIGTERM, lease, DAG mode) as
  POSIX-only (`skipif(sys.platform == "win32")` with that reason) and keeps the key and text legs all-OS.
- Test: the row itself. TEST_SANITY's two-run determinism on Windows is the check.

Order: most severe first.

## Checked and not raised
- **The in-job `announce_only` backend and §3.1.**
  - m68a's in-job `service_hosts=("driver",)` forces a GPU or imaged recipe to leg 3 cluster-hosted.
  - The driver's outer `ServiceSet` pops the announce. `runner.run`'s set re-probes it as leg 1.
  - The status identity is the announced one, which is m68a's exit item for the m68b reviewer.
  - A `TimeoutError` there exits 1 (`driver.main`'s set sits outside the run's try) and is retried by `RETRY`.
- **`RunHandle(dag=True)`.** m67's `_poll` already maps DAGMan `ExitCode` 0 to done and anything else to failed
  (`driverless.py:78-79`), and `probe_dag_service` X's DAGMan `ExitCode 1` confirms it. Saved m67 handles load with
  the default.
- **m67 frozen refusals stay green under `job_root`.** `test_driverless_payload.py:191-236` matches `worker_ports`
  and `/afs`, and the refusal order is kept.
- **§7 and commit sizes.** The plan's estimates are 600, 350 and 170, plus a freeze of about 900, all ≤2k. The
  total of about 1.1k matches §7.
- **References.** §8 `api.rst` (`job_root`) and the §9 m68b lines are consistent with §3.3.

## Exit items
Appended to `reviews/m68b-exit-items.md` under "## r8 exit items". None of them makes this round unclean.

## Verdict
**NOT CLEAN**: M18–M23.
- M18 and M19 would each fail a live leg as written: attached cluster hosting, and the DAG.
- M20 and M21 are resource leaks or hangs at real sites.
- M22 and M23 are decisions the test author would otherwise have to invent.
- Each finding closes with a sentence-level decision and one test leg, as given above.
