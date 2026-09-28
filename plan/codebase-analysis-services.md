# Services arc: codebase analysis (driverless · Triton pools · histserv fills)

- §0 Sources, path prefixes, probes
- §1 What a Plan captures vs what a run needs (driverless)
- §2 Triton plugin: the address seam and the invocation path
- §3 Histogram fill/combine seam in graphed-histogram
- §3a Histogram construction path and per-histogram attachment (appended after §6)
- §4 histserv: API, wire format, server, live probe
- §5 Executor seams: resources/workers, `/hello`, events, launcher knobs, pilot entry
- §6 Open facts the planner must not assume
- §7 Conversion template: HggInclusiveProcessor (inputs, outputs, op surface, install, data reach)

Builds on `codebase-analysis.md` (Shape, traces a/b, §1–§3) and `plan.md` §1–§2 without repeating
them. It reads and probes only; no recommendations.

## §0 Sources, path prefixes, probes
- `ge/` = `~/vibe-coding/lanes/htcondor/graphed-executors/src/graphed_executors/`, branch `lane/htcondor` @ f9253fa.
- `g/` = graphed **0.0.6 in `~/vibe-coding/lanes/htcondor/.venv`** site-packages, built from 3c46e01,
  the live `origin/main` (`git ls-remote origin main` → `3c46e017…`). The `m52/graphed` checkout
  is on `feat/always-attribute` with a stale `origin/main` ref (81e177c), so it was not read.
- `gh/` = `graphed_histogram/boost.py`, installed copy byte-identical to `origin/main` 4c4b79f (`diff` empty).
- `hs/` = `~/vibe-coding/lanes/htcondor/refs/histserv/src/histserv/` @ b097444 (0.2.1).
- Probes live in `probes/services-code/`: **P1** `probe_triton_plan.py`→`.txt`,
  **P2** `probe_hist_partial.py`→`.txt`, **P3** `probe_histserv.py`→`.txt`.

## §1 What a Plan captures vs what a run needs (driverless)
There are **two Plan types**:
- `g/core/execution.py:209 Plan`, the runtime job: live `process`/`combine`/`empty`, plus `tasks`,
  `next_tasks`, `stop`, `open_once`; docstring "PROVISIONAL (the real serializable Plan is M8)".
- `g/core/plan.py:126 DurablePlan`, the M8 durable form (`DurablePlanV2` `:267` for shuffles).

Executors accept **only the runtime Plan** (`HTCondorRunner.run`, `ge/htcondor_backend/backend.py:165`;
`grep -rn "DurablePlan\|OpSpec" ge/` is empty).

**DurablePlan wire.** `to_bytes` (`plan.py:195-209`) writes sorted-key JSON with `ir_b64`,
`process`/`combine`/`empty` as `OpSpec`, partitions, `read_columns`, `stopping`, `file_locality`
and `resource_hints`. `from_bytes` is at `:212`.
- `OpSpec.from_callable` (`:97-109`): `kind="ref"` (`module:qualname`) if it re-imports to the same
  object, else `kind="opaque"` (cloudpickle by value).
- `run_resumable` (`g/checkpoint/runner.py:80`) resolves the three OpSpecs and calls
  `process(part, resources)` (`:145`). **It never reads `plan.ir`.** The IR goes into `task_id`
  (`plan.py:164-176`) and the fingerprints only.
- The only in-tree producers of a durable plan are the shuffle/join builders
  (`g/shuffle.py:198,269`, V2). `Session.serialized_ir` (`g/session.py:195`) yields IR bytes only.
  **No function converts an `aggregate_plan` runtime Plan into a `DurablePlan`** (grep over `g/`).

