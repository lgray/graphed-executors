**B2 HOLDS ON 0e48380**

Base check of plan-services §3.3 B2 (plan HEAD fcef9ab) against executors main 0e48380 (m68a, PR #39), worktree
`~/vibe-coding/cloud/code-m68b-main`. Lines are `git show fcef9ab:plan/plan-services.md` lines. Driven probe:
`plan/probes/m68b/probe_b2base_injob.{py,txt}` (macOS, graphed d0ad16b, `graphed_executors` from the 0e48380 tree).
No premise needed the pool: m68a changed no DAG or condor-side behaviour that B2 relies on, so no container was started.
No design change. One stale coordinate. Three exit items (E1–E3).

| # | Premise | Plan line | File @0e48380 | Verdict | Evidence |
|---|---|---|---|---|---|
| 1 | `job_root: str \| None = None` after `jobs_can_submit` composes with m68a's `services` field, `__post_init__` and positional `__reduce__`; `replace(SITES["lpc"], sandbox_root=…, services={})` works | 603, 735 | `sites.py` `SiteProfile` | holds | probe §5: fields `[… jobs_can_submit, job_root, services]`; the pickle round trip is equal and keeps `job_root`; `replace(…, services={})` → `{}` |
| 2 | `_SELF_SUBMIT_ROOT` exists and is read after the `jobs_can_submit` and `worker_ports` refusals; a profile outside the dict self-submits unchecked | 608–611 | `driverless.py` `_SELF_SUBMIT_ROOT`, `submit_driverless` | holds | order unchanged: `jobs_can_submit` → `_refuse()` → `worker_ports` → root. m68a only adds `services=` validation before them |
| 3 | m67's frozen generic self-submit, lxplus `/afs`, `driver.log`-in-`log_dir` (`test_driverless_live.py:90`) and `driver.sh`-by-name (`test_driverless_payload.py:107`) pins | 607, 611, 647, 695 | `tests/frozen/m67/**` | holds | `git diff --quiet c2298d7 0e48380 -- tests/frozen/m67` → exit 0; lines 90 and 107 carry the cited asserts |
| 4 | No m68a frozen test is caught by the fail-closed `job_root` or by DAG routing | 609, 622 | `tests/frozen/m68a/*.py` | holds | `grep pilots="condor"` hits only m67. m68a's driverless tests build `web_spec` (an image-less child), so they submit plain jobs |
| 5 | Selecting a SERVICE node reads `submit_driverless(services=)`, the row's `services` (lpc `triton` = EAF), the in-job `service_hosts == ("driver",)` and m68a's image/GPU placement test | 613–617 | `driverless.py`, `sites.py` lpc row, `backend.py` `in_job` branch, `services.py` `_managed` | holds | read. Probe steps 3 and 4: the site row wins before `host_service`, and without `host_service` it raises `ServiceUnavailable` |
| 6 | In the job, leg 2 runs before leg 3; a failure of the driver's own set (a name outside `announce_only`, or a `TimeoutError`) exits 1 and is retried | 614–616, 663–664, 697–699 | `services.py` `_resolve`; `driver.py` `main` | holds | the driver's `ServiceSet` sits outside `runner.run`, so the outer `except Exception` gives `EXIT_FAILED`. Probe step 2: the `ValueError` propagates out of `start()` |
| 7 | The 8-hex nonce is already minted for `JobBatchName` | 623 | `driverless.py` `submit_driverless` | holds | `f"graphed-driverless-{uuid.uuid4().hex[:8]}"` |
| 8 | `_stage(log_dir, script_name, module)` keeps its signature, builds `env.tgz` and writes `driver.sh` with the `exec` line | 631, 687–690 | `launch.py` `CondorPilots._stage` | holds | unchanged by m68a |
| 9 | lxplus keeps `MY.SendCredential` and `spool=True` | 633, 735 | `sites.py` lxplus row | holds | read |
| 10 | The DAG is submitted by a direct `schedd.submit(Submit.from_dag(…))`, never spooled | 639–641 | `launch.py` `_submit` | holds | m68a changed `_submit` to `(htc, schedd, desc, n, stack)`. B2 does not call it for the DAG, and with no spool nothing needs releasing after the submit. The plain path already passes m68a's stack |
| 11 | `run.json` gains `dag_dir` and `announce_only`; `_runner` reads both with defaults; m68a's hand-built dicts lack them; `_runner(run, job, log)` keeps its signature (a m68a README pin) | 650–652 | `test_services_sites.py` `driver_run`; `driverless.py` run dict | holds (E1) | m68a writes `endpoints` only. `grep -rn announce_only src tests docs` → 0 hits (the same grep matches `_SELF_SUBMIT_ROOT`) |
| 12 | The `,`-in-`user_modules` refusal is B2's to add | 652–653 | `launch.py` `_refuse` | holds | m68a has no such refusal |
| 13 | With `announce_only`, the in-driver task server is built as for condor pilots: `Machine` from the ad, the row's `worker_ports`; the backend takes `in_job=`; `write_secret` uses mode 0600 | 654–661 | `driver.py` `_runner`; `services.host_identity`; `launch.write_secret` | holds | m68a renamed `machine_host()` to `host_identity()` (same `Machine` read). Also, m68a's `advertise_host = host`, so for local pilots B2's host switch also moves the services started beside the driver to `Machine`. That stays within B2's N-02 assumption of one shared network namespace |
| 14 | `host_service(spec, scope)` → `(endpoint, identity, key)`; `release_service(key)`; the status is `leg="managed", host="cluster"` with the announced identity | 661–668, 735 | `services.py` `_managed`, `_record`; logger `graphed_executors.services` | holds | probe step 1: `('managed', 'cluster', 'service-node')`, calls `host_service 'a b'` then `release_service:svc0` |
| 15 | One plan per driver start, and `runner.run` resolves no second time | 666 | `driver.py` `main`; `engine.py` `ServiceSet(…, endpoints=given, scope=ctx.run_nonce)` | holds | `main` sets `runner.services = endpoints`, so every spec takes leg 1 inside the run |
| 16 | `RunHandle` fields, `_poll`, `wait`, `TERMINAL` and `save`/`load` are unchanged; `dag: bool = False` loads m67 handles | 669–676 | `driverless.py` `RunHandle` | holds | read |
| 17 | `result()` on a missing `result.pkl` raises `FileNotFoundError` today; it retrieves only when in the queue on a spooled site | 677–680, 735 | `driverless.py` `RunHandle.result` | holds | m68a's comment: "a missing file raises as itself". m68a now also wraps a `result.pkl` that will not load in a `RuntimeError` naming `driver.log`; B2's DAG path inherits it |
| 18 | The driver overwrites `result.pkl` on every exit it reaches | 691 | `driver.py` `main` tail | holds | the unconditional `(job / RESULT_FILE).write_bytes(blob)` |
| 19 | `recipes.triton(name, image, model_repository)`: kind `triton`, gRPC-only argv, `inputs=(model_repository,)`, `gpus=1`; `htcondor_runner(services=)` gives leg 1 | 699–704, 712 | `recipes.py`, `backend.py` | holds | read |
| 20 | The shape of m68a's `test_driverless_endpoints` (`get_plan`/`GetProcess`/`DriverResolved`, `resolve_services`) | 736 | `services_harness.py`; `engine.py` `resolve_services` | holds | grep |
| 21 | The exit table sits at `docs/htcondor.rst` 279–296 | 771 | `docs/htcondor.rst` | stale coordinate | it is now 279–298: m68a's exit-1 row grew |

## Exit items (constraints for the implementer; no design change)
- **E1.** The "or hold §2's empty list" clause (L652) and §2's `announce_only: [] (m68; …)` (L168) are false on 0e48380:
  m68a's `run.json` carries `endpoints` and no `announce_only`. The `run.get("announce_only") or {}` decision stands.
  Smallest change: L168 → "(m68b adds `announce_only: {name: node id}` and `dag_dir`)", and L652 drops "or hold §2's
  empty list".
- **E2.** A frozen m68a pin now binds commit 2. `test_services_packaging.py::test_no_service_is_named_in_the_engine`
  requires no case-insensitive `triton|histserv` in `htcondor_backend/**` apart from `sites.py`. There are 0 hits at
  0e48380; `sites.py` has 2 (control). B2's code, comments and docstrings in `driverless.py`, `driver.py`, `backend.py`
  and `launch.py` must not name them.
- **E3.** m68a added text that B1+B2 make false. Commit 3 (docs) and commit 2 (docstring) rewrite it:
  - `docs/htcondor.rst:328–329`: "cluster hosting, which this release does not have yet, so such a run is refused
    naming `host_service`". Also the closing paragraph of the Services section: a driverless GPU or imaged recipe
    now becomes a SERVICE node.
  - `docs/design.rst:884–885`: "a later release fills".
  - `backend.py`'s module docstring: "in a driver job … a managed service may start only beside the driver …
    `host_service` is not here: cluster hosting is a later seam".

  "Cluster-hosted services" fits as a subsection of m68a's existing "Services" (`htcondor.rst:308`).
