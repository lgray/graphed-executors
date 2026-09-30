# Plan — services arc on the HTCondor backend (m67 driverless · m68 services (graphed, executors m68a/m68b) · m69a H→γγ · m69b histserv · m70 dask/parsl hosting)

Extends `plan.md` (m66): its §1 shape, D1–D7, ladders, file tables, frozen-test style and commit bands hold and are
not restated. Evidence lives in `probes/` and `journal.md` (including the grep showing ids m67–m70 free in all
three repos); this file states decisions.

**Cut:** m67 = driverless without services (a direct driver job). Executors m68 is two units (owner): **m68a** = the
engine service set (three legs, checks, probe, recipes), driver-hosted services, the site table with LPC's EAF row,
driverless endpoints; **m68b** = condor cluster-hosted services, the DAGMan path (driver JOB + SERVICE nodes), the
lxplus GPU/Triton run. **m69a** = the H→γγ translation alone, on the released packages (graphed 0.0.6, histogram
0.0.4, the coffea fork b2612ab, uproot ca3a8a2); **m69b** = histserv backing, the six diagnostic fills and the site
run; **m70** = cluster-hosted services on dask and parsl. One graphed PR (m68) carries the service surface and its
preservation; §7 orders the PRs.

- **D1 the service description is analysis data, owned by graphed.** `graphed.services.ServiceSpec(name, kind, check,
  ports, launch, timeout_s)` is a frozen, JSON-round-tripping record in two parts. The **requirement**: `name` is what
  nodes and fills reference, `kind` a free string the site table matches on, `check` the readiness rule (`"tcp"`,
  `"http:<path>"`, or `"grpc:<service>"` = the standard `grpc.health.v1` Check), `ports` the range a managed instance
  may bind. The optional **recipe** `launch=Launch(argv, image, inputs, env, resources)` (argv templates
  `{port}`/`{host}`/`{python}`, rendered where the service starts; `image` a cvmfs path or registry ref; `resources` =
  `cpus`/`memory_mb`/`gpus`); a requirement without one is satisfiable by legs 1–2 only. The core names no service:
  `graphed_executors.submit.recipes` (`triton(…)`, `http_server(…)`) and `graphed_histogram.remote.histserv_spec` are
  plain data constructors, and the generic `http_server` recipe runs the whole path in the frozen suite. A `Session`
  holds the declared specs; a node references one by name (`params["service"]`) and recording refuses an undeclared
  name, naming the declared ones. The runtime `Plan` and the `DurablePlan` carry the referenced specs (`services`, a
  key written only when non-empty, so a plan without services serializes byte-identically to today); the bundle
  manifest carries them the same way (`"services"` beside `"externals"`, present only when the IR references one, like
  `"variations"`) and `inspect()` lists them. The run-time endpoint map is provenance of a run, not of the analysis:
  it rides the `RunReport` (`endpoints`), attached outside the manifest and fingerprint (m65c), and `inspect()` prints
  it under each run report. **An endpoint is `scheme://host:port`**, scheme ∈ `tcp`/`http`/`https`/`grpc`/`grpcs`
  (`graphed.services.split_endpoint(e) -> (scheme, "host:port")` refuses all else, bare `host:port` too). The wire
  (protocol + TLS) lives on the endpoint because one requirement is met on different wires (the EAF Triton: gRPC+TLS
  on :443; a managed one: plaintext on a worker port); `check` runs only over a wire that carries it
  (`http:`↔`http(s)`, `grpc:`↔`grpc(s)`, `tcp` any; otherwise the leg fails naming both, undialled), because the EAF
  gateway answers HTTP 200 on every path (P8).
- **D2 executors satisfy a surface in three legs, in order.** For each spec of `plan.services`: (1) a user endpoint
  (`SubmitRunner(..., services={name: endpoint})`) — checked, and a failing one refuses the run naming it (an explicit
  instruction is never silently replaced); (2) a site endpoint (`SiteProfile.services`, by `kind`; any backend may
  expose `site_services`) — checked, a failing one falls through and the status records it; (3) managed spin-up with
  the backend in use, which needs `launch`: driver-hosted when the recipe has no image and no GPUs and the site allows
  it (`"driver" in service_hosts`), else cluster-hosted where the backend has a `host_service` attribute (D10); a
  managed instance is plaintext, its endpoint minted with the check's scheme (`http:` → `http://`, `grpc:` →
  `grpc://`, `tcp` → `tcp://`). Nothing left → `ServiceUnavailable(name)` naming the three legs and why each failed.
  A managed service lives in the scope of the submission that started it (§3.1); to keep one warm across plans the
  user holds a started `ServiceSet` (user scope) and passes its endpoints as leg 1.
  Endpoints bind before the first plan-task submit through graphed's `bind_services(plan, endpoints)`, which calls the
  process's duck-typed hook that graphed's composites forward (no `RunContext` field, pilot registry or `/hello` change). Readiness = the check where the service runs, then the same
  check from worker-side probe tasks (§3.1). Host identity is one function on every side: `host_identity()` =
  `Machine` from `$_CONDOR_MACHINE_AD` when set, else `socket.getfqdn()`; a backend may supply the driver's
  (`backend.host_identity`, duck-typed; condor outside a job: `htc.param["FULL_HOSTNAME"]`, the name condor writes as
  `Machine` for that host's slots, P-g). The probe passes on a passing answer from an identity ≠ the service's, or,
  when every answer carries the service's identity, iff that is the driver's too (one machine: `ThreadBackend`,
  `LocalCluster`, one-node HTEX or pool).
- **D3 condor placement.** Attached runs: driver-hosted = a subprocess beside the driver; cluster-hosted = a second
  one-job cluster (`ServiceJob`) announcing its endpoint to the task server. Driverless runs: driver-hosted = a
  subprocess inside the driver job (the LPC managed path, next to `LocalPilots` on the fat slot; reachable from
  self-submitted pilots through `worker_ports`); cluster-hosted = a DAG SERVICE node DAGMan removes when the DAG
  ends (`probes/m68b/probe_dag_service.txt`), allowed only where the DAG dir lies under the site's
  `SiteProfile.job_root` (lxplus `/afs`, generic `/`, LPC none; §3.3) and refused naming that field.
- **D4 reachability is site data + a runtime check.** `service_ports` (login-node ports workers reach, for attached
  driver-hosted services) and `worker_ports` (worker↔worker); `service_hosts` derives from them; `services` (kind →
  endpoint) is the site's hosted-service table. Measured: LPC `worker_ports=(10000, 10100)` (inside the measured open
  10000–10101, P6), `service_ports=(10001, 10100)` (worker→login 10000 open, m66; the task server binds its
  `driver_ports` first, so the overlap cannot collide) → `("driver", "cluster")`, no GPUs (P4); `services={"triton":
  "grpcs://triton.fnal.gov:443"}` (the EAF Triton, reached from a batch worker, P8). lxplus `worker_ports=(10000,
  10100)` (exactly, P7), `service_ports=None` (the only open login port, 8786, is the task server's) → `("cluster",)`,
  `services={}`. `generic` both `(10000, 10100)`, `services={}`. Rule for any profile: a `None` range refuses the
  matching host at construction naming the row; both `None` → legs (1) and (2) only; a `services` value
  `split_endpoint` refuses fails construction naming the row (`services` lands in m68a, with that form).
- **D5 driverless payload** = stdlib-pickled runtime `Plan` (its `services` included) + `run.json` + `user_modules`
  (P2: 2.3 kB, runs in a fresh interpreter). Not `DurablePlan`: no executor accepts it, nothing converts an
  aggregate plan, and `run_resumable` never reads `plan.ir`.
- **D6 driverless per site.** LPC = one fat slot: the driver job runs `HTCondorRunner` over `LocalPilots(n)` with
  `request_cpus=n` (a job cannot submit, P2). lxplus = `pilots="condor"`: the driver job hosts the task server on a
  worker port and self-submits pilots (P5: submit from a job works with an explicit pool + schedd; inner jobs need an
  AFS iwd); the fat slot is its fallback. Results return as `transfer_output_files=result.pkl,driver.log`. Retries
  have one owner: outside a DAG the submit keys `max_retries=2, retry_until=3` (JDL: an integer `retry_until` is the
  exit code that ceases retries); inside a DAG `RETRY driver 2 UNLESS-EXIT 3` and no `max_retries` in the node `.sub`.
  Exit 1 = environment, retried by that owner (`JobMaxRetries` outside a DAG, `RETRY` inside): worker loss (a
  `StageError` from `KilledWorker`, e.g. every pilot preempted), or any exception before or after
  `runner.run(plan)` (`run.json`, unpickle, pilots, and in m68a the driver job's `ServiceSet`:
  endpoints and placement are environment). Exit 3 = every other exception from `runner.run(plan)`: the plan's
  own error, as a `StageError` or re-raised intact (a task's `ValueError` arrives unwrapped,
  `probes/services-code/probe_exit_code_r8.txt` leg F), deterministic, not retried. Exit 0 = done (owner ruling
  2026-09-25). `driver.main` classifies by phase, and only inside `runner.run(plan)` does `_exit_code` classify by
  type (m67's, plus the in-run service phase's types as 1, §3.1): the same `OSError` exits 1 before `runner.run` and 3 inside it
  (`probes/class/probe_phase_and_release_r14.txt` A). A service that fails mid-run surfaces in plan code and exits 3
  (owner item, §9). Follow-on, not designed: multi-node driverless at LPC via a `condor_chirp
  set_job_attr` / `schedd.query` rendezvous (chirp in the container unmeasured).
- **D7 Triton names a service.** `params["service"]` (a declared name) or `params["url"]` (literal, unchanged path),
  never both; bind fills the evaluator's `endpoint`; the per-process resource cache keys on `(kind, content_hash,
  endpoint, the params `load` reads)`: `ExternalPlugin.load_params: tuple[str, ...] = ()` names them (Triton `("url", "transport")`, every
  other built-in `()`), so nodes differing only in evaluate-time params (Triton `output_name`, correctionlib
  `systematic`) share one resource, as 0.0.6's `(kind, content_hash)` key shared it across universes. The endpoint's scheme picks the transport: `http(s)` → `tritonclient.http`, `grpc(s)` →
  `tritonclient.grpc`, `ssl=True` on the `s`, the client given the bare `host:port` (both refuse a scheme, P-b); a
  literal `url` without `://` stays 0.0.6's HTTP; `params["transport"]` still overrides.
- **D8 histserv backing lives on the reduce, not the IR.** `Histogram(..., backing="hists")` /
  `graphed_histogram.backed(h, "hists")` names a declared spec (`remote.histserv_spec(name)` builds the example
  recipe); IR, params, evaluator and replay id are unchanged (P4 §3a). The reduce ships (evaluators receive values
  only, `execute.py:260-271`; the fill needs the partition for its `unique_id`, and only the plan's `process` sees the
  partition, so a process wrapper hands it to the reduce). The fill path is §5.1: bind-time `init`, one `Fill` per
  partition keyed `unique_id=str(partition)`, a receipt through the tree, one memoized snapshot per receipt taken by
  graphed's `resolve_services(plan, value)` (§3.2) at the end of the run while the server is up (`unpack` reads it; a receipt no
  runner resolved snapshots at `unpack`), deletion when the run's services close; named dense axes only.
- **D9 the translation is all rewrites** (§4) on the released packages, validated chunk for chunk against the
  unedited original script.
