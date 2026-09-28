# Review r3 (delta) — `plan-services.md` 600 lines: r2 repairs (H1, M1–M4, E1–E5)

Delta read at the r2 anchors and what they reference. Closed and verified: **M1** — the probe is an ordinary
`backend.submit` returning its hostname, resubmitted until another host answers, bounded, fails closed (L240-246);
`not_on_host` has zero hits in the plan and `workers=` appears only as the dask actor's genuine affinity pin (L377)
and the probe transcript quote (L113). **M2** — `run.json.announce_only` (L153, L277) and the spy leg in
`test_driverless_services.py` (L360: zero `host_service` calls for a DAG-hosted name). **M3** — dask announces and
stops over `distributed.Variable` (L98, L379-385), the engine announce plane is gone, parsl keeps its HTTP plane
with the ceiling in §9; re-run `probe_dask_service.py variable` (distributed 2026.8.0, LocalCluster 2×1):
`VARIABLE_ANNOUNCE_FROM_PINNED_WORKER True … after 0.0s, no driver listener`,
`OTHER_TASKS_RAN_ELSEWHERE_WHILE_VARIABLE_SERVICE_HELD True`, `STOP_VIA_VARIABLE True … after 0.0s`. **M4** —
`{python}` argv placeholder (L19, L222, L471) rendered as `./env/bin/python` in `service.sh`, which is exactly
`pilot.sh`'s resolution (`launch.py:197,200`), `env.tgz` shipped on `ship_env` profiles iff the recipe has no
`image` (L257-262; `SiteProfile.ship_env` is a real field, `sites.py:31,48,64`), pinned in `test_services_sites.py`
(L357). **E1** key set not count (L329); **E2** `advertise_host` per backend (L241-242); **E3** exit 3 by origin
(L156); **E4** closed in r2; **E5** fixture size stated once (L443, L557).

## Design findings

**H1 · §3.1 `submit/protocol.py` (+2) · the flag as a `SubmitCapabilities` field breaks three frozen pins.** The
r2 ruling moved `host_service`/`release_service` off the Protocol, but `host_cluster_service: bool` is still added
to `SubmitCapabilities` (L216-218), and L409 claims "m42/m46/m66 conformance untouched and green". Frozen:
`m42/test_submit_protocol_conformance.py:198` asserts `tuple(f.name for f in dataclasses.fields(SubmitCapabilities))
== FLAG_NAMES` (the seven names, `:54-61`); `m46/test_parsl_capabilities.py:88-96`
(`test_capability_fields_are_exactly_the_frozen_seven`, docstring "No new capability field, ever … dispatch goes
through a backend attribute, never capability fields") asserts the same tuple and `type(caps) is
SubmitCapabilities`; `m66/test_htcondor_submit_conformance.py:38-46` builds `ALL_FALSE = SubmitCapabilities(<seven
kwargs>)` at import — a required eighth field is a `TypeError` for the whole module, a defaulted one still fails
`:198`/`:95` and `:93` (`backend.capabilities == ALL_FALSE`) wherever the condor backend reports `True`. An eighth
field is unreachable without editing frozen tests. Closed by: the capability is the backend attribute the m46
docstring names — hosting iff `getattr(backend, "host_service", None)` is callable (the m47 transport-dispatch
precedent), `SubmitCapabilities` untouched, D10 and `test_hosted_service_flag.py` reworded to that attribute
(`hasattr` on Thread/TPE False, dask/HTEX/condor-with-cluster True), and the m42/m46/m66 suites green on the m68
PR with no file under `tests/frozen` in the diff.

## Exit-round (constraints for the dispatch; no round)
- E1 §3.5 dask stop: the actor "polls `Variable(stop)`" — each `get(timeout=…)` miss logs
  `distributed.core - ERROR - Exception while handling op variable_get` on the scheduler (seen in the re-run's
  stderr, 8 lines for one hold); `distributed.Event.wait()` blocks without the per-poll error, or the poll catches
  `TimeoutError` at a coarse interval. Either keeps the measured mechanism.

## Verdict
**NOT CLEAN** — design finding: H1 the flag field vs the frozen seven-field pins (m42:198, m46:95, m66:38/93).
Exit-round: E1. Everything else from r2 is closed in the delta.