**An `aggregate_plan` process** is `_PartitionReduce` (`g/aggregate.py:60`, built `:242`), a frozen
dataclass of `ir`, `source_name`, `backend_factory`, `columns`, `reader` (a `PartitionedSource`;
partitions are **URIs as the driver saw them**), `externals` ((key, evaluator) tuple), `reduce`,
`frames`, optional `store`. `__call__` (`:82-95`): `read_partition` → `evaluate_ir` → `reduce`. Measured:
- **P2, histogram plan:** the whole runtime Plan stdlib-pickles to **2,315 B** (2 tasks), and a
  fresh interpreter with no `PYTHONPATH` and a different cwd unpickles and runs it through
  `SequentialRunner`: `rc 0 WeightedSum(value=20000, …)`. Every callable is a class or function of
  an installed package (`graphed`, `graphed_histogram`). Partition uris are the driver's absolute
  paths (`partition0 uri='/var/folders/…/f0.parquet'`).
- **P2:** `OpSpec.from_callable` gives `process opaque`, `combine ref`, `empty opaque`.
  `_PartitionReduce` and `_ZeroHist` are instances, so they become opaque.
- **P1, user-module reduce:** `DurablePlan(process=OpSpec.from_callable(plan.process), …)` is
  6,767 B. A fresh interpreter's `run_resumable` fails without the user module on the path
  (`rc 1 ModuleNotFoundError: No module named 'probe_funcs'`) and succeeds with it
  (`rc 0 [9950.0, 10050.0]`). **cloudpickle-by-value of an importable user function still
  references its module.**

**Not captured by either Plan:** executor/backend choice and config; the Monitor; whether data uris
resolve on the run host; service endpoints beyond IR params (§2); the installed environment
(`DurablePlan` has no environment digest). Runtime `next_tasks`/`stop` are callables
(`execution.py:215-216`) and pickle by reference.

**Remote stores (m62).** `aggregate_plan(store=)` takes a dir or fsspec URL; `FsspecStore` iff
`"://" in store` (`g/aggregate.py:129`). `FsspecStore(url, node, **storage_options)`
(`g/checkpoint/fsspec_store.py:40`) mirrors the local layout, one object per journal record (`:1-12`).

## §2 Triton plugin: the address seam and the invocation path
- **The address is a node param:** `params["url"]` → `tritonclient.http.InferenceServerClient(url=…)`
  (`g/preserve/externals/triton_external.py:31-35`), **HTTP, not gRPC**, by default; swappable via
  `params["transport"]="module:attr"` (`:38-48`, a factory whose module also supplies the request
  classes). No env var, no `PayloadDescriptor` field. tritonclient is **not installed** in the venv.
- `record_external` (`_base.py:218-244`) copies every param into the IR node (P1 `EXT_NODE_PARAMS
  {… "url": "http://gpu-a:8000", "transport": …}`), so the URL is IR identity: P1
  `IR_BYTES_DIFFER_WHEN_ONLY_URL_CHANGES True`, `EXTERNAL_KEYS_DIFFER_BY_URL True`; `task_id`
  hashes `ir`, so a URL change changes every task id.
- **Invocation:** `_PluginEvaluator.__call__` (`_base.py:267-281`), once per node per partition,
  loads once per **process** into module-global `_RESOURCE_CACHE`, then `eval_triton` makes **one
  `client.infer` with the whole partition** (`triton_external.py:80`). P1: 2 nodes × 2 partitions → 4
  infers of 100 rows.
- **Measured: the cache key ignores the URL** (`(kind, content_hash)`, `_base.py:268`). P1, two nodes
  with the same descriptor and urls gpu-a/gpu-b: `CONNECTS ['http://gpu-a:8000']`, all 4 `INFERS`
  to gpu-a; gpu-b never dialed. (`ResourceCache`, `:88-93`, the preserve path, keys on params.)
- Evaluators get only input values (`g/execute.py:260-271`), never `WorkerResources`/`WorkerEnv`.
  `_RESOURCE_CACHE` is never closed (only `get`/set at `_base.py:269,280`), so `close_triton` does
  not run on the executor path.

