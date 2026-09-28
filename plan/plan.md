# Plan — direct HTCondor backend (graphed-executors, milestone m66)

Assumptions: the milestone id is **m66** (the next free id; `grep -r m66` over the lane artifacts is empty).
The issuer decisions bind, and this plan designs within them. Evidence lives in `probes/` and
`journal.md`; this file states decisions. The implementer also inherits the exit-round constraint
block in `reviews/plan-r1.md`.
- **D1:** the backend gets its own frozen conformance file. It copies the m42 `submit_backends.py`
  helpers into its harness, as `m46/parsl_harness.py` did, with no cross-directory import.
- **D2:** every task-server request carries a per-run secret (stdlib `hmac`), and unauthenticated
  requests are refused before any unpickle.
- **D3:** `htcondor2` is imported lazily. The binding tests are Linux-only, and a personal HTCondor
  runs on the ubuntu CI job.
- **D4:** a non-editable venv is shipped inside the site image, user modules travel through
  `transfer_input_files`, and a `__main__` or lambda `process`/`combine` is refused at submit.
- **D5:** a lost pilot's lease is re-queued once to another pilot, then surfaces as a `WorkerLost`
  the engine attributes.
- **D6:** lxplus uses `transfer_output_files=""` with `output_destination` optional. The lxplus job
  waits on the owner's permission.
- **D7:** on LPC the driver runs inside the apptainer image with the LPC condor config bound.

## 1. Shape and seam

graphed-executors is one plan engine over a small backend protocol. `submit/engine.py:SubmitRunner`
owns *what* runs: the `plan_tree` future graph, the adaptive `running_fold`, task keys, broadcast
tokens, monitor draining, and the translation of worker death into a `StageError` through the
backend's optional `describe_failure`. `submit/protocol.py:SubmitBackend` + `SubmitCapabilities` is
the boundary. A backend owns *where and how* a task runs: workers, dispatch, resolving future
arguments before `fn` runs, `broadcast`, the event tap, `cancel` and `close`. `common/` holds the
backend-agnostic exchange engines. The parsl and dask packages are adapters. This statement lives
in `docs/design.rst` ("One engine, many clusters") and the module docstrings of `submit/engine.py`,
`submit/protocol.py` and `parsl_backend/backend.py`. It was confirmed by the two traces in
`codebase-analysis.md`.

The HTCondor backend is a third adapter at the **all-False floor**, and it supplies the worker pool
itself. It launches N pilot jobs through `htcondor2`. Each pilot pulls pickled tasks from a
driver-side HTTP task server and posts results back. The engine is unchanged.

## 2. Package `src/graphed_executors/htcondor_backend/`

The package name mirrors `parsl_backend/` and `dask_backend/`. Six files, about 780 LOC.

### Ladders (task · by hand · rung)
| Mechanism | Task | By hand | Rung |
|---|---|---|---|
| launcher | start N pilot jobs and remove them later | `condor_submit` + `condor_rm` | (3) the platform's bindings `htcondor2` (brief: bindings only); the rungs above fail because there is no launcher in the repo and parsl's `launch.py` is HTEX-only |
| site profiles | per-site submit keys | the probe's `PROFILES` dict | (6) a frozen dataclass of data; lpcjobqueue's `schedd.py` choice rewritten over `htcondor2` |
| task server | pilots pull tasks and return results | none by hand; HTEX/dask do it | (6) a `ThreadingHTTPServer` subclass with a path switch: the `http_plane._DualRouteServer` skeleton (rung 2 pattern); its routes do not fit (analysis §2) |
| event/envelope | worker env + events ride back with the result | — | (2) import `parsl_backend._shim._parsl_task_shim`, `dispatch_events` and `_ParslFuture` verbatim; they are parsl-free |
| auth (D2) | refuse forged requests before unpickling | compare a MAC | (3) stdlib `hmac.new(secret, body, sha256)` + `hmac.compare_digest` |
| lease (D5) | re-run a dead pilot's task once | watch the heartbeat | (6) a reaper thread over `last_beat` timestamps |
| env ship (D4) | the pilot runs the driver's venv inside the image | lpcjobqueue `ship_env` | (3) stdlib `tarfile` (one file; condor cannot transfer symlinked dirs, which is why lpcjobqueue unlinks `lib64`) |
| user code (D4) | pilots import `plan.process` by name | `transfer_input_files` | (1)+(3) transfer the files; `python -m` already puts the cwd on `sys.path` (Python docs, `-m`), so no code is needed |
| refusal (D4) | fail at submit, not on a pilot | unpickle in a fresh interpreter (measured failure, `probes/probe_pickle_scope.txt`) | (3) `pickle.Unpickler.find_class` override (stdlib "Restricting Globals") |

