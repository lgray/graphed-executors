**NOT CLEAN**

# Review r12-B2: plan-services.md §3.3 part B2 (DAG driverless, `job_root`, lxplus), whole-part read

Snapshot: `plan/reviews/plan-services-m68b-r12-b2-snapshot.md`. Scope:
- §3.3 preamble and the B2 ladder rows (L415-429);
- "B2 — DAG driverless, `job_root`, lxplus" (L499-566);
- the B2 frozen rows, "Fails on (B2)" and the B2 commits (L568-599);
- §6 CI m68b lines, §7 figures, §8 docs, §9 m68b risks;
- D3, D4 and D6 as they bind the DAG path.

B1, and m68a's §3.1, were taken as written. Code: graphed-executors `c2298d7`.

## Checked and holding

**m67's frozen tests stay green under `job_root`.** The plan orders the new check after `jobs_can_submit` and `worker_ports`:
- `test_condor_pilots_are_refused_on_a_profile_without_worker_ports` still refuses naming `worker_ports`. Its profile has `jobs_can_submit=True` by default, and `worker_ports` is checked first.
- The lxplus refusal still names `/afs`.
- The generic self-submit cases (`test_driverless_payload.py:143`, `test_driver_entry.py:180`, live (b)) pass under `root == "/"`, including on Windows (`probe_code_premises.txt` W).
- No frozen or extra test references `_SELF_SUBMIT_ROOT` (a grep of `tests/`; the only hit is `driverless.py:33`).
- No m66 or m67 test pins `SiteProfile`'s field list.

**Consistency with D3, D6 and §3.1.** D3's driverless line, D6's in-DAG retry owner (`RETRY driver 2 UNLESS-EXIT 3`, no `max_retries` in the node `.sub`) and §3.1's leg order all agree with B2:
- §3.1's leg 3 calls `host_service` without looking at `service_hosts`, so the in-job `("driver",)` backend with announce-bound methods resolves a DAG name there.
- Only the driver's outer `ServiceSet` calls `host_service`, and its `wait_announce` pops the record once. The inner set sees the name as leg 1.
- m68a's exit item asking for the announced identity is answered at L545.

**DAG mechanics against the probes.**
- `probe_dag_service.txt` shows DAGMan exit codes 0 and 1, the SERVICE node's `RemoveReason`, the rescue file under `force`, and the retried driver re-announcing.
- `probe_r8_fromdag_force.txt`, `probe_r11_dag_names.txt` and `probe_r11_fromdag_versions.txt` show what the plan says they show.
- `probe_sim_gpu.txt` shows one simulated GPU that a `request_gpus=1` job matches and a `request_gpus=2` job does not.
- In CI, `MOUNT_UNDER_SCRATCH =` (`ci.yml:279`) makes the pytest tmp DAG dir readable and writable by both nodes, which the `generic` `job_root="/"` premise needs.

**Figures.** §7's m68b totals match B1 + B2: src+ci+docs 650 + 420 + 170 ≈ 1.2k, tests 650 + 450 ≈ 1.1k.

## Design findings

### M40-B2 — a DAG run hides a held driver node: `status()` says "running" for ever
- **Where.** L547-549 ("Tracking"). `RunHandle(..., dag=True)` tracks only the DAGMan cluster and maps its exit code 0/1 to `done`/`failed`. The frozen row at L580 pins only that mapping.
- **Why it changes code.**
  - m67's handle reports `held` (`driverless.py:77`, pinned by m67's `test_run_handle` for `JobStatus 5`).
  - Under a DAG, the driver node is a separate cluster. The DAGMan ad stays at `JobStatus 2` while that node is held, and DAGMan never fails the DAG. So `status()` returns "running" and `wait(timeout)` raises "still running" for a run that cannot progress.
  - Holds are not hypothetical. A driver that dies without writing `result.pkl` holds its node at output transfer, because `transfer_output_files` names `result.pkl`. Examples are an OOM kill, a walltime signal or a container crash. A node input the schedd cannot read holds at input transfer, which the plan itself names at L522.
  - The implementer has to decide how a DAG handle reports this. The plan is silent, and m67's contract has a `held` state.
- **Measurement.** `probes/m68b/probe_r12_dag_held_node.{py,txt}` (htcondor/mini 25.13.2, `from_dag` with `usedagdir`/`force`, unspooled, JOB driver + SERVICE + RETRY):
  - Run 1: the driver executable is missing, so the node is held at input transfer.
  - Run 2: the driver does `kill -9 $$`, so the node is held at output transfer with HoldReasonCode 12.
  - In both runs DAGMan is still queued after 403 s, and its ad reads `JobStatus = 2, DAG_JobsHeld = 1, DAG_NodesFailed = 0`.
  - Positive control: the same ad carries `DAG_JobsHeld`, and m67's plain-job path reports `held` from `JobStatus 5`.
- **Closed when.** The Tracking paragraph states how a `dag=True` handle reports a held node. For example: project `DAG_JobsHeld` beside m67's attributes, and report `held` when the DAGMan job is running with `DAG_JobsHeld > 0`, which also covers a held SERVICE node. Alternatively, query the `DAGNodeName == "driver"` job.
- **Test that shows it closed.** In `test_driverless_dag.py`, `RunHandle(dag=True)` over a synthetic DAGMan ad `{JobStatus: 2, JobUniverse: 7, DAG_JobsHeld: 1}` returns `"held"`. m67's mapping gives `"running"`. `{JobStatus: 2, DAG_JobsHeld: 0}` stays `"running"`.

## Not raised (exit items)
Recorded under "## r12-B2 exit items" in `plan/reviews/m68b-exit-items.md`:
- the lpc legs must run on an lpc copy with a tmp `sandbox_root`;
- `htcondor_backend/services.py` is missing from B2's file list, and `ServiceJob` needs a watch/no-submit path;
- `svc<i>` indexing wording;
- the stale `service-svc<i>/` in a reused `log_dir`;
- site check (2) needs an `/afs` cwd for `models`;
- `api.rst` is missing from commit 3;
- r11's `or []` is superseded.

## Cleanup
Container `r12b2-pool` removed with `docker rm -f`. No background processes were started. Scratch is in `/tmp/claude-0/review-r12-b2/`.
