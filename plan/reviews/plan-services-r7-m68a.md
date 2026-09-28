# Review r7 — `plan-services.md` (625 lines), unit m68a (§3.1 + D1/D2/D4/D7/D10, §6/§7/§8/§9 lines)

Delta read against `reviews/plan-services-r6-snapshot.md`. Code probes ran read-only against the m67 implementation clone
(`~/vibe-coding/lanes/driverless/graphed-executors`, head 9450e3d) with `PYTHONDONTWRITEBYTECODE=1`; probe script copied
to `probes/services-code/probe_driver_profile_r7.py`. No commit, no lane clone written, no cluster job.

## r6 findings (m68a side)
- **M7 closed.** `submit_driverless(..., services=)` runs `split_endpoint` before any bindings call into
  `run.json.endpoints` (L250-252); `test_driverless_endpoints.py` pins "a bare `host:port` there refused with the
  recorder call list empty" (L275).
- **M10 closed.** The §3 preamble (L197-200) fixes one External param set (`graphed_identity`, `INPUT0`→`OUTPUT0`) for
  the CI container, lxplus and EAF; §6 (L569-571) puts the python-backend twin at `tests/frozen/m68a/data/triton_models/`;
  the LPC leg-2 transcript infers on it (L263-266, P9 `REPORT.md`: READY, bit-for-bit from cmswn2186).