### Files and public symbols
**`sites.py`** (~90, no bindings import)
- `SiteProfile(name: str, submit: Mapping[str, str], spool: bool, ship_env: bool, sandbox_root: str | None, schedd_query: tuple[str, str] | None)`
  is a frozen dataclass.
  - `submit` values are templates over `{image}`, `{uid}`, `{user}` and `{home}`.
  - `schedd_query` is `(param naming the collectors, constraint)`; `None` means `htcondor2.Schedd()`,
    the user's `SCHEDD_HOST`.
- `SITES: Mapping[str, SiteProfile]`:
  - `lpc`:
    - submit keys: `use_x509userproxy=true`; `x509userproxy={home}/x509up_u{uid}` (the measured
      "unable to read proxy" trap); `+DesiredOS="EL9"`; `MY.SingularityImage="{image}"`.
    - `spool=True`, `ship_env=True`, `sandbox_root=/uscmst1b_scratch/lpc1/3DayLifetime/{user}`.
    - `schedd_query=("FERMIHTC_REMOTE_POOL", 'FERMIHTC_DRAIN_LPCSCHEDD=?=FALSE && FERMIHTC_SCHEDD_TYPE=?="CMSLPC" && MaxJobsRunning!=0')`.
  - `lxplus`:
    - submit keys: `MY.SingularityImage="{image}"`, `MY.SendCredential=True`, `+JobFlavour="longlunch"`.
      Assumption: a 2 h pilot; override it through `extra_submit`.
    - `spool=True`, `ship_env=True`, `sandbox_root=None`, `schedd_query=None`.
  - `generic`: `{}`, `spool=False`, `ship_env=False`, `sandbox_root=None`, `schedd_query=None`.
- `schedd_weight(ad) -> float` is the wrapper formula `0.7·RecentDaemonCoreDutyCycle·100 + 0.2·ShadowsRunning/MaxJobsRunning·100 + 0.1·TotalIdleJobs`.
  `choose_schedd(ads) -> str` returns the lowest weight.
- `counts_as_alive(ad) -> bool` is True for JobStatus 1 or 2, and for JobStatus 5 with
  HoldReasonCode 16 (the measured transient spooling hold).

**`launch.py`** (~230)
- `_htcondor()` is the lazy accessor (the parsl `_lazy.py` idiom, inlined). Its `ImportError`
  names the `[htcondor]` extra.
