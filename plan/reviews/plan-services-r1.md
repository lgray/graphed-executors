# Review r1 (whole artifact) — `plan-services.md` (m67 · m68 · m69), against the 445-line file amended mid-review

Reviewer probes ran in `~/vibe-coding/lanes/htcondor/.venv` (graphed 0.0.6, executors lane/htcondor 613aaa7,
histogram 4c4b79f, histserv 0.2.1) and a scratch venv; condor bindings have no macOS wheel, so the retry
semantics come from `htcondor/docs/man-pages/htcondor-jdl.rst` (main). The amendment (D4 primary path on
`worker_ports=(10000,10100)`, D6 lxplus self-submit, outbound-IP advertise, sites test row, §8) was diffed
against the reviewed copy; H3 and M1–M4 sit outside the diff and stand. Premises checked and holding: the
`bind_services` hook site (`_leaf_task` passes only `env.resources`, `engine.py:215`; `_PluginEvaluator` is per
node with `node_params`, `_base.py:245,257-268`); the reduce layout carries per-slot data outside IR/params
(`_GroupReduce.layout`, `boost.py:434-443`; P4); `hist_id` is `uuid.uuid4().hex` server-side (`service.py:317`);
`ALREADY_EXISTS` on a replayed `unique_id` (`service.py:234-237`); `wants_partition` = the two `self.reduce(`
sites in `_PartitionReduce.__call__` (`aggregate.py:86,105`); `_refuse_shortfall` returns on `outputs >= marked`
(`boost.py:938`); `run_resumable` never reads `.ir` (0 hits, control 9); `driver_ports` lxplus `(8786, 8786)`
and `spool=True` on both sites (`sites.py:47,63,68`); histserv resolves on Windows x86_64/arm64 py3.12 (uv
dry-run); diff-cover ignores files absent from `coverage.xml` (synthetic repo: `examples/b.py` not counted,
`rc=0`), so "not coverage-gated" is mechanically true for `examples/`. The P6/P7 reports landed during the round; H1 is withdrawn below.

## Design findings (ranked; H1 withdrawn after the P6/P7 reports)

**H1 — withdrawn.** Both reachability rows are now measured (`probes/services-lxplus/P7-ports/REPORT.md`:
10000–10100 open both ways, 9999/10101 refused, Triton at :10000 reachable from another worker;
`probes/services-lpc/P6-ports/REPORT.md`: 10000/10050/10100/10101 open both ways, 9999/18080 refused), so a
frozen pin of the shipped `SITES` rows is a pin on reports and the report-refused fallback is moot for the two
sites. The labels are E13 below.

**H2 · D3/D6/§3.1 · driverless refuses `host="driver"`, the only managed path on the LPC fat slot.** L27: "nothing
on the submit host owns a process" — in driverless the driver *job* owns processes, and P3 measured same-node
reachability (200 from a client on the service's node, `services-lpc/…/transcript-c.txt:11,14`; refused from
another node). A `Popen` histserv inside the driver job with `LocalPilots` needs no open port and is what
`driver.py` gets for free from `ServiceSet.start()` over `run.json.services`; the plan refuses it (L226) and
freezes the refusal (`test_driverless_dag.py`, L278). With H4 below, LPC driverless has no managed service at
all. Closed by: "driverless driver-hosted is allowed with `pilots="local"`, and with `pilots="condor"` iff
`worker_ports`", and a `test_driver_entry.py` leg where `run.json.services=[histserv]` starts the server in the
driver job, pilot tasks fill it (server pid ≠ driver pid), and the port is free on exit.

**H3 · D9/§4.2 · the oracle cannot run on `nano_dy.root`.** The template reads `Rho.fixedGridRhoAll` (`:460,832`),
`BeamSpot.sigmaZ/sigmaZError` (`:833-834`), `Electron.mvaIso_WP80/90`, `GenVtx.z`, and ORs the Era2022
`HLT_Diphoton30_22_*`/`HLT_DiphotonMVA14p25_*` paths (`:354-359`); `nano_dy.root` (40 events, 1499 branches)
has none of them — it carries `fixedGridRhoFastjetAll` and no `HLT_Diphoton*` (uproot probe over
`coffea-graphed-mvp/tests/samples/nano_dy.root` vs `refs/hgg/inclusive_processor.py`). So `test_hgg_conversion.py`
(L379) has no runnable fixture and "the eager template on nano_dy.root" (L63) is not an oracle; a ≥v13 fixture
also needs `jetid.json.gz` (`tpl:119-125`) in the repo. Closed by: the plan names the fixture (a ≥v12 NanoAOD skim
of a few hundred events pulled at LPC under the proxy, committed with its `jetid.json.gz` and metaconditions JSON
under `tests/frozen/m69/data/`) and the pre-freeze check "eager oracle on the fixture returns nonzero `nTot` and
≥1 selected diphoton".

**H4 · §3.1 DAG driverless · LPC cluster-hosted SERVICE nodes are allowed by the new D4 but have no rendezvous.**
L221-223 still reads "LPC has no shared path, so cluster-hosted driverless services are refused there by D4
anyway" and `test_driverless_dag.py` (L278) refuses "on lpc citing D4" — but amended D4 gives LPC
`("driver", "cluster")`, so nothing refuses, and the SERVICE wrapper polls a `driver.url` file that LPC jobs
cannot see (P3: no `/uscms`, `/uscmst1b_scratch`, `/eos` inside the container). Closed by: the refusal keyed on
the rendezvous datum (`DagmanProfile.dag_root` shared with jobs: lxplus `/afs`, generic; LPC none), named in
the error, with the frozen test citing that row; or the `condor_chirp set_job_attr` rendezvous D6 defers,
brought forward if it is to be LPC's path.