## §3 Histogram fill/combine seam in graphed-histogram
- **A fill is an External node.** `Histogram.fill` records
  `session.record_external("histogram.fill", FillEvaluator, inputs, params, descriptor=…)`
  (`gh:617-624`, axis mode `gh:762-769`). P2 shows descriptor
  `kind "histogram", framework "boost_histogram", io_schema "uhi"` and params
  `spec` (canonical axes+storage JSON), `n_axes`, `weighted` and `sampled`.
- **Per partition:** `FillEvaluator.__call__` (`gh:88-127`) fills a fresh `zero_of(spec)`
  **`boost_histogram.Histogram`** for that one chunk. The plan's `reduce` sums a partition's fill
  outputs by output index: `_SumFills` (`gh:403-423`) or `_GroupReduce` for multi-histogram plans
  (`gh:430-443`). The partition result is a boost histogram, or a dict `{slot: hist}`.
- **Across partitions:** `combine = add_histograms` (`gh:387-400`, native `+` after widening growth
  axes) or `_add_groups` (`gh:446-450`). The **executor** applies it: in the fixed path it runs
  `_combine_task` over `plan_tree`, and in the adaptive path the driver's `running_fold`
  (`codebase-analysis.md` trace a). The histogram node has no combine hook of its own.
- **Plan builders:** `Histogram.plan()` (`gh:784-831`) and `graphed_histogram.plan({name: h})`
  (`gh:866-912`) are thin wrappers over `graphed.aggregate_plan`. They pass `externals=`, and the
  wrapper's reduce/combine/empty are the only histogram-specific parts.
- Plug points in code (named, not judged): (a) `FillEvaluator`, per node per partition; (b) the
  plan's `reduce`, per partition; (c) `combine`/`empty`, applied by the executor tree; (d) a new
  aggregate wrapper beside `plan()`. `unpack` (`gh:1018`) shapes the user-facing dict.
- **Output objects:** `boost_histogram.Histogram` (P2 `PARTIAL_TYPE`). `hist.graphed.Hist`
  (`site-packages/hist/graphed/hist.py:52`) subclasses `hist.Hist` and `ghb.Histogram`, and the
  hist fork ships it in hist 2.12.0.
- **Size:** a 50-bin Weight partial stdlib-pickles to **1,153 B** (P2), against 912 B for a histserv
  fill of the same histogram (§4).

## §4 histserv: API, wire format, server, live probe
**Client** (`hs/client.py`):
- `Client(address)` (`:75`): lazy `grpc.insecure_channel` (`:107`), no compression, 512 MB send
  limit; `__getstate__` drops the channel, so it pickles. `init(hist, *, token, compression)`
  (`:124`, all axes named) → `RemoteHist`; `connect(hist_id, token=)` `:176`.
- `get_connection_info()` (`:339`) → `{address, hist_id, token}`; `from_connection_info` (`:288`)
  does one `Describe` RPC. `fill(**axes, weight, sample, unique_id, compression)` (`:363`);
  `fill_many` (`:413`) sends one dense payload per chunk key.
- `snapshot(delete_from_server=False)` (`:542`) → `ChunkedHist` (`.to_hist()` → `hist.Hist`);
  `flush(destination)` (`:578`) writes HDF5 **on the server's filesystem** (needs h5py there). Also
  `reset`, `delete`, `exists`, `was_filled_with_unique_id`, `stats`.
- **Token:** gRPC metadata `x-histserv-token` (`:121-122`). An entry created with a token refuses
  any other token (`hs/service.py:202`). P3: both a wrong token and no token get
  `NOT_FOUND unknown histogram id`, not a permission error.
- **Idempotency:** a repeated `unique_id` returns `ALREADY_EXISTS` (`service.py:226-240`) instead of
  being dropped silently (P3 `REPLAYED_UNIQUE_ID StatusCode.ALREADY_EXISTS`). Ids are held in an
  in-memory set per histogram, and `Reset` clears them (`:648`).

