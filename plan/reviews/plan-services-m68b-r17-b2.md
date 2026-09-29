**NOT CLEAN**

# Review r17-B2: plan-services.md §3.3 part B2, whole-part read after the owner-directed redesign

Snapshot: `plan/reviews/plan-services-m68b-r17-b2-snapshot.md`. Scope: the B2 ladder rows (L415–431), the shared
"HTCondor behaviour relied on" subsection (L432–452) as it binds B2, "#### B2" (L569–683), B2's frozen rows, "Fails on
(B2)" and commits (L684–726), the §6/§7/§8/§9 items assigned to B2, and D3/D4/D6 on the DAG path. Code read:
graphed-executors `c2298d7` (`htcondor_backend/{driverless,driver,launch,sites,backend}.py`, `tests/frozen/m67/*`,
`docs/htcondor.rst`, `.github/workflows/ci.yml`).

One design finding: M45-B2. The exit items are appended under "## r17-B2 exit items" in `m68b-exit-items.md`.

## What holds
- **Every HTCondor/DAGMan behaviour B2 relies on maps to a NEEDS/RESULTS row whose observation matches, with one
  gap now measured.**
  - Strictness override: `AddToEnv: _CONDOR_DAGMAN_USE_STRICT=0` turns an idle or held SERVICE node at DAG end into
    DAGMan exit 0 (D-06, D-S `idle-/held-AddToEnv-strict0`).
  - Outcome from the latest driver try: each RETRY is a new cluster (D-08).
  - Held from a driver-node query, not `DAG_JobsHeld` (D-07, D-S `driver-held-counter`: node JobStatus 5 at once,
    counter 293 s later).
  - A fresh run directory with no `force` (D-01, D-02, D-04), made before submit (S-03).
  - The placeholder `result.pkl` prevents the S-15 hold.
  - The one behaviour the matrix left unpinned is that DAGMan's `RETRY … UNLESS-EXIT 3` retries a driver that dies
    by signal. D-08's probes are exit codes only. I measured it: `probes/m68b/probe_r17_b2_sigretry.txt`. A SIGKILLed
    try with a placeholder present is never held, is retried three times, and its ads carry `ExitBySignal`. A failed
    `exec` (rc 127) is retried the same way. Both end with DAGMan `ExitCode 1` and the placeholder in the run dir. The
    plan's claim at L655 holds; only its citation is short (exit item).
- **Nothing relies on a not-assumable knob.** B2 reads no `DAG_*` counter, no `DAG_Status` and no DAGMan
  `ExitCode`. `periodic_remove` is slot hygiene only. `SendCredential` comes only from the lxplus row.
- **The `from_dag` fixture is stable across the bindings CI installs.** The PyPI wheel 25.14.1 produces
  `probe_dag_service.txt`'s 25.13.2 description under B2's exact options, identical after the DAG-dir, CsdVersion and
  dagman-path substitutions, including `-insert_env _CONDOR_DAGMAN_USE_STRICT=0` and the `environment` order
  (`probes/m68b/probe_r17_b2_fromdag_wheel.txt`).
- **m67's frozen suite stays unmodified and green under B2's changes.**
  - `job_root` replaces `_SELF_SUBMIT_ROOT` (`driverless.py:33,174-179`).
  - The `worker_ports` refusal still precedes the root check, so `test_condor_pilots_are_refused_on_a_profile_without_worker_ports` (a six-kwarg profile, `job_root=None`) still matches `worker_ports`.
  - Generic `"/"` keeps `test_driverless_payload.py:147` and live (b) submitting.
  - lxplus outside `/afs` still names `/afs` (`:225-236`).
  - `driver.sh` is read only by name (`:106-107`).
  - The live tests exec the driver through `driver.sh`, and the driver overwrites the placeholder on every exit it
    reaches (`driver.py:350`).
- **The plain-job behaviour change is consistent with D6.**
  - Before: a killed driver was held (S-15).
  - Now: it completes by signal, is retried by `max_retries` (L-06: SIGKILL retried, since `OnExitRemove` tests only
    `ExitCode` 0/3), and is `failed` in `_poll`, because JobStatus 4 with no `ExitCode` is not 0.
  - `result()` then raises the placeholder `RuntimeError`. That is "environment → retried by the one owner".
  - m67's docs do not yet describe it (exit item).