- **D10 cluster hosting is one seam, three implementations.** A backend hosts cluster services iff
  `callable(getattr(backend, "host_service", None))` (the m47 transport-dispatch precedent): the capability IS the
  pair of duck-typed methods `host_service(spec, scope) -> (endpoint, identity, key)` and `release_service(key)`, like
  `site_services` and `advertise_host`. `key` is minted per call (`f"{scope}-{secrets.token_hex(8)}"`, `scope` the
  calling submission's `run_nonce`, §3.1) and names that call's rendezvous record, logs and release, because a record
  named by the service outlives its run and the next run of that name reads it
  (`probes/lifetime/probe_percall_key_r17.txt`); `release_service(key)` stops that call's service and drops its record.
  `host_service` returns the minted `scheme://host:port` and the service's
  `host_identity()` only after a readiness check passed where the service runs (condor: `announce.py`'s stdlib
  self-check, `check_ready`'s rule for `http:` and a connect for `tcp` and `grpc:`, §3.3; dask and parsl:
  `check_ready` in the actor), since a task may use it at once (`probe_ready_identity.txt`). `SubmitCapabilities` and the `SubmitBackend`
  Protocol are untouched (their frozen m42/m46/m66 pins stay green unmodified); the engine checks the attribute, then
  calls. Each implementation owns its rendezvous: condor (m68b) its task server's `/announce`; dask (m70)
  scheduler-mediated `distributed.Variable`/`Event`; parsl (m70) the existing `EscalatingHttpTransport` plane (§3.4).
  A TaskVine adapter adds the two methods, nothing else. `host_service` returns with the service up, or releases
  what it started and then raises; inside it each acquisition registers its release when that acquisition returns
  (condor: the cluster when `schedd.submit` returns, before spool).

Measured for this plan (`probes/services-code/`): histserv (`probe_histserv_prebinned.txt`, §5.1); `_refuse_shortfall`
passes on `outputs >= marked`; the engine passes `retries` to the backend only, so the condor requeue keeps the
partition. Preservation: `DurablePlan.to_bytes` and the manifest are sorted-key JSON (`core/plan.py:195`,
`bundle.py:280`), so an omitted key is the byte-identity mechanism (`"variations"`, `bundle.py:267`); run reports
attach outside the fingerprint (m65c); `RunReport.from_json` reads named keys, so `endpoints` needs no version bump.
dask/parsl hosting: `probe_{dask,parsl}_service.txt` (§3.4; module-level actors: `__main__` ones pickled by value lose
their globals). Endpoint wire and host identity: `probe_endpoint_protocol.{py,txt}` (P-a…P-g),
`probe_ready_identity.{py,txt}` and `probes/services-lpc/P8-eaf-triton/`, `P9-eaf-model/` `REPORT.md` (P8, P9).

## 1. Shape and seam (one paragraph, extending m66 §1)

Unchanged: one engine over `SubmitBackend`; the HTCondor backend supplies its pool as pilots pulling from a
driver-side task server. This arc adds one thing to graphed and three to executors. In graphed, an analysis
declares its **service surface** (D1): specs on the `Session`, names in node params, specs in `Plan`, `DurablePlan`
and the bundle. At the executors engine seam: (a) `SubmitRunner` learns a **service set** (`submit/services.py`):
each run resolves each spec by the three legs (D2), probes them from another host, binds the endpoints into
the plan, hands the run's value to graphed's `resolve_services(plan, value)` while the services are up, and closes what it
started when it ends; a user keeps services warm across plans by holding a `ServiceSet` and passing its endpoints. (b) The HTCondor backend implements **cluster hosting** (D3, D10) and the
task server one plain-text **`/announce`** route. (c) A **driverless** entry (`htcondor_backend/driver.py`) runs
the same `HTCondorRunner` from inside a job over a pickled plan, and `driverless.py` submits it, tracks it and
collects `result.pkl`. Below the seam, graphed's `_PartitionReduce`, `_Collated` and the histogram process learn
`bind_services` and `resolve_services` (one walk), which is how an endpoint reaches an evaluator or a fill without touching graph identity. The
translation (m69a) is a user of the released seam only; m70 adds the dask and parsl hosting implementations behind
D10. This statement will live in `docs/design.rst` "On an HTCondor pool" (new paragraphs "Driverless" and
"Services"), graphed's `architecture.rst` "Service surface", and the module docstrings named below.

## 2. m67 — driverless runs (graphed-executors PR, stacked on lane/htcondor)

### Ladders (task · by hand · rung)
| Mechanism | By hand | Rung |
|---|---|---|
| driver entry | `python driver.py` in the job | (6) `python -m …htcondor_backend.driver <dir>`: unpickle, `HTCondorRunner`, write `result.pkl`; `pilot.py` runs tasks, not plans |
| pilots inside the fat slot | pilots as subprocesses | (2) `LocalPilots(n)` verbatim; `request_cpus=n` |
| self-submitted pilots (lxplus) | `condor_submit -name -pool` from the job | (2) `CondorPilots` + `schedd_locate=(pool, name)` in `_choose` (P5) |
| payload | `pickle.dump(plan)` | (3) stdlib pickle; `_require_importable` reused (m66 D4) |
| results back | `condor_transfer_data` | (3) `transfer_output_files=result.pkl,driver.log` + `schedd.retrieve` |
| retries | resubmit | (3) `max_retries` + `retry_until` submit keys (D6) |
| wait/collect | `condor_q` | (6) `RunHandle` over `schedd.query` (m66 `counts_as_alive`) |
| across sessions | remember the cluster | (3) a JSON file (`RunHandle.save/load`) |
| advertised host | read the machine ad | (3) `Machine` from `$_CONDOR_MACHINE_AD` (LPC P2 `transcript.txt:36,49`); container hostnames are fabricated (P3) |

### Files and public symbols
**`htcondor_backend/driver.py`** (~120): `main([dir])` loads `plan.pkl` + `run.json` (`{pilots: "local"| "condor",
n_pilots, site, image, log_dir, min_pilots, retries, max_in_flight, endpoints: {} (m68a; m68b adds `announce_only: {name: node id}` and `dag_dir`),
schedd_locate: [pool, name] | null, user_modules: []}`), builds `LocalPilots(n)` (cwd on `sys.path`) or
`CondorPilots(profile, …, schedd_locate=…)` with `host=` the `Machine` of `$_CONDOR_MACHINE_AD`, runs, writes
`result.pkl` = `(ok, ExecResult | exception)`, exits 0 / 3 (raised inside `run`) / 1 (raised outside it);
`driver.log` gets pilot count, pids, timings. Imports no bindings unless `pilots == "condor"`.

**`htcondor_backend/driverless.py`** (~300)
- `submit_driverless(plan, *, site="generic", image=None, n_pilots=2, pilots="local", request_memory_mb,
  log_dir=None, user_modules=(), env=None, extra_submit=None, min_pilots=1, retries=3, max_in_flight=2) ->
  RunHandle`. Refuses: `pilots="condor"` where `worker_ports is None`, a `__main__`/lambda process, an lpc
  `log_dir` outside the sandbox. Writes `plan.pkl`, `run.json`, `driver.sh` (`pilot.sh`'s shape), the env tarball
  via the m66 recipe, then submits ONE job: `CondorPilots.submit_description`'s base keys with
  `executable=driver.sh`, `request_cpus=n_pilots` (fat slot) or `1`, `transfer_input_files ∋ plan.pkl,run.json
  [,env.tgz][,user_modules…]`, `transfer_output_files="result.pkl,driver.log"`, `max_retries=2`, `retry_until=3`,
  `JobBatchName=graphed-driverless-<nonce>`, then the profile keys, then `extra_submit`. `pilots="condor"`:
  `run.json.schedd_locate` = (`htc.param["COLLECTOR_HOST"]`, the chosen schedd) and `run.json.log_dir` an absolute
  path the schedd reads (lxplus: under `/afs`, else refused). `run.json.extra_submit` carries the same keys to the
  in-job driver's `CondorPilots`, so every job the run submits (driver, SERVICE nodes, pilots) takes them last, as
  attached pilots do (owner, 2026-09-30).
- `RunHandle(site, schedd, cluster, log_dir, submitted_at)`: `status() -> "queued"|"running"|"held"|"done"|
  "removed"|"failed"` from one projected query (`JobStatus`, `HoldReasonCode`, `ExitCode`); `wait(timeout=None,
  poll_s=15)`; `result()` (retrieve when spooled, unpickle, re-raise a pickled exception intact); `remove()`;
  `save(path)`/`load(path)`; `logs()`. Every schedd call goes through `Collector.locate` on the recorded name.

**`launch.py`** (+40): `CondorPilots(..., schedd_locate=None)`; `_choose` returns
`Schedd(Collector(pool).locate(DaemonType.Schedd, name))` when set (P5). **`sites.py`** (+25): `service_ports=None`,
`worker_ports=None` after `driver_ports` (frozen m66 passes the six old kwargs only); `service_hosts` property; no
`services` (m68, D4). **`__init__.py`**: exports `submit_driverless`, `RunHandle`.

### Frozen tests `tests/frozen/m67/` (harness `driverless_harness.py`: the m66 copies it needs + `RecordingSchedd`)
| File | Property | Witness | Fixture |
|---|---|---|---|
| `test_driverless_payload.py` (all OS) | with `launch._htcondor` a recorder: `plan.pkl` unpickles and runs bit-for-bit in a fresh interpreter (no `PYTHONPATH`, other cwd); the description carries the keys above, `request_cpus == n_pilots` for `pilots="local"`, `retry_until == "3"`; refusals (lambda, `__main__`, `pilots="condor"` on a `worker_ports=None` profile, non-AFS `log_dir` on lxplus) raise before any bindings call; nothing references `SiteProfile.services` (m68's field) | recorder call list empty on refusal, one `submit` otherwise | m66 `concat_plan` copies |
| `test_driver_entry.py` (all OS) | `python -m …driver <dir>` with `run.json{pilots:"local", n_pilots:2}` writes `result.pkl` equal to the sequential result, ≥2 pilot pids ≠ driver pid; a poisoned plan exits 3 with an intact `StageError` in `result.pkl`; `n_pilots` that cannot start (a bogus python) exits 1 | pids; `type(err) is StageError`; exit codes | m66 `PoisonUriProcess` copy |
| `test_run_handle.py` (all OS) | `status()` over synthetic ads (JobStatus 1/2/4/5+16/5+13/3, ExitCode 0/1/3, derived from the status lines of `probes/services-lpc/p1-dag/transcript-p1c-spool-tif.txt`); `wait` bounded; `result()` before done raises; `save/load` round-trips; the schedd is located by name, never `Schedd()` | `RecordingSchedd` sees `locate(name)` | `data/driver-ads.json` (synthetic) |
| `test_driverless_live.py` (minicondor) | (a) `pilots="local"`, generic, `n_pilots=2`: `wait()` → `result()` bit-for-bit, `driver.log` in `log_dir`, queue empty, history `ExitCode 0`; (b) `pilots="condor"`: the driver job submitted its own cluster (history ≥3 rows), pilot pids ≠ driver pid; (c) the live ad carries `JobMaxRetries == 2` and an `OnExitRemove` naming exit code 3; (d) a poisoned plan: history `NumJobStarts == 1`, `ExitCode 3` (no retry) | ads, history, pids | the pool |

Fails on: a driver that computes on its own pid, a lost exception, a hang, a `Schedd()` call inside the job path, a
retried plan error, an unshipped `run.json`.

### Commits (≤2k each; the test author's freeze ~900 first)
1. `feat(htcondor): driver entry module and schedd_locate` — `driver.py`, `launch.py`, `sites.py`,
   `tests/extra/m67/` (~400)
2. `feat(htcondor): submit_driverless and RunHandle` — `driverless.py`, `__init__`, extra tests (~500)
3. `ci+docs(htcondor): driverless leg and how-to` — ci.yml (m67 in `test-htcondor`), `docs/htcondor.rst` "Running
   without a login session", `design.rst` "Driverless", changelog (~200)

Site check (implementer): LPC fat slot over `concat_plan` → `probes/site-lpc/m67-driverless.txt`; lxplus
`pilots="condor"` and the fat slot → `probes/site-lxplus/m67-driverless.txt` (owner permission).

## 3. m68 — services: graphed PR, executors m68a (engine, driver-hosted, site legs) and m68b (condor cluster hosting)
Defaults rule (this arc): a mapping/list dataclass field defaults through `field(default_factory=...)` (frozen: to
`MappingProxyType({})` or `()`; 3.11 refuses a bare mappingproxy default), a function parameter to `None`. Every m68
Triton leg (the CI container, lxplus `models/`, EAF) serves `graphed_identity` with `INPUT0`→`OUTPUT0` FP32, the name
and I/O EAF serves (P9), so one set of External params (`model="graphed_identity", input_name="INPUT0",
output_name="OUTPUT0"`, no `transport`) runs on all three.

### 3.1 executors m68a — engine service set, driver-hosted and site legs, driverless endpoints (PR stacked on m67)
| Mechanism | By hand | Rung |
|---|---|---|
| declare a requirement | a name + a kind, in the analysis | (2) graphed's `ServiceSpec` (§3.2); executors define none |
| a launch recipe | a command line + an image in a helper | (6) `submit/recipes.py`: plain data constructors, the only executors file naming a service |
| resolve a requirement | try the URL you were given, then the site's, then start one | (6) `ServiceSet.start` over three legs (D2) |
| readiness | `nc -z` / `curl` / `grpc_health_probe` | (3) `socket.create_connection` / `urllib` GET; (4) grpcio's generic `unary_unary` on `/grpc.health.v1.Health/Check` with the one-field request hand-encoded — `grpcio-health-checking` would add generated stubs for a two-byte message (raw = reference stub answers, P-a) |
| worker reachability | one job on another node that connects | (2) a task through `backend.submit`, resubmitted until a host other than the service's answers |
| managed on the driver | `subprocess.Popen` | (3) stdlib, engine-level, every backend |
| teardown | `with ExitStack()` | (2) `HTCondorBackend.__init__`'s stack, each undo logging as `driver.main` does (`probes/class/probe_exitstack_semantics.txt`) |
| status surface | read the log | (6) `ServiceStatus` records + `logging`; the `Monitor` protocol is graphed's, nobody asked for a tile |

**`submit/recipes.py`** (~40, plain data): `triton(name, image, model_repository, *, gpus=1) -> ServiceSpec` (kind
`"triton"`, argv `("tritonserver", f"--model-repository={model_repository}", "--grpc-port={port}",
"--allow-http=false", "--allow-metrics=false")`, `inputs=(model_repository,)` (relative, where the job lands it),
`check="grpc:"`: gRPC, one bound port, because the site Triton the same requirement must accept serves only gRPC, P8;
flags and the `ServerIsReady`-backed health Check exist at r24.11/r25.11, P-e), `http_server(name, *, root=".") ->
ServiceSpec` (argv `("{python}", "-m", "http.server", "{port}")`, kind `"http"`, `check="http:/"`); histserv's lives
in graphed-histogram (§5.1). Nothing else in executors names a service.

**`submit/services.py`** (~320, no bindings)
- `ServiceStatus(name, leg: "user"|"site"|"managed", host: "driver"|"cluster"|None, endpoint, identity, started_at,
  ready_at, closed_at, detail)`; `ServiceUnavailable(name, legs: Mapping[str, str])` (each leg → why it did not
  apply); `ServiceUnreachable(name, endpoint, worker, reason)`; both pass exactly their constructor arguments to
  `super().__init__` (so the stdlib exception pickling, `(type, args, __dict__)`, rebuilds them; StageError's
  `__reduce__` exists for its keyword-only constructor, which these do not have) and define a `__str__` that names
  the name and the reason or each leg's reason (`probes/services-code/probe_result_blob_r9.txt`); `Endpoints` (a `Mapping[str, str]` with
  `on_close(callback)`).
- `check_ready(endpoint, check, timeout) -> str | None` (`None` = ready, else why), the one check every caller runs:
  `tcp` → connect; `http:<path>` → GET `<scheme>://<host:port><path>`, ready on a 2xx whose content-type is not
  `application/grpc*` (EAF's answer to every path, P8, P-a'); `grpc:<svc>` → grpcio imported lazily (absent → the
  reason names it), `insecure_channel` or `secure_channel(ssl_channel_credentials())` by scheme, ready iff the reply
  is `b"\x08\x01"` (SERVING); a check/scheme mismatch or an unknown check form → the reason, nothing dialled.
- `ServiceSet(specs, backend, *, endpoints: Mapping[str, str] | None = None, scope: str | None = None)`, a context
  manager (`__enter__` = `start() -> Endpoints`, `__exit__` = `close()`; `endpoints` values go through `split_endpoint`
  at construction; `scope` is the submission's `run_nonce`, and a user-held set, given none, mints its own).
  `start()` resolves each spec by D2: leg 1 the given endpoint (checked; failure → `ServiceUnavailable` naming it and
  stopping); leg 2 `backend.site_services` (duck-typed, `{}` default; condor: the profile's `services` by
  `spec.kind`), checked, a failure recorded in `detail` and passed over; leg 3 managed: refused without `launch`;
  driver-hosted when the recipe has no `image`, `resources.gpus == 0` and `"driver" in backend.service_hosts`
  (duck-typed; condor: the profile's; other backends: `("driver",)`): bind a free port from `backend.service_ports`
  (condor: the profile's; others: the spec's `ports`) on `backend.advertise_host` (duck-typed, default
  `socket.getfqdn()`; `ThreadBackend` `"127.0.0.1"`), holding one module-level `threading.Lock` from the scan until
  readiness or failure, released in a `finally`, its wait outside `timeout_s` (the scan frees the port before the child
  binds it, and every run in one process picks from one port space; picks in other processes, m68b's and m70's and
  another driver process's on one host, only the post-check poll guards), `Popen(argv)` with `{python}` =
  `sys.executable` and the recipe's `env`, poll the check and `proc.poll()` until `timeout_s`: ready = the check
  passing and then `proc.poll() is None` (a pass with a dead child, like an early exit, fails at once naming its
  returncode), a check never passing → `ServiceUnavailable` whose `legs["managed"]` names the check and its last
  reason; else cluster-hosted iff `callable(getattr(backend, "host_service", None))`: `backend.host_service(spec, scope) ->
  (endpoint, identity, key)`. Then it probes: an ordinary `backend.submit` of `_probe_services(checks)` keyed
  `f"svc-{scope}-probe-{i}"` (`check_ready`
  each `(endpoint, check)`, 5 s, returns `host_identity()` and the reasons), each answer awaited up to the spec's
  `timeout_s` (none → `ServiceUnreachable(reason="no worker answered")`: an unanswered submit never completes,
  `probes/class/probe_start_before_wait_r15.txt`), resubmitted with a fresh key until an identity other than the
  service's answers, bounded by `max(2, n_workers())` submissions; its reason → `ServiceUnreachable(reason=<it>)`;
  only the service's identity answering passes iff it is the driver's (D2), else `ServiceUnreachable(reason="only
  same-host workers answered")`. `ServiceStatus.identity` per leg: driver-hosted → the driver's; cluster-hosted → the
  one `host_service` returns; user and site → `None`, where any passing answer passes. One mechanism on every backend:
  no placement kwarg, no lease filter. `start()` logs each status at INFO on `graphed_executors.services` (the
  record's `status` attribute); `statuses()`. Every acquisition in `start()` puts its release on a
  `contextlib.ExitStack` when it returns, as in `HTCondorBackend.__init__` (`Popen`: terminate, `wait(grace)`, kill,
  wait; `host_service`: `release_service(key)`; a probe submit: `backend.cancel([fut])`; `on_close`: a callback), and each release logs its failure and never
  raises (`driver.main`'s rule), so the first exception is the one that surfaces; the set keeps the stack
  `pop_all()` hands over after the probe passes, and `close()` is that stack's `close()`.
- `submit/engine.py` (+45): `SubmitRunner(..., services: Mapping[str, str] | None = None)` stores the public attribute
  `services`, read once at each run's start like `monitor`. **A submission's scope is its run's `RunContext`**, named
  by its `run_nonce` (`SubmitRunner._context`, one per `run`; `submit` runs through `run`). `run` opens one `ExitStack`
  per call and registers on it everything the submission acquires or submits: when `plan.services` is non-empty, after
  the cancel check, `ServiceSet(plan.services, self.backend, endpoints=self.services, scope=ctx.run_nonce)`; and a
  `backend.cancel` of its plan tasks not done (the four `_run_*` paths submit through one per-run wrapper holding
  only futures not yet done: each is discarded in its done callback under a lock, since a held dask future pins its
  result in cluster memory). The body runs
  unchanged on `bound = bind_services(plan, eps)` (graphed's) and returns the `ExecResult` whose value is graphed's
  `resolve_services(bound, value)` (§3.2) while the services are up; the stack closes when `run` returns or raises, so
  no service, record or pending task of a submission outlives it or reaches another
  (`probes/scope/probe_submission_scope.txt`). The port lock and worker slots are not submission scope; `close()` is
  m67's. **Warm across plans (opt-in)** is user scope, outside any submission, reached as leg 1: the runner checks and probes a user-held set's names each run, starting none:
  `with SubmitRunner(backend) as runner, ServiceSet(specs, runner.backend) as eps: runner.services = eps; ...` — the
  `with` closes the set before `runner.close()` closes the backend its releases use
  (`probes/lifetime/probe_lifetime.txt` B). `HTCondorRunner.run` (m67) waits for pilots before `super().run`, so the
  probe follows the wait. Every other executors plan runner (`_BaseExecutor.run`, `transport_run_plan`, `parsl_run_plan`: `grep -rnE 'def (run\(self, plan|[a-z_]*run_plan\()'
  src`, less the two `run`s above) calls graphed's `require_bound(plan)` before its first task, as `SequentialRunner`
  does, and gains no service phase. Executors pin `graphed>=<the m68 release>` (CI installs graphed from the PR ref
  through `env.GRAPHED` until then). Facades pass `services=`.

**`htcondor_backend/`** (`sites.py` +15, `backend.py` +20, `launch.py` +10, `driverless.py` +20, `driver.py` +20)
- The m66 acquirers, same rule: `HTCondorBackend.__init__` registers `launcher.stop`, `LocalPilots.start` each child,
  `CondorPilots.start` the cluster before spool; `driver._runner` holds the backend on a stack until `HTCondorRunner`
  returns. `HTCondorBackend.close`, `LocalPilots.stop` and `CondorPilots.stop` become the close of the stack each
  kept (today a raising `launcher.stop` leaves the task server's port bound, `probes/class/probe_phase_and_release_r14.txt` B).
- `sites.py`: `services` (D4). `HTCondorBackend(..., in_job: SiteProfile | None = None)`. Attached (`in_job=None`):
  `site_services`, `service_ports`, `service_hosts` = the launcher's profile; `advertise_host` = the task server's
  host; `host_identity()` = `htc.param["FULL_HOSTNAME"]`, the only bindings use (D2). In a driver job `driver.py`
  passes `in_job=SITES[run.site]` (m67's launcher fallback would give `LocalPilots` the generic row): `site_services`
  = that row's `services`, `service_hosts = ("driver",)`, reachability the task server's own — `pilots="local"`:
  `advertise_host="127.0.0.1"`, any free port of the spec's `ports`; `pilots="condor"`: `advertise_host` = the slot's
  `Machine`, the row's `worker_ports` — and `host_identity()` = the module function, no bindings. `host_service`
  arrives in m68b, so leg 3 on an attached `("cluster",)` profile (lxplus) refuses here naming the attribute.
- **Driverless endpoints.** `submit_driverless(..., services: Mapping[str, str] | None = None)` is the user leg:
  `split_endpoint` over its values before any bindings call (m67's refusal idiom), into `run.json.endpoints`;
  driver-hosted is a `Popen` beside `LocalPilots`
  (the LPC managed path) or, with `pilots="condor"`, on the driver's worker port; in m68a it needs no condor hosting
  and is m69b's driverless path. `driver.main` runs in phases — setup, `wait_for_pilots()`, `with ServiceSet(
  plan.services, runner.backend, endpoints=run.json.endpoints) as eps: runner.services = eps; runner.run(plan)` (leg 1
  for every name; its value resolved), `runner.close()`, `result.pkl` — with the set's `with` outside the
  `runner.run` try, so its exceptions exit 1 whatever their type (D6); `runner.run`'s own set re-probes those names
  inside the try, so `_exit_code` also maps `ServiceUnavailable`, `ServiceUnreachable` and the probe's raw
  `WorkerLost` to 1 (`probes/lifetime/probe_inner_worker_loss_r17.txt`). `driver._result_blob` returns its blob
  only after `pickle.loads(blob)` succeeds inside its existing `try`, so any payload that dumps but cannot load (a
  user exception whose constructor differs from its `args`) reaches `result.pkl` as the text `RuntimeError` (a blob
  that did not round-trip through pickle). `result.pkl` crosses from the job's environment to the submitter's, so the
  submitter's load is the authority: `RunHandle.result()` loads it inside one `try`, and a failed load raises
  `RuntimeError` naming the load error and `driver.log`, which holds the traceback.
- **LPC leg 2 (evidence).** A Triton External on `graphed_identity` (the owner's ONNX Identity in EAF's store; P9
  measured it READY with gRPC infer bit-for-bit from a batch worker, `probes/services-lpc/P9-eaf-model/REPORT.md`)
  resolves `service="triton"` by leg 2 to the lpc row, the worker probe passes, and infer returns its input
  bit-for-bit (`probes/site-lpc/m68-eaf-triton.txt`).

Frozen `tests/frozen/m68a/` (harness `services_harness.py`):
| File | Property | Witness | Fixture |
|---|---|---|---|
| `test_services_protocol.py` (all OS, `ThreadBackend` + a two-host fake backend) | the generic `recipes.http_server` requirement (readiness URL `http:/`, neither Triton nor histserv imported: `sys.modules` checked) runs the whole path — resolve, bind, probe, a task GET, close; resolution order on a plan with two specs: a given endpoint wins over a site endpoint; a dead given endpoint refuses naming `user` with zero plan submits; a dead site endpoint falls through to managed and the status says so; no `launch` and no endpoint → `ServiceUnavailable` naming all three legs; a GPU recipe on a backend without `host_service` → refused naming the attribute; injected faults, parametrized (a check never passes; a ready child, then a later spec refuses; `host_service` returned, then a later spec refuses; `host_service` raises; the probe refuses; `release_service` raises, then a later spec refuses; the spec's port range held, so the bind raises `OSError`; a probe `submit` raising the backend's worker-loss exception; a probe no worker answers within `timeout_s`): `run` and `ServiceSet.start` each raise the injected exception itself and, with the runner still open, every managed pid is reaped (`os.kill(pid, 0)` raises), every port is free, `release_service` ran exactly with the keys `host_service` returned; a raising `on_close` is logged, the child is still reaped and `run`'s value stands; per run: a managed child answers a plan task's GET and is gone when `run` returns, and two runs of one plan start two pids; on the fake, two sequential runs each release only their own key; overlapping submissions A (`run`) and B (`submit`, a longer `timeout_s`) on one `SubmitRunner` over the fake, submitting through a `ThreadBackend(1)` whose worker a gate holds until A raises: each run's task keys and plan tasks' `RunContext` carry its own `run_nonce`, the keys released at each run's end are exactly those `host_service` minted under its nonce, and A's unanswered probe is cancelled before B's first task is leased (it never runs); a run whose third leaf `submit` raises there has its two queued leaves cancelled before `run` raises (neither runs); two `ServiceSet`s over the driver-hosted spec entered together behind a `threading.Barrier`, 10 trials: distinct ports, and both children alive while both sets are open; warm: a user-held `ServiceSet` with `runner.services = eps` serves two plans with one pid, both runs log `leg="user"` and start no process, and the child is gone when the set's `with` exits, the runner still open; `bind_services` seen by a spy process after the probe and before the first plan-task submit; the spy process's `resolve_services` is called once with the run's value while the child is alive, and `run`'s value is what it returned; the same through `collate({"a": spy_a, "b": spy_b})` and through an `aggregate_plan` whose `reduce` is the spy: each spy's `resolve_services` is called once, with its own sub-value, while the child is alive (the engine's `getattr(plan.process, "resolve_services")` finds no hook on either, `probes/class/probe_resolve_traversal_r16.txt`); an unbound spy plan (its `bind_services` raising `UnboundService` on a missing name, the `Bindable` contract) through `ThreadExecutor.run` raises `UnboundService` with zero process calls; on `ThreadBackend` every probe answer carries the driver's identity and the probe passes; on the two-host fake (driver on host A; its `host_service` returns `(endpoint, B, key)`; an ordinary `submit`; the spy sees no placement kwarg on the probe), the status carries identity B, and the run refuses with "only same-host workers answered" when only B answers, passes when A or a third host does; a user- or site-leg service (`identity=None`) passes on any passing answer; the probe task returns `host_identity()` (`Machine` from a synthetic `$_CONDOR_MACHINE_AD`, else `getfqdn`); `on_close` callbacks run before teardown; each status is logged with `leg`/`ready_at` | spy call order; pid; submit spy; `legs` text | none |
| `test_service_checks.py` (all OS; gRPC cases `importorskip("grpc")`, and `import grpc` must succeed wherever the GIL is enabled) | `check_ready` against in-process servers: with the reference `grpc_health.v1.health.HealthServicer`, `grpc:` passes on SERVING and fails on NOT_SERVING and an unknown service, and the same server as `grpcs://` fails (TLS attempted); a gRPC server without health fails; `http:/v2/health/ready` fails on a server answering 200 `application/grpc` to every path (P8's shape) and `http:/` passes on `http.server`, which fails as `https://`; `http:` on `grpc://` and `grpc:` on `http://` fail naming both with zero connections accepted; `tcp` passes on every scheme; an unknown form refused; `_probe_services` on the NOT_SERVING server returns its reason (a connect-only probe would not); `ServiceSet(…, endpoints={"x": "h:1"})` refuses naming the schemes | reasons; accept counter | in-process servers |
| `test_services_sites.py` (all OS) | `SITES` rows' measured fields equal D4 (`driver_ports`, `service_ports`, `worker_ports`, `service_hosts`: lpc `("driver","cluster")`, lxplus `("cluster",)`, generic both) as pins on the P6/P7 reports, `services` values unpinned (site data) but each passes `split_endpoint`; the derivation on synthetic profiles: each `None` range refuses the matching host at construction naming the row, both `None` → legs 1–2 only, a bare `host:port` `services` value refuses naming the row; `recipes.triton` argv holds `--grpc-port={port}`, `--allow-http=false`, `--allow-metrics=false` with `check == "grpc:"`; the minted managed scheme per check (`http:`/`grpc:`/`tcp`); `{python}` rendered as `sys.executable` on the driver; `backend.host_identity()` returns a faked `FULL_HOSTNAME`; driver-job backends are `driver._runner({"site": s, "pilots": "local", …}, tmp, log).backend` (never `HTCondorBackend(..., in_job=)` directly: the row guards `driver.py` passing `in_job`), with a synthetic `$_CONDOR_MACHINE_AD` and `sys.modules["htcondor2"] = None`: for `site="lpc"`, `site_services == SITES["lpc"].services`, `service_hosts == ("driver",)` and `host_identity()` returns the ad's `Machine`; for `site="lxplus"`, `service_hosts == ("driver",)` (the launcher fallback's generic row gives `("driver", "cluster")`, the attached lxplus row `("cluster",)`) and it starts a driver-hosted `http_server`; a fault in the second `LocalPilots` spawn, `CondorPilots`' spool, or `driver._runner`'s runner leaves no pilot, cluster or port (`probes/class/probe_acquire_record.py`); `HTCondorBackend.close` over a launcher whose `stop` raises still frees the task server's port (`probes/class/probe_phase_and_release_r14.py` B) | pure functions on data; one started server | — |
| `test_triton_service_ref.py` (all OS) | a graphed plan with `service="triton"` through `SubmitRunner(ThreadBackend, services={"triton": "grpc://<fake>"})`: the fake was built with the bound endpoint; two nodes/two specs → two endpoints; the literal-`url` plan runs with `plan.services == ()` and no set started | fake's connect log | graphed's `fake_triton.py` copied |
| `test_driverless_endpoints.py` (all OS) | a plan declaring `recipes.http_server` with `pilots="local"` and a process whose tasks GET it and whose `resolve_services` puts the GET body into the value: `driver.py` starts the server in the driver job (server pid ≠ driver pid), pilot tasks GET it, the port is free on exit, and `result.pkl`, loaded after the job exited, holds that body (with the value shipped unresolved it would not); `submit_driverless(services=)` short-circuits the launch through `run.json.endpoints`; a bare `host:port` there refused with the recorder call list empty; `python -m …driver` with a dead `run.json.endpoints` value exits 1 with `ServiceUnavailable` in `result.pkl`, with the spec's port range held exits 1 with `OSError`, and with a live one that refuses only its in-run re-check exits 1 with `ServiceUnavailable` in `result.pkl` (m67's `_exit_code` gives 3), `driver._exit_code`, parametrized, is 1 for `ServiceUnavailable`, `ServiceUnreachable` and a raw `WorkerLost` and 3 for `ValueError` and a `StageError` from a task's `ValueError`, and with a live one and a process raising `ValueError`, or `OSError`, exits 3 with that exception intact; `pickle.loads(driver._result_blob(False, ServiceUnreachable("t", "grpc://h:1", "w", "refused")))` is a `ServiceUnreachable` with all four fields equal and `"refused"` in its `str`, the same for `ServiceUnavailable` and its `legs`, and an exception whose constructor takes more arguments than it passes to `super().__init__` comes back as the text `RuntimeError` naming its type (m67's dumps-only blob makes that load raise `TypeError`); `RunHandle.result()` on a `result.pkl` holding an exception from a temporary module that is then removed raises `RuntimeError` naming `ModuleNotFoundError` and `driver.log` (a bare `pickle.loads` raises `ModuleNotFoundError`), with no bindings | pids; port; recorder; exit codes; loaded types | — |
| `test_services_live.py` (minicondor + docker Triton) | (a) a driver-hosted `recipes.http_server` over two pool pilots: every probe answer carries the pool host's `Machine`, equal to `backend.host_identity()`, so the probe passes; a pilot task GETs it; the port is free when `run` returns; (b) `services={"triton": "grpc://localhost:8001"}` and the §3 params over local pilots: the `grpc:` check and the probe pass on the container, output == input (the port answers only gRPC: `tritonclient.grpc` witnessed); (c) a profile copy with `services={"triton": "grpc://localhost:8001"}` resolves by leg 2 with no launch | identities, pids, port | the pool + container |
| `test_scope_dask_memory.py` (`importorskip("distributed")`, run in `test-dask`) | one batch of 40 leaves through `SubmitRunner(DaskBackend(LocalCluster 2×1), control=RunControl())` (the windowed adaptive path, the one that bounds outstanding leaves): at each `next_tasks` call the count of this run's `-leaf-` keys whose `client.who_has()` holder list is non-empty never exceeds `backend.task_slots()` | held-key counts | the local cluster |
| `test_services_packaging.py` | ci `test-htcondor` installs `tritonclient[grpc]`, `grpcio-health-checking`, starts the container with the recipe's flags on 8001 serving `tests/frozen/m68a/data/triton_models/graphed_identity`, waits on `check_ready`, runs `tests/frozen/m67` and `tests/frozen/m68a`; `.coveragerc-htcondor` sources ∋ `graphed_executors.submit.services`; diff-cover include widened; `grep -rc "triton\|histserv"` over `submit/services.py`, `submit/engine.py`, `submit/protocol.py`, `htcondor_backend/` minus `sites.py` (site data may name a site's Triton) is 0 (control: `submit/recipes.py` > 0); the frozen README states the positive leg: the generic `http_server` recipe is the third recipe every hosting test runs (§3.1, §3.3, §3.4) | text | — |

Fails on: bind after submit, a same-host probe pass off the driver's machine, a driverless bare endpoint reaching the
job, a service, record or pending task outliving its submission or a warm set's `with`, a consumed result held until the run ends, a cleanup failure replacing the refusal, a raising release step skipping a later one,
a service-phase exception exiting 3, a returned value that needs a released service (a composed plan's too), an unanswered probe that hangs, a URL-blind cache, a replaced given endpoint, a service name in the engine,
an HTTP check passing a gRPC gateway, a scheme-blind TLS choice, a connect-only probe, a driver job that ignores its site row,
a service refusal that is not retried or a plan error that is, a `result.pkl` the submitter cannot load.

Commits (≤2k each; freeze `test(services): frozen m68a` ~1.3k first): 1. `feat(services): three-leg service set in the
engine, D10 attribute` — no `submit/protocol.py` change and nothing under `tests/frozen` (m42/m46/m66 stay green
unmodified), `submit/services.py`, `submit/recipes.py`, `check_ready`, engine, facades, `require_bound` in the other runners, `tests/extra/m68a/` (~750); 2.
`feat(htcondor): site services, driver identity, driverless endpoints` — sites, backend, driverless, driver (~200); 3.
`ci+docs(m68a)` — ci (Triton container, m68a dir), `htcondor.rst` "Services", `design.rst` "Services", changelog
(~250)

### 3.2 graphed PR (one PR; `python/graphed/`)
| Mechanism | By hand | Rung |
|---|---|---|
| the spec | a dict the user writes | (6) two frozen dataclasses + `to_json/from_json` over primitives |
| specs with the analysis | a list on the session | (2) the `Session` registry idiom (`_externals`); `services()` view like `sources()` |
| in the durable plan | one more key | (3) sorted-key JSON already; omit when empty |
| resolve a run's value | the same walk as binding | (2) `bind_services`'s walk, through the same composites |
| in the bundle | one more manifest key | (2) the `"variations"` idiom |
| run endpoints | a note in the report | (2) `RunReport` field + `attach_run_report` |
| endpoint form | read the URL | (3) `urllib.parse.urlsplit` + a closed scheme set; refuse a missing port or a path (P-f) |
| Triton wire | pick the client | (2) `tritonclient.http` / `.grpc` share the request classes `eval_triton` uses (m9 real-server test runs both) |

| File | Change |
|---|---|
| `graphed/services.py` (~150) | `Launch(argv: tuple[str, ...], image: str \| None = None, inputs: tuple[str, ...] = (), env: Mapping[str, str], resources: Mapping[str, float])` (both empty by the §3 defaults rule); `ServiceSpec(name, kind, check="tcp", ports=(10000, 10100), launch: Launch \| None = None, timeout_s=600.0)`, both frozen with `to_json()`/`from_json()` (sorted, primitives, tuples); `bind_services(plan, endpoints) -> Plan` (`replace(plan, process=plan.process.bind_services(endpoints))` when the hook exists, else the same plan); `Bindable` protocol; `UnboundService(GraphedError)` naming the service and the two ways to bind; `split_endpoint` (D1; bare `host:port`, an unknown scheme, a missing port, a path → `ValueError` naming the form and schemes); `bind_services` runs it over every endpoint before binding. |
| `session.py` (+25) | `declare_service(spec)` (a second declaration of a name must be equal, else `ValueError`); `services() -> dict[str, ServiceSpec]`; `service_for(name)` refuses an undeclared name naming the declared ones. `preserve/externals/_base.py` `record_external` (+8) calls it when `params["service"]` is present. |
| `core/execution.py` (+3) | `Plan.services: tuple[ServiceSpec, ...] = ()` (old pickles valid). `aggregate.py` (+25): `aggregate_plan(..., services: Sequence[str] = ())`; `Plan.services` = the session's specs referenced by the compiled External nodes' `service` params ∪ the named ones, sorted by name; `_PartitionReduce.bind_services(endpoints)` → `replace(self, externals=…, reduce=…)` binding each member with the hook. |
| `core/plan.py` (+20) | `DurablePlan.services: tuple[ServiceSpec, ...] = ()`; `to_bytes` writes `"services"` only when non-empty; `from_bytes` reads `doc.get("services", ())`; `task_id` unchanged (the spec is not identity: the model's content hash already is, and the endpoint never was). |
| `preserve/externals/_base.py` (+25) | `_PluginEvaluator.endpoint: str \| None = None` (old pickles valid); `bind_services` fills it from `node_params["service"]` (missing name → `UnboundService`); `__call__` passes `{**node_params, "url": endpoint}` to `load` when bound; cache key `(kind, content_hash, endpoint, {p: params[p] for p in plugin.load_params})`; `ExternalPlugin.load_params: tuple[str, ...] = ()`, Triton's plugin `("url", "transport")`. |
| `preserve/externals/triton_external.py` (+35) | `service=` xor `url=` (both or neither → `PreserveError`); `triton_transport(params)` = D7's scheme choice (`tcp` → `PreserveError` naming `http(s)`/`grpc(s)`), and `_transport_module_and_factory` returns the scheme's module with it; `triton_http_transport` stays exported; the docstring says the connection is environment and the name is identity. `pyproject.toml` `ml`: `tritonclient[grpc,http]`. |
| `preserve/bundle.py` (+40) | `build_bundle` adds `manifest["services"] = [spec.to_json() …]` for the session's specs the IR references, only when that list is non-empty; `inspect()` prints a `services:` block (name, kind, check, image/argv or "external only", resources) after the external payloads, and `_render_run_reports` prints `endpoints: name → endpoint` under a report that has them. `debug/report.py` (+15): `RunReport.endpoints: Mapping[str, str]` (empty, §3 rule) in `to_json`/`from_json` (`data.get`, version stays 1); `RunRecorder.report(..., endpoints=None)`. |

Frozen `tests/frozen/preserve/m68/` (fake transport copied from `tests/frozen/preserve/m26/fake_triton.py`):
| File | Property |
|---|---|
| `test_service_spec_roundtrip.py` | a spec → `to_json` → `from_json` equal; a session with a declared Triton spec and a node naming it: `DurablePlan.services` holds it and survives `to_bytes/from_bytes`; `build_bundle` → `Bundle.open` manifest `services` equal to `to_json`; `inspect()` names the service, kind and recipe; a report with `endpoints` attached → `inspect()` shows `name → endpoint` and the fingerprint is unchanged; an undeclared name refused at record time naming the declared ones |
| `test_bundle_without_services_unchanged.py` | the no-services analysis: the manifest key set is exactly {format_version, analysis, sources, externals, opaque_nodes, provenance, environment, config, seed} and the `to_bytes` document keys are exactly 0.0.6's ten — no `services` — while the same analysis with one declared, referenced spec differs in exactly that key; a declared-but-unreferenced spec is not written |
| `test_bind_services.py` | a bound plan's evaluators carry the endpoint, the original is unchanged, an unknown name raises naming it, a plan without services binds to an equal process; `split_endpoint` gives `(scheme, "host:port")` for all five schemes and `grpc://[::1]:8001`, refuses a bare `host:port`, `triton://h:1`, a missing port and a path; `bind_services` refuses a bare endpoint naming the schemes, the original unbound |
| `test_triton_transport_by_scheme.py` | main matrix; fake `tritonclient.http` and `.grpc` modules in `sys.modules`, the m26 extra-test idiom: a bound node without `transport` connects through the scheme's module with `url="host:port"` and `ssl` true exactly for `https`/`grpcs` (`grpcs://triton.fnal.gov:443` among them), and builds its requests from that module; `tcp://` → `PreserveError`; a literal `url="h:8000"` → the http module, url unchanged |
| `test_triton_service_param.py` | IR bytes identical under two bound endpoints — P1 inverted; the `url` path byte-identical to the 0.0.6 recording; two same-payload nodes on two services → two connects; two nodes on one service differing only in `output_name` → one connect, differing in `transport` → two; two correctionlib nodes on one payload differing only in `systematic` → one `load`; `url`+`service` refused |
| `test_triton_service_live.py` | the `triton` CI job's `scorer` model through `bind_services`, no `transport` param, one leg per wire: `http://$GRAPHED_TRITON_HTTP` and `grpc://$GRAPHED_TRITON_GRPC`, each gated on its variable as `preserve/m9/test_triton_server.py`; the gRPC port answers only gRPC, so its pass witnesses `tritonclient.grpc` |
Commits (freeze `tests/frozen/preserve/m68` ~600 first): 1. `feat(services): ServiceSpec, session registry,
Plan/DurablePlan services, endpoint form, bind_services, Triton service refs and wire` (~270 src, ~600 tests); 2.
`feat(preserve): services in the bundle manifest, inspect(), run-report endpoints` (~90 src, ~250 tests); 3. `docs`.

**The resolve walk** (graphed PR `feat(services): resolve a run's value through the plan's process tree`, stacked on
main before the release executors floor at; ~30 src, ~120 tests). Resolving follows binding's walk: `services.py` adds
`Resolvable` (runtime-checkable, one method `resolve_services(value) -> value`) and `resolve_services(plan, value)` =
`plan.process.resolve_services(value)` when the process is `Resolvable`, else `value`; the composites that forward
`bind_services` to a process or a `reduce` forward it too — `_PartitionReduce` to `reduce`, `_Collated` per name over
`{name: value}` (a name without a sub-value is not called) — and the ones that bind only externals (`_WritePart`,
`_VariedWritePart`, `CheckedExternal`, `_PluginEvaluator`) gain nothing (the set: `git grep -n "def bind_services"
-- python`). Frozen `tests/frozen/preserve/m68/test_resolve_services.py` under a new tag `freeze-preserve-m68-3` (the
`-2` amendment precedent): a `Resolvable` spy as a plan's process, as `collate`'s part and as `aggregate_plan`'s
`reduce` is called once with its own sub-value and its return lands at the same place in the value; a process
without the hook returns the value unchanged (`is`); control: without the forwarding the collated spy is never
called (`probes/class/probe_resolve_traversal_r16.txt`).

### 3.3 executors m68b — condor cluster-hosted services, DAG driverless, lxplus GPU/Triton (PR stacked on m68a)
Two parts, each with its own text, frozen rows and commits: **B1 attached cluster hosting** (`ServiceJob`,
`service.sh`/`announce.py`, the task server's `/announce`, `HTCondorBackend.host_service`/`release_service`; D3's
attached line, D10's condor lines) and **B2 DAG driverless, `job_root`, lxplus** (`SiteProfile.job_root` and m67's
self-submit on it, the DAG, `announce_only`, the in-job backend, the lxplus run and site checks, D3's driverless line,
§9's m68b lines). Shared items: the frozen harness, its invocation rules and `test-htcondor` running
`tests/frozen/m68b` with the simulated-GPU pool line (§6; commit 1, so B1 is gated on its own and B2's live
file finds the GPU when it lands) are B1's; the docs commit and the §7 figures are B2's (commit 3).

| Part | Mechanism | By hand | Rung |
|---|---|---|---|
| B1 | readiness, cluster-hosted | the job curls itself, tells the driver | (6) `service.sh` + stdlib-only `announce.py` owning the service's child (no venv in a Triton image): in-job port, self-check, signed announce; the task server's `/announce` |
| B1 | managed on the cluster | a second pilot cluster | (2) `CondorPilots` shape, another executable, behind D10 |
| B1 | teardown | `condor_rm` | (2) `act(Remove)` at once (a service never drains) |
| B2 | driverless with services | `condor_submit_dag` | (3) `htcondor2.Submit.from_dag` with `usedagdir`, a fresh directory per run, + SERVICE nodes (`probes/m68b/probe_dag_service.txt`); DAGMan removes its SERVICE nodes |
| B2 | where job-made files live | a path in a README | (2) `SiteProfile.job_root` beside `jobs_can_submit`, the one field m67's self-submit and the DAG read |

#### HTCondor behaviour relied on (both parts)
graphed's needs from HTCondor are stated once, as rows `S-*` (submit), `X-*` (scratch), `L-*` (lifecycle), `Q-*`
(queries), `D-*` (DAGMan) and `N-*` (network) in `probes/m68b/condor_surface/NEEDS.md`, each observed on
htcondor/mini 25.13.2 across 11 execute-point configurations in `condor_surface/RESULTS.md` (probe ids there;
`test-htcondor`'s pool, from get.htcondor.org, runs 25.14.1 at 0e48380). A
decision below cites a row only where the row matches or pins it (rows S-19, D-08a and Q-04, and the consequence lines the
`service/` design supersedes, are in RESULTS' appended section); none relies on a value RESULTS lists as not
assumable, each of which is met per job or per DAG instead:
| Not assumed | How the plan stands without it |
|---|---|
| `MOUNT_UNDER_SCRATCH`, `STARTER_NESTED_SCRATCH`, `SINGULARITY_*` (X-01, X-02, X-05, X-08) | the child runs in `service/`, which holds exactly its declared inputs; no scratch name is reserved; job-side paths come from the cwd, never a layout or `/srv` |
| `DAGMAN_USE_STRICT` (D-05, D-06) | each DAG is submitted with `AddToEnv: _CONDOR_DAGMAN_USE_STRICT=0`, and the run's outcome is the driver node's exit, not DAGMan's |
| `DAGMAN_QUEUE_UPDATE_INTERVAL` (D-07) | no `DAG_*` counter and no `DAG_Status` is read; held is a driver-node query |
| `PERIODIC_EXPR_INTERVAL` (L-05) | `periodic_remove` on SERVICE nodes is slot hygiene; no outcome depends on when it fires |
| `MachineMaxVacateTime` (L-02) | `ServiceJob` sets `job_max_vacate_time = 30`; `announce.py` bounds its own reap |
| a credd/credmon (X-04) | `MY.SendCredential` only where a site row has it (lxplus), never on generic, and dropped on an attached `ServiceJob` |
| a job `PATH` (S-05) | `announce.py` never uses `sys.executable`; a bare name resolves on `os.defpath` |
| per-job network namespaces (N-02) | the in-job bind-scan and the SERVICE node dialling the driver assume a shared one; a site check measures it |
Also from the matrix: graphed never reads back its own `act(reason=)` (dropped, L-09); a job's `output`/`error` exist
only once it produced them (S-04); an `initialdir` must exist at submit (S-03); a missing `transfer_output_files`
entry holds a job for every exit (S-15); a symlink to a directory, or a `,` in a path, holds a job at input transfer
(S-08, S-09).

#### B1 — attached cluster hosting (`htcondor_backend/services.py` ~230, `announce.py` ~290, `server.py` +60, `backend.py` +30, `launch.py` +1)
- **Secrets.** A `ServiceJob` never carries the task server's secret, which signs pickles: the task server mints a
  per-call *announce secret* (`TaskServer.announce_secret(keys) -> bytes`, 32 random bytes valid only on `/announce`
  and only for those keys; attached: the call's one key; B2: a driver start's node ids), and that is what the job
  gets as `graphed-secret`. `announce.py` also reads it into memory and unlinks the file before starting the child:
  the child runs in `service/` and cannot serve it, but it could still read `../graphed-secret` (history: with the
  pilots' secret in a served cwd a worker-port GET gave code execution in the driver,
  `probe_r12_b1_secret_served.txt`, `probe_r12_b1_pool.txt`; unlinked, `probe_announce_rules.txt` L8).
- **The child's directory holds exactly its declared inputs, by construction.** A service does not depend on the
  analysis, and scratch receives what condor and the job put there (on lxplus the user's Kerberos ticket cache,
  `KRB5CCNAME=FILE:/srv/<user>.cc`, `probes/site-lxplus/m67-driverless.txt`; on lpc the transferred
  `x509userproxy`; the job and machine ads; `tmp`/`var` under `MOUNT_UNDER_SCRATCH`; our own `service.sh`,
  `service.json`, `announce.py`, `graphed-secret`, `env.tgz`/`env`). So the inputs never enter scratch's namespace:
  `ServiceJob.files(dir)` builds `dir/service/` on the submit side with one entry per recipe input, named by its
  basename — a file as a symlink to its absolute path (`probe_r22_b1_relative_paths.txt`), a directory as a real directory tree mirroring it (walked
  without following links) whose files are symlinks — and transfers that one directory, `dir/service` (no trailing
  separator). Condor follows file symlinks and holds a job on a symlink to a directory anywhere (S-08), hence the
  mirror; an input sharing a job file's name, `.machine.ad` included, lands inside `service/` and replaces nothing,
  so the identity `$_CONDOR_MACHINE_AD` names stays the EP's (S-12; `probes/m68b/probe_input_dir.txt`, unspooled and
  spooled). `announce.py` starts the child with `cwd=service/` (created empty when the recipe has no inputs; a
  `service` that is a mount point exits 3 naming it), never using its own `sys.executable`, which is empty for a
  bare `python3` in a job without `PATH` (S-05). `{python}` names the job dir's interpreter and is resolved there,
  before rendering: a name with a separator is made absolute against `announce.py`'s cwd (on POSIX `Popen` resolves a
  relative `argv[0]` against the child's `cwd`, so `./env/bin/python` would miss from `service/`,
  `probe_announce_rules.txt` L10), a bare name with `shutil.which` on `$PATH` or `os.defpath`, else passed bare. A
  literal `argv[0]` is left as written, so a relative one resolves against `service/`, where the recipe's inputs
  are (L11: an executable input `./serve.sh` runs; a mirrored 0755 file lands executable, spooled or not,
  `probe_r17_b1_input_exec.txt`). A `Popen` that raises exits 3 naming `argv[0]` and the error (L12). L9: a
  stand-in ticket beside `service/` 404, an input 200. The one rule: the child's cwd contains exactly
  the declared inputs. The only refusals, at `ServiceJob` construction naming the input, are about the allowlist
  itself: an input that does not exist, two inputs sharing a basename, an input that is or contains a symlink to a
  directory (S-08). An input or nested file whose name holds `,` transfers intact inside `service/`
  (`probe_r17_b1_comma.txt` A); what a `,` splits is a listed path (S-09), so every `transfer_input_files` entry is
  named relative to `initialdir` (B). No scratch name is reserved, so no site's scratch layout is assumed. An attached `ServiceJob`
  drops `MY.SendCredential` from the profile keys: it gets its inputs by transfer and needs no ticket (the pilots'
  keys keep it); a watch-mode one (B2) keeps it.
- The child's environment is the recipe's `env` over the job's own (`{**os.environ, **env}`): condor's
  `CUDA_VISIBLE_DEVICES` (S-18) and an image's `PATH` (X-08) reach it (L15). `recipes.http_server` with its default
  `root` has `inputs=()` and serves its cwd, `service/`; any other `root` is its input, so it must be a bare name
  (`probe_r23_b1_base_claims.txt` H).
- `ServiceJob(spec, launcher: CondorPilots, *, key, url=None, secret=None, watch=None)`: `files(dir)` writes
  `service.sh`, `service.json`, `graphed-secret` (`write_secret`, attached only) and a copy of `announce.py` into
  `dir` and returns the submit keys without submitting (B2 writes SERVICE nodes with it); `submit()` does that in a
  new `service-<key>/` under `launcher.log_dir` (created with `exist_ok=False`: the key is per call,
  so no call reuses another's directory; its `initialdir`, pinned: `CondorPilots.submit_description`'s own
  `initialdir`/`arguments` are not reused) and submits one cluster of one job on the launcher's schedd in
  `CondorPilots.start`'s shape, `with ExitStack() as stack: launcher._submit(…, stack); …; self._stack =
  stack.pop_all()`: `_submit` registers the cluster's removal on `stack` when `schedd.submit` returns and then spools
  (the profile's spool holds), and it is this `with`, not `_submit`, that closes the stack, removing the cluster, when
  the spool raises (a raising `schedd.submit` has registered nothing). `CondorPilots.start` makes `log_dir` absolute before it writes there
  (`os.path.abspath` over the given or `mkdtemp` directory), so every path later spelled from it — `service-<key>/`
  with its `initialdir` and `executable`, the `env.tgz` link target, the pilots' secret `CondorPilots.stop` unlinks —
  names the directory `start` wrote into, whatever the cwd then (`probe_r23_b1_logdir_abs.txt`). Keys:
  `CondorPilots`' base keys (`transfer_output_files='""'`), `executable=<initialdir>/service.sh` (absolute: a relative
  executable resolves against the submitter's cwd, not `initialdir`, as `CondorPilots.start` already knows,
  `probe_r8_paths.txt` E), `arguments="service.json"` (secret and url travel in files), `output`/`error`/`log` =
  `service.{out,err,log}`, `transfer_input_files=announce.py,service.json,graphed-secret[,env.tgz][,service]`, every
  entry relative to `initialdir`, so a `,` in `launcher.log_dir` splits nothing (`probe_r17_b1_comma.txt` C) (no
  `graphed-secret` in watch mode; `service` when the recipe has inputs, their paths resolved against the driver's
  cwd; the argv names each input by its basename, relative to `service/`, so a recipe must name an input by a bare
  name, e.g. `recipes.triton(model_repository="models")`, never `data/models` or an absolute path; `env.tgz` a
  file symlink in `initialdir` to the pilots' own `env.tgz`, followed by condor, spooled or not
  (`probes/m68b/probe_r18_b1_envlink.txt`), not rebuilt, on
  `ship_env` sites iff the recipe has no `image`), `request_cpus` = `resources["cpus"]` (default 1), `request_memory` =
  `resources["memory_mb"]` (default the launcher's), `request_gpus` iff `resources["gpus"] > 0`, each rendered
  `str(int(v))` (`Launch.resources` is `Mapping[str, float]`),
  `JobBatchName=graphed-service-<key>`, `job_max_vacate_time=30` (a stuck service releases the slot and GPU in
  30 s whatever the EP's `MachineMaxVacateTime`, L-02), then the profile keys (attached: less `MY.SendCredential`), `MY.SingularityImage` = `f'"{image}"'` (quoted as
  the profile templates it; over the profile's), the launcher's `extra_submit`. `service.json` = `{argv, env, check, ports: profile.worker_ports, key,
  url, watch, python, timeout_s, lease_s, beat_s}` (attached: `url` the backend's task server's, `watch` null; watch
  mode: `url` null), `lease_s`/`beat_s` = `server.LEASE_S`/`POLL_S` read when the files are written (`announce.py`
  imports nothing of ours; watch mode reads neither); the secret is no field: attached mode reads `graphed-secret`
  in its cwd, watch mode `<watch>/graphed-secret`. The
  interpreter (`python`, and what `service.sh` execs) is `CondorPilots._stage`'s for an image-less recipe
  (`./env/bin/python` on a `ship_env` site, else the driver's `sys.executable`) and `python3` for an imaged one;
  `service.sh` unpacks `env.tgz` when present, exits 3 naming the interpreter when `command -v` misses it, then
  `exec`s it on the transferred `announce.py service.json` (a job has no package to `-m`: an imaged recipe runs
  without our venv). `alive()` as `CondorPilots`; `stop()` closes that stack at once, i.e. `CondorPilots._remove`
  (a spooled job that already completed, `JobStatus` 4, is retrieved first, so `service.out`/`.err`, the reason
  `announce.py` exited 3, reach `service-<key>/`; what is queued is removed, which ends the child,
  `probe_service_job.txt` B), then unlinks its submit-side `graphed-secret`; no drain, since a service never exits by
  itself (`CondorPilots.stop` drains 20 s first; `probe_r23_b1_base_claims.txt` K, D). `host_service`'s
  `RuntimeError` names `service-<key>/` without assuming either file exists (a job held at input transfer never wrote
  them, S-04).
- `announce.py` (module `graphed_executors.htcondor_backend.announce`, prototype `probes/m68b/announce_proto.py`):
  stdlib only, runs under python ≥ 3.9 (`from __future__ import annotations`; timeouts caught as `OSError`, never
  `socket.timeout`, which ruff's py311 `UP041` would rewrite to a class that differs on 3.9; no 3.10+ stdlib names),
  a `__main__` guard, so the file the job runs by path and `python -m` run the same code. The `test` job's prek runs
  `mypy --strict` on Windows too, so its Unix-only names (`os.WNOHANG`, `signal.SIGKILL`,
  `pthread_sigmask`/`SIG_BLOCK`/`SIG_UNBLOCK`) sit behind `sys.platform` guards placed so the every-OS in-process
  legs still run on Windows: in `hard_reap` after the `pid is None` return (`if pid is None or sys.platform ==
  "win32": return`), in `start` around the `pthread_sigmask` calls (the block, and the unblock the child's
  `preexec_fn` and the `finally` run); never at module or `main()` level. A POSIX-only test body spells those names
  behind the same guard or as literals in `tests/extra/m68b`, since mypy checks a `skipif` body on Windows too
  (`probe_r24_b1_win32_mypy.txt`, `probe_r23r_b1_win32_mypy.txt` T); `pyproject.toml` disables `attr-defined` for
  `tests.frozen.*`, so a frozen body may spell them bare. Identity = a stdlib copy
  of `host_identity()`; every job-side path is taken from its cwd (scratch is `/srv`, `/srv/scratch` or a host path by
  EP configuration, X-01, X-08). Start, with `timeout_s` the budget of the whole start: for each port of `ports` in order,
  skip it unless it is free; render the argv (`{port}`, `{host}` = the identity, `{python}`), `Popen` it, poll the
  self-check and `child.poll()`; ready = the self-check passing with the child alive. A child that exits moves on to
  the next port only when its port is no longer free (another process took it after the scan); otherwise exit 3 at
  once naming its returncode (no restart per port). "Free", in the scan and after an exit, is a bind with
  `SO_REUSEADDR` set succeeding: a listener refuses it, the `TIME_WAIT` the service's own self-check leaves does not
  (a plain bind reads that as taken and restarts the child per port, `probe_r9_timewait.txt`;
  `probe_announce_rules.txt` L7). At the deadline a live, unready child is killed and the script exits 3 naming the
  last reason; the range exhausted likewise (`probe_service_job.txt` A: first port the task server's, second a
  listener's, the third announced; `probe_announce_rules.txt` L1–L3). The self-check dials `identity:port`, the
  endpoint it announces: `http:<path>` by `check_ready`'s rule (2xx, content-type not `application/grpc*`), `tcp`
  and `grpc:` by a connect (the worker probe runs the gRPC check, §3.1; a connect cannot tell its child from a
  process that took the port, and a child that then dies ends the job, which `host_service` reports). It then POSTs
  the UTF-8 text `key host:port identity`, signed (hex HMAC-SHA256, as pilots sign) with the announce secret, to
  `<url>/announce`.
  Attached mode: the lease clock starts when the child is ready; the POST repeats each second until the first 200,
  then every `beat_s`; a 403 on any POST (another server on that port) or no 200 for `lease_s` — before the first
  200 too — is an orphaned service, as for a pilot: it reaps the child with the one bounded reap below and exits 0,
  so a driver that died, even while the job was still idle, frees the slot (`probe_announce_rules.txt` L4–L6; a
  SIGTERM-ignoring child is killed within 5 s + margin, L13; nothing outside the job would end it, since `job_max_vacate_time`
  applies only to a removal). Watch mode (`watch` = a
  directory, B2's SERVICE node) has no orphan rule: each second it reads `<watch>/driver.url` and
  `<watch>/graphed-secret` and announces each new pair until it takes a 200 (a torn read or a refused POST is
  retried; a retried driver rebinds the same url with a new secret, `probe_dag_service.txt` R). Once ready it logs
  `ready pid=<child pid>` to its stdout. **One bounded reap** serves every exit path — orphan (403 or no 200),
  SIGTERM, the start deadline, a start that fails: terminate the child, wait for it at most 5 s, kill it (a child
  that exited already needs none). The SIGTERM handler (condor sends SIGTERM to the whole process family at once,
  L-02) never waits: it sets SIGTERM to ignored and raises a private `BaseException` into the main thread, whose
  top level reaps and leaves through `sys.exit(143)` (so coverage saves its data). A handler that waited could
  block for good on `Popen`'s waitpid lock, which an interrupted `wait` in the main thread holds
  (`probe_r19_b1_orphan_reap.txt`), and the raise itself can land just after `Popen` took that lock and leak it; so
  the post-SIGTERM reap works on the child's pid, never through `Popen`: `os.kill(SIGTERM)`, `os.waitpid(pid,
  WNOHANG)` polled for at most 5 s, then SIGKILL and a blocking `os.waitpid` (an already-reaped child ends it); a
  recorded child whose `returncode` is set, which `Popen` has reaped, is not signalled, since its pid may be reused
  (L17). The
  child is created and recorded with SIGTERM blocked (`pthread_sigmask`), and the child unblocks it before exec
  (its `preexec_fn`), so no SIGTERM lands between the two and the child still sees condor's. A SIGTERM during an
  orphan reap ends the job within 5 s + margin (L14); the handler neither waits nor polls (L16). Otherwise the exit code is the child's.
- `TaskServer`: `/announce` is routed before the pickled routes' signature check and before any `pickle.loads`
  (today every signed body is unpickled, `probe_code_premises.txt` T): the body is decoded as UTF-8 text only (not
  UTF-8, or empty: 403, nothing recorded, since no key means no secret to verify against); its first field names
  the key, and the signature must verify against the announce secret registered for that key
  (never the pilots' secret), else 403 and nothing recorded; then exactly three whitespace-separated fields `key
  host:port identity` with an integer port, else 400. The pickled routes verify only the pilots' secret, so an
  announce secret signs no pickle (403). `announce_secret(keys)` registers; `forget_announce(keys)` drops. It
  records `(host:port, identity)` under `key` and wakes `wait_announce(key, timeout) -> tuple[str, str] | None`,
  which pops the record it returns (`None` after `timeout`). Other paths route as today (`/result` the
  fallthrough); `lease` is unchanged. Announces wait
  on their own `Condition`, so a wake-up meant for a leasing pilot is never taken by `wait_announce`.
- `HTCondorBackend`, attached: `host_service`/`release_service` are instance attributes iff the launcher is a
  `CondorPilots` and `"cluster" in self.service_hosts` (absent otherwise: a `LocalPilots` or `("driver",)` backend
  refuses a GPU recipe naming the attribute, §3.1). `host_service(spec, scope)` mints the D10 key and its
  announce secret, starts a `ServiceJob` (its removal registered when `schedd.submit` returns) and calls `wait_announce(key, …)` in `POLL_S`
  slices with `job.alive()` between: an announce → `(f"{scheme}://{host:port}", identity, key)`, scheme by D2; the
  job gone or held (other than spooling, code 16) → removed, `RuntimeError` naming the key, `JobStatus` and
  `ExitCode`/`HoldReasonCode`, `HoldReason` only when condor set one (graphed's own `act(reason=)` is dropped and
  never read back, L-09) (from `schedd.history(..., match=1)` once it left the queue, as `RunHandle._poll`);
  `spec.timeout_s` passed → removed, `TimeoutError` naming the timeout and `JobStatus` (a GPU request no slot matches
  stays idle, `probe_service_job.txt` D); every failure path, `ServiceJob`'s construction refusal, `schedd.submit` raising and the spool raising included, also calls
  `forget_announce([key])` before it raises. `release_service(key)` = `forget_announce([key])` first (a beat after
  it gets 403 and records nothing), then that key's `ServiceJob.stop()` and a pop of its record.

#### B2 — DAG driverless, `job_root`, lxplus (`sites.py` +10, `driverless.py` +190, `driver.py` +35, `backend.py` +25, `launch.py` +10, no `services.py` change)
- **`SiteProfile.job_root: str | None = None`** (after `jobs_can_submit`): the tree the site's schedd and every job
  read and write directly, so a job-submitted cluster's `initialdir` and a DAG's directory must lie under it. lpc `None` (none;
  its jobs cannot submit either), lxplus `"/afs"`, generic `"/"` = every path (the one-host pool). "Under" is
  `root == "/" or Path(os.path.abspath(p)).is_relative_to(root)` (`PureWindowsPath("C:/x").is_relative_to("/")` is
  False, and m67's all-OS generic self-submit case stays green), applied to the directory actually used (with
  `log_dir=None`, generic accepts the temporary dir, any other root refuses). `driverless._SELF_SUBMIT_ROOT` is
  deleted: `submit_driverless(pilots="condor")` reads `profile.job_root` after its `jobs_can_submit` and
  `worker_ports` refusals, as today; `None` refuses naming `job_root` (today a profile outside the dict self-submits
  unchecked: fail closed), a dir outside refuses naming the root (lxplus: `/afs`, as m67's test reads). A DAG reads
  the same field the same way (`probes/m68b/probe_code_premises.txt` S, W).
- **Which specs become SERVICE nodes.** `submit_driverless` assigns a spec of `plan.services` a SERVICE node iff it
  has a `launch`, no `services=` endpoint names it, its `kind` is not a key of the site row's `services` (D2: leg 2
  is tried in the job first; if it fails there, leg 3 has no host for that name and the run's `ServiceSet` raises,
  which exits 1 and is retried), and the driver job cannot host it (`launch.image` or `resources.gpus > 0`; a driver
  job's `service_hosts` is `("driver",)`, §3.1). So a driverless LPC Triton plan resolves by the EAF row, as in m68a.
  Each such spec gets a derived node id `svc<i>` (`i` its index among those specs, in name order): node name, `.sub` file stem and
  announce key alike, since a spec name is a free string (`driver` collides with the driver node and DAGMan refuses
  the DAG, `probe_r11_dag_names.txt`; whitespace cannot cross the three-field announce). `run.json.announce_only` =
  `{name: id}`.
- **DAG.** A non-empty `announce_only` makes the submission a DAG in its own new run directory
  `<log_dir>/graphed-<nonce>/` (`nonce` the 8-hex one m67 already mints for `JobBatchName`; created with
  `exist_ok=False`, so no DAG ever reuses a directory), refused before any bindings call unless `worker_ports` is set
  and `job_root` holds `log_dir`, every `user_modules` path and every `announce_only`
  recipe's `inputs` (each refusal naming its field, the path and the root; lpc names `job_root`): the unspooled
  nodes transfer those paths straight from the schedd, and one it cannot read holds its node (S-13): a held driver
  node (an unreadable `user_modules` path) stays `held` (D-09); a held SERVICE node is removed by its
  `periodic_remove` and the driver then fails after three × `timeout_s`. The check is lexical (`abspath`, not
  `realpath`): an input under `job_root` that is a symlink to a path outside it passes it and takes that path. Copying them into the DAG dir is not done (a model repository can be large). Files: `driver.sub` (m67's
  description less `max_retries`/`retry_until`), per id (after `_stage` has built the run dir's `env.tgz`, which the node's `env.tgz` link names) a `service-svc<i>/` written by B1's `ServiceJob(...,
  key=id, watch=<DAG dir>).files` (no secret, `url` null) and `svc<i>.sub` = its keys with that dir as `initialdir`,
  keeping the profile's `MY.SendCredential` (the node reads `dag_dir` in the job every second, and on lxplus that is
  AFS, which needs the user's ticket; `service/` keeps the ticket cache out of the child's served cwd),
  plus `periodic_remove = JobStatus == 5` just before the launcher's `extra_submit`, which may override it: slot
  hygiene (a held SERVICE node frees its GPU once the schedd evaluates it, L-05); the DAG's outcome does not depend on
  it, `run.dag` = `JOB driver driver.sub`, `SERVICE svc<i>
  svc<i>.sub` each, `RETRY driver 2 UNLESS-EXIT 3`, node files named relative to the DAG dir; submitted as
  `schedd.submit(htcondor2.Submit.from_dag(<abs run.dag>, {"UseDagDir": True, "AddToEnv":
  "_CONDOR_DAGMAN_USE_STRICT=0"}))` (an idle or held SERVICE node when the driver ends otherwise turns DAGMan's exit
  into 1 under the site's default strictness, D-05, D-06), never spooled (the dir is under
  `job_root`, which the schedd reads). `usedagdir` makes DAGMan submit the nodes from the DAG dir whatever the
  submitter's cwd (without it a relative node file fails, `probe_r8_paths.txt` D1–D2). A fresh directory per run
  means no previous `run.dag.*`, rescue DAG, `driver.url`, `graphed-secret`, `service-svc*/`, `result.pkl` or
  `driver.log` can be read as this run's, so there is no `force` and no cleanup (`probe_dag_service.txt` R, X, each
  in a fresh dir). The returned `RunHandle`'s `log_dir` is the run directory, so `save`/`load` are unchanged.
  m67's plain driverless job keeps `log_dir` itself as its run directory: m67's frozen live test pins `driver.log`
  in `log_dir` (`tests/frozen/m67/test_driverless_live.py:90`), and a plain job reaches `done`/`failed` only through a
  completed output transfer, which rewrites `result.pkl` (a removed or held one is refused by `result()`), so its
  reuse cannot surface a previous result. `run.json` gains `dag_dir` (absolute) and
  `announce_only`; `driver._runner` reads both with defaults (`run.get("announce_only") or {}`, `run.get("dag_dir")`),
  since m67's `run.json` and m68a's hand-built run dicts lack them. `submit_driverless`, plain or DAG, refuses
  before any bindings call a `user_modules` path containing `,`, which would split the input list (S-09).
- **In the driver job.** `driver._runner` with `announce_only` builds the task server as for `pilots="condor"` (host
  the slot's `Machine`, ports the row's `worker_ports`: the SERVICE node dials it from another node) and, once it
  listens and before `wait_for_pilots`, writes `graphed-secret` (the announce secret its task server mints for the
  run's node ids; a SERVICE node never reads the pilots' secret, which m67's `pilots="condor"` keeps under
  `<dag_dir>/pilots/` in the same tree) then `driver.url` into `dag_dir`,
  each through a temporary file written as `write_secret` writes the pilots' secret (mode 0600) and then
  `os.replace`d (on a local `job_root` such as generic's `/` the run dir is umask-readable). The SERVICE node reads it from `dag_dir`, not from its child's
  cwd. Its backend (`in_job=`, §3.1) is `HTCondorBackend(..., announced=announce_only)`
  and binds `host_service`/`release_service` iff `announced` is non-empty, submitting nothing: a name outside it →
  `ValueError` naming `announce_only` (a driver job starts no `ServiceJob`); else `wait_announce(announced[name],
  spec.timeout_s)` → `(scheme://host:port, identity, id)`, `None` → `TimeoutError` naming the SERVICE node;
  `release_service(id)` pops the record and stops nothing (DAGMan removes the node at DAG end). Keying by the node id
  is sound here: the task server lives for one driver start, which runs one plan. So a DAG-hosted name resolves by
  §3.1's leg 3 cluster-hosted, and its status carries `leg="managed", host="cluster"` and the announced identity,
  which the worker probe compares.
- **Tracking.** `RunHandle(..., dag: bool = False)` (m67 saved handles load) tracks the DAGMan cluster
  (`JobUniverse 7`) and its driver node. `status()` maps DAGMan's own ad (queue, else history, as m67) by its
  `JobStatus`: 3 → `removed`; 5 → `held`; 1 or 2 → one query for the driver node (`DAGManJobId == <cluster> &&
  DAGNodeName == "driver"`, projecting `ClusterId`, `JobStatus`, `HoldReasonCode`): `held` if it is held other than
  spooling, `running` if it runs, else `queued`; 4, queued or in history → the latest driver try's outcome, the
  highest `ClusterId` among `schedd.history(<driver-node constraint>, [...], match=3)` (`RETRY driver 2` allows three
  tries, each a new cluster, D-08): `ExitCode` 0 → `done`, else or none → `failed`; any other DAGMan `JobStatus` (6, 7) → `running`, as m67's `_poll` maps it. No `DAG_*` counter (refreshed every 300 s by default, D-07), no `DAG_Status`
  and no DAGMan `ExitCode` is read (D-05, D-06). `wait()` keeps m67's terminal set (`held` stays releasable, as for m67's plain job), so on a
  held driver node its `TimeoutError` names `held`; `result()` reads `result.pkl`
  where the driver node's output transfer lands it, the run directory, and never retrieves, spooled site or not; a
  `failed` DAG without one (every driver start removed, DAGMan failing at startup) raises `RuntimeError` naming the
  status and `run.dag.dagman.out`, not a bare `FileNotFoundError`. The
  description's `OtherJobRemoveRequirements = DAGManJobId =?= $(cluster)` removes each SERVICE node when DAGMan
  leaves the queue; on that success path its `RemoveReason` names it (`probe_dag_service.txt` R, X), while DAGMan's
  abort path writes "Removed by DAGMan" (D-11).
- **A killed driver is a failed try, never a held node.** A `transfer_output_files` entry missing at exit holds a job
  whatever its exit (S-15), so a driver killed before writing `result.pkl` (OOM, SIGKILL, a missing interpreter)
  would hold its node, and m67's plain job likewise, for ever (`probe_r12_dag_held_node.txt`). `driver.sh` (written by
  `launch.CondorPilots._stage`, through an argument only the driver's call passes, so `pilot.sh` is unchanged;
  plain and DAG alike) therefore first writes `result.pkl` = the pickle of `(False,
  RuntimeError("the driver exited before writing a result; see driver.log"))`, its bytes embedded at submit as
  `printf` octal escapes, and appends to `driver.log`, then `exec`s the interpreter; the driver overwrites
  `result.pkl` on every exit it reaches (`probes/m68b/probe_placeholder.txt`: killed → that `RuntimeError` loads,
  finished → the driver's value). A killed try then completes by signal and is retried by `max_retries` (plain,
  L-06) or `RETRY` (DAG: a SIGKILLed or exec-failed driver with the placeholder present is retried three times, never held,
  `probe_r17_b2_sigretry.txt`); after the last one `result()` raises that `RuntimeError`. m67's frozen tests read
  `driver.sh` only by name (`test_driverless_payload.py:107`) and run the driver as `python -m …driver`, so they stay
  unmodified and green. A SERVICE node that dies before
  announcing costs up to three driver starts × `timeout_s` before the DAG fails (the in-job backend does not query
  the schedd).
- **lxplus GPU/Triton run (evidence).** The analysis declares `recipes.triton("triton",
  image="/cvmfs/unpacked.cern.ch/nvcr.io/nvidia/tritonserver:24.11-py3", model_repository="models")` (§3.1's gRPC
  argv, `inputs=("models",)`, `resources={"gpus": 1}`) with `models/graphed_identity/` = P9's ONNX files verbatim
  (24.11-py3 ships the `onnxruntime` backend, `probes/services-lxplus/p3-triton-image/transcript.txt`) and the §3
  params with `service="triton"`; `htcondor_runner(site="lxplus", n_pilots=2, image=coffea…,
  extra_submit={"+JobFlavour": '"espresso"'})` resolves it by leg 3 cluster-hosted from CPU pilots (B1's path).
- **Site checks** (owner, after the PR's CI is green; not blocking the freeze): (1) the lxplus run above →
  `probes/site-lxplus/m68-triton.txt`: the announce (with the image's `python3 --version` and which identity form it
  carried, `Machine` or `getfqdn`; that the `ServiceJob`, without `MY.SendCredential`, is accepted and starts;
`ls -A` of its scratch and of `service/`, with no ticket cache in `service/`; inside the image `echo $PATH $TMPDIR
$HOME` and `python3 -c 'import sys; print(repr(sys.executable))'`; `condor_status -af MachineMaxVacateTime` for a
GPU slot and that a removed Triton leaves the slot within `job_max_vacate_time`; whether two jobs on one node share
ports, N-02), the probe's `grpc:` check from another host, infer bit-for-bit over
  `tritonclient.grpc`, then a second run with `services=` a user-held `ServiceSet`'s endpoints (leg 1, same plan);
  (2) the same plan driverless from an `/afs` cwd (where `models/` lies) and `log_dir` → `probes/site-lxplus/m68b-dag.txt`: the `from_dag(<abs
  run.dag>, {"UseDagDir": True, "AddToEnv": "_CONDOR_DAGMAN_USE_STRICT=0"})` submit accepted unspooled
  (`dagman.out` shows `DAGMAN_USE_STRICT setting: 0`; `condor_config_val -schedd DAGMAN_USE_STRICT
  DAGMAN_QUEUE_UPDATE_INTERVAL` recorded), the SERVICE node reading
  `driver.url`/`graphed-secret` on AFS, inside the SERVICE node's image (`condor_ssh_to_job`) its `klist`, or where `klist` is absent that `$KRB5CCNAME`'s cache file exists, and `ls -a` of its `service/` (no ticket cache),
  `fs listacl` of the DAG dir, the node removed at DAG end; (3) at lpc (owner, with m69b's site run): a job's
  `x509up_u<uid>` landing name and `$X509_USER_PROXY`, and `ls -A` of its scratch (the EP's
  `MOUNT_UNDER_SCRATCH` effect), X-03, X-05.

#### Frozen `tests/frozen/m68b/`
Harness (B1): m68a's `services_harness.py` copied. The subprocess legs run `announce.py` as `[sys.executable, "-m",
"graphed_executors.htcondor_backend.announce", "service.json"]`, the same code the job runs by path, so
`test-htcondor`'s coverage records it (a file run by path or a transferred copy records nothing,
`probe_r11_coverage.txt`), with `$_CONDOR_MACHINE_AD` in their env naming a file whose `Machine` is `localhost` (a
runner's `getfqdn` is not assumed to resolve) and identities compared against `host_identity()` under the same env.
B2's live file needs the CI pool's one simulated GPU (`probes/m68b/sim_gpu.config`, `probe_sim_gpu.txt`); B1's
timeout leg asks for two, which that pool never matches.
| Part | File | Property | Witness | Fixture |
|---|---|---|---|---|
| B1 | `test_announce_route.py` (all OS) | unsigned `/announce` → 403, nothing recorded; signed with the pilots' secret → 403; signed with another key's announce secret → 403; signed with the key's announce secret (`announce_secret([key])`) `key host:port identity` → 200, `wait_announce(key, t)` returns `(host:port, identity)` as the body carried, and a second call returns `None` after `t`; a signed body that is not exactly those three fields (two, four, a non-integer port) → 400, nothing recorded; a pickle signed with an announce secret to `/result` → 403 and one signed with the pilots' secret still settles its task; after `forget_announce([key])` the key's announce → 403; a body that is not UTF-8, or empty, → 403, nothing recorded | marker | m66 auth harness copy |
| B1 | `test_cluster_service_job.py` (all OS; the subprocess legs POSIX-only, `skipif(sys.platform == "win32")`: Windows delivers SIGTERM as `TerminateProcess` and can refuse an `os.replace` of an open watched file, and `announce.py` only runs in a Linux job) | `hasattr(backend, "host_service")` iff a `CondorPilots` launcher and `"cluster" in service_hosts`; `ServiceJob` keys: `files(dir)` builds `dir/service/` with one entry per input named by its basename — a file input a symlink to its absolute path, a `models/` directory input a real tree whose files are symlinks — and `transfer_input_files` names `service` (relative to `initialdir`) once, never an input itself, `request_*` from `resources` (no `request_gpus` at 0), `MY.SingularityImage` over the profile's, the launcher's `env.tgz` named for an image-less recipe on a `ship_env` profile and not for an imaged one, `os.path.isabs(executable)` naming `service.sh` in the fresh `service-<key>/`, `initialdir` that dir, `MY.SingularityImage == '"<image>"'`, an integer rendered for a float resource, `arguments == "service.json"`, no secret or url in any value, no `MY.SendCredential` key on an attached `ServiceJob` built on `SITES["lxplus"]` (a watch-mode one keeps it) (control: the pilots' description on that profile keeps it), `graphed-secret` ≠ the task server's pilot secret, an input named `service.json`, `tmp`, `.job.ad`, `.machine.ad` or `a,b` is accepted and `files()` places it only under `dir/service/` (the job's own `service.json` untouched), and `transfer_input_files` names `service` (relative to `initialdir`, the `dir/service/` tree) once and never an input, every entry relative (no absolute entry; a launcher whose `log_dir` holds `,` submits the same keys), `env.tgz` a file symlink in `initialdir`; a `ship_env` launcher (a fake venv) `start()`ed under the recorder from cwd A with `log_dir="logs"`, then, from a cwd B holding its own `logs/env.tgz` and `logs/graphed-secret`, a `ServiceJob` on an input named relatively to B: `initialdir` lies under `A/logs`, `os.path.samefile(<initialdir>/env.tgz, A/logs/env.tgz)`, every file link under `<initialdir>/service/` resolves (`os.path.isfile`), and the launcher's `stop()` unlinks `A/logs/graphed-secret` and leaves B's; a missing input, two sharing a basename, and an input that is or contains a symlink to a directory are refused at construction naming it (control: `models/` accepted); `job_max_vacate_time == "30"`; `service.json` `ports == profile.worker_ports` and `lease_s`/`beat_s` the server's; `stop()` unlinks the job's `graphed-secret`; `service.sh` execs `./env/bin/python`, `sys.executable` or `python3` per case; `announce.py` imports stdlib only and parses with `feature_version=(3, 9)`; in process, on every OS (the prototype's `main`, `serve`, `on_sigterm`, `_Stop` and `CHILD` keep their names): `on_sigterm` called with `Popen.wait` and `Popen.poll` spied raises `_Stop`, leaves `signal.getsignal(SIGTERM) is SIG_IGN`, and the spies saw no call; `main()` with `serve` raising `_Stop` and `CHILD[0]` a `Popen` already waited on exits 143 with no `os.kill` call (spied; control, POSIX-only, the pid reap using the Unix-only `os.WNOHANG`/`SIGKILL`, `probe_r23_b1_l17_nonposix.txt`: an unreaped child gets exactly one SIGTERM); each restores the previous SIGTERM disposition in a `finally`; `host_service` on a spec whose input is missing raises at `ServiceJob` construction after minting its announce secret, and a spy on `TaskServer.forget_announce` sees that key forgotten (under `record_bindings`, as the failed-spool leg); m68a's `test_a_failed_spool_leaves_no_cluster_and_no_port` shape for `host_service`, on `dataclasses.replace(SITES["generic"], spool=True)` under `record_bindings` with `RecordingSchedd(queue=[[{"JobStatus": 5}]])` and the backend over `CondorPilots` built first (its own spool passes): with `schedd.spool_raises` then set, `host_service` raises it, the log from the service's `submit` on holds an `act` naming `Remove` on `ClusterId == FAKE_CLUSTER` before `close()`, and the `forget_announce` spy saw the key; with `schedd.submit` raising instead (patched on the recorder after the build), the spy saw the key and the call logged no `act`; subprocess legs (env `{**os.environ, "_CONDOR_MACHINE_AD": …}`, keeping `COVERAGE_PROCESS_START`) against a real `TaskServer` on a `{python} -m http.server {port}` spec, `service.json` and `graphed-secret` in the job dir (the child runs in `service/`), as in the job: a child that records at start whether `../graphed-secret` exists records False (unlinked before the start: the discriminating leg), while the beats still take 200; with a stand-in ticket `user.cc` in the job dir beside a `service/models/` laid out as `files()` makes it, the child's cwd lists exactly `models`, `GET /user.cc` → 404 and `GET /models/<file>` → 200; with `service.json.python` = `./env/bin/python`, an `sh` script in the job dir that writes a marker file and then `exec`s `sys.executable "$@"`, the service announces and the marker exists (a relative path would make `Popen` raise); with an executable input `serve.sh` (it `exec`s `python3 -m http.server "$1"`) and argv `("./serve.sh", "{port}")` the service announces, its argv[0] left relative (no absoluteness check); argv[0] `./missing` exits 3 within a few seconds naming `./missing`, with no traceback; with `PATH` removed from the env and `{python}` a bare `python3`, a child that writes its own `sys.executable` to a file announces and wrote `P`, the `sys.executable` that `shutil.which("python3", path=os.defpath)` prints when run without `PATH` (skipped unless `P` is absolute and ≠ the harness's `sys.executable`; `ps`'s `argv[0]` cannot tell, since a macOS framework build re-execs, `probe_r22_b1_python_witness.txt`); a child that ignores SIGTERM is killed within 5 s + margin of `announce.py`'s SIGTERM; with `lease_s` shortened and `url` on a closed port, a SIGTERM-ignoring child: `announce.py` exits 0 within `lease_s` + 5 s + margin with the child's pid gone, and the same with SIGTERM sent to `announce.py` about 1 s after its "orphaned" line exits within 5 s + margin; a child records a job variable and a recipe `env` variable and sees both; a child records its blocked-signal mask, which excludes SIGTERM; with the range's first port held by a listener bound to `("", port)` it announces the next (on macOS a `127.0.0.1` listener does not refuse `free()`'s bind, `probe_r22_b1_held_port.txt`), identity = `host_identity()`; a `tcp` spec announces through the connect self-check; an `http:` spec on a server answering 200 `application/grpc`, over a multi-port range, never announces and exits 3 within `timeout_s` plus a small margin; a child that exits at once, over a ≥10-port range, exits 3 within a few seconds naming its returncode; a child that answers the `http:` check once with a non-2xx and then exits nonzero, over a ≥5-port range, repeated ×10, exits 3 naming that returncode after exactly one child start each time (a count file the child appends to); with `lease_s` shortened: `url` on a closed port (no 200 ever) reaps the ready child and exits 0, a server with another secret (403) likewise at once, and shutting the server down after the announce does the same; watch mode: after announcing to a first server through the watch files, both files replaced by a second server's → the second receives the announce, and the secret alone replaced (same url) → announced again; SIGTERM reaps the child; `announce.py` passes `test-htcondor`'s per-file gate (≥ 90%) with these legs executing it | text; subprocess exit codes; server records; coverage report | — |
| B1 | `test_cluster_services_live.py` (minicondor) | (a) a generic copy with `service_ports=None` (`("cluster",)`): a cluster-hosted `recipes.http_server` (`inputs=()`, serving the empty `service/`) announces the pool host's `Machine`; every probe answer carries it, equal to `backend.host_identity()`, so the probe passes; a pilot task GETs it; the run's end removes the service cluster (it leaves the queue within `job_max_vacate_time`, polled), `close()` empties the queue, history shows both clusters; two sequential runs on one runner each get their own service cluster, and run 2's task records the time `t` of its GET (`time.time()` on the pool host, the one clock of the one-host pool that also stamps history): in history, run 1's service cluster (`JobBatchName` `graphed-service-<run 1 key>`) was removed (history `EnteredCurrentStatus`, JobStatus 3) before `t`, and run 2's (`JobBatchName` carrying run 2's `run_nonce`) has `JobCurrentStartDate` ≤ `t` and `int(t)` ≤ its `EnteredCurrentStatus` (condor stamps whole seconds, truncated, and run 2's removal can share `t`'s second; all three present in a removed job's history, Q-04, `probe_r19_b1_history_times.txt`, `probe_r24r_b1_history_seconds.txt`) (control: `GET /service.json` answers 404, the job's own files being outside `service/`); a queued `submit` overlapping a direct `run` gets two service clusters, and each run's end removes only its own; (b) failure paths on that copy, with a spy on `TaskServer.forget_announce`: `resources={"gpus": 2}` with `timeout_s=20` raises `TimeoutError` naming the timeout and `JobStatus` 1, and the job has left the queue after (polled, not assumed when `act` returns); a recipe whose child exits at once raises `RuntimeError` naming the job's status before `timeout_s`, the job gone from the queue (polled); the spy saw the key forgotten on both paths, and on a successful run's release before `ServiceJob.stop` (a stop spy) | ads, history, pids | the pool |
| B2 | `test_driverless_dag.py` (all OS; the fixture comparison only where real bindings and `condor_dagman` are on PATH, i.e. `test-htcondor`; the placeholder `sh` sub-leg `skipif(shutil.which("sh") is None)`) | `SITES` `job_root` (lpc `None`, lxplus `"/afs"`, generic `"/"`); `driverless` has no `_SELF_SUBMIT_ROOT`; `pilots="condor"` on a generic copy with `job_root=None` refused naming `job_root`, lxplus outside `/afs` naming `/afs`; `announce_only` holds a GPU or imaged launch, not an image-less CPU one, a `services=` name, nor a spec whose `kind` the row's `services` serves: on `dataclasses.replace(SITES["lpc"], sandbox_root=<tmp>)` registered with `monkeypatch.setitem(SITES, "lpc", …)` (`submit_driverless` takes a site name; with `image=` and a fake venv) a `recipes.triton` plan submits one plain job with `announce_only == {}` (control: the same copy with the row's `services={}` is refused naming `job_root`, the recorder empty); ids: specs named `a b` and `driver` get `svc0`/`svc1` (declared `driver` before `a b`, beside an image-less CPU spec `0web` that sorts first and gets no id: ids count only SERVICE specs, in name order) as node names, `.sub` stems, `service-svc<i>/` dirs and `service.json` keys, no `graphed-secret` in them, `driver.sub` keeps the driver's keys, `run.json.announce_only == {"a b": "svc0", "driver": "svc1"}`; DAG text (`JOB driver`, one `SERVICE svc<i>` per id, `RETRY driver 2 UNLESS-EXIT 3`), no `max_retries`/`retry_until` in any node sub, on `dataclasses.replace(SITES["lxplus"], job_root=<tmp>)` (registered with `monkeypatch.setitem`, with `image=`, a fake venv and a GPU or imaged spec) `svc0.sub` carries `MY.SendCredential = True`, and for an image-less GPU spec `os.path.isfile(<run dir>/service-svc0/env.tgz)` (the link resolves: `files()` ran after `_stage`) and the DAG is submitted with `spool=False` although the profile spools (the attached `ServiceJob` on that profile does not, B1's row), `periodic_remove = JobStatus == 5` in every `svc<i>.sub` and not in `driver.sub`, `from_dag` called on the absolute DAG path with exactly `{"UseDagDir": True, "AddToEnv": "_CONDOR_DAGMAN_USE_STRICT=0"}` and `submit` without spool (recorder); a `user_modules` path containing `,` refused before any bindings call, plain and DAG; the `driver.sh` text writes `result.pkl` before its `exec` line, and those embedded bytes, run through `sh` in a scratch dir, load as `(False, RuntimeError)` naming `driver.log`; each submission's files, `run.dag` included, lie in a new `<log_dir>/graphed-<nonce>/` (the handle's `log_dir`), and a second submission into the same `log_dir` gets a different run directory and leaves the first untouched; refused before any bindings call, the recorder empty: lpc naming `job_root`, a generic copy without `worker_ports` naming it, lxplus outside `/afs`, and on a copy with `job_root=<tmp>/root` and `log_dir` under it, a `user_modules` path or an `announce_only` recipe input outside the root naming the path and `job_root` (control: the same under the root submits); the check is lexical: an input path under the root that is a symlink to a file outside it is accepted; `driver._runner` with a run dict lacking both new keys builds as m67's; with `announce_only` it writes `graphed-secret` (on POSIX `stat.S_IMODE(st_mode) == 0o600`) before `driver.url` (an `os.replace` spy) with a url on the ad's `Machine` and a `worker_ports` port, and that secret is not the task server's pilot secret (a pickle signed with it to `/result` → 403); that backend's `host_service` returns `(endpoint, the announced identity, "svc0")` after a signed announce under `svc0`, refuses another name naming `announce_only`, and a `ServiceSet` over it logs `leg="managed", host="cluster"` with that identity; `RunHandle(dag=True)` over a gone DAGMan ad and driver-node history ads takes the outcome from the highest-`ClusterId` driver try, the recorder returning the driver history ads highest-`ClusterId` last (recorded order, Q-03), and logging `match=3`: DAGMan `ExitCode 1` with that try's `ExitCode 0` → `done`, a last try's `ExitCode 1` or no driver ad → `failed`; a running DAGMan ad (`JobStatus 2`, `DAG_JobsHeld: 0`) with a driver-node ad at `JobStatus 5` → `held` (m67's mapping gives `running`), and the recorder logged a query constrained on `DAGManJobId` and `DAGNodeName == "driver"`; no logged projection or constraint names a `DAG_*` attribute; `wait(timeout=0.3)` over the held case raises `TimeoutError` naming `held`, and on a `spool=True` profile a queued DAGMan ad at `JobStatus` 4 beside a driver history ad with `ExitCode 0` and a `result.pkl` in the run dir gives `done` and `result()` that value with no `retrieve` logged (control: the same ads with `dag=False` make m67's `retrieve` call); DAGMan `JobStatus` 1 with no driver ad → `queued`; DAGMan's own `JobStatus` 3 → `removed`, 5 → `held`, 2 with the driver node at `JobStatus` 2 → `running`, and any other `JobStatus` (e.g. 6, 7) → `running`, as m67 maps it; a `failed` DAG handle whose run directory has no `result.pkl` raises `RuntimeError` naming `run.dag.dagman.out` (m67's code raises `FileNotFoundError`); an m67 saved handle loads with `dag=False` | recorder; spies; log record | `data/from_dag-generic.txt` (`probes/m68b/probe_dag_service.txt`'s description under those options; compared after substituting the DAG dir, the bindings' own `CsdVersion` and the `condor_dagman` path; the 25.14.1 wheel's description under these options matches after them, `probe_r17_b2_fromdag_wheel.txt`) |
| B2 | `test_driverless_dag_live.py` (minicondor) | driverless on generic, from a cwd other than `log_dir` (`monkeypatch.chdir(tmp_path)`), with `http_server` given `resources={"gpus": 1}` and a plan whose tasks GET it and whose `resolve_services` puts the body into the value (m68a's `test_driverless_endpoints` shape): a universe-7 DAGMan ad, one SERVICE cluster named `svc0` (`NumJobStarts` 1, `AssignedGPUs` set), `result()` holds the body, on this success path the SERVICE job's `RemoveReason` names `DAGManJobId` (D-11), the queue is empty (polled); a second DAG run (the same GPU SERVICE spec, `RunHandle(dag=True)`) whose plan process SIGKILLs its pilot's parent, the driver (`pilots="local"`), with three driver clusters in history, ends `failed` after the driver's three tries with the placeholder `RuntimeError` from `result()`, never `held` | ads, history, result | the pool |

Fails on (B1): an announce before readiness or without an identity, a port chosen off the node that binds it, a
secret in a job ad, a user credential or any file but the recipe's inputs in the service's cwd, an input that
replaces a job file, a relative `{python}` left relative, the task server's
secret readable through the service or signing a pickle with an announce secret, an announce secret left
registered after a failed or released call, a relative job executable, a dropped or wrong input or env transfer (a link that does not resolve, or reaches another runner's `env.tgz`), a `stop()` unlinking another runner's secret, a directory
input landed without its name, a service restarted per port or given `timeout_s` per port, a timed-out, dead,
orphaned or failed-spool `ServiceJob` left running or queued (orphaned before its first announce too), a service outliving its run,
a run reading or releasing another run's service, an `announce.py` the frozen suite does not measure, a child
started through `announce.py`'s own `sys.executable`, a `{python}` resolved against `service/` or an input's argv[0]
against the job dir, a raising `Popen` that exits with a traceback, a reap (orphan path included) that waits on a
SIGTERM-ignoring child, a SIGTERM handler that waits, a reaped child's pid signalled, a recipe `env` that replaces the job's environment, an input
holding a directory symlink, an absolute `transfer_input_files` entry. (B2): a DAG
without SERVICE, a held driver node reported as running, a status or outcome read from DAGMan's exit, a `DAG_*`
counter or `DAG_Status`, a SERVICE node failing a DAG whose driver succeeded, a killed driver held for ever, a DAGMan `JobStatus` left
unmapped (a queued `4` read as running), a SERVICE node given the pilots' secret, a SERVICE node without the credential its `dag_dir` needs, a node name, file
or key taken raw from a spec name, a SERVICE node for a kind the site serves, a DAG that runs only from its own dir
or reads another run's files, two retry owners, a retried driver the SERVICE node never re-announces to, a DAG
input the schedd cannot read, a second `ServiceJob` from the driver job, a site root read from two places.

Commits (≤2k each; each part's freeze first): B1 — 0. `test(services): frozen m68b, attached hosting` (harness,
three B1 files, ~750); 1. `feat(htcondor): cluster-hosted services and /announce` — `htcondor_backend/services.py`,
`announce.py`, `service.sh` text, server, attached backend, `launch.py` (`CondorPilots.start`'s absolute `log_dir`), `ServiceJob`'s `files()`/`watch` path (its
`MY.SendCredential` kept in watch mode, which B1's row asserts), `test-htcondor` running `tests/frozen/m68b` with the
simulated-GPU pool line (~950). B2 — 0. `test(services): frozen m68b, DAG
driverless` (two B2 files, ~550); 2. `feat(htcondor): job_root and driverless DAG with SERVICE nodes` — sites,
driverless, driver, in-job backend, `launch.py` (`_stage`'s driver-only placeholder argument), the driver-node
tracking (~500); 3. `docs(m68b)` — `api.rst` (`SiteProfile.job_root`), `htcondor.rst`
"Cluster-hosted services" (with `job_root`, whose check is lexical: an input under it that is a symlink to a path outside it passes the check,
and a node the schedd then cannot read is held (a SERVICE node removed after three × `timeout_s`, a driver node
`held`); the child runs in `service/` holding exactly the recipe's inputs by
basename, so `model_repository` is a bare name; a SERVICE node that
never announces costs up to three × `timeout_s`) + the lxplus GPU walk-through; the driverless section: a driver killed before writing a result (OOM, SIGKILL, a missing
interpreter) is now retried like exit 1, not held, after the last try `result()` raises "the driver exited before
writing a result; see driver.log", and the exit table (`docs/htcondor.rst` 279–298) gains a "killed" row; changelog
(~190).

### 3.4 m70 — cluster-hosted services on dask and parsl (graphed-executors PR, stacked on m68b)
One engine change and one implementation per backend; the engine's three legs, probe and teardown are m68a's, and each
backend owns its rendezvous (D10): the engine opens no listener. **Engine** (`submit/services.py` +15): `n_workers()`
on a hosting backend subtracts its hosted services (a hosted actor holds a worker slot for the run); `release_service`
is awaited with the spec's `timeout_s`, and a stop never acknowledged is the refusal; a hosted actor renders
`{python}` as its worker's `sys.executable`. **dask** (`dask_backend/backend.py` +80, `_service.py` ~50):
`host_service` picks a worker from `client.scheduler_info()["workers"]` — the first whose `resources` cover
`launch.resources` (`gpus` → `{"GPU": n}`) and that hosts none of this backend's live actors (its `key → (worker,
future)` map, which `release_service` pops), else refused naming the worker table (`probes/lifetime/probe_dask_first_cover_r21.txt`) — and submits the module-level actor
with `workers=[addr], allow_other_workers=False, pure=False, key=f"service:{name}:{key}"`, exactly the
`pin_to_worker` path `submit()` already forwards (`backend.py:83-84`); the actor `Popen`s the recipe, waits for
`check_ready` where it runs, sets `Variable(f"svc:{key}")` to `(host, port, pid, host_identity())` and loops
on `Event(f"stop:{key}").wait(timeout)` (a bool per miss, no scheduler error); the driver `get`s the Variable
with the spec's timeout and returns `(endpoint, identity, key)`; `release_service(key)` sets that key's Event, awaits
its actor's future, then `client.cancel(fut, force=True)` as the backstop, and deletes the Variable. Scheduler-mediated, so no worker→driver reachability
premise and no driver listener. Premise: `probe_dask_service.txt` (`variable`/`event` legs). **parsl**
(`parsl_backend/backend.py` +70, `transport_peer.py` +50): `host_service` opens the driver side of the existing
rendezvous plane (`_open_driver_endpoint(key)`, one epoch per call) and submits the module-level actor through `executor.submit` (HTEX
has no placement: the actor lands on any manager, which is what a service needs; `resources.gpus > 0` refused naming
HTEX's per-block provisioning); the actor `Popen`s the recipe, waits for `check_ready` where it runs, mints its
endpoint on the plane (`HOST` stays the plane's single-machine loopback, the ceiling §9 names), announces `("service",
name, host, port, pid, identity)` (`host_service` returns `(endpoint, identity, key)` from it), blocks on `recv` until
`("stop",)`, kills the child; `release_service(key)` pops that key's driver endpoint, sends `("stop",)` on it, awaits that call's actor future up to the spec's `timeout_s` (the actor returns only after its child is reaped; a timeout raises naming the actor), and closes the endpoint in a `finally` (`EscalatingHttpTransport.close` suppresses its own errors, `common/http_plane.py`) — `Future.cancel()` on a running HTEX task is local
(measured), so the message is the mechanism. `host_service`/`release_service` are bound on the HTEX instance only (TPE
has none). Premises: `probe_parsl_service.txt`, `probe_ready_identity.txt`. **m70 freezes** `tests/frozen/m70/` (run
in the `test-dask` / `test-parsl` CI legs; local clusters):
| File | Property | Witness | Fixture |
|---|---|---|---|
| `test_hosted_service_attribute.py` (all OS) | `host_service` is callable on condor (a `("cluster",)` profile), `DaskBackend` and `ParslBackend(HTEX)` and absent on `ThreadBackend` and `ParslBackend(TPE)`; `dataclasses.fields(SubmitCapabilities)` names are still the m42 seven; a GPU recipe on an attribute-less backend refuses naming `host_service`; `n_workers()` drops by one per hosted service on both hosting backends | attributes; field names; counts | — |
| `test_dask_hosted_service.py` | `SubmitRunner(DaskBackend(LocalCluster 3×1), …)` (a slot beyond the hosted actors) over a plan declaring the generic `recipes.http_server` requirement with no endpoint given: the status is `leg="managed", host="cluster"`, the announce came from a worker address ≠ the driver, plan tasks completed while the actor held, the probe passes on answers carrying the driver's identity, a task GETs the endpoint at its first try, zero `EscalatingHttpTransport` constructions on the driver (spy), the run's end frees the port and leaves every worker's `processing` empty; two sequential runs and a `submit` overlapping a `run` on one runner each get their own actor pid, the overlapping pair's actors on different worker addresses with both `host_service` calls returning within `timeout_s`, and each run's end stops only its own; a recipe with `resources={"gpus": 1}` on a cluster without a `GPU` resource refuses naming the worker table, with it (`LocalCluster(resources={"GPU": 1})`) lands on that worker, and a `host_service` while every covering worker hosts an actor refuses naming the worker table | scheduler_info; pid; port | the local cluster |
| `test_parsl_hosted_service.py` | the same over `start_htex(workers=3)` (a slot beyond the hosted actors): the announce pid ≠ driver pid, tasks ran on a worker pid other than the actor's, the run's end ends the child (pid gone) and frees the port, also for a harness actor whose stop handler sleeps ~1 s before it kills the child; the same two-run and overlap legs as dask, after which each run's driver endpoint refuses connections and `threading.active_count()` is back to its value before the runs; a stop that is never acknowledged (a recipe whose actor ignores stop, injected through the harness) refuses at the timeout naming the actor and its driver endpoint then refuses connections; on TPE the recipe refuses naming `host_service` | pids; port; timeout text | HTEX |
Fails on: a service outliving its run, a run reading or releasing another run's service, two actors on one worker, an actor on the driver, a driver endpoint left open, a double-counted slot, a future-only cancel, an engine
naming a backend. Commits: 1. `feat(services): hosted-service accounting and stop timeout` (~60 + extra tests); 2.
`feat(dask): host_service` (~150 src, ~300 tests); 3. `feat(parsl): host_service` (~120 src, ~300 tests); 4.
`ci+docs(m70)` (`htcondor.rst` "Services on dask and parsl"; ~100). Freeze ~700 first.

## 4. m69a — the H→γγ translation (graphed-executors PR against `main`, parallel with m67)

Home `examples/hgg/` (`analysis.py`, `run_local.py`, `validate_real.py`, README): an analysis, linted and typed by
prek, on the frozen test's `sys.path` (m66 `user_modules` idiom), outside the coverage gate. Events are coffea
NanoEvents, `NanoEventsFactory.from_root({uri: "Events"}, schemaclass=NanoAODSchema, mode="graphed", metadata={…})`
(fork b2612ab), never hand-zipped uproot arrays; chunks are explicit `Partition(uri, "Events", start, stop)`s given
to `aggregate_plan(…, partitions=)`. It reads what the original reads, where it reads it: `infer_nano_version` from
the installed `higgs_dna`, the golden and jet-ID JSONs via `importlib.resources` on `higgs_dna` at the original's
paths (`probe_hgg_infer_and_sums.txt`). Per chunk: the original's return `{dataset: {nTot, nPos, nNeg, nEff,
genWeightSum}}` and parquet part (sorted columns, KV metadata), named `<uri stem>_Events_<start>-<stop>.parquet`
(the original's suffix; its prefix is the file UUID). Plan value `{part_name: counters}` (combine = disjoint
union); `totals(value)` = `coffea.processor.accumulate(value.values())`, as coffea's Runner accumulates the
original's returns.
| # | Template op | Decision |
|---|---|---|
| 1 | `int()`/`len()` on deferred counts | rewrite: counters are plan outputs (`gak.num(events, axis=0)`, `gak.sum(genWeight)`, `gak.sum(genWeight > 0)`, …); `HggProcess` gives each the original's Python type |
| 2 | `.to_numpy()` | rewrite: the counters above |
| 3 | `__setitem__` | rewrite: `gak.with_field` |
| 4 | `ak.Array({...})` rebuild | rewrite: `gak.zip` of the flat columns |
| 5 | `ak.to_arrow_table` → parquet | rewrite: `HggProcess`, a picklable wrapper of the plan's `process` (`__call__(partition, resources)` runs the inner `_PartitionReduce`, then the original's `dump_to_parquet` steps on the materialized record — `ak.to_arrow_table(extensionarray=False)`, sorted columns, KV metadata merged — and returns `{part_name: counters}`); `to_parquet` is a second pass with no per-file metadata |
| 6 | `events.attrs[...]._partition_key` | rewrite: the part name from the partition, inside `HggProcess` |
| 7 | `LumiMask` | rewrite: a 25-line user plugin through `graphed.preserve.externals.record_external` (payload = the golden JSON bytes at the original's path; evaluator = coffea `LumiMask` on eager run/lumi); data only |
| 8 | `CorrectionSet.evaluate` | rewrite: `gak.apply_correction` |
| 9 | `numpy.where`/`numpy.copy` | rewrite: `gak.where`; drop `copy` |
| 10 | `bool(gak.num(...) > 0)` guards | rewrite: delete the guards (the ops are total); each fixture's second chunk is an empty selection |
| 11 | `with_name("PtEtaPhiMCandidate")` needs `charge` | rewrite: already zipped; vector behaviors come with graphed NanoEvents (P5: 28 shapes OK); no row needs a graphed change |

### The oracle is the original (`tests/frozen/m69a/`, harness `hgg_harness.py`)
`data/inclusive_processor.py` is byte-identical to the owner's file (sha256 `791229c2…d1dd` pinned; path-excluded
from ruff and mypy), imported as a module. `higgs_dna` @ d179305 installs from its gitlab ref with `--no-deps` (the
script's only import, `misc_utils`, needs coffea's deps; the declared ones add torch, xgboost, onnxruntime).
`Era2022_v1.json` ships in the package; the 2024 golden JSON and `jetid.json.gz` (sha256-equal to what
`pull_files.py` places) are checked in under `data/`, and a session fixture (`hgg_harness.place_higgs_dna_data()`)
copies them to `pull_files.py`'s target paths in the installed package (iff absent; a present file with another
sha256 fails naming the path). Measured at LPC on real 2024 NanoAOD:
`probes/services-code/probe_hgg_original_lpc.txt`.
- `oracle_parts(uri, dataset, year, ranges, out)`: per range, the original's `process()` on
  `NanoEventsFactory.from_root({uri: "Events"}, entry_start=s, entry_stop=e, metadata={…})` with no `mode`, as its
  `__main__` calls it (coffea's `virtual`: equal to `mode="eager"` on the LPC chunk, 9× faster) → `{(s, e):
  (counters, pa.Table)}`.
- `compare_part(expected, actual) -> list[str]`: counters `==`; beyond values, the pyarrow schema (names, order,
  types, nullability); per column the validity bitmap and the valid values bit-for-bit (floats through their
  same-width unsigned view, so NaN positions count); KV metadata `==`. `[]` = identical.

Fixtures (`data/`): `make_hgg_fixture.py` (seed 20260925) → `nano_hgg_v15.root` (MC, from the fork's
`tests/samples/nano_tt_v15.root`: 200 events, two photons + the mainAnalysis triggers in events 0–59) and, with
`--data`, `nano_hgg_v15_data.root` (no `GenPart_*`/`GenVtx_*`/`LHE*`/`genWeight`, so the original takes its data
branch; run/lumi from the golden JSON: events 0–29 certified, 30–59 not).
| File | Property | Witness |
|---|---|---|
| `test_hgg_oracle_fixture.py` | the original's sha256; `infer_nano_version`'s file lies in the installed `higgs_dna`; placed files' sha256 equal `data/`'s; the oracle on the MC fixture (one chunk) returns `run_oracle.txt`'s counters and part shape; on the data fixture only events 0–29's diphotons survive (rows pinned at freeze); a rebuilt fixture is byte-identical | counts |
| `test_hgg_compare.py` | `compare_part` is `[]` for an oracle part against itself re-read from disk (control) and non-empty, naming the change, for: a one-ulp change in one float column (`np.nextafter`), a dropped row, two columns swapped, an int64 column narrowed to int32 with equal values, one value set null, one KV value changed, one counter off by one | each mutation caught |
| `test_hgg_conversion.py` | per fixture, `analysis.plan(fixture, ranges=[(0, 100), (100, 200)])` via `SequentialRunner` and `SubmitRunner(ThreadBackend)`: each part `compare_part`s `[]` against `oracle_parts` on the same ranges (the second is empty: a zero-row part with the oracle's schema); names end `_Events_<s>-<e>.parquet`; `totals(value)` = `accumulate` of the oracle's counters. NanoEvents: events are `coffea.nanoevents._graphed.GraphedNanoArray`, `events.Photon` has `metric_table`/`delta_r` (an absent name is `False`), `events.metadata["dataset"]` is the dataset; a search of `examples/hgg` for `import uproot`/`uproot.` finds nothing, the same search of `data/make_hgg_fixture.py` matches (control); the source node is `_GraphedTTreeSource` on both routes and a raw `uproot.graphed` array has no `Photon`, so these carry the claim (`probe_hgg_nanoevents_witness.txt`) | 1:1 parts; type; search |
| `test_hgg_lumimask_plugin.py` | the plugin on `(run, lumi)` pairs spanning certified and uncertified 2024 lumis equals coffea's `LumiMask` on the checked-in golden JSON; its descriptor carries the JSON's content hash | equality; descriptor |

Fails on: wrong-row-space counters, a float changed by an optimizer rewrite, a part named without its range,
whole-file metadata, a raise on the empty chunk, the wrong golden JSON, events outside NanoEvents.

**Real-data validation (evidence, not CI).** `examples/hgg/validate_real.py --parts 2` (imports `hgg_harness`)
takes the first file of `GluGluHto2G_M-125_amcatnlo_2024` and of `DataC_2024` (the `refs/hgg` manifests), prints
each file's `num_entries`, splits `[0, --entry-stop)` (default all) into `--parts` ranges, runs `oracle_parts` and
the graphed plan on them, prints each part's `compare_part` result and both counters. Run at the LPC login node by
`probes/services-code/hgg-original-lpc/run.sh`'s recipe plus graphed 0.0.6, the fork and uproot ca3a8a2; transcript
`probes/site-lpc/m69a-validate-real.txt`. A difference is a finding to root-cause, never a tolerance.

**CI, commits, docs.** `test-hgg` (ubuntu, py3.12): `.[dev]` + the fork (`env.COFFEA`) + `vector correctionlib` +
higgs_dna `--no-deps`; `GRAPHED_HGG_REQUIRED=1 pytest tests/frozen/m69a` (unset, files `importorskip`
coffea/higgs_dna); in `ci-required.needs`; no coverage. Freeze: A `test(hgg): fixtures, the original as oracle`
(builder, two ROOT files, original, golden JSON, jetid, path excludes; ~1.2k), B `test(hgg): frozen m69a` (harness,
conftest, four files; ~750). Implementer: 1. `feat(examples): H→γγ inclusive analysis on graphed` (`analysis.py`
~750, `run_local.py`, `validate_real.py` ~80, README); 2. `ci+docs(hgg)` (`test-hgg`, `docs/hgg.rst`: the 11
rewrites and how the translation is validated; changelog; ~250); the LPC transcript lands before the PR leaves
draft.

## 5. m69b — histserv-backed histograms (graphed-histogram PR) + diagnostics and site run (executors PR, stacked on m68a)

### 5.1 graphed-histogram PR (`boost.py` + `remote.py`)
| Mechanism | By hand | Rung |
|---|---|---|
| declare backing | a flag on the histogram | (6) `backing: str \| None` kwarg + `backed(h, name)` (the hist fork's `Hist.__init__` takes no extra kwarg); the name is a declared `ServiceSpec` |
| the recipe | a command line | (2) `histserv_spec(name)` builds graphed's `ServiceSpec` (argv `["{python}", "-m", "histserv", "--port", "{port}"]`, kind `"histserv"`, `check="tcp"`: histserv 0.2.1 serves no health service) — an example recipe, not a core name |
| partition into the reduce | — | (6) `_RemoteProcess(inner)` wrapper of the plan's `process`: `__call__(partition, resources)` binds the partition for the reduce; `bind_services` inits and delegates to `inner.bind_services` |
| ship a partition's fill | `remote.fill(x=…)` re-bins raw values | (4) `hist_pb2.FillRequest` from the boost partial's `view(flow=True)` (measured 832 B) |
| one server histogram per slot | `client.init` once | (6) at bind on the driver (ids are server-assigned) |
| idempotent retries | `unique_id` | (4) `unique_id=str(partition)`; `ALREADY_EXISTS` counted as done |
| nothing in the tree | a token | (6) `FillReceipt(slot, endpoint, hist_id, fills, snapshot=None)`; combine adds `fills` |
| the final object | `snapshot().to_hist()` | (4) memoized on the receipt by `_GroupReduce.resolve_services`, reached by graphed's `resolve_services(plan, value)` walk at run end (m68a's engine calls it), else at `unpack`; into `zero_of(spec)` |
| deletion | `delete()` | (2) `Endpoints.on_close` registered at bind |
| compose with other outputs | — | (2) split `plan()` into `pieces()` + `aggregate_plan(services=)` |

- `Histogram.__init__(*axes, storage=None, metadata=None, backing: str | None = None)`; `backed(h, backing)`. With
  a backing every axis needs a name (`hist` axis `.name`, else `metadata["name"]`) else `ValueError` naming
  histserv; only non-growing `Regular`/`Variable`/`Integer` axes, else refused naming the ceiling.
- `remote.py` (~210): `histserv_spec(name="hists", ports=(10000, 10100))`; `RemoteSlot(service, hist_id, template)`;
  `bind(endpoints)` → `Client(split_endpoint(e)[1]).init(hist.Hist(named axes from spec))` per backed slot (a
  `grpcs`/`https` endpoint refused naming it: `histserv.Client` dials `insecure_channel` only) and
  `endpoints.on_close(delete)`; `FillReceipt` with `__add__`; `ship(partial, slot, partition)`; `resolve(receipt)`
  snapshots once without delete, stores the `bh.Histogram` on the receipt, returns it; a `Client` per worker process
  cached by endpoint; `histserv` imported lazily.
- `_GroupReduce` ships per backed slot and returns a receipt; `_GroupZero` returns an empty receipt; `_add_groups`
  adds receipts; `_RemoteProcess` wraps the plan's process when any slot is backed and forwards `bind_services` and
  `resolve_services` to it; `_GroupReduce.resolve_services(value)` runs `resolve` on every receipt in the value and
  returns it, so the walk reaches it under `plan()`, `collate` and a composing `reduce` that forwards both hooks
  (`test_pieces_composition.py`'s `Composed` does). `unpack` reads a resolved receipt with zero connects, resolves an
  unresolved one, and is pure (a second `unpack` returns the memoized object). `Histogram.plan()` refuses a backed histogram with the
  group-plan message. `pieces(histograms) -> HistogramPieces(fill_nodes, reduce, combine, empty, externals,
  on_compiled, services)`; `plan()` = `aggregate_plan(*pieces…, services=pieces.services)` + the wrapper, so
  `Plan.services` carries the backing's spec (undeclared → the session's refusal naming the declared names).
  Unbound: the first backed reduce raises `UnboundService` naming `bind_services` and the executor's `services=`.
- Packaging: `histserv = ["histserv>=0.2.1", "hist>=2.12"]`. CI installs `.[dev,histserv]` on every leg but `3.14t`
  (grpcio publishes no `cp314t` wheel); the m69b frozen files `importorskip("histserv")` at module level so they
  collect everywhere, and `test_histserv_available.py` asserts the import succeeds wherever `sys._is_gil_enabled()`
  is True, so the skip fires only on the free-threaded leg. The histogram PR's CI installs graphed from the m68 PR
  ref through `env.GRAPHED`; the floor bumps at the release.

Frozen `tests/frozen/m69b/` (graphed-histogram; histserv from PyPI as a subprocess; harness `histserv_harness.py`):
| File | Property | Witness | Fixture |
|---|---|---|---|
| `test_backing_surface.py` (no server) | `backing` stored; `backed()` on the hist fork; unnamed / category / growth axes refused with the named reasons; IR bytes and `external_key`s identical to an unbacked twin; `Histogram.plan()` refuses; `plan()` of a backed histogram carries the declared spec in `Plan.services` and refuses an undeclared name; extra pins `histserv>=0.2.1`; `remote` not imported by `import graphed_histogram` | `sys.modules`; byte equality | — |
| `test_remote_fill_path.py` | `plan({"m": backed, "n": local})` + `bind_services(plan, Endpoints({"hists": "tcp://127.0.0.1:<port>"}))` (the same as `grpcs://` refused naming the plaintext client): server `stats` shows one entry; every backed partition result is a `FillReceipt` ≤ 256 B pickled, the local slot a `bh.Histogram`; `unpack` gives `bh.Histogram` for both, backed == local bit-for-bit (values, variances, flow) for Double, Weight and Int64; `unpack` twice returns equal objects and the server still has the entry; the `on_close` callback deletes it (0 entries); a value passed through `resolve_services(plan, value)` before that deletion unpacks after it to the same histograms with zero connects | pickled size; `stats` | `SequentialRunner` |
| `test_remote_fill_idempotent.py` | the reduce run twice for one partition → one fill on the server (`was_filled_with_unique_id(str(partition))`); another partition adds; a non-`ALREADY_EXISTS` RPC error propagates as itself | server answers | — |
| `test_pieces_composition.py` | `aggregate_plan(*p.fill_nodes, extra, reduce=Composed(p.reduce), …, services=p.services)` runs and its histograms equal `plan(hists)`; `plan()` equals the pieces path | equality | — |
| `test_unbound_backing.py` | running unbound raises `UnboundService` intact through `SequentialRunner`, before any RPC | no listener | — |
| `test_histserv_available.py` | `import histserv` succeeds when the GIL is enabled | — | — |

Fails on: a histogram riding the tree, a snapshot per partition, uuid unique ids, a mismatched final type, a
deleting `unpack`, the backing leaking into params/descriptor. Commits: 1. `feat(histogram): backing surface,
pieces(), refusals` (~250); 2. `feat(histogram): histserv remote fill path, receipts, unpack` (~370); 3.
`docs(histogram): remote backing` (~120).

### 5.2 executors m69b PR (stacked on m68a): diagnostics, LPC run
Adds to `examples/hgg/`: six histserv-backed diagnostic histograms over the selected diphotons, Weight storage,
weight = `weight`: `m_gg` Regular(80, 100, 180), `pt_gg` Regular(50, 0, 250), `lead_pt`/`sublead_pt` Regular(50, 0,
200), `lead_eta`/`sublead_eta` Regular(50, −2.5, 2.5), `n_jets` Regular(8, −0.5, 7.5) (a Regular: category axes are
chunk keys); owner may re-cut. One pass: `aggregate_plan(*pieces.fill_nodes, *counters, record,
reduce=HggReduce(pieces.reduce, …), combine=…, empty=…, externals=pieces.externals, on_compiled=pieces.on_compiled,
services=pieces.services)` wrapped by `HggProcess`; the session declares `histserv_spec("hists")`. `run_lpc.py`:
the manifests → `PartitionedSource`s per dataset (bounded `--files N`), `htcondor_runner(site="lpc",
user_modules=[examples/hgg])` (leg 3 driver-hosted at the login node; `--hists <endpoint>` passes leg 1), parquet
to `root://cmseos.fnal.gov//store/user/<user>/hgg/` (awkward through fsspec-xrootd; the job has the proxy, P2),
histograms `unpack`ed and saved as UHI JSON. Evidence `probes/site-lpc/m69-hgg.txt`; the driverless variant (in-job
histserv on the fat slot) is the second transcript. Frozen `tests/frozen/m69b/` (executors;
`importorskip("histserv")` as above):
| File | Property | Witness | Fixture |
|---|---|---|---|
| `test_histserv_managed.py` (all OS) | `SubmitRunner(ThreadBackend)` over a backed plan declaring `histserv_spec("hists")`: the server is alive during the run (status `leg="managed", host="driver"`) and gone when `run` returns (port free); `unpack` equals the local twin; the same plan with `services={"hists": <a running server>}` starts none (`leg="user"`); driverless (`python -m …driver`, `pilots="local"`, in-job histserv): `result.pkl` loaded after the job's server is gone unpacks equal to the local twin with zero connects | pid/port; statuses; connect count | histserv from PyPI |
| `test_hgg_diagnostics.py` (`test-hgg` job) | the six histograms from the converted analysis on the fixture equal a direct `bh` fill from the oracle part's columns bit-for-bit, backed (managed histserv) and unbacked alike, and the m69a products are unchanged | view equality | m69a `data/` |
| `test_hgg_live_pool.py` (minicondor) | the converted analysis over 2 local pilots with the declared histserv on the driver → histograms equal the sequential run's; the run's end leaves no server | equality; port | the pool |
Commits: 1. `feat(examples): H→γγ diagnostics as histserv-backed fills` (~250); 2. `feat(examples): LPC runner +
histserv recipe docs` (`run_lpc.py`, `docs/htcondor.rst` "histserv-backed histograms" + "An H→γγ run", changelog)
(~250).

## 6. CI
- **executors `test-htcondor`** (ubuntu, py3.12): + `docker run -p 8001:8001 … tritonserver:25.11-pyt-python-py3`
  running `recipes.triton`'s argv at port 8001 on `tests/frozen/m68a/data/triton_models/`, whose `graphed_identity` is
  a python-backend identity with P9's name and I/O (the backend graphed CI's `scorer` runs on this image; graphed's
  disk-free step included), waited on by `check_ready`, + `pip install "tritonclient[grpc]" histserv
  grpcio-health-checking` (`histserv` from the m69b PR on: no m68a file imports it), from the m68b PR on adds
  `probes/m68b/sim_gpu.config`'s two lines to the runner's pool config (one simulated GPU) before the pool starts,
  or follows them with `condor_restart -daemon startd` (`probe_sim_gpu.py`), runs `tests/frozen/m66 m67 m68a m68b m69b tests/extra/m6*` (each PR the dirs it has);
  `.coveragerc-htcondor` sources add `graphed_executors.submit.services`; diff-cover include adds
  `src/graphed_executors/submit/services.py`. The all-OS `test` job installs `histserv grpcio-health-checking` (not on
  3.14t: no `cp314t` grpcio, P-d) and runs the no-bindings files of m67/m68a/m68b/m69b (m68b: `test_announce_route`,
  `test_cluster_service_job`, `test_driverless_dag`) (the histserv subprocess and
  the in-process gRPC servers on every OS; a Windows bind failure is a finding, not a skip). **`test-dask`** adds
  `tests/frozen/m68a/test_scope_dask_memory.py` to its explicit file list; it and **`test-parsl`** (existing legs) add `tests/frozen/m70` and their backend's `_service.py`/`transport_peer.py` deltas
  to their coverage sources.
- **graphed**: the main matrix runs `tests/frozen/preserve/m68` on the fake transports; the `triton` job (already `-p
  8001`, `GRAPHED_TRITON_GRPC`) adds the live service-ref test on both wires.
- **Site runs are evidence transcripts only:** LPC and lxplus driverless (m67), LPC EAF Triton by leg 2 (m68a), lxplus
  GPU/Triton attached and driverless DAG (m68b's two site checks, owner-run), LPC H→γγ with login-node / in-job
  histserv (m69b).

## 7. PR / commit partition
Executors: m69a on `main` (~1.1k examples, ~2k fixture/test lines, two fixture binaries), and stacked PRs on
`main` (`lane/htcondor` #34 merged as `eefc0f3`, m67 as `b966a28`): m68a (~1.2k src+ci+docs, ~1.3k tests) → m68b
(~1.5k src+ci+docs, ~1.3k tests) → m70 (~500 src, ~800 tests); m69b (~500 examples, ~600 tests) stacks on m68a, independent of m68b and m70.
graphed: the m68 PR (~360 src, ~850 tests, docs) and the resolve walk (§3.2, ~150). graphed-histogram: one PR (m69b, ~660 src, ~1k tests). At m66's
measured estimate-to-shipped ratio (journal) every commit above stays under 2k. Order: m69a and m67 start now; graphed
m68 PR and the resolve walk before executors m68a (installed by ref, floored at the release that holds both); m68b after m68a, m70 after m68b; histogram m69b
PR before executors m69b, which branches after m69a is merged into `main` and `main` into the m68a stack (it extends
`examples/hgg`, m69a's `data/` and `test-hgg`; its runs use driver-hosted, in-job and user-leg histserv, all m68a).

## 8. Docs
Each milestone's docs commit names its pages (§2, §3.1–§3.4, §5); beyond those: `htcondor.rst` "Services" (surface,
legs, wires and checks, site table, placement, probe, "unreachable"); `design.rst` "Cluster hosting" (m70); README
rows, `api.rst` (m68b: `SiteProfile.job_root`). graphed `architecture.rst` "Service surface" and the preserve page's "services in a bundle";
graphed-histogram `design.rst` "Remote (histserv) backing".

## 9. Risks (premise → evidence) and owner items
- Self-submitted pilots from an lxplus driver job *inside the coffea image*: bindings submit from a job works (P5,
  no image line in its `.sub`); whether the inner jobs start, and whether the Kerberos cache is usable inside the
  container for that submit, are unmeasured → measured by one spooled one-liner submitted from an image job with
  `SendCredential` (`NumJobStarts == 1` on the inner job) before the m67 lxplus site check.
- `$_CONDOR_MACHINE_AD` inside the container: present at LPC (P2) and in lxplus's coffea image
  (`probes/site-lxplus/m67-driverless.txt`); inside the lxplus Triton image unmeasured: absent, `announce.py`
  announces the container's `getfqdn()`, which the self-check must resolve, and the probe still passes on answers
  from pilots on other nodes; m68b's site check (1) records which form was announced.
- The EAF Triton at LPC is reachable from a batch worker (P8) and serves `graphed_identity` (P9) → the lpc row.
  Readiness stays the server's (`ServerIsReady`, P-e): the served set changes under users (P8: `resnet50` `NOT_FOUND`
  minutes after READY), so a check-time model probe proves nothing at infer time and would put Triton's model RPC in
  the core; a missing model fails the first infer with Triton's `NOT_FOUND` inside the `StageError`. EAF's inference
  access policy is unmeasured; TLS uses default roots (P8).
- `python3` ≥ 3.9 in the Triton image (`announce.py`): nvcr 24.11-py3 ships it (python backend; the version is
  site check (1)'s); absent, `service.sh` exits 3 naming it.
- dask GPU placement: worker `resources` selection is unmeasured on a real GPU cluster; the m70 frozen test
  measures it on a `LocalCluster(resources=…)`, the site run is Phase 2.
- parsl hosted actors on a multi-node HTEX share the peers' single-machine `HOST` ceiling; not in m70.
  Driver-hosted services on any real cluster need workers to dial `advertise_host` (dask: the client's fqdn); the
  probe fails closed when they cannot, and dask cluster hosting carries no such premise (D10).
- Parquet writes to EOS over xrootd from a job: unmeasured → `run_lpc.py` falls back to a local dir +
  `output_destination`.
- `pull_files.py` places the 2024 golden and jet-ID JSONs at LPC (`probe_hgg_original_lpc.txt`); gitlab.cern.ch
  from GitHub runners (`test-hgg`'s higgs_dna install) is unmeasured → freeze commit A's first CI run measures it.
- histserv Double/Int64 dense dtypes: only Weight measured; the m69b frozen test discriminates. histserv under many
  pilots and the Windows start-up: unmeasured.
- A DAG dir on AFS holds `graphed-secret` (an announce secret, which signs no pickle) and, with `pilots="condor"`,
  m67's `pilots/graphed-secret` (the pilots' secret, as in m67), both 0600; on AFS the directory's ACL, not the file
  mode, is what guards them; m68b's site check
  (2) records `fs listacl`. The `from_dag` description (with `UseDagDir`/`AddToEnv`) passes `getenv` including `CONDOR_CONFIG`
  (`probe_dag_service.txt`); at lxplus it is accepted or not by site check (2), and a refusal there is a finding.
- HTCondor configuration m68b cannot read from the submit side (execute-point scratch layout and mounts,
  Apptainer, DAGMan strictness and update interval, periodic-expression interval, vacate time, a credd, per-job
  network namespaces) is met per job or per DAG, never assumed: §3.3 "HTCondor behaviour relied on",
  `probes/m68b/condor_surface/RESULTS.md`; per-job network namespaces (N-02) remain a premise the site checks measure.
- **Owner:** lxplus submissions (m67 site check, m68b's site checks (1)–(3)); re-cut of the six diagnostic histograms if wanted.
  A service that fails mid-run surfaces in plan code (a task, a bind hook, `resolve_services`) and exits 3 (D6):
  retrying it would need task errors to carry their cause, a decision not taken here.
