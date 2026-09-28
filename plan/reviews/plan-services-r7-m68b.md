# Review r7 — `plan-services.md` §3.3 executors m68b, reviewed alone

Scope: §3.3, plus the D2/D3/D10 text it depends on and the §6–§9 lines that name m68b. Delta:
`git diff --no-index --word-diff reviews/plan-services-r6-snapshot.md plan-services.md`. Read-only against the lane
clone `~/vibe-coding/lanes/htcondor/graphed-executors` (613aaa7). Scratch fetches are in this session's scratchpad.

## r6 items
- **M10: closed.**
  - The §3 preamble fixes one set of params (`graphed_identity`, `INPUT0`→`OUTPUT0`, no `transport`).
  - `P9-eaf-model/graphed_identity/{config.pbtxt,1/model.onnx}` exist, and the platform is `onnxruntime_onnx`.
  - `p3-triton-image/transcript.txt` shows that 24.11-py3 lists `onnxruntime` among its backends.
- **C7: closed.** `test_cluster_service_job.py` pins "an `http:` spec by `check_ready`'s rule".
- **M9: closed at the announce, but the identity is lost one hop later.** See M11.

## Design findings

**M11 · D10 + §3.3 `host_service`/`wait_announce` · the announced identity never reaches the probe.**
- Premise: `grep` shows D10's `host_service(spec) -> endpoint` (L96) and §3.1's "cluster-hosted → the one it
  announces" (L245). The `wait_announce` rows (L344, L347, L371) return or record only the endpoint. Positive
  control: the same grep matched 17 `host_service` lines.
- So `ServiceSet.probe` has no identity for a cluster-hosted service. The pass rule "only the service's identity
  answering passes iff it is the driver's" cannot be evaluated. `test_cluster_services_live` (a) asserts exactly
  that rule on one-node minicondor.
- The DAG `announce_only` path has the same gap: it resolves "as a provided endpoint", which has no identity.
- m70 has the same gap: the dask Variable and the parsl announce carry the identity, but `host_service` still returns
  one string.
- Closed by: D10 `host_service(spec) -> (endpoint, identity)`. `wait_announce` returns both, and the `announce_only`
  resolution keeps the announced identity. `test_announce_route` asserts that `wait_announce` returns the identity
  the body carried.

