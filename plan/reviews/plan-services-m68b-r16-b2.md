**NOT CLEAN**

# Review r16-B2: plan-services.md §3.3 part B2, whole-part read

Snapshot: `plan/reviews/plan-services-m68b-r16-b2-snapshot.md`. Scope: all of B2, read as its implementer and test
author would:
- the §3.3 preamble and ladder rows tagged B2 (L415–431);
- "B2 — DAG driverless, `job_root`, lxplus" (L537–621);
- B2's frozen rows, "Fails on (B2)" and the B2 commits (L623–660);
- the shared items: §6's m68b lines and the simulated-GPU pool, §7's m68b figures, §8, and §9's m68b risks and site
  checks;
- D3, D4 and D6 where they bind the DAG path.

B1 and m68a's §3.1 are taken as written. Code: graphed-executors `c2298d7` (`driverless.py`, `driver.py`,
`launch.py`, `sites.py`, `tests/frozen/m67`). graphed: `python/graphed/services.py` on main. One new probe was run on
`htcondor/mini` 25.13.2 (container `r16b2-pool`, now removed).

## Design findings

### M44-B2: a failed DAG reads a previous run's `result.pkl` from a reused `log_dir` as its own result
- **Where.** L576–577 lists what is removed before a DAG submits into a reused `log_dir`: `driver.url`,
  `graphed-secret` and `service-svc*/`. The list does not include `result.pkl`. L594–602 maps DAGMan's
  `ExitCode 1` to `failed`, and `result()` then reads `result.pkl` from the DAG dir (L601–602). m67's `result()`
  accepts `failed` and unpickles whatever is in the file (`driverless.py:93-104`).
