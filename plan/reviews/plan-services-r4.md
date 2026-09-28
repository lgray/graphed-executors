# Review r4 — `plan-services.md` (600 lines)

## Part A — delta: r3 H1 (hosting capability) + r3 E1 (dask stop)

- **H1** — D10 (L93-100) and §3.1 (L216-217, L238, L267-268) make hosting `callable(getattr(backend,
  "host_service", None))`; `submit/protocol.py` +0; m68 commit 1 says nothing under `tests/frozen` (L410). Every
  `tests/frozen` path in the plan is a new dir (m67, m68, m69a, m69b, m70, preserve/m68). Live probe: pytest plugin
  `reviews/plan_services_r4_attr_plugin.py` binds `host_service`/`release_service` as instance attributes on every
  `HTCondorBackend` (worst case), every `DaskBackend` and HTEX-only `ParslBackend`, then runs the frozen pins
  unmodified (`PATH=../.venv/bin:$PATH … pytest -p plan_services_r4_attr_plugin tests/frozen/m42/
  test_submit_protocol_conformance.py m42/test_submit_no_dask_import.py m46/test_parsl_capabilities.py
  m46/test_parsl_submit_conformance.py m66/test_htcondor_submit_conformance.py`): 47 passed, exit 0,
  `R4_BOUND [('DaskBackend', 11), ('HTCondorBackend', 11), ('ParslBackend', 7)]` (the bindings ran; m42:198 field
  tuple, m46:95 `type(caps) is SubmitCapabilities`, m66 `ALL_FALSE` import + `capabilities == ALL_FALSE`, and every
  `isinstance(…, SubmitBackend)` held).
- **Flag wording** — `grep -n "host_cluster_service\|flag-False\|D10 flag"`: 0 hits; `host_service` control: 16
  hits; the only `flag` left (L471) is the histogram `backing` row, unrelated.
- **E1** — L379-381 stop on `Event.wait(timeout)`. Re-run `probe_dask_service.py event`: `STOP_VIA_EVENT True …
  after 0.00s`, 0 `ERROR` lines in stdout+stderr. Control (same capture, one-worker LocalCluster, three misses each):
  `Variable.get(timeout=0.3)` → `['TimeoutError']×3`, 3 `distributed.core - ERROR … variable_get` lines;
  `Event.wait(timeout=0.3)` → `[False]×3`, 0 lines. The ERROR instrument is live; Event is the clean mechanism.

### Design findings

**M1 · §3.5 m70 table, `test_hosted_service_attribute.py` (L401) · the absence leg names "the process backends",
which are not backends.** The `SubmitBackend` implementations are `HTCondorBackend`, `ThreadBackend`,
`DaskBackend`, `ParslBackend` (`grep -rn "def n_workers" src/` → those four + the Protocol); the process-pool
classes are `local/executors.py` executors, and `grep -rn "ProcessPool\|PinnedPool\|_ProcessExecutorBase"
src/graphed_executors/submit/` → 0 hits (control `ThreadBackend` in `submit/threadpool.py`: 3). They never reach
`ServiceSet`, so an absence assertion on them cannot fail in a direction that matters. Closed by: the absence set
names only `SubmitBackend`s (`grep -c "process backends" plan-services.md` → 0).