**M12 · §3.3 `ServiceJob` `arguments="<url> graphed-secret <name> <port>"` · the port is chosen off the node that
binds it.**
- Premise: `grep 'free port|<port>'` finds a free-port rule only for driver-hosted services (L237, "bind a free port
  from `backend.service_ports`"). For the ServiceJob it finds a single `<port>` (L334) with no source.
- The m66 idiom scans a range where the bind happens (`server.py` `_bind`, L85-90).
- On a shared lxplus GPU node, a port the driver picks can be taken. Triton then never binds and never announces.
- Closed by: `arguments` carries the profile's `worker_ports` range (the measured worker↔worker set, P7).
  `announce.py` (stdlib) takes the first free port of that range in-job, renders the argv, and announces the port
  it took. `test_cluster_service_job` pins the range in `arguments`. A stdlib case holds the range's first port with
  a listener and asserts that the next port is the one announced.

**M13 · §3.3 `host_service` · a `wait_announce` timeout leaves the ServiceJob queued.**
- Premise: `grep release_service` (7 hits) shows the only removal path is `close()` → `release_service` "for
  cluster ones" (L247). Nothing states what `host_service` does on timeout.
- A GPU ServiceJob that is idle past `timeout_s` fails the run. It then later starts and holds a GPU with no driver
  left.
- Closed by: on timeout, `host_service` removes its cluster (m66 `stop()`) before raising, and the reason names the
  timeout and the job's status. A new `test_cluster_services_live` leg submits `resources={"gpus": 1}` with a short
  `timeout_s` on minicondor, which has no GPU slot. It asserts that the call raises naming the timeout and that the
  queue is empty afterwards.

**M14 · §3.3 DAG driverless · the SERVICE node has no secret, and it announces only once.**
- Premise, secret: the only delivery path is `graphed-secret` in `transfer_input_files`, written from
  `TaskServer.secret`, which is generated in `TaskServer.__init__` (`server.py:99`; `launch.py:51,78`). The
  `<name>.sub` is written at DAG submit, before the driver job's task server exists. `grep -i secret` over the plan
  hits only the ServiceJob lines (L333-339, L376). The wrapper "polls `driver.url`" (L350) and receives no secret,
  so its announce gets 403.
- Premise, one announce: `announce.py` "POSTs … then `wait`s" (L341). `RETRY driver 2 UNLESS-EXIT 3` restarts the
  driver with a new server, url and secret. The retried driver then waits on an announce that never comes, times
  out, exits 1 and burns every retry.
- Closed by: each driver start writes `graphed-secret`, then `driver.url` (atomic rename), into the DAG dir. The
  SERVICE wrapper reads both and re-announces whenever `driver.url` changes. A new `test_driverless_dag` case
  (stdlib, all OS) starts the wrapper against a signed stub, replaces both files with a second stub's, and asserts
  that the second stub receives the announce.

**M15 · §3.3 `test_cluster_services_live` (a)/(b) · on generic, `http_server` never reaches cluster hosting.**
- Premise: under D2, a recipe with no image and no GPUs is driver-hosted when `"driver" in service_hosts`. D4 and
  m68a's pinned `test_services_sites` give generic `("driver","cluster")`.
- So leg (a) resolves driver-hosted, and leg (b) builds no DAG ("a cluster-hosted recipe makes the submission a
  DAG").
- Closed by: both legs run on a generic profile copy with `service_ports=None`, which gives `("cluster",)`. m68a's
  live (c) already uses a profile copy.

**M16 · D3 + §3.3 `DagmanProfile` · generic's `dag_root` has no value.**
- D3 reads "lxplus `/afs`, generic; LPC none", and §3.3 reads "generic = stock `from_dag` with the shared dir".
- `test_driverless_dag` pins the `DagmanProfile` values and needs generic to accept the DAG, so the test author has
  to invent the value.
- Closed by: generic `dag_root="/"`. minicondor is one host, so every path counts as shared.

**M17 · §3.3 lxplus run `model_repository="models/"`, `inputs=("models/",)` · the trailing slash drops the directory.**
- Premise: `htcondor-jdl.rst` (htcondor main) says: "When a directory is specified with a trailing path separator …
  the contents are transferred, but the directory itself is not."
- The job therefore lands `graphed_identity/` directly in scratch, and `--model-repository=models/` does not exist
  there.
- Closed by: `model_repository="models"` (no slash) in the lxplus run.

## Exit-round constraints (for the dispatch)
- **X1 (D10 L97-98).** "only after `check_ready` passed where the service runs (condor: `announce.py`)" is false for
  `grpc:`, because `announce.py` only connects. Reword it to "`announce.py`'s stdlib self-check (a connect for
  `grpc:`)".
  - For Triton, the only `grpc:` recipe, the connect is sufficient: `main.cc` (r24.11) calls `ServerNew` at L481 and
    `StartEndpoints` at L500, and core `server.cc` `Init` sets `SERVER_READY` (L272/L276) inside `ServerNew`.
- **X2 (`test_announce_route`).** A malformed signed body means one that is not exactly `name host:port identity`.
  The identity field is required.
- **X3 (§7).** `lane/htcondor` (#34) merged as executors main `eefc0f3` (journal 16:28Z). The m67 base is `main`,
  and m68b still stacks on m68a.
- **X4 (§9).** `$_CONDOR_MACHINE_AD` inside the lxplus Triton image is unmeasured, and the fallback is the
  container's `getfqdn`. The lxplus probe still passes, because the pilots run on other nodes. The transcript
  records which form was announced.

## Self-sufficiency
- Complete apart from its stack: frozen table, files, commits (~500/~300/~150 plus the ~800 freeze, all ≤2k, and
  consistent with §7's ~950/~800), PR on m68a, §6 CI dirs, and the §8/§9 lines.
- m70's `release_service` timeout and slot accounting are not needed by condor: `stop()` is synchronous, and the
  ServiceJob is its own cluster.
- It needs nothing that is defined only in m70.

## Verdict
**NOT CLEAN**: M11–M17.
- Each finding is a sentence-level decision, and its closing decision is given above.
- This is the first round of the split unit. Under the non-convergence rule, a further non-falling round would be a
  second split of m68 work, so it goes to the owner.
