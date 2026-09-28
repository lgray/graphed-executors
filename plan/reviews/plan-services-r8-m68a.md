# Review r8 — `plan-services.md`, unit m68a (delta vs `plan-services-r7-snapshot.md`)

**Verdict: NOT CLEAN — 2 design findings (N3, N4), both one-clause decisions the dispatch can make.** r7's N1 and N2
are closed at their causes. No whole-unit pass was run, because the delta returned findings.

Probes were read-only against `~/vibe-coding/lanes/driverless/graphed-executors` (head 386d65d), run with the driverless
`.venv` python and `PYTHONDONTWRITEBYTECODE=1`. The script is `probes/services-code/probe_driver_job_r8.py`; its output
is in `probe_driver_job_r8.txt`. For the r8 run only its `image` argument was fixed. Merged graphed-side code was read in
`lanes/svc-graphed/graphed`.

## r7 findings
- **N1 closed at the cause.** `driver.py` passes `in_job=SITES[run.site]` (§3.1 L261-267), so the driver-job backend's
  service data now comes from the run's own site row. Before the change, `_runner` gives the launcher's profile:
  - probe `L`: `pilots="local"` resolves to profile `generic` for both `site=lpc` and `site=lxplus`;
  - probe `C`: an lxplus-shaped row gives `service_hosts=('cluster',)` and `service_ports=None`.
  The in_job values the plan picks are the ones the task server already uses:
  - the task server binds `127.0.0.1:10000` in the slot (probe L);
  - it binds `<Machine>:10000` under `pilots="condor"` (probe C), and on lxplus live
    (`probes/site-lxplus/m67-driverless.txt:141`, `b9p16p6451.cern.ch:10000`).
  Identity:
  - Both the driver's `machine_host()` and the pilots' equal the ad's `Machine` (`slot-host.example`).
  - `FULL_HOSTNAME` (`login-or-container.example`) is not that name.
  - `launch._htcondor()` raises `ImportError` with `sys.modules["htcondor2"]=None`, so the module function is the only
    identity that is correct and free of bindings.
  - `ServiceSpec.ports` defaults to `(10000, 10100)` (`graphed/services.py:91`), so "a free port of the spec's
    `ports`" is well defined.
- **N2 closed at the cause.** D10 L100, §3.1 L245 and L250-251 now define `host_service(spec) -> (endpoint, identity)`
  and the per-leg identity. The two-host fake row pins both paths:
  - refuse when only B answers;
  - pass when A or a third host answers.
  This matches D2 L49-51. `None` for user/site means any passing answer passes, which is consistent with "resubmitted
  until an identity other than the service's answers". The condor (L357-358), dask (L407) and parsl (L415)
  implementations each return `(endpoint, identity)`. No mention of `host_service` treats it as endpoint-only (grep of
  `host_service` over the file).

## Design findings

**N3 · `test_services_sites.py` (L284), the driver-job rows · the N1 guard can pass without the N1 fix.** The row says
"a driver-job backend" but does not say how it is built. Two readings of the row are too weak:
- *Direct construction.* A test built as `HTCondorBackend(LocalPilots(...), n, in_job=SITES[...])` never runs
  `driver.py`. A `driver.py` that omits `in_job` (the r7 cause) then passes every m68a frozen row.
  `test_driverless_endpoints.py` does not catch it either: its site is unstated, and with the generic fallback a
  driver-hosted histserv starts anyway.
- *Through `_runner`, lxplus leg.* The lxplus `pilots="local"` leg does not discriminate the missing `in_job`. Probe L
  shows `_runner` falls back to `generic`, whose `service_hosts` holds `"driver"`, so `http_server` starts with or
  without `in_job`.
- *The lpc `"driver" in service_hosts` clause.* It cannot fail either way, because lpc and generic both hold
  `"driver"`.
- Only `site_services == SITES["lpc"].services` discriminates (generic's `{}` against lpc's EAF row), and only when
  the backend comes from `driver._runner`.

**Closed by:** the driver-job rows build the backend through `driver._runner(run_json_dict, tmp, log)`. Probe L
builds it that way on macOS with the bindings blocked, so it works on all OS. The lxplus leg asserts the backend's
`service_hosts == ("driver",)`, which fails both for the attached lxplus row (`("cluster",)`) and for the generic
fallback (`("driver","cluster")`). Delete the lpc `"driver" in service_hosts` clause.

**N4 · D6 L77-79 (edited this round) × §3.1 L270-273 (`driver.py` runs `ServiceSet` in the job) · a service refusal
in a driver job has no stated exit code.**
- r7's D6 said "exit 3 = an exception raised inside `runner.run(plan)`", which covered it.
- r8 narrows exit 3 to "a `StageError` raised by the plan's own code" and exit 1 to worker loss "or any exception
  before or after `runner.run`".
- m68a adds the first non-`StageError` exceptions raised *inside* `runner.run`: `ServiceUnavailable` and
  `ServiceUnreachable`, from `ServiceSet.start`/`probe` in `SubmitRunner.run`. `_result` re-raises ordinary exceptions
  intact (`engine.py:626-635`).
- m67's `_exit_code` (`driver.py:85-88`) sends every non-`KilledWorker` exception to 3, so they would exit 3 and not be
  retried. D6 no longer says that.
- The implementer must choose between that code and D6's categories. The choice decides whether a probe failure on an
  lxplus `pilots="condor"` driver (placement-dependent) or a transiently dead EAF leg gets the job's 2 retries.
- The owner ruling (journal 18:05Z/18:50Z) covers `StageError`s only.

**Closed by** one D6 clause chosen in the dispatch. Recommended, on the owner's axis (deterministic → 3, environmental
→ 1): "exit 3 only for a plan `StageError`; every other exception, service refusals included, exits 1." The code is
one line: `_exit_code` returns 3 iff `isinstance(exc, StageError) and not lost`. That change is safe for m67's pins:
- `test_driver_entry.py:152` uses a poisoned-plan `StageError`;
- `tests/extra/m67/test_m67_driver.py:131` uses `("fail", 3, "ValueError")`, which is StageError-wrapped.

Add a `test_driverless_endpoints.py` leg: a user endpoint that is dead under `pilots="local"` exits 1, with
`ServiceUnavailable` in `result.pkl`.

## Exit-round constraints (to the implementer)
- **E8** For the in-job `pilots="local"` backend, `service_ports` is `None` / absent, and the engine reads
  `getattr(backend, "service_ports", None) or spec.ports`. §3.1 L243 says "others: the spec's ports" but not the
  `None` case. The task server already holds 10000 on `127.0.0.1` in the slot (probe L). The engine's pick must
  try-bind on `advertise_host`, not assume the range's first port.
- **E9** Label the in-job backend's `host_identity` (attribute or absent) either way: both yield the module function
  (D2 L47-48).
- **For the m68b reviewer (not this unit):** §3.3 L384's `announce_only` in-job leg resolves from the announce, not
  `host_service`, so the per-leg `ServiceStatus.identity` rule (L250-251) does not name its identity. It should be the
  announced one. m68b's condor `host_service` is absent in a job (`in_job` gives `("driver",)`), which is consistent
  with r7's note.
- r7's E1–E7 still stand as constraints.