**Wire** (`hs/protos/hist.proto`): `FillRequest{hist_id, unique_id?, chunk_key[], dense_view bytes,
codec?}`.
- **The client pre-bins.** It fills a local dense `Hist` and ships `view(flow=True)` bytes
  (`client.py:394`).
- Category axes (`IntCategory`/`StrCategory`) become chunk-key axes (`chunked_hist.py:196`), and
  every other axis is dense.
- Payload per call ≈ ∏(dense bins incl. flow) × storage itemsize + ~80 B, independent of the row
  count. P3, `Regular(50)` + `StrCategory` with Weight storage: dense shape `(52,)` × 16 B →
  **912 B per `Fill` for 10,000 rows**. The server logs `request=912 B`.
- Optional codecs: `zstd`/`lz4` (numcodecs).

**Server:** console script `histserv` or `python -m histserv`. Flags (`hs/__main__.py:17-53`):
`--port` (0 = free port), `--prune-after-seconds` (default 86400; idle histograms dropped),
`--prune-interval-seconds`, `--stats-interval-seconds`, `--log-level`, `--dashboard-port`. Binds
**`[::]:port` insecure** (`server.py:67`), no TLS or auth flag; dashboard on `0.0.0.0` (`:132`).
Receive limit 0.5 GB (`:53`). State is the in-memory `Histogrammer._entries` (`service.py:143`),
lost at exit. A plain asyncio process with no external state; running it in a batch job is not
probed (§6).

**Install trap:** `uv pip install ./refs/histserv` fails with
`RuntimeError: Dashboard UI not pre-built` (`hatch_build.py:11-14`; `probes/services-code/install.log`).
The probe ran the b097444 source via `PYTHONPATH=…/src` with the pyproject's dependencies installed.
PyPI serves `histserv==0.2.1`, the same version (`uv pip install --dry-run histserv`).

**Live probe (P3, 60 s, localhost):** `init` of a `Regular(50)`+`StrCategory` Weight histogram,
`token="run-secret"`; 2 spawn processes (one got the pickled `RemoteHist`, 2,021 B; one used
`from_connection_info`), each 3 fills × 10k rows + 1 replayed id. `snapshot().to_hist().sum(flow=True)`
= `WeightedSum(value=60000, variance=60000)`, exactly the 6 accepted fills;
`was_filled_with_unique_id("1-0") True`, `("9-9") False`; stats `histogram_bytes 832`, v0.2.1;
port free after `terminate()`.

**The example pattern** (`example/coffea_processor.py`): `client.init` once on the driver in
`Processor.__init__`. The processor pickles to workers, `process` calls `remote_hist.fill` and
returns `None`, and the driver `snapshot()`s at the end.

## §5 Executor seams
- **`resources`/`workers`:** protocol kwargs (`ge/submit/protocol.py:62-63`) a backend "silently
  ignores" without the capability (`:67-69`). The engine **never passes them**: every
  `backend.submit` in `ge/submit/engine.py` (`:353,363,415,444,493,560`) passes only `key`/`retries`.
  `HTCondorBackend`: `per_task_resources=False`, `pin_to_worker=False` (`backend.py:33-41`), "The
  hints are ignored" (`:95-96`). `DurablePlan.resource_hints` (`plan.py:142`) has no consumer in `ge/`.
- **`/hello`:** a pickled **string only**, `f"{hostname}:{pid}:{uuid8}"` (`pilot.py:86-87`);
  `TaskServer.hello` records a beat and returns `{"beat_s", "lease_s"}` (`server.py:175-177`). No
  slot, GPU, port or capability. Every id counts in `live_pilots()`/`n_workers()` (`:153-156`) and
  leases any task via `/next` (`:186-203`), with no per-pilot filter. `_route` (`:287-301`) treats
  **any path other than hello/beat/next as `/result`** (`else:` at `:298`).
