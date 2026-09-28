# Review r2 (delta) — `plan-services.md` 594 lines: r1 repairs + constraints 10/11 (m70, ServiceSpec split, recipes, three legs)

Delta read against the r1-reviewed copy, then the 594-line state (D1 requirement/recipe split, `submit/recipes.py`,
D4 `services` kind→`host:port`, the `http_server` path with a `sys.modules` witness, the packaging grep with `recipes.py`
as positive control — constraint 11 (i)–(iii) and constraint 10 are each placed and faithful); sections touched: cut/D1–D10, §1, §2 (retries, advertise, tests), §3.1–3.5,
§4 (m69a), §5 (m69b), §6–§9. r1 rulings verified in place: H2 (Popen in the driver job, `test_driverless_services.py`),
H3 (derived v15 fixture: `fixtures/nano_hgg_v15.root` 2.36 MB, `jetid_2024_Summer24.json.gz` 942 B, `run_oracle.txt`
nTot 200 / 52 rows / both KV keys — matches §4), H4 (refusal keyed on `DagmanProfile.dag_root`), M1 (exit 0/3/1,
`retry_until=3`, one retry owner; JDL integer semantics hold), M2 (`not_on_host` lease + bounded resubmits), M3
(histserv extra off 3.14t, `test_histserv_available.py` on `sys._is_gil_enabled()`), M4 (pure `unpack`, delete on
`close`), E1–E13. New premises probed and holding: `DurablePlan.to_bytes` is sorted-key JSON of a dict
(`core/plan.py:195-209`), so an omitted key is byte identity; the `"variations"` idiom (`bundle.py:267`) and the
manifest dict (`:269-279`); `attach_run_report` (`bundle.py:107`) with m65c `test_m65c_bundle_reports.py` present;
`RunReport.from_json` checks only `version` (`report.py:88`); `Session._externals` registry + `sources()` view
(`session.py:34,232`); dask `workers=` → `allow_other_workers=False` (`dask_backend/backend.py:83-84`); parsl
`_open_driver_endpoint` (`transport_peer.py:334`, `HOST="127.0.0.1"` `:40`); `EscalatingHttpTransport(…, epoch=)`
(`common/http_plane.py:99-108`); the task server's `lease(pilot)` sees the pilot id, so a host filter is one
comparison (`server.py:186`); both probe transcripts say what §3.5 quotes (dask announce 0.1 s, cancel empties
`processing`; parsl announce 1.3 s, `cancel()` local-only, stop-by-message 0.1 s).

## Design findings (ranked)

**H1 · §3.1 `submit/protocol.py` · two new Protocol members break three frozen conformance pins.** `SubmitBackend` is
`@runtime_checkable` (`protocol.py:45-46`) and `isinstance(backend, SubmitBackend)` is asserted in frozen
`m42/test_submit_protocol_conformance.py:166`, `m46/test_parsl_submit_conformance.py:67` and
`m66/test_htcondor_submit_conformance.py:92`. Adding `host_service`/`release_service` to the Protocol (L219-221) makes
every backend that lacks them fail `isinstance` at m68 — the plan implements them on condor only (dask/parsl wait for
m70; `ThreadBackend`/process backends never) — so the m42 and m46 frozen suites go red on the m68 PR, and frozen
tests cannot move. Closed by: the two methods are duck-typed behind the flag, like `site_services`/`advertise_host`
already are in §3.1 (rung 2, no protocol change), or every backend gains a refusing implementation in m68 commit 1
(named in the file table). The check: m42/m46/m66 conformance green on the m68 PR with no edit under `tests/frozen`.

**M1 · §3.1 `probe` · `workers=` is overloaded as an anti-affinity.** The protocol's `workers: Sequence[str] | None`
(`protocol.py:63`) is a strict affinity list (dask forwards it as `workers=[…], allow_other_workers=False`); L243-245
route `not_on_host=<service host>` "through `backend.submit(..., workers=)`", which on dask would pin the probe TO the
named host and on condor needs a pilot list the protocol does not expose (`n_workers()` only). Closed by: the
anti-affinity is its own advisory kwarg on `submit` (dropped like `resources` on backends without placement; the
condor lease filter and the bounded resubmits stay), so the dask/TaskVine seam is untouched; `test_services_protocol.py`
shows the dask-shaped fake receives no `workers=` for the probe.