- **The in-job leg is consistent with §3.1.**
  - Leg 3 goes cluster-hosted iff `host_service` is callable, independent of `service_hosts` (§3.1 L262/L272). So the
    in-job backend with `service_hosts == ("driver",)` and `announced` non-empty routes GPU/imaged specs to the
    announce.
  - The outer `ServiceSet` sits outside the `runner.run` try, so a SERVICE node that never announces exits 1. That
    matches "up to three × `timeout_s`".
  - The m68a exit item (announced identity on the status) is met.
- **The watch-mode re-announce to a retried driver works.** It is shown by `probe_dag_service.txt` R (two starts,
  two announces) and pinned by B1's watch leg.
- **Commits and partition.** B2-0 is ~550 test lines and B2-2 is ~500. The docs commit is ~170. The §7 m68b totals
  (~1.5k src+ci+docs, ~1.3k tests) add up from the B1 and B2 commits. The all-OS `test` job lists
  `test_driverless_dag`. The CI pool sets `MOUNT_UNDER_SCRATCH =`, so the SERVICE node reads a `dag_dir` under
  `tmp_path` (ci.yml:277-279).

## M45-B2: `status()` has no rule for a DAGMan ad at JobStatus 4 in the queue, so the no-retrieve test can pass vacuously
- **Where.** L636–644 (Tracking) and the B2 row L697 ("on a `spool=True` profile with the DAGMan ad still queued at
  `JobStatus` 4 its `result()` makes no `retrieve` call (m67's would)").
- **Why it changes code.** The rule has three clauses. None of them covers the case the frozen row constructs, a
  DAGMan ad in the queue at JobStatus 4:
  - DAGMan's own ad gives `removed` (3) and `held` (5).
  - "while DAGMan runs", a driver-node query gives `held`, else `running`/`queued`.
  - "once DAGMan has left the queue", the latest driver try decides.

  The implementer must choose between two readings:
  - (a) Map it through "while DAGMan runs" to `running`/`queued`. Then `result()` refuses with "no result yet" before
    any read, and the "no retrieve" assertion holds without exercising anything. An implementation that keeps m67's
    `if in_queue and spool: retrieve` for a done DAG also passes, which is the property the leg exists to catch.
  - (b) Treat JobStatus 4 as finished and read the driver tries.

  Only (b) makes the leg a witness. The same gap leaves the DAGMan-idle (JobStatus 1) and no-driver-ad-in-queue cases
  to be invented, though those two are harmless.
- **Measurement.** `driverless.py:74-76,99-100`: m67 maps JobStatus 4 by the ad's own `ExitCode` and retrieves
  whenever it is in the queue on a spooled profile. L-01 says an unspooled DAGMan leaves the queue at completion, so
  the queued-4 state arises only in the test's recorder. The test therefore defines what it pins.
- **Closed when.** L636–644 say which DAGMan state leads to which result:
  - JobStatus 4, queued or in history, takes the latest driver try's outcome.
  - JobStatus 3 gives `removed` and 5 gives `held`.
  - JobStatus 1/2 uses the driver-node query: `held` if that node is held, `running` if it runs, else `queued`.
- **Test.** L697's spool leg:
  - The queued-4 DAGMan ad sits beside a driver history ad with `ExitCode 0` and a `result.pkl` in the run dir.
    `result()` returns that value, and the recorder logged no `retrieve`.
  - Control: the same ads with `dag=False` make m67's `retrieve` call.

## Evidence
- `probes/m68b/probe_r17_b2_sigretry.{py,txt}`: DAG RETRY of a signal-killed or exec-failed driver with a placeholder
  present. Never held; three tries; the last try's ad decides.
- `probes/m68b/probe_r17_b2_fromdag_wheel.txt`: the 25.14.1 wheel's `from_dag` description under B2's options.
- Container `r17b2-dag` (htcondor/mini) was started and removed. Scratch was `/tmp/claude-0/review-r17-b2/` (a venv
  holding the 25.14.1 wheel).