- **Events:** `subscribe_events` stashes a per-topic handler (`backend.py:104-112`); worker events
  buffer in `_ParslWorkerEnv.emit` and ride back inside the result (`ge/parsl_backend/_shim.py:56-81`),
  dispatched on unwrap. No mid-task push from a pilot.
- `WorkerEnv`: `resources` (`open_once`), `worker`, `emit` (`engine.py:80-88`). `RunContext` is a
  frozen 5-field dataclass (`:65-77`), no free-form slot. `Monitor` (`g/core/execution.py:371-381`)
  is passive: `on_task`, `on_profile`, `on_combine`, `worker_profiler_factory`.
- **Launcher knobs:** `CondorPilots(site, image, request_cpus, request_memory_mb, log_dir,
  user_modules, env, extra_submit)` (`launch.py:107-118`). `submit_description` layers the base
  keys, then the site profile, then **`extra_submit` last** (`:141-167`), so it can add any key,
  such as `request_gpus`, which has no named parameter.
- `start` submits **one cluster of `n` identical jobs** (`count=n`, `:210`) and overwrites
  `self.cluster`/`_constraint` (`:213-215`): one `CondorPilots`, one cluster. **Fixed executable:**
  generated `pilot.sh` untars `env.tgz` if present, then `exec <python> -m
  graphed_executors.htcondor_backend.pilot <url> graphed-secret` (`launch.py:36,197-201`). Secret is
  a transferred 0600 file, never args/env (`:4-6,51-54`); `transfer_output_files=""` (`:157`); site
  profiles are data (`sites.py:34-67`).
- **Pilot entry:** `pilot.main([url, secret_path])` (`pilot.py:82-97`): one task at a time, a beat
  thread, exit 0 on 410 / 2 on 403, self-SIGTERM once the driver is unreachable > `lease_s` (`:49-55`).
  **Server bind:** all interfaces, first free port of 10000–10100, advertised host `socket.getfqdn()`
  (`backend.py:57,62`; `server.py:85-90,110`). `LocalPilots` (`launch.py:68-95`) = same pilot as subprocesses.

## §6 Open facts the planner must not assume
1. **Node↔node reachability and schedd access from inside a job are unmeasured here.** This covers
   pilot→driver-job, task→Triton-slot and task→histserv-slot. The `svc-probe-lxplus`/`lpc` lanes
   own them (`journal.md:289`), and `probes/services-{lpc,lxplus}/` were empty when this was
   written.
2. GPU slots exist on lxplus but not in the LPC wrapper collector (`journal.md:287`). Triton
   startup inside an HTCondor GPU job, the image path and the ports were not probed. A live
   tritonclient round trip was not run (tritonclient is not installed; P1 used a fake transport).
3. There is no graphed path that turns a user's session output into a `DurablePlan` with an
   aggregate process, and no executor accepts a `DurablePlan`. Whether a pickled runtime Plan
   (P2: 2,315 B, library-only refs) is an acceptable driverless payload is a design question.
   Runtime Plans holding user-module callables need those modules on the path (P1).
4. Not measured: whether submit-host data uris resolve on a driver job's host. 5. histserv under load was not measured: throughput, memory at many bins or chunk keys, behaviour at
   the 0.5 GB receive limit, and multi-client concurrency beyond 2 processes. Neither was `flush`
   (h5py not installed) nor the dashboard.
6. histserv's `unique_id` returns ALREADY_EXISTS on a retried fill. How that interacts with
   `TaskServer`'s requeue-once and the engine's `retries=3` is untested.
7. The Triton `_RESOURCE_CACHE` URL-blind key (§2) is measured with a fake transport only; its
   effect with real tritonclient is inferred, not run.