- `PilotLauncher` is a Protocol: `start(url: str, secret: bytes, n: int) -> None`, `alive() -> int`, `stop() -> None`.
- `CondorPilots(site: str | SiteProfile = "generic", *, image: str | None = None, request_cpus: int = 1, request_memory_mb: int = 2048, log_dir: str | Path | None = None, user_modules: Sequence[str | Path] = (), env: str | Path | None = None, extra_submit: Mapping[str, str] | None = None)`
  - `submit_description(url: str, n: int) -> dict[str, str]` is pure, with no bindings, so it can
    be tested on data. The base keys are:
    - `universe=vanilla`, `executable=pilot.sh`, `arguments="<url> graphed-secret"`, `initialdir=<log_dir>`
    - `output/error=pilot.$(ProcId).{out,err}`, `log=pilots.log`
    - `should_transfer_files=YES`, `when_to_transfer_output=ON_EXIT_OR_EVICT`
    - `transfer_input_files=graphed-secret[,env.tgz][,user_modules…]`
    - `transfer_output_files=""` (D6; lpcjobqueue and dask-lxplus both set it, and it stops the
      unpacked venv coming back)
    - `request_cpus`, `request_memory`, `JobBatchName="graphed-pilots-<nonce>"`
    - then the profile's keys, then `extra_submit`.
  - `start`:
    1. Refuse with a `ValueError` when `image is None` and a template needs `{image}`, or when
       `log_dir` lies outside `sandbox_root` (the LPC schedd can only touch 3DayLifetime:
       `FS_REMOTE_DIR`, journal §LPC).
    2. Write `graphed-secret` with mode 0600. The secret goes in a file, never in `arguments` or
       `environment`, because both are readable by anyone who can query the job ad.
    3. Write `pilot.sh`: `[ -f env.tgz ] && tar xzf env.tgz; exec <python> -m graphed_executors.htcondor_backend.pilot "$@"`. `<python>` is `./env/bin/python`
       under `ship_env`, and otherwise the driver's `sys.executable`.
    4. When `ship_env`, tar `env` (default `sys.prefix`). Refuse if it is not a venv (no
       `pyvenv.cfg`), or if any `*.dist-info/direct_url.json` in its own site-packages says
       `"editable": true`. The error names the dists and the D4 recipe.
    5. Choose the schedd: `Collector(node).query(AdType.Schedd, constraint, projection)`, trying
       each node in the param's list in turn and failing over on error (as lpcjobqueue's
       `acquire_schedd` does) → `choose_schedd` → `Schedd(Collector.locate(DaemonType.Schedd, name))`.
       Do not use `Schedd(ad)`, which fails with a `KeyError` on `CondorVersion` (measured).
    6. `schedd.submit(Submit(desc), count=n, spool=profile.spool)`, plus `schedd.spool(result)`
       when spooling.
    7. Keep `self.cluster: tuple[str, int]` (schedd name, ClusterId) and the `Schedd` object,
       because the choice flips between runs (measured).
  - `alive()` counts the cluster's ads that satisfy `counts_as_alive`.
  - `stop()` waits up to `CLOSE_WAIT_S` for `alive()==0`, then `retrieve(f"ClusterId=={cid}")` (the
    spooled logs land in `log_dir`), then `act(JobAction.Remove, …)`. A spooled job lingers until it
    is removed (measured).
- `LocalPilots(*, python: str = sys.executable, pythonpath: Sequence[str | Path] = ())` runs
  pilots as local subprocesses. It is the no-batch-system launcher: a laptop dry run of the exact
  wire path, and the frozen suite's real pilots. `alive()` counts the `Popen` objects whose
  `poll()` is None.

**`server.py`** (~200)
- Constants, each with its reason in one line:
  - `LEASE_S = 30.0`: a pilot beats every `LEASE_S / 6` (5 s), so it counts as lost after six
    missed beats. This tolerates a GIL-bound task stalling the beat thread and a transient network
    drop. At the measured 8.6 ms RTT the beat load is negligible. The server and the reaper read
    `server.LEASE_S` at call time; it is never copied at construction or bound as a default.
  - `POLL_S = 10.0`: the `/next` long-poll bound.
  - `CLOSE_WAIT_S = 2 * POLL_S`: pilots see the 410 on their next poll.
- `WorkerLost(Exception)` has `.key: str` and `.pilot: str`. It is raised on the driver only.
- `TaskServer(host: str, port_range: tuple[int, int])` binds the first free port in the range on
  `""` and advertises `http://{host}:{port}`. It generates the secret with `secrets.token_bytes(32)`.
- Every request is a POST whose body is a pickle, with the header
  `X-Graphed-Sig: hmac-sha256(secret, body)`. A missing or wrong signature gets **403 before
  `pickle.loads`**. Responses are pickles too.
