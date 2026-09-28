**NOT CLEAN**

# Review r13-B2: plan-services.md §3.3 part B2, delta round

Snapshot: `plan/reviews/plan-services-m68b-r13-b2-snapshot.md`. The delta was taken against `plan-services-m68b-r12-b2-snapshot.md`.

Scope is B2's delta plus the context it needs:
- the §3.3 preamble's shared-item split;
- the B2 file list;
- `svc<i>`, the DAG files and the reuse cleanup;
- the in-job announce secret;
- Tracking;
- the B2 frozen rows, "Fails on (B2)" and the B2 commits;
- §7 figures and §9's AFS line.

B1, and m68a's §3.1, were taken as written. Code: graphed-executors `c2298d7`. New evidence is in `plan/probes/m68b/probe_r13_dag_held_service.{py,txt}` and `probe_r13_dag_held_service_prm.py` (htcondor/mini 25.13.2).

## Checked and holding

**M40-B2 is closed at its cause for a held driver node.**
- In `probe_r12_dag_held_node.txt`, the DAGMan ad reads `JobStatus = 2, DAG_JobsHeld = 1` while the driver node sits at `JobStatus 5`. m67's `_poll` (`driverless.py:72-77`) returns `running` for that ad, through `counts_as_alive`.
- The new rule (a running DAGMan job with `DAG_JobsHeld > 0` is `held`) turns it into `held`.
- The row pins both sides: `{2, 7, 1}` gives `held`, `DAG_JobsHeld: 0` gives `running`, and m67's mapping is named as giving `running`.
- M41-B2 below covers what that row does not pin.

**The DAG-dir announce secret.**
- The driver mints the secret for its node ids and writes `graphed-secret` and then `driver.url` into `dag_dir`, each through `os.replace`.
- The SERVICE node (watch mode) reads both files from `dag_dir` each second. Nothing of the secret reaches its scratch dir: watch mode transfers no `graphed-secret`, and its child serves only its cwd.
- This is consistent with D6. A retried driver start is a new `TaskServer`, which mints a new secret for the same ids and writes a new pair. Watch mode announces each new pair until it gets a 200 (`probe_dag_service.txt` R). A torn read between the two `os.replace`s is retried.
- The previous run's `graphed-secret` and `driver.url` are removed before submitting, so a new DAG's node never announces to an old pair.
- Keying records by node id is sound. There is one `TaskServer` per driver start, and `wait_announce` pops the record.
- The pickle-403 check in the row discriminates between the announce secret and the pilots' secret.

**`ServiceJob.files(dir)` for B2.**
- `service-svc<i>/` is written by `files` with `key=id` and `watch=<DAG dir>`. It carries no secret, and `url` is null.
- `svc<i>.sub` is those keys with that dir as `initialdir`. The executable is absolute (B1), and `env.tgz` is `<launcher.log_dir>/env.tgz`, where `launcher.log_dir` is the DAG dir (`driverless.py:184`).
- The file list (`services.py +15`) and commit 2 name the watch-mode addition.

**`svc<i>` and reuse.**
- "Index among those specs, in name order" agrees with the row: `{"a b": "svc0", "driver": "svc1"}`.
- The reuse cleanup now removes `service-svc*/`, and the row checks this.

**lpc copies.** A `sandbox_root=<tmp>` copy gets past `_refuse` (`launch.py:187-190`) and reaches the announce-only decision. See the exit item on how to register it.

**Figures.**
- §7: 700 + 450 + 170 ≈ 1.3k src+ci+docs, and 700 + 500 = 1.2k tests.
- Commit 2's ~450 against its header's +275 keeps r12's ratio (+255 against ~420).

## Design findings

### M41-B2 — nothing pins the `held` fix against a real schedd, and the `wait()` claim is false
- **Where.** Tracking, L570-575, and the B2 row at L606.
- **Why it changes code.**
  - *Projection.* The fix works only if `DAG_JobsHeld` is in the query's projection.
    - m67's `STATUS_ATTRS` is `["JobStatus", "HoldReasonCode", "ExitCode"]`. A real schedd returns only the projected attributes.
    - The frozen recorder (`tests/frozen/m67/driverless_harness.py:243-248`) logs the projection but returns the whole synthetic ad.
    - So an implementation that tests `ad.get("DAG_JobsHeld")` without projecting it passes the row, and still reports `running` for ever in production. That is M40-B2's bug.
  - *`wait()`.* L574 says "so `wait()` returns instead of timing out as 'running'". m67's `wait` loops until `TERMINAL = ("done", "failed", "removed")` (`driverless.py:28,87`), and `held` is not in it. Under m67's code a held DAG still times out, now as "still held", and `wait(None)` never returns.
    - Read literally, the sentence tells the implementer to make `held` terminal for DAG handles. That is a change to m67's contract ("polls to a terminal state"), and no test pins it either way.
    - Keeping `held` non-terminal is the consistent choice: a held node can be released, as for m67's plain job. Also, a held SERVICE node never counts, and the DAG still ends (M42-B2).