## §3a Histogram construction path and per-histogram attachment
`gh/` as §0; the `g/` files cited are byte-identical in the 3c46e01 clone and the venv (`diff -q`). Probe **P4** `probe_hist_identity.py`→`.txt` (lane venv).
- **Declaring.** `gh.Histogram(*axes, storage=, metadata=)` (`gh:461,471`), a `boost_histogram.Histogram`
  subclass. Storage defaults to `Double` (`gh:472-473`) and is fixed at construction. `histogram/2d/dd`
  (`gh:1080,1089,1102`) pick `Int64`/`Weight`; `factory(*arrays, histref=)` (`gh:1052`) copies a
  reference. **hist fork:** `hist.graphed.Hist` (`hist/graphed/hist.py:52`) = `FillModeMixin, hist.Hist,
  ghb.Histogram`; `hist.graphed.new` (`__init__.py:13`) is QuickConstruct; the mixin (`:15-49`) only
  reroutes `unweighted=`/`variation_axis=` to `ghb.Histogram.fill`.
- **Held before execution:** that object, eager state empty, plus `_spec` (canonical axes+storage JSON,
  `_spec.py:152-159`, storage by type name `:156`), `_fill_nodes`, `_evaluators {chash: FillEvaluator}`
  (`gh:475-490`).
- **Fill → External** (`gh:493`): `FillEvaluator(spec, n_axes, has_weight, has_sample, n_weights)`
  (`gh:581-586`); `chash = _fill_chash(...)` (`gh:588`; `content_hash(spec)` + unweighted/n_weights/
  variation discriminators, `gh:291-318`); `PayloadDescriptor(kind="histogram", content_hash=chash,
  framework="boost_histogram", version=bh.__version__, io_schema="uhi", preprocessing_ref=None)`
  (`gh:589-596`); params `{spec, n_axes, weighted, sampled[, n_weights]}` (`gh:597-604`);
  `session.record_external("histogram.fill", evaluator, inputs, params, descriptor=, form=)`
  (`gh:617-624`); `_evaluators[chash] = evaluator` (`gh:628`). Axis mode: `gh:732-770`.
- **What reaches the executor.** `record_external` stores only `descriptor`+`params` (`g/session.py:383`);
  the evaluator goes to `session._externals` (`:385`), never the IR. `aggregate_plan` wires each
  surviving External's evaluator under `external_key` = `content_hash|sorted-JSON(params)`
  (`g/aggregate.py:172-189`, `g/execute.py:201-214`; explicit `externals=` overrides, `aggregate.py:237-240`)
  into `_PartitionReduce.externals` (`:248`), i.e. the pickled runtime Plan; workers resolve it in
  `evaluate_ir` (`execute.py:258-268`). **No other per-histogram path reaches a worker:** it is IR
  (descriptor/params) or the evaluator object inside the Plan.
- **Identity (P4).** `NodeKey::External{descriptor, params, inputs}` derives `Hash`/`Eq` (`src/node.rs:40,
  56-60`), and `PayloadDescriptor` derives both over all six fields (`:14-22`). Varying one at a time:
  `kind`, `content_hash`, `framework`, `version`, `io_schema`, `preprocessing_ref` and a new param
  `backing` each give `distinct_node=True` (control: equal params `same_params_interned=True`). Storage
  changes IR via `spec` (`STORAGE_WEIGHT_vs_DOUBLE_IR_DIFFER True`).
- **Task ids (P4).** A `FillEvaluator` subclass with `backing="histserv://host:50051"`, descriptor/params
  unchanged: `EVALUATOR_SWAP_IR_IDENTICAL True`, the worker object carries it (`PLAN_EXTERNALS_TYPES
  ['BackedFill'] … ['histserv://host:50051']`), the replay capture id (`ir`+partition, `aggregate.py:121`)
  is unchanged, and the process `OpSpec` identity (a `DurablePlan.task_id` input, `g/core/plan.py:164-176`)
  changes. As a node param instead: `PARAM_BACKING_IR_DIFFER True`, so every task id changes too.