**M2 · §3.1 driverless DAG · the in-job `ServiceSet` re-hosts a SERVICE-node service.** L271-275: `driver.py` runs
`ServiceSet` over `plan.services` inside the driver job, and a cluster-hosted recipe is also a DAG `SERVICE` node
announcing to that driver. Nothing tells the in-job leg 3 that the spec is already hosted, so it calls
`host_service` again (a second `ServiceJob` from the job — refused at LPC by P2, a duplicate server at lxplus/generic)
or, if refused, fails a run whose service is up. Closed by: `run.json` names the DAG-hosted specs and the in-job set
treats them as announce-only (`wait_announce`, no submit); `test_driverless_services.py`'s DAG case asserts one
service cluster in history and `driver.log` shows "waiting for announce", never a submit.

**M3 · §3.5 m70 · the dask announce plane needs worker→driver reachability the plan does not state, and a smaller rung
exists.** L366-368 open a driver `EscalatingHttpTransport` for "a flagged backend with no announce route of its own";
dask has one: `distributed.Variable`/`Queue`/`Event` (importable, distributed 2026.8.0) are scheduler-mediated, reach
the driver through the connection workers already hold, and carry the stop the same way (rung 4). The probe measured a
`LocalCluster` where the driver listener is loopback; on a real cluster the client host is not always dialable from
workers, and §9 names that ceiling for parsl only. Closed by: dask announces/stops over a `distributed` primitive
keyed by the service nonce (the parsl plane stays, it has nothing else); `test_dask_hosted_service.py` asserts no
driver listener is opened for dask (the transport spy sees zero `EscalatingHttpTransport` constructions).

**M4 · §3.1 `ServiceJob` / `recipes.py` / §5.1 · python recipes bake the driver's interpreter and ship no environment.**
`http_server` (L224-225) and `histserv_spec` (§5.1 ladder) put `sys.executable` — the driver's path — into the spec's
argv, and `ServiceJob` (L257-263) transfers `graphed-secret,announce.py` + the recipe's `inputs`, never `env.tgz`.
A cluster-hosted python recipe therefore runs only where the job shares the driver's filesystem (minicondor, so
`test_services_live (a)` passes) and cannot start at lxplus, where `service_hosts=("cluster",)` routes histserv to a
`ServiceJob` inside the coffea image with no histserv installed. Closed by: a `{python}` argv template rendered in
`service.sh` the way `pilot.sh` resolves its interpreter (untar `env.tgz` when present), `ServiceJob` shipping
`env.tgz` when the recipe has no `image`, and recipes using `"{python}"` not `sys.executable`;
`test_services_sites.py` renders a `{python}` recipe to the job-side path and shows `env.tgz` in the description
for an image-less recipe, absent for an image one.

## Exit-round (constraints for the dispatch; no round)
- E1 §3.2 `test_bundle_without_services_unchanged.py`: "the eight 0.0.6 keys" — the manifest has nine
  (`bundle.py:269-279`); state the key set, not a count (the ten `to_bytes` keys are right).
- E2 §3.5: `advertise_host` is defined for condor and `ThreadBackend` only; say what dask and parsl answer (the
  loopback rule then decides whether the probe runs on each).
- E3 D6/§2: exit 3 covers `StageError`/`ValueError` — a `ValueError` from a bad `run.json` is infrastructure; name the
  plan-error set by exception origin (raised inside `run()`), not by type.
- E4 §3.4: closed by the 594-line state (`recipes.py` is the grep's positive control; `http_server` carries the
  `sys.modules` witness).
- E5 §4: `data/` holds the 2.36 MB fixture; §7 counts m69a fixtures at ~1.8k lines — say the binary size once so the
  repo-size trade is explicit (or prune, as `make_hgg_fixture.py` can).

## Verdict
**NOT CLEAN** — design findings: H1 Protocol members vs frozen `isinstance` pins; M1 `workers=` overloaded as
anti-affinity; M2 in-job `ServiceSet` re-hosts the DAG SERVICE; M3 dask announce plane (reachability premise +
smaller rung); M4 python recipes bake `sys.executable`, `ServiceJob` ships no env. Exit-round: E1–E3, E5 (E4 closed).
