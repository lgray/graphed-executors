**NOT CLEAN**

# Review r14-B2: plan-services.md §3.3 part B2, delta round

Snapshot: `plan/reviews/plan-services-m68b-r14-b2-snapshot.md`; delta against `plan-services-m68b-r13-b2-snapshot.md`.
Scope: B2's delta plus the context it needs (the preamble's shared-item split, B1's new `service/` and
`MY.SendCredential` lines where B2's `svc<i>.sub` inherits them, the DAG files, the in-job secret, Tracking, the B2
rows, "Fails on (B2)", commits, §7 and §9's AFS line). B1 and m68a's §3.1 taken as written. Code: graphed-executors
`c2298d7`. No new probe was needed; no container was started.

## Checked and holding

**M41-B2 is closed at its cause.**
- Tracking now says the status query projects `DAG_JobsHeld` beside m67's `STATUS_ATTRS` and cites the probe
  (`probe_r13_dag_held_service.txt`: absent from a projection on m67's three attributes).
- `wait()` keeps m67's `TERMINAL = ("done", "failed", "removed")` (`driverless.py:28`); its error is
  `f"cluster {c} is still {status} after {timeout}s"` (`driverless.py:89`), so over the held ad it names `held`.
- Row: the recorder logs `("query", constraint, tuple(projection))` (`tests/frozen/m67/driverless_harness.py:243-244`)
  and returns the whole ad, so "the logged `status()` projection contains `DAG_JobsHeld`" fails for an implementation
  that reads the attribute without projecting it, and passes the fix. `wait(timeout=0.3)` over the held ad raises on
  the second poll (the loop sleeps `min(poll_s, remaining)`). Both discriminate.

**M42-B2 is closed at its cause.**
- Every `svc<i>.sub` carries `periodic_remove = JobStatus == 5`; the `_prm` variant of the probe gives DAGMan
  `ExitCode 0` with svc0 removed by `PeriodicRemove` (held at input transfer, removed while the driver still ran),
  against `ExitCode 1` without it.
- A SERVICE node removed before announcing: DAGMan does not retry SERVICE nodes, so the driver's `wait_announce`
  times out, exits 1 and `RETRY driver 2` gives the three × `timeout_s` path the paragraph already states. Consistent.
- Tracking limits "a node held" to the driver node. "Fails on" names both. The row pins the key in every
  `svc<i>.sub` and its absence from `driver.sub`; the `from_dag` fixture is unaffected (node files, not the DAGMan
  description).

**GPU pool line.** Now in B1's commit 1 with `test-htcondor` running `tests/frozen/m68b`; B2's live file lands after
it. B1's timeout leg asks for two GPUs, which a one-GPU pool never matches. §6 (L842-844) agrees. §7: 720 + 450 + 170
≈ 1.3k src+ci+docs still holds.

**Pilots' secret claim.** m67's in-job `CondorPilots` gets `log_dir = out/pilots` (`driverless.py:212`) and writes
`graphed-secret` there (`launch.py:200-202`), so "kept under `<dag_dir>/pilots/`" is right; §9's AFS line now names
both files.

**lpc copy.** `submit_driverless` and `RunHandle` both read `SITES[site]` from the module's dict
(`driverless.py:49,149`), so `monkeypatch.setitem(SITES, "lpc", …)` reaches them.

**svc<i> ordering.** With `driver` declared before `a b`, declaration order gives `driver: svc0`; with `0web` sorting
first, an index over all specs gives `a b: svc1`. The expected `{"a b": "svc0", "driver": "svc1"}` rejects both.

## Design findings

### M43-B2 — a SERVICE node without `MY.SendCredential` cannot read the lxplus DAG dir it watches
- **Where.** B1's new line (L442-443), "a `ServiceJob` drops `MY.SendCredential` … a service gets its inputs by
  transfer and needs no ticket", which B2 inherits through "`svc<i>.sub` = its keys" (L545-546); round-7 decision 1
  in `m68b-exit-items.md`.
- **Why it changes code.**
  - The premise holds for an attached `ServiceJob`, not for B2's watch mode. There the SERVICE node reads
    `<dag_dir>/driver.url` and `<dag_dir>/graphed-secret` directly from inside the job every second (L570-571,
    "The SERVICE node reads it from `dag_dir`"), and on lxplus `dag_dir` must lie under `job_root = "/afs"`.
  - The only measured in-job AFS access on lxplus is with the credential: m67's driver job (profile keys with
    `MY.SendCredential = "True"`, `sites.py:74`) had `KRB5CCNAME=FILE:/srv/lgray.cc` and wrote `pilots/` under
    `/afs/…/graphed-m67-site/a` (`probes/site-lxplus/m67-driverless.txt`). A credential-less job gets no ticket and so
    no AFS token; a DAG dir holding a secret is not `system:anyuser` readable (§9 relies on its ACL). Unmeasured at
    lxplus (unreachable), but nothing in the plan says why it would work, and the round-7 decision's reasoning
    ("a service gets its inputs by transfer") does not cover watch mode.
  - Failure mode if wrong: the SERVICE node never announces, each driver start times out, and every lxplus
    driverless Triton run fails after three × `timeout_s` — the headline B2 run.
  - Keeping the credential in watch mode costs no exposure that B1 has not already closed: B1's `service/` subdir
    keeps the ticket cache out of the child's served cwd (`probe_announce_rules.txt` L9).
  - The implementer must decide: `ServiceJob(..., watch=…)` keeps the profile's `MY.SendCredential` (B1's drop only
    for the attached path), or B2 states another way the node reads `dag_dir`.
- **Measurement.** `m67-driverless.txt` (ticket in scratch, in-job AFS writes, both with the credential);
  `sites.py:74`; plan L442-443 against L570-571 and site check (2) (L606-608: "the SERVICE node reading
  `driver.url`/`graphed-secret` on AFS"), which also does not record the node's `klist`.
- **Closed when.** B2 says a watch-mode `ServiceJob` keeps the profile's `MY.SendCredential` (and why: it reads
  `dag_dir` in the job), or states a deliberate alternative; the round-7 decision is scoped to the attached path;
  site check (2) records the SERVICE node's `klist` and that `service/` holds no ticket cache.
- **Test.** In `test_driverless_dag.py`, on `dataclasses.replace(SITES["lxplus"], job_root=<tmp>)` registered with
  `monkeypatch.setitem`, a DAG's `svc0.sub` carries `MY.SendCredential = True` (control: B1's attached `ServiceJob`
  on `SITES["lxplus"]` still has none, as B1's row already asserts). An implementation that inherits B1's drop fails
  it; the current rows pass it.

## Not raised (exit items)
Under "## r14-B2 exit items" in `plan/reviews/m68b-exit-items.md`.

## Cleanup
No container or background process was started; no `r14b2-` containers exist. Scratch unused.