## §7 Conversion template: HggInclusiveProcessor
`tpl` = `refs/hgg/inclusive_processor.py`; `hdna/` = `refs/HiggsDNA` @ d179305; coffea fork =
`~/vibe-coding/coffea-graphed-mvp` @ b2612ab0. Probes: **P5** `probe_hgg_surface{,2,3}.py`→`.txt`
(pre-written; re-run by me) → `.txt` on **graphed 0.0.5** (`~/vibe-coding/lanes/notebook/.venv`) and → `.006.txt` on
**graphed 0.0.6** = clone HEAD 3c46e01 (lane `.venv`, plus the coffea fork and uproot ca3a8a2 installed to match the
notebook venv, `lane-coffea-install.log`), on `coffea-graphed-mvp/tests/samples/nano_dy.root`; **P6** `higgsdna-install.log`; **P7** `probe_xrootd_open.py`→`.txt`.

**(a) External inputs.** The only `higgs_dna` import is `infer_nano_version` (`tpl:53` →
`hdna/higgs_dna/utils/misc_utils.py:396`: NanoAOD version from field presence). jetID, fiducial and
truth helpers are inlined (`tpl:88-186`). `importlib.resources` data: `metaconditions/Era2022_v1.json`
(triggers + MET filters, `tpl:883`) **exists**. **Missing** in both the clone and the installed package
(`is_file()` → `True False False`): 7 golden JSONs `metaconditions/CAF/certification/Collisions{16,17,18,
22,23,24,25}/…` (`tpl:266-274`) and 5 `systematics/JSONs/POG/JME/{2022_Summer22,2022_Summer22EE,
2023_Summer23,2023_Summer23BPix,2024_Summer24}/jetid.json.gz` (`tpl:119-125`, read only for NanoAOD ≥ v13).
The console script `pull_files.py` (`hdna/pyproject.toml:66`) fetches them: `--target GoldenJSON` via https
from `cms-service-dqmdc.web.cern.ch` (`pull_files.py:1144,1197`); `--target JetMET` copies from
`/cvmfs/cms-griddata.cern.ch/cat/metadata/JME` (`:1215,1219`). There is no `/cvmfs` here. Year is a constructor dict
`{dataset: [year]}` (`tpl:294-296`). Manifests: data 8 datasets / 5,765 files, mc 51 / 22,517, all
`root://cms-xrd-global.cern.ch//store/…`.

**(b) `process()` returns** `{dataset: {nTot, nPos, nNeg, nEff, genWeightSum}}`: Python `int`/`float`
(`tpl:774-785`; data uses `len(events)`, `nNeg=0`). **No histogram, `hist.Hist`, coffea accumulator or
array is returned.** The physics output is a side effect. With `output_location` set, `dump_to_parquet`
writes one flat parquet per chunk to `<output_location>/<dataset>/nominal/<partition_key>.parquet`
(`tpl:740-761,856-861`) with sorted columns and string schema metadata `sum_genw_presel` (+
`sum_weight_central` for MC, `tpl:792-795,841`). Columns: `lead_*`/`sublead_*` (all photon fields), diphoton
`pt,eta,phi,mass,charge,rapidity`, `n_jets,NJ,PTJ0,PTJ1,YJ0,{first,second}_jet_{eta,phi,mass,charge}`,
`event,lumi,run,nPV,fixedGridRhoAll,BeamSpot_sigmaZ(Error),dZ,weight,weight_central,sigma_m_over_m`. MC adds
`genWeight,fiducial{Classical,Geometric}Flag,TruthPTH,TruthYH`. Weight = `genWeight` (MC) or 1.
`postprocess` is `pass` (`tpl:864-865`). `__main__` calls `process` on one local file, no coffea Runner.

**(c) Op surface vs graphed.** Ops used:
- `ak.{where,num,with_name,zip,ones_like,fill_none,zeros_like,argsort,sum,pad_none,flatten,fields,
  unflatten,to_arrow_table,local_index,is_none,firsts,combinations,any,all,Array}`;