- **Measurement.**
  - `probe_r13_dag_held_service.txt`: at every poll, the DAGMan ad projected on m67's three attributes lacks `DAG_JobsHeld` ("in m67-projected ad: False"). The same query with `DAG_JobsHeld` added carries it.
  - The `wait` behaviour is from reading `driverless.py:83-91` and m67's `test_wait_is_bounded`.
- **Closed when.**
  - Tracking says that `wait()` keeps m67's terminal set, so its `TimeoutError` names `held` (or it states a different, deliberate choice).
  - The row pins the projection.
- **Test.** In the `RunHandle(dag=True)` leg of `test_driverless_dag.py`, the recorder's `query` log entry for `status()` has a projection that contains `DAG_JobsHeld`. With `DAG_JobsHeld` left out of `STATUS_ATTRS`, that assertion fails, while the current row passes. Add also: `wait(timeout=0.3)` over the held ad raises a `TimeoutError` whose text says `held`.

### M42-B2 — a SERVICE node that is held when the DAG ends turns a successful run into DAGMan exit 1 (`failed`)
- **Where.** Tracking, L570-571: "exit 0 once the driver node succeeds". Also the `svc<i>.sub` keys at L544-545.
- **Why it changes code.**
  - DAGMan does not count a held SERVICE node in its held count. It logs "0 job proc(s) currently held" after svc0's `ULOG_JOB_HELD`, and the ad keeps `DAG_JobsHeld = 0`.
  - When the driver node succeeds, DAGMan removes the held SERVICE node. It then logs "Number of counted held job processes (0) is not equivalent to Node svc0's internal count … (1)". Under the default `DAGMAN_USE_STRICT = 1`, that warning is fatal: DAGMan writes `run.dag.rescue001` and exits 1.
  - `RunHandle(dag=True)` then reports `failed` for a run whose driver exited 0 and whose `result.pkl` holds `(True, ExecResult)`. m67's `result()` still returns the value for `failed`, so `status()` and `result()` disagree.
  - The trigger is a SERVICE node that is held after it announced, for example by a site's periodic hold (memory or runtime) or by `condor_hold`, while the plan finishes.
  - Whether the plan accepts this is a decision the implementer has to make, and it touches a line either way:
    - add a key to `svc<i>.sub`, or
    - change the status mapping, or
    - add a documented caveat.
  - The Tracking paragraph's "(a node held at input or output transfer …)" is also true only for the JOB node. A held SERVICE node never shows as `held`. It costs the bounded three × `timeout_s` that the paragraph already states.
- **Measurement.** `probes/m68b/probe_r13_dag_held_service.txt`:
  - The driver sleeps 200 s and exits 0. svc0 is held at input transfer.
  - DAGMan history: `JobStatus 4, ExitCode 1`. The driver node shows `4/0`, and svc0 was removed by DAGMan.
  - Variant: the same DAG with `periodic_remove = JobStatus == 5` in `svc0.sub` gives DAGMan `ExitCode 0`. svc0 was removed by its `PeriodicRemove`.
  - No SITES profile sets a `periodic_*` key (grep of `htcondor_backend/`).
- **Closed when.** B2 states how a SERVICE node held when the DAG ends is handled. The measured option is `periodic_remove = JobStatus == 5` in each `svc<i>.sub`, after the profile's keys and before the launcher's `extra_submit`, or at a stated position. A removed SERVICE node before its announce takes the same path the paragraph already describes for a node that dies. Tracking's "a node held" is limited to the driver node.
- **Test.** In the recorder leg of `test_driverless_dag.py`, each `svc<i>.sub` carries `periodic_remove = JobStatus == 5` and `driver.sub` does not. The `data/from_dag-generic.txt` fixture is unaffected, because the key is in the node files, not the DAGMan description. A live leg is optional. `probe_r13_dag_held_service_prm.py` is the shape: about 4 min on the CI pool.

## Not raised (exit items)
Recorded under "## r13-B2 exit items" in `plan/reviews/m68b-exit-items.md`:
- The simulated-GPU pool line reaches CI only in commit 3, while `test-htcondor` runs `tests/frozen/m68b` from commit 1. B2's live file needs the GPU, so commit 2 is red. The harness's "the live files" means B2's one file.
- The rationale "never the pilots' secret: the DAG dir sits on a shared tree", "Fails on: a pilots' secret in the DAG dir" and §9's AFS line ignore `<dag_dir>/pilots/graphed-secret`. m67's in-job `CondorPilots` writes the pilots' secret there, under the same ACL.
- The lpc copy has to be registered with `monkeypatch.setitem(SITES, "lpc", …)`, because `submit_driverless` takes a site name. m67's lpc test is a refusal (`test_driverless_payload.py:209`), not a submit. "`services={}`" there means the row's field, not the kwarg.
- The `svc<i>` row should declare `driver` before `a b`, plus one non-SERVICE spec that sorts first, so that name order and "among those specs" are both discriminated.

## Cleanup
- Container `r13b2-pool` was removed with `docker rm -f`. No `r13b2-` containers remain.
- No background processes were started.
- Scratch is in `/tmp/claude-0/review-r13-b2/`.
- Probe evidence was copied to `plan/probes/m68b/probe_r13_dag_held_service*`.
