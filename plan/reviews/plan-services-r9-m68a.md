# Review r9 — `plan-services.md`, unit m68a (delta vs `plan-services-r8-snapshot.md`)

**Verdict: NOT CLEAN — 1 design finding (N5), a one-line cut plus one frozen leg that the dispatch can carry.**
r8's N3 and N4 are closed at their causes. No whole-unit pass was run, because the delta returned a finding.

Probes were read-only against `~/vibe-coding/lanes/driverless/graphed-executors` (head 386d65d), run with the driverless
`.venv` python and `PYTHONDONTWRITEBYTECODE=1`: `probes/services-code/probe_driver_job_r8.{py,txt}`,
`probe_exit_code_r8.{py,txt}`, and the new `probe_refusal_pickle_r9.{py,txt}`.

## r8 findings
- **N3 closed at the cause.** The §3.1 `test_services_sites.py` row now builds the driver-job backends as
  `driver._runner({...}).backend` and never through `HTCondorBackend(..., in_job=)` directly. `SubmitRunner.backend`
  exists (`submit/engine.py:270`), and probe_driver_job_r8 L builds it this way on macOS with the bindings blocked.
  Both legs now assert `service_hosts == ("driver",)`, which neither of the wrong states can satisfy:
  - the launcher fallback: `_runner` resolves to profile `generic`, which gives `("driver","cluster")` (probe L, both
    sites);
  - the attached row gives lpc `("driver","cluster")` and lxplus `("cluster",)` (probe_exit_code_r8.txt tail).

  The clause that could never fail is gone.
- **N4 closed at the cause.** D6 and §3.1 now say how `_exit_code` sorts exceptions by type: `KilledWorker`
  StageError, `ServiceUnavailable` and `ServiceUnreachable` exit 1; any other exception from `runner.run` exits 3.
  - The plan measured why the r8 recommendation (only a StageError exits 3) was wrong: a task's `ValueError` reaches
    `_exit_code` unwrapped (probe_exit_code_r8 F: `type=ValueError is_StageError=False`, exit 3). Under that rule a
    deterministic plan error would have been retried.
  - This matches the owner ruling: a plan StageError exits 3, and worker loss exits 1.
  - The new `test_driverless_endpoints.py` leg pins both directions. A dead endpoint exits 1, and m67 fails this (probe
    S: `_exit_code(ServiceUnavailable)=3`). A raised `ValueError` exits 3 intact, and the StageError-only rule fails
    this.
- **D10 consistency (m68b/m70).**
  - Every `host_service` mention returns `(endpoint, identity)`: L103, L248, L361-363, L406-414, L420.
  - In a driver job, condor's `host_service` is absent, because `service_hosts=("driver",)` and L361 binds it iff
    `"cluster"` is in that tuple. That agrees with §3.1 L270.

## Design findings

**N5 · `driver._result_blob` (m67, `driver.py:76-82`) × D6/§3.1 (a refusal becomes the run's `result.pkl`) · a
refusal that dumps but cannot be loaded breaks the submitter's collect.**
- `_result_blob` only checks `pickle.dumps`. The submitter reads the file with `pickle.loads` at `driverless.py:101`.
- An exception whose `__init__` takes different arguments than its `args` dumps cleanly and fails on load. The
  signatures in §3.1, `ServiceUnavailable(name, legs)` and `ServiceUnreachable(name, endpoint, worker, reason)`, lead
  to exactly that natural form:
  - probe_refusal_pickle_r9: the natural `ServiceUnreachable` gives `dumps ok, loads raises TypeError: ... missing 3
    required positional arguments`;
  - with StageError's `__reduce__` idiom (`graphed/debug/errors.py:73`) it loads.
- The effect: `DriverlessRun.result()` raises a `TypeError` about `__init__` in place of the refusal and its reason.
- The frozen leg that expects `ServiceUnavailable` in `result.pkl` forces that one class to be picklable.
  `ServiceUnreachable` is not pinned. The same failure hits any user exception with extra arguments, which arrives
  unwrapped (leg F).

**Closed by:**
1. `_result_blob` round-trips its blob (`pickle.loads(blob)` inside the existing `try`). A failure falls back to the
   existing text `RuntimeError`.
2. Both refusals pickle by StageError's `__reduce__` idiom, and keep a `__str__` that names the reason: under that
   idiom `args` is empty, and probe r9 shows `str=''`.
3. A frozen leg: `pickle.loads(driver._result_blob(False, ServiceUnreachable(...)))` returns a `ServiceUnreachable`
   whose `reason` is intact.

## Exit-round constraints (to the implementer)
- **E10** In D6, "(owner ruling 2026-09-25)" sits after "Exit 0 = done". The ruling covers exit 3 for a StageError
  and exit 1 for worker loss. It does not cover exit 3 for an unwrapped task exception or exit 1 for a service
  refusal: those are this plan's decisions. Label them as such in the docstring of `driver.py`. That docstring also
  still says "1 anything else" and needs the new classification.
- **E11** Drop "(m67 maps them to 3)" from §3.1 L276 when it is carried into code or docs, because it is history.
- Considered, not raised: under D6 a deterministic `ServiceUnavailable` (no leg configured, or a GPU recipe with no
  `host_service`) exits 1 and uses the job's 2 retries. The plan states this choice ("endpoints and placement are
  environment"). The cost is bounded, and the reason still reaches `result.pkl`.
- r8's E8, E9 and r7's E1–E7 still stand.