- **M9 (m68a side): the attached-run rule is closed; the driver-job side and the seam are not (N1, N2).** D2 L46-51
  defines `host_identity()` and the pass rule without the loopback skip; `probe_ready_identity.txt` shows LocalCluster
  workers equal the driver's identity; P-g shows LPC/lxplus login `FULL_HOSTNAME = getfqdn` and CI slot `Machine =
  FULL_HOSTNAME`, so `test_services_live.py` (a) passes as written.

## Design findings

**N1 · §3.1 L255-256 (`HTCondorBackend`: `site_services`/`service_ports`/`service_hosts` = the profile's;
`host_identity()` = `htc.param["FULL_HOSTNAME"]`) + L252-254 (`driver.py` runs `ServiceSet` in the driver job) · inside a
driver job the backend's service data has no stated source. The login-node definitions apply by default and are wrong
there.** One cause with two symptoms:
- *Wrong site.* `driver._runner` builds `HTCondorBackend(LocalPilots(...), ...)` for `pilots="local"`, and the backend
  takes its profile from `getattr(launcher, "profile", SITES["generic"])`. `LocalPilots` has no `profile`. Measured
  (`probe_driver_profile_r7.py`): `run.site=lpc` → backend profile `generic`; `run.site=lxplus` → `generic`;
  control `CondorPilots(lpc).profile` → `lpc`. So on the LPC fat slot (D6, the path the plan names "the LPC managed
  path") `site_services` = generic `{}`. Leg 2 never sees the EAF row, and a Triton spec falls to leg 3, which is
  refused in m68a with no `host_service`. The same run attached resolves by leg 2. For `pilots="condor"` the
  profile's `service_ports`/`service_hosts` are login-node reachability. lxplus has `service_ports=None`, so
  `("cluster",)`, which refuses the driver-hosted "on the driver's worker port" leg that L253-254 and D3 promise.
- *Bindings in the job.* D2 L47-48 limits `FULL_HOSTNAME` to "condor outside a job", but §3.1 L256 is unconditional,
  and the engine takes the driver's identity from `backend.host_identity` when present (D2). In `driver.py` that is
  an `htcondor2` import. `test_driverless_endpoints.py` is "(all OS)", and the all-OS `test` job installs `.[dev]`
  only. Measured: `ci.yml` test job `pip install -e ".[dev]"`, and `htcondor2` is only in `test-htcondor`
  (`.[dev,htcondor]`). pyproject says "the htcondor bindings ship Linux wheels only". `python -c "import htcondor2"`
  → `ModuleNotFoundError`. So that row fails on every all-OS leg, and m67's "imports no bindings unless
  `pilots == "condor"`" (L151) breaks. In a container job `FULL_HOSTNAME` would also not be the `Machine` the pilots
  report (P8: fabricated `gethostname`).
- **Closed by one decision at `driver.py`/`HTCondorBackend`:**
  - The driver job's backend carries the run's site profile (`SITES[run.site]`, not the launcher's).
  - Its driver-hosted reachability is the task server's own: `pilots="local"` → `"driver"` allowed, bound on
    `127.0.0.1`, any free port; `pilots="condor"` → `worker_ports` on `Machine`.
  - `host_identity()` in a job is the module `host_identity()`, with no bindings. `htc.param["FULL_HOSTNAME"]` is
    only for an attached `CondorPilots` driver.
- **Tests:**
  - `test_driverless_endpoints.py` already witnesses the no-bindings leg on all OS.
  - `test_services_sites.py` adds: a driver-job backend for `site="lpc"` has `site_services == SITES["lpc"].services`
    and `"driver" in service_hosts`, and with a synthetic `$_CONDOR_MACHINE_AD` and `sys.modules["htcondor2"] = None`
    its `host_identity()` returns the ad's `Machine`.
  - A driver-job backend for `site="lxplus"`, `pilots="local"`, starts a driver-hosted `http_server`.

**N2 · D10 L96-97 (`host_service(spec) -> endpoint`) + §3.1 L245 ("cluster-hosted → the one it announces") · the
probe needs the service's identity, and the seam m68a defines returns only the endpoint.**
- All three implementations receive the identity: condor `/announce` carries `name host:port identity` (L341), the
  dask Variable holds `(host, port, pid, host_identity())` (L394), and the parsl announce carries `identity` (L404).
  But each returns only the endpoint (L346-347 "returns the endpoint minted").
- The engine's pass rule (D2 L49-51, §3.1 L242-245) compares answers against that identity. m68a writes both the
  engine side of D10 and the two-host fake whose "service on a host ≠ the driver's" is the refusal leg (L271). The
  test author cannot write that fake without inventing the interface.
- Legs 1-2 have no identity defined at all (L245 names driver-hosted and cluster-hosted only).
- Measured: `grep -no 'host_service(spec)[^;,]*'` → L96 `host_service(spec) -> endpoint`, L240, L346. `grep -no
  'identity: driver-hosted[^.]*\.'` → L245 only.
- **Closed by:** D10 `host_service(spec) -> (endpoint, identity)`, and `ServiceStatus.identity` set per leg:
  driver-hosted = the driver's; cluster-hosted = returned; user/site = `None`, where any passing answer passes.
  `test_services_protocol.py`'s two-host fake returns host B's identity from `host_service`, and the refusal leg is
  answers only from B with the driver on A.

## Exit-round constraints (to the dispatch)
- **E1** m67 already has the rule as `driver.machine_host()` (`driver.py:35`). Make one definition,
  `submit/services.host_identity`, and have `driver.py` call it. The plan never names `host_identity`'s module.
- **E2 (r6 C6, still unstated)** `test_triton_service_ref.py`'s harness binds a listener that passes the declared spec's
  check: a TCP accept for `tcp`, or the in-process health servicer for `grpc:`.
- **E3 (r6 C4)** `test_driverless_endpoints.py` imports histserv, so it uses `importorskip("histserv")`
  (`test-experimental` 3.14t has no cp314t grpcio).
- **E4 (r6 C2/C3)** One mint helper in `submit/services.py` serves the driver-hosted `Popen` and, later,
  `host_service`. `check_ready`'s docstring/comments must not say "Triton" (the packaging grep covers the whole of
  `services.py`).
- **E5** m67's `run.json` field note `announce_only: [] (m68)` (L148) now means m68b.
- **E6** The `test_services_packaging.py` README sentence cites plan sections ("§3.1, §3.3, §3.4"). Frozen text should
  name the test files, not plan coordinates.
- **E7** The LPC leg-2 transcript (L263-266) should say whether it is attached or driverless. After N1, driverless
  also resolves by leg 2.
- **For the m68b reviewer (not this unit):** L345 binds `host_service` iff `"cluster" in profile.service_hosts`, and
  inherits N1's profile source. With the generic fallback, an LPC fat-slot driver job would get a condor
  `host_service`, but a job cannot submit at LPC (P2).

## Self-sufficiency
- The frozen table, files and symbols, commits (freeze ~1.3k, then ~750/~200/~250) and the PR are complete for m68a.
- It stacks on m67 and the graphed m68 PR, consistent with §7 L587-591.
- Nothing it needs is defined only in m68b/m70: the GPU refusal names the absent attribute (L256-257, L271). N2
  changes m68b/m70's return value, which they have not been written against yet.

## Verdict
**NOT CLEAN** on N1 and N2. Both are sentence-level decisions, and the closing text is given above. N1 is one
cause: the driver-job backend's service data. Its two symptoms (site profile, bindings-backed identity) are cut
together at `driver.py`/`HTCondorBackend`. The count is 2 against executors m68's 3 at r6, so the loop is converging.