**M1 · D6/§2/§3.1 · retries compound and retry deterministic failures.** JDL: "If the job fails (does not exit with
the success_exit_code exit code) it will be retried up to max_retries times" (`htcondor-jdl.rst:1379-1387`); the
driver exits 1 on a `StageError` (L116), so a poisoned plan runs three times, and the DAG adds `RETRY driver 2` on
a node whose `.sub` already carries `max_retries=2` (L128, L223) — up to nine runs. Closed by: two exit codes
(plan error vs infrastructure) with `retry_until=<plan-error code>` and one retry owner (DAG `RETRY` xor the submit
key); `test_driverless_live.py` shows the poisoned run has `NumJobCompletions == 1` in history.

**M2 · D2/§3.1 · one probe task can pass on the service's own node.** P3 is exactly "200 on the same node, refused
elsewhere"; "runs once more, then proceeds" (L193) accepts a second same-host answer, so the probe cannot fail in
the direction it guards when both land on the service host — and under D4's no-report default the probe is the
only check. Closed by: probe until a pilot on another host answers (bounded by `n_pilots` submits or `timeout_s`)
else `ServiceUnreachable(reason="only same-host pilots answered")`; `test_services_protocol.py` drives a two-worker
fake where the first probe's host equals the service's.

**M3 · §5/§4.1 · the histogram `3.14t` CI leg cannot install the histserv extra.** `graphed-histogram/.github/
workflows/ci.yml:77-89` runs `pytest tests/frozen` on `3.14t`; grpcio 1.84.0 publishes no `cp314t` wheel (PyPI
JSON: `cp314t wheels: []`; numcodecs cp314t = macOS only), so `.[dev,histserv]` there builds grpcio from source
or fails and the m69 frozen files cannot run. Closed by: the plan states the 3.14t leg's install set and how m69
files behave there (`importorskip("histserv")` with a pin on the other legs that the skip did not fire), or an
owner ruling to drop that leg's m69 run.

**M4 · D8/§4.1 · `unpack` is single-shot.** `snapshot(delete_from_server=True)` at `unpack` (L60, L314) makes a
second `unpack` of the same result `NOT_FOUND`, while the local path's `unpack` is pure; the design makes the
state reachable and the receipt cannot tell it apart. Closed by: `resolve` memoizes the `bh.Histogram` on the
receipt (or snapshot without delete and release at `close()`); `test_remote_fill_path.py` unpacks twice, equal.

## Exit-round (constraints for the dispatch; no round)
- E1 D6: LPC fat slot cites P3 for worker↔worker; P2 (a job cannot submit) alone carries it — cite P2.
- E2 §3.1: `submit` applied last can replace `transfer_input_files=graphed-secret,announce.py` (§3.3 already
  repeats it) — merge that key instead of overriding.
- E3 §2 `test_driverless_live.py (c)`: the ad has no `max_retries` attribute; probes show the generated
  `OnExitRemove` — assert `JobMaxRetries`/`OnExitRemove`.
- E4 §2 `test_run_handle.py`: `transcript-p1c-spool-tif.txt` holds 8 status lines and no `attr = value` ads; the
  ads fixture is synthetic — say so or cite m66's recorded ads.
- E5 D8: state why the reduce, not the evaluator, ships the fill (evaluators get values only, `execute.py:260-271`;
  `unique_id` needs the partition, which only the reduce sees).
- E6 §6: the histogram m69 PR imports `UnboundService`/`bind_services` from graphed m68; its CI rides `env.GRAPHED`
  on the PR ref, floor bumped at release — state it.
- E7 §8: the lxplus primary (D6) self-submits from a driver job *in the coffea image*; P5's `schedd*.sub` carry no
  image line, so Kerberos inside the container is an unmeasured premise — add it beside "inner jobs start".
- E8 §4.2: the m69 executors freeze = tests + a 905-line oracle + harness + data; state its band or give the oracle
  fixture its own commit.
- E9 §3.2: `m26/fake_triton.py` and `m9/test_triton_server.py` live under `tests/frozen/preserve/` — write the path.
- E10 D4: LPC `service_ports=(10001,10100)` overlaps `driver_ports`; the task server binds first, so no collision —
  say so in one clause.
- E12 D4/§3.3/§8/owner list: "P7 is blocked until the owner hand-runs" is stale — cite the P7 REPORT, mark the
  lxplus rows measured, and make the §3.3 full GPU run the measured expectation (worker→GPU infer 3–7 ms).
- E13 D4/§3.4/§8: drop "owner-stated, unmeasured" and the `*_owner_stated_unmeasured` test name; the frozen
  sites test pins the `SITES` rows citing the P6/P7 REPORTs (LPC's range extends past 10100, upper bound
  unmeasured — the profile's `(10000, 10100)` sits inside it); the report-refused rule stays as the generic rule.
- E11 §2 driver advertise: `.machine.ad` is in the sandbox (`_CONDOR_MACHINE_AD=/srv/.machine.ad`, LPC P2
  `transcript.txt:36,49`) and names the real node — a file read is a smaller rung than the UDP `getsockname()`.

## Verdict
**NOT CLEAN** — design findings: H2 driverless `host="driver"` refusal;
H3 nano_dy oracle unrunnable; H4 LPC DAG SERVICE nodes allowed with no rendezvous; M1 compounding/deterministic
retries; M2 same-host probe pass; M3 histogram 3.14t leg; M4 single-shot `unpack`. Exit-round: E1–E13 (H1 withdrawn).