- Each task record holds a raw `concurrent.futures.Future`, the task `key`, the `deps` (the
  `_ParslFuture` args), the payload, `leased_to` and `requeued`. The future's state machine:
  - PENDING while it waits on its deps or sits in the queue.
  - When the last dep finishes (an `add_done_callback` on each dep), there are two cases:
    - a dep failed or was cancelled: `set_exception(<that dep's exception, or CancelledError>)` on this task, so `WorkerLost` and
      every other worker error reach the dependent of any arity unchanged;
    - otherwise the args are resolved with `.result()` (they are done, so this does not block),
      the payload is pickled, and the task is queued.
  - At the first lease only, `set_running_or_notify_cancel()`. False means cancelled, so the task
    is dropped.
  - A requeue changes only the lease record (`leased_to`, `requeued`). The future stays RUNNING.
  - Every `set_result`/`set_exception` is guarded by `if not fut.done()`, so the first result wins.
    Each call is made after the queue `Condition`'s lock is released, because a dep's done-callback
    runs inside it and takes that lock to queue the dependent.
- Routes:
  - `/hello` registers a pilot id (`hostname:pid`) and returns `{"beat_s": LEASE_S / 6, "lease_s": LEASE_S}`.
  - `/next` leases the next task. It returns 200 with the pickled `(task_id, shim, fn, args)`, 204
    after `POLL_S`, or 410 when the server is closed or the pilot was declared lost. `close()`
    calls `notify_all` on the queue's `Condition`, so a waiting `/next` answers 410 at once.
  - `/beat` returns 200 or 410.
  - `/result` receives `(pilot, task_id, ok, value)` and sets the future. The first result wins,
    and a late result from a lost pilot is ignored.
- The reaper runs every `beat_s`. A pilot whose last beat is older than `LEASE_S` is lost, and each
  task it leased is handled as follows:
  - never requeued: requeue it at the head of the queue (another pilot takes it, because the lost
    id now gets 410);
  - already requeued: `set_exception(WorkerLost(key, pilot))`. Its dependents fail with the same
    exception through the dep rule above.
- When no pilot is live, tasks are queued, and `launcher.alive()==0`, every queued task fails with
  `WorkerLost(key, "no pilots left; see <log_dir>")`. This is the no-silent-hang rule. The reaper
  calls `alive()` only in that state, which keeps the schedd load bounded.

**`pilot.py`** (~80): `python -m graphed_executors.htcondor_backend.pilot <url> <secret_path>`.
- Startup: `/hello`, then a daemon beat thread.
- Loop: `/next`; 204 continues; 410 exits 0; 200 runs `shim(fn, *args)` and posts `/result`. A
  403 exits 2, printing "driver refused the pilot's signature: wrong secret file".
- Errors: a raising `fn` posts `ok=False` with the exception pickled. If that pickling fails, it
  posts `RuntimeError(f"{type}: {msg}\n{traceback}")` instead, so the future is never left hanging.
- Lost driver: if the driver has been unreachable for longer than `LEASE_S`, the pilot exits 1.
  This keeps orphans from holding batch slots after a driver crash.