- `numpy.{abs,sqrt,log,exp,sin,cos,tan,arcsin,arctan,cosh,sinh,isnan,where,copy,zeros_like,sum,errstate}`;
- coffea `PtEtaPhiMCandidate` (`+`, `.pt/.eta/.phi/.mass/.charge/.energy/.z`, `metric_table`); `vector` only via `register_awkward()` (`tpl:57`);
- `CorrectionSet.from_file(…)[…].evaluate` (`tpl:126-146`) and `LumiMask` (`tpl:335-337`).

The graphed entry point is `NanoEventsFactory.from_root(..., mode="graphed")`, in the coffea fork's
`src/coffea/nanoevents/factory.py:274,411,625,873` and `nanoevents/_graphed.py`. Every `ak.*` except
`to_arrow_table`/`Array` has a `def` in `g/awkward/functions.py` (one `^def <name>(` hit each;
`to_arrow_table` 0). P5: 28 shapes OK and they run through one `aggregate_plan` (`PLAN_RUN_OK n_outputs 20`).
**Fails or has no equivalent as written (P5).** Verdict 0.0.5→0.0.6; the path-normalized `diff` of `.txt` against `.006.txt` is empty (control: a diff made to differ prints):
- `int()`/`len()` of deferred counts → `TypeError` — unchanged.
- `.to_numpy()` (`tpl:412-414,779,793`) → `GraphedTypeError` — unchanged.
- `__setitem__` on events/records (`tpl:397-398,409,452,608,626-671,805-806,828-851`) → `AttributeError`; `gak.with_field` (`functions.py:142`) OK — unchanged.
- `ak.Array({...})` rebuild (`tpl:738`) → `GraphedTypeError … to_list()`; `gak.zip` OK — unchanged.
- `ak.to_arrow_table` (`tpl:751`): no gak function; the writer is `graphed.awkward.io.to_parquet` (`g/awkward/io.py:794`) — unchanged.
- `events.attrs[...]._partition_key` (`tpl:746`) → `AttributeError … cannot answer 'attrs'` — unchanged.
- `LumiMask(path)(run, lumi)` → `AttributeError shape` — unchanged.
- `CorrectionSet[…].evaluate(graphed)` → `ValueError`; `gak.apply_correction` (`functions.py:517`) OK — unchanged.
- `numpy.where`/`numpy.copy` on graphed silently return an eager `ndarray` of shape `()`; `gak.where` is deferred — unchanged.
- `bool(gak.num(x, axis=0) > 0)` (the `if`s at `tpl:555,564-565`) is `True` even when the selection is empty — unchanged.
- `gak.with_name(…,"PtEtaPhiMCandidate")` needs a `charge` field, which `tpl` always zips — unchanged.

**(d) Install (P6).** Into `probes/services-code/hdna.venv`: rc 0, 2.4 s, 113 packages, `higgs-dna==0.0.0`
(PyPI coffea 2026.9.0, not the fork; uproot 5.7.6, correctionlib 2.9.0, vector 1.9.0, xrootd 6.1.1, fsspec-xrootd 0.5.5). The `infer_nano_version` import works.

**(e) Data reach (P7).** The lane `.venv` had **no uproot** at probe time (`ModuleNotFoundError`; uproot ca3a8a2 installed later for P5), so P7 ran with
`hdna.venv`. The first data URL (`…/Run2024C/EGamma0/NANOAOD/MINIv6NANOv15-v1/2540000/3151ab41-….root`)
gave `security protocol 'ztn' disallowed for non-TLS connections.` and then
`OSError Failed to open file: [ERROR] Operation expired` after 72 s. There is no X509 proxy
(`/tmp/x509up_u501` absent, no `voms-proxy-info`). **Not reachable from this machine.**