- **Why this changes code.** m67's plain job reaches `failed` only as `JobStatus 4`, a completed job, so its output
  transfer has just written a fresh `result.pkl`. If the driver dies without writing one, the plain job is held,
  not failed (`probe_r12_dag_held_node.txt`). A DAGMan cluster reaches `ExitCode 1` without the driver node
  transferring anything in several ways:
  - every driver start is removed rather than completed (by the user or by a site's held-job or wall-time policy);
  - DAGMan fails at startup (a parse error: `probe_r11_dag_names.txt`, DAGMan `ExitCode 1` at once);
  - the node's submit is refused.

  m67 allows a reused `log_dir`, and the plan keeps that (L574). So `RunHandle(dag=True).result()` returns the
  previous run's `(True, ExecResult)` as this run's value. That is a silently wrong result, not an error. On a fresh
  `log_dir` the same path raises a bare `FileNotFoundError` that names nothing useful.
- **Measurement.** `probes/m68b/probe_r16_dag_stale_result.{py,sh,txt}` (new). The setup: a reused DAG dir holding
  `result.pkl = (True, "PREVIOUS RUN'S VALUE")`, with `JOB driver`, `SERVICE svc0`, `RETRY driver 2 UNLESS-EXIT 3`,
  `from_dag` with `usedagdir`/`force`, unspooled.
  - Part 1: an evicted driver node is held at output transfer (`ON_EXIT_OR_EVICT`, m67's key), which matches L597–599.
  - Part 2: each held driver node was removed with `condor_rm`. DAGMan retried twice and then logged `EXITING WITH
    STATUS 1`. The DAGMan history reads `JobStatus 4 ExitCode 1`, which is `failed` under L595. `result.pkl` still
    holds `(True, "PREVIOUS RUN'S VALUE")`.
  - Control: the same stale file under m67's plain-job mapping is unreachable, because removal gives `removed`
    (`driverless.py:78`) and `result()` refuses it.
- **Closed when:**
  - B2's pre-submit cleanup also removes `result.pkl` (and `driver.log`, which `logs()` would otherwise serve as this
    run's traceback);
  - `result()` on a `dag` handle whose `result.pkl` is absent raises `RuntimeError` naming the DAG status and
    `run.dag.dagman.out`.
- **Test** (`test_driverless_dag.py`):
  - The reused-`log_dir` leg also asserts that the previous `result.pkl` and `driver.log` are gone before `from_dag`
    (recorder).
  - `RunHandle(dag=True)` over an `ExitCode 1` DAGMan ad with no `result.pkl` raises `RuntimeError` naming
    `dagman.out`. m67's code raises `FileNotFoundError`, and with a stale file it returns the stale value.

## Checked and holding
- **`job_root`** (L538–547). It is one field, read by `pilots="condor"` and by the DAG. Several things support the
  text:
  - `_SELF_SUBMIT_ROOT` exists today only as `{"lxplus": "/afs"}` (`driverless.py:33`), and a profile outside the dict
    self-submits unchecked (`driverless.py:174-175`), so "fail closed" describes a real change.
  - The refusal order after `jobs_can_submit`/`worker_ports` matches `probe_code_premises.txt` S9.
  - Every m67 frozen `pilots="condor"` case either reaches those earlier refusals or uses `generic`
    (`test_driverless_payload.py:147,201,225`), which has `"/"`.
  - The lxplus refusal still names `/afs` (`test_driverless_payload.py:230`).
  - The Windows case: W, `PureWindowsPath('C:/Users/x').is_relative_to('/')` is False, and the `root == "/"`
    short-circuit covers it.
- **SERVICE assignment** (L548–556). The rule agrees with §3.1's leg-3 order: an image or GPUs goes to cluster
  hosting, and the driver job's `service_hosts` is `("driver",)`. graphed's `ServiceSpec.name` is a free string
  (`services.py:84-96`), so `a b` can be built, and `referenced_services` returns specs in name order, which makes
  the ids deterministic. The lpc case lands on its EAF row, and the control, with `services={}`, lands on the
  `job_root` refusal.
- **DAG files and submit** (L557–579). They are backed by probes:
  - `probe_dag_service.txt` R, X and U cover a retried driver re-announced to, a failed driver ending the DAG with
    `ExitCode 1`, and a reused dir with the rescue file renamed `.old`;
  - `probe_r8_paths.txt` D1–D2 covers relative node files and `usedagdir`;
  - `probe_r13_dag_held_service.txt` covers the held SERVICE node versus `periodic_remove`;
  - `probe_r11_fromdag_versions.txt` supports the fixture substitutions.

  `driver.sub` inherits an absolute `executable` and an `initialdir` equal to `log_dir` from `submit_description`
  (`driverless.py:190-205`, `launch.py:168-169`). `env.tgz` is written into `log_dir` by `_stage` before any
  `ServiceJob.files` call can name it.
- **The in-job backend** (L580–593). The following hold together with §3.1's `driver.main` phases and D6:
  - the outer `ServiceSet` reaches `host_service` for the SERVICE names;
  - a timeout or an unknown name there exits 1 and is retried by `RETRY`;
  - the inner set re-checks the names as leg 1;
  - the probe's identity rule passes on the one-host pool, where the driver `Machine` equals the announced
    `Machine`.

  Records survive until `wait_announce` pops them, so an announce that arrives before the wait is not lost.
- **Tracking** (L594–606). `DAG_JobsHeld` is returned only when projected, and a held SERVICE node is not counted
  (`probe_r13_dag_held_service.txt`). A held driver node leaves DAGMan at `JobStatus 2`
  (`probe_r12_dag_held_node.txt`), and the probe run above reproduces this. `load` of an m67 handle defaults
  `dag=False`.
- **CI and partition.**
  - The all-OS job runs `pytest tests/frozen tests/extra` by directory (`ci.yml:60`), and `test-htcondor` names
    directories (`ci.yml:300`), so no job lists a file before it exists.
  - The simulated GPU is `probe_sim_gpu.txt` G1/G2.
  - The live file's slots fit a 4-CPU runner: a driver at `request_cpus=2` plus one service slot. DAGMan uses the
    scheduler universe.
  - §7's m68b figures agree with the commit sums: B1 ~720 plus B2 ~450 plus ~170 is about 1.3k, and the tests
    ~700 plus ~500 are about 1.2k.
- **Site checks and §9.** The premises that cannot be measured here are named owner steps: the DAGMan job's AFS
  access and `getenv` acceptance, the SERVICE node's ticket, and `$_CONDOR_MACHINE_AD` in the Triton image. Owner
  ruling: LPC and lxplus are unreachable.

Exit items: `m68b-exit-items.md`, "## r16-B2 exit items".