**`backend.py`** (~150)
- `HTCondorBackend(launcher: PilotLauncher, n_pilots: int, *, host: str | None = None, port_range: tuple[int, int] = (10000, 10100))`
  starts a `TaskServer` and calls `launcher.start(url, secret, n_pilots)`.
  - `host` defaults to `socket.getfqdn()`: LPC workers reached `cmslpc305.fnal.gov:10000`
    (measured). The port range is lpcjobqueue's and dask-lxplus's.
  - `capabilities` is the all-False `SubmitCapabilities`.
  - `submit` never blocks and never raises on a dependency. It hands `(fn, args)` to the server's
    task record (the dep state machine above), which later pickles `(shim, fn, resolved)` with
    stdlib `pickle` (the engine's own codec, from `engine._fingerprint`). It returns
    `_ParslFuture(raw, handlers)`. The hints are ignored.
  - `broadcast` returns the payload unchanged.
  - `subscribe_events` and `cancel` behave as in parsl.
  - `n_workers()` and `task_slots()` return the pilots registered and live right now. That is a
    measurement, never a wait.
  - `wait_for_pilots(n: int, timeout: float = N_WORKERS_WAIT_S) -> int` blocks until `n` pilots
    are live and returns the count. On timeout it raises `RuntimeError` naming `log_dir`.
    `N_WORKERS_WAIT_S = 600`: LPC measured 45 s from submit to finish on an idle pool, and a busy
    pool queues for minutes.
  - `describe_failure(exc)` returns `(exc.key, exc.pilot)` when `exc` is a `WorkerLost`, otherwise
    None. The engine maps the key back to the partition.
  - `close()`: the server answers 410, then `launcher.stop()`, then the server shuts down and the
    secret file is unlinked. The backend owns its pilots because it launched them.
- `HTCondorRunner(SubmitRunner)` takes `(backend, *, min_pilots: int = 1, monitor=None, retries=3, max_in_flight=2)`.
  `run(plan)`:
  1. calls `_require_importable(plan.process, "process")` and `_require_importable(plan.combine, "combine")`;
  2. before the first run only, calls `backend.wait_for_pilots(min_pilots)`. The wait turns
     pilots that never start into a loud error, where there would otherwise be a queue that never
     drains;
  3. then `super().run(plan)`.
  - A `PicklingError`, `AttributeError` or `TypeError` from `pickle.dumps` (a lambda or a local
    function) becomes a `ValueError`.
  - So does a `__main__` global found by the `find_class` probe.
  - The message: "pilots import plan.<role> by name; move <obj> into a module and pass it in
    `user_modules=[...]`".
- `htcondor_runner(*, n_pilots: int, site: str | SiteProfile = "generic", image: str | None = None, request_cpus: int = 1, request_memory_mb: int = 2048, log_dir: str | Path | None = None, user_modules: Sequence[str | Path] = (), env: str | Path | None = None, extra_submit: Mapping[str, str] | None = None, host: str | None = None, min_pilots: int = 1, monitor: Any = None, retries: int = 3, max_in_flight: int = 2) -> HTCondorRunner`
  is the `parsl_runner`-style facade. `runner.close()` removes the pilots.

**`__init__.py`** exports `HTCondorBackend`, `HTCondorRunner`, `htcondor_runner`, `CondorPilots`,
`LocalPilots`, `PilotLauncher`, `SiteProfile`, `SITES` and `WorkerLost`. It imports no `htcondor2`,
`htcondor` or `classad2`.

**Packaging.**
- The extra is `htcondor = ["htcondor>=25.13"]`. That floor is the version resolved and measured
  in the LPC image (`probes/site-lpc/venv-recipe.txt`, D7). There is no marker: wheels exist for
  Linux cp38–cp314 only, so a macOS install fails loudly.
- Main `[tool.coverage.run] omit` gains `*/htcondor_backend/*`. The frozen parsl pin checks
  membership, not equality.

## 3. Frozen test plan (`tests/frozen/m66/`, isolated test author)

**Harness and config.**
- D1: `htcondor_harness.py` **copies** the m42 `submit_backends.py` helpers the suite uses, as
  `m46/parsl_harness.py` did. There is no cross-directory import, no m42 `pythonpath` entry, and no
  second file with the `submit_backends` basename. The harness copies **every** helper that the
  copied m42 bodies use. It also adds `PoisonUriProcess(uri)`, which runs `exit_process` for that
  one uri and concatenates otherwise (for test 4).
- The harness also provides:
  - deferred `htcondor_api()`;
  - `local_backend(n)`, which builds `HTCondorBackend(LocalPilots(pythonpath=[m66 dir]), n, host="127.0.0.1")`
    and then calls `wait_for_pilots(n)`, so the frozen `n_workers() == n` assertions cannot race;
  - the module-level task fn `pilot_prefix()`, returning `(sys.prefix, $_CONDOR_SCRATCH_DIR)`;
  - `run_bounded`.
- Every local-pilot test is bounded, so a hang fails instead of wedging CI.

Each file below lists the property, then the stub it discriminates.

1. **`test_htcondor_submit_conformance.py`** (D1). The m42 conformance bodies over `local_backend(2)`:
   - `fixed_plan_matches_sequential_bit_for_bit[n∈0,1,2,5,16]`, key-order reduction, adaptive
     exhaustion, `StageError` intact, the direct seam, and the monitor's exact
     SUBMITTED<STARTED<FINISHED per leaf;
   - `isinstance` against both protocols, and `capabilities == SubmitCapabilities(*7×False)`;
   - the composed task's `where()` pid is not the driver pid and its worker is not in
     `("", "driver", "local")`.

   Fails on: a driver-side compute stub (the pid witness), unresolved future args (the fn crashes),
   a non-bytes broadcast, a stringified `StageError`, and lost events.
2. **`test_htcondor_sites.py`** runs on every OS with no bindings. It uses the recorded ads
   (`probes/recorded-ads/lpc-schedd-ads.json` minus `MyAddress`, frozen as `data/`):
   - `choose_schedd` returns `lpcschedd4.fnal.gov`;
   - for each weighting term (`RecentDaemonCoreDutyCycle`, `ShadowsRunning/MaxJobsRunning`,
     `TotalIdleJobs`), the test author derives from the recorded ads an ad set, data derived from
     data. In it:
     - the deciding term picks the full-formula winner;
     - the other two terms together rank the ads in the opposite order, so removing the deciding
       term flips the winner.

     Every set runs with its ads in stored order and reversed, and asserts the same winner both
     ways. A `schedd_weight` with any one term removed fails at least one ordering;
   - `SITES["lpc"].schedd_query` equals the wrapper's constraint text;
   - `counts_as_alive` is True for `{JobStatus:5, HoldReasonCode:16}`, False for a code-13 hold,
     and True for 1 and 2.

   Profile descriptions from `submit_description`:
   - lpc: `x509userproxy` is the absolute `~/x509up_u<uid>` path, the image is quoted, and
     `+DesiredOS` is set;
   - lxplus: `transfer_output_files == '""'` and `MY.SendCredential`;
   - generic: none of the site keys, and `spool` is False;
   - `graphed-secret` is in `transfer_input_files`.

   Refusals: lpc or lxplus without an image, an lpc `log_dir` outside the sandbox root, and a
   shipped venv with an editable `direct_url.json`. Each raises a `ValueError` naming the fix. The
   control, a non-editable venv, yields an `env.tgz` containing `pyvenv.cfg`.

   Fails on: a formula missing any term, and the proxy-default trap.
3. **`test_htcondor_auth.py`** (D2):
   - an unsigned or wrong-signature POST to each of the four routes gets 403, and a body whose
     unpickle would touch a marker file leaves the marker absent;
   - control: the same body correctly signed makes the marker appear, which shows the instrument
     is live;
   - a pilot started with the wrong secret gets no task, and the run completes on the correct pilot.

   Fails on: unpickling before the check, and a check that is skipped on one route.
4. **`test_htcondor_lost_pilot.py`** (D5; `monkeypatch LEASE_S=2.0`, 3 local pilots):
   - `DieOnceProcess` (copied): the run is bit-for-bit, the marker exists, and the successful pid
     differs from the dead pid. This exercises the requeue of a RUNNING future;
   - on a 4-leaf plan through the fixed, non-windowed path, whose `process` runs `exit_process` for
     one leaf's uri only: `type(err) is StageError`, the poisoned leaf's uri is in `err.partition`,
     `cause_type == "KilledWorker"`, and a pilot id is in the message. The failure crosses a combine
     dependency before it reaches the root;
   - with one pilot, `exit_process` surfaces as a `StageError`, not a hang (the no-pilots-left rule);
   - `describe_failure` maps a `WorkerLost` to `(key, pilot)` and anything else to None.

   Fails on: requeue-forever (a bounded hang), fail-on-first-loss (the `DieOnce` run errors), a
   second `set_running_or_notify_cancel` on requeue (`RuntimeError`), a raw `WorkerLost` escaping
   through a blocking dependency resolution in `submit`, and attribution to the task key instead of
   the partition.
5. **`test_htcondor_refusals.py`** (D4). `HTCondorRunner(local_backend(1)).run(plan)` raises a
   `ValueError` mentioning `user_modules`, with zero `backend.submit` calls (a spy), for:
   - a lambda `process`;
   - a function with `__module__="__main__"` registered on `sys.modules["__main__"]` via
     monkeypatch (it pickles to about 35 B, as measured);
   - a `__main__` class instance used as `combine`.

   The control, the same fn from the harness, runs. Fails on: letting the engine's `PicklingError`
   through, and a refusal that only catches lambdas.
6. **`test_htcondor_no_import.py`** (main matrix, all OS): a subprocess imports the package and
   finds `htcondor2`, `htcondor` and `classad2` absent from `sys.modules`. Fails on an eager import.
7. **`test_htcondor_packaging_pins.py`** (main matrix):
   - the extra is exactly `["htcondor>=25.13"]`;
   - main omit ∋ `*/htcondor_backend/*`;
   - `.coveragerc-htcondor` sources are `{graphed_executors.htcondor_backend}`, with `fail_under 90`
     and branch coverage;
   - the ci.yml `test-htcondor` job runs `get.htcondor.org` and pytest over `tests/frozen/m66` with
     `--cov-config=.coveragerc-htcondor` and no path-valued `--cov=`.
8. **`test_htcondor_live_pool.py`** (D3; `importorskip("htcondor2")`, Linux job). It runs against
   the personal pool:
   - (a) `htcondor_runner(site="generic", n_pilots=2, user_modules=[htcondor_harness.py])`:
     - `concat_plan(8)` is bit-for-bit, and the leaves ran on at least 2 pids that are not the
       driver pid;
     - imports succeeded with no PYTHONPATH in the job env, which proves the transfer;
     - while the pilots run, the full job ads (`schedd.query(ClusterId)` with no projection)
       contain neither the secret bytes nor their hex anywhere;
     - after `close()`, `schedd.query(ClusterId)` is empty, `schedd.history` reaches 2 rows within
       a bounded poll, and `pilot.0.out` is in `log_dir`.
   - (b) a custom `SiteProfile(name="ci-spool", spool=True, ship_env=True, sandbox_root=None, submit={}, schedd_query=("COLLECTOR_HOST", "true"))`
     with `env=` a venv the test builds (`venv --system-site-packages` + `pip install --no-deps <repo>`):
     the run completes, and `pilot_prefix()` (which returns `sys.prefix` and
     `$_CONDOR_SCRATCH_DIR`) shows the prefix under the scratch dir, not the driver's prefix. After `close()`, `pilot.0.out`
     was retrieved into `log_dir` and the queue is empty. This drives the spool + retrieve + remove
     path, the tar/unpack path, and the collector-choice + `Collector.locate` path on a real
     collector. The minicondor schedd ad carries all four weighting attributes (measured,
     `probes/ci-minicondor/schedd-ad.transcript`).

   Fails on: a launcher that never submits, a missing bookkeeping, retrieve or remove step, a
   secret leaking into the ad from `start`, a shipped env that is ignored, and dead transfer of
   `user_modules`.

**Coverage.** The pilot subprocesses self-measure through the `test-parsl` job's recipe: a `.pth`
`coverage.process_startup()` plus `COVERAGE_PROCESS_START=.coveragerc-htcondor`. `LocalPilots`
inherits the env, so `pilot.py` and `server.py` are covered by the frozen tests 1–5. `launch.py`'s
bindings paths are covered by test 8. The site data paths are covered by test 2.

## 4. Commits (implementer; the test author's freeze is its own commit, about 1.3k)
| # | Commit | Files | LOC |
|---|---|---|---|
| 1 | `ci(htcondor): personal-pool CI leg` | ci.yml `test-htcondor` (ubuntu, py3.12; `sudo` installer, wait for `condor_status -schedd`; pytest + combine + per-file gate + diff-cover scoped to `htcondor_backend/**`; added to `ci-required.needs`), `.coveragerc-htcondor` (`sigterm = true`, parallel, branch), pyproject extra + omit | ~110 |
| 2 | `feat(htcondor): site profiles and the htcondor2 pilot launcher` | `sites.py`, `launch.py`, `__init__.py` (launcher exports), `tests/extra/m66/` for the launcher | ~450 |
| 3 | `feat(htcondor): task server, pilot loop and HTCondorBackend` | `server.py`, `pilot.py`, `backend.py`, the rest of `__init__.py`, `tests/extra/m66/` for the server | ~600 |
| 4 | `docs(htcondor): HTCondor how-to and design section` | docs (§5) | ~350 |

The PR is the whole backend at the floor. **The peer `transport` route is a later milestone and not
in this PR.** It needs `HOST` parameterised in `parsl_backend/transport_peer.py`, a
`peer_transport` property, and a probe of worker↔worker reachability on LPC and lxplus. That work
is about 150–300 LOC, per the analysis.

**The implementer's first step** is commit 1, pushed on its own. The frozen m66 tests fail
pre-implementation, but the installer and pool-start steps report. That step measures the
installer's systemd path on a real runner. The recipe was measured only in an ubuntu:24.04
container, with `condor_master` started by hand.

**Site check (implementer).** On LPC, run `htcondor_runner(site="lpc", n_pilots=2, image=coffea-almalinux9-noml:2026.9.0-py3.12)`,
with the driver inside the image per D7, over `concat_plan`. The transcript goes to
`probes/site-lpc/m66-check.txt`. **lxplus stays gated on the owner's permission to submit** (D6).

## 5. Docs
- **`docs/htcondor.rst`** (how-to):
  - install `[htcondor]`;
  - the laptop dry run with `LocalPilots`;
  - an LPC walk-through: proxy, the D7 driver recipe (`apptainer exec` with bootstrap.sh's bind
    set incl. the `.cmslpc-local-conf` wrapper and `CONDOR_CONFIG=/etc/condor/config.d/01_cmslpc_interactive`,
    the venv via `python -m venv --system-site-packages` + `pip install <clone>` non-editable),
    then `htcondor_runner(site="lpc", …)`;
  - an lxplus walk-through: the image-hosted driver, `transfer_output_files=""`, optional
    `output_destination` via `extra_submit`, JobFlavour;
  - a plain pool;
  - `user_modules`, and the `__main__`/lambda error;
  - pilot logs in `log_dir`.
- **`design.rst` "On an HTCondor pool"**, in the house style (`docs-didactic/styleguide.md`): pilots
  pull, the driver resolves futures, heartbeat/lease/requeue-once, and the per-run secret.
- **Other doc edits:**
  - the README install line and runner-table row;
  - an `index.rst` row;
  - an `api.rst` automodule;
  - a `changelog.rst` entry;
  - delete "no direct HTCondor" from `improvements.rst:6`, `design.rst` ("Direct HTCondor and
    SLURM submission") and `README.md:105`, keeping SLURM and TaskVine.

## 6. Risks (premise → evidence) and owner items
- The driver in the image needs bootstrap.sh's *full* binds; the plain binds fail
  (`probes/driver-in-image/attempt1-plain-binds.txt` vs `attempt2-bootstrap-binds.txt`).
- The tar-shipped venv relocating on an LPC worker is unmeasured. lpcjobqueue ships an unpacked dir.
  The LPC site check measures it.
- lxplus is unmeasured end to end: the driver in the image (the Kerberos and `/etc/condor` binds),
  the job, and driver-port reachability. The schedd's spool refusal *was* measured
  (`probes/site-lxplus/submit.transcript`).
- `transfer_output_files=""` on LPC comes from the lpcjobqueue source, not a measurement. The LPC
  site check confirms it.
- The personal pool accepts spooled submits, and retrieve + remove works on it
  (`probes/ci-minicondor/spool.transcript`).
- Pilot start latency versus `N_WORKERS_WAIT_S`: 45 s on an idle LPC pool (`probes/site-lpc/submit.transcript`).
  A busy pool is unmeasured.
- htcondor is resolved at 25.13.2 in the image and 25.14.1 on PyPI, so the floor is 25.13
  (`probes/site-lpc/venv-recipe.txt`).
- **Owner:** `ParslBackend.submit` resolves future args with a blocking `.result()`. A failed leaf
  therefore escapes the engine's `describe_failure` translation on any plan with ≥2 leaves. The
  same shape was found in this plan's review and designed out here; the parsl fix is out of this
  lane.
- **Owner:** permission for the lxplus test job (D6). No custom image or wheel is needed: the
  coffea image and PyPI wheels suffice (`venv-recipe.txt`). A valid LPC proxy is needed at
  site-check time.