### Exit-round (constraints for the dispatch; no round)
- E1 §3 m67 `sites.py` (L176-178): the new `SiteProfile` fields must be defaulted — they follow the defaulted
  `driver_ports` (a dataclass refuses a non-default after a default), and frozen m66 builds `SiteProfile` from the
  six old kwargs (`test_htcondor_sites.py::ship_site`, `test_htcondor_live_pool.py` `ci-spool`). Decided:
  `service_ports=None`, `worker_ports=None`, `services` empty — an undeclared profile makes no reachability claim
  (D4's own `None` rule → legs 1–2); the named `SITES` rows set theirs explicitly.

**Part A verdict: NOT CLEAN** — M1 (a three-word deletion). H1 and E1 from r3 are closed by probe.
### Part A′ — the 09:47 fold of part A (journal ~16:50Z)
M1 closed: the m70 row reads "absent on `ThreadBackend` and `ParslBackend(TPE)`" (`grep -c "process backends"` → 0).
E1 is folded, but the fold brought in a new defect:

**M2 · §2 `sites.py` (the `**sites.py** (+25)` paragraph) · `services=MappingProxyType({})` as a dataclass default
fails at import on CPython 3.11.** Executors has `requires-python = ">=3.11"` and CI runs 3.11 (`ci.yml:35`). Probe
(`uv run --python {3.11,3.12,3.14}`, a frozen dataclass with that default after a defaulted field):
`3.11.15 mappingproxy.__hash__ is None: True REFUSED mutable default <class 'mappingproxy'> … use default_factory`;
3.12.10 / 3.14.6 `OK`. Control: a `{}` default is refused on all three. The journal's "accepted — probed" holds
only for 3.12+. Decided: `field(default_factory=lambda: MappingProxyType({}))`. Closed by: that text on the
`sites.py` line, plus the same probe printing `OK` on 3.11.

## Part B — delta: §4 m69a "same answers as the original, on NanoEvents" (L394-468)

Checked against the owner ruling (journal 14:22Z). Holds:
- **Oracle = the original.** `data/inclusive_processor.py` is sha256-pinned, and `shasum` of `refs/hgg/` and
  `~/Downloads/` both give `791229c2…d1dd`. The file has no trailing whitespace, no CR, and ends in `\n`. The
  executors hooks are `ruff-check --force-exclude`, `ruff format --check`, and mypy, so nothing rewrites it. Real
  `higgs_dna` is installed `--no-deps`. LPC premise (`probe_hgg_original_lpc.txt`): `PINNED_MATCH True`, the
  original runs unedited, and `DEFAULT_VS_EAGER equals(check_metadata=True) True`.
- **Same ranges, 1:1.** The unmeasured premise behind "the second is empty: a zero-row part with the oracle's
  schema" was bought with `reviews/plan_services_r4_empty_range.py` (the original on the fixture, hdna.venv):
  `RANGE (100, 200) … _Events_100-200.parquet ROWS 0` and `SCHEMA_EQUAL_IGNORING_META True … NDIFF 0` against
  (0, 100) (52 rows). `aggregate_plan(…, partitions=)` exists (`graphed/python/graphed/aggregate.py:204`).
- **NanoEvents.** `from_root(…, mode="graphed")` is in the fork (`factory.py:274,411`). The witnesses are measured
  (`probe_hgg_nanoevents_witness.txt`: `GraphedNanoArray`, `metric_table`/`delta_r` True, control False, and a raw
  `uproot.graphed` `.Photon` raises), and the uproot-search control matches `make_hgg_fixture.py:3`.
- **Real data.** `validate_real.py` runs on the first GluGluH 2024 and first DataC_2024 files, with a part-by-part
  `compare_part` and "a difference is a finding, never a tolerance".
- **Comparator control.** The fixture part holds a NaN (`nans_in 1 ['TruthYH']`), so the re-read control fails a
  comparator that treats NaN ≠ NaN, and the ulp mutation fails one with a tolerance.

**M3 · §4 `test_hgg_compare.py` · two of `compare_part`'s five legs have no mutation that would catch them.** The
schema leg (types, nullability) and the validity-bitmap leg can be deleted from `compare_part` and the five
mutations plus the control still pass. Integer columns compare by value, and `np.array_equal` of int64 and int32
with equal values is True. The fixture part has no nulls (`NONEMPTY_PART nulls_in 0`), so the control never
exercises the bitmap. Part types measured: `bool, double, float, int64, uint32, uint64, uint8`. The owner ruling
names dtypes. Closed by: the mutation list adds one int column cast to a narrower width with equal values, and one
value set null. Each is caught, naming the column.

### Exit-round (constraints for the dispatch)
- E2 §4 real-data validation: the LPC premise covered only the MC file (4180 entries, 23.8 s ≈ 5.7 ms/event
  in `virtual` mode). The first DataC_2024 file's entry count and the original's data branch at LPC are
  unmeasured. `validate_real.py` prints `num_entries` before it runs and takes an `--entry-stop` cap, and the
  transcript records the ranges used.

## Verdicts
- Part A: NOT CLEAN (M1; closed in A′, M2 new from the fold). Part B: NOT CLEAN (M3); otherwise §4 meets the owner's instruction.
- **Overall: NOT CLEAN.** Two design findings, M2 and M3, each fixed by one line in the plan; E2 is exit-round.
  After a delta round that closes them, the lead's whole-artifact pass follows.
