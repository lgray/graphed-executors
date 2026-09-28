# Review r5 — `plan-services.md` (600 lines)

## Part A — delta: r4 M2, M3, E2

- **M2 closed.** §2 `sites.py` (L161-163) now reads `services=field(default_factory=lambda: MappingProxyType({}))`.
  Probed with `uv run --python {3.11,3.12,3.14}`, a frozen dataclass with `driver_ports` defaulted and then the
  three new fields: `3.11.15 OK mappingproxy`, `3.12.10 OK`, `3.14.6 OK`. Nothing hashes a `SiteProfile`
  (`grep lru_cache|hash(|frozenset(` over `htcondor_backend/` and frozen m66 finds none).
- **M3 closed.** The mutation list (L446) now includes int64→int32 and one value nulled. Probe
  `reviews/plan_services_r5_compare_legs.py` builds `compare_part` from the L435 text (legs: counters, schema,
  names, validity, values, kv), deletes one leg at a time, and runs the re-read control plus the seven mutations on
  the fixture's (0, 100) oracle part.
  - With a non-empty assertion only: deleting `schema` misses `int64->int32`, and deleting `validity` misses
    nothing, because the values leg's length catches the null.
  - With each mutation asserting its own leg's entry: `DELETE schema missed ['swap', 'int64->int32']`,
    `DELETE validity missed ['null']`, `DELETE values missed ['ulp']`, `kv → ['kv']`, `counters → ['counter']`,
    and `(none) → []`.
  - The plan's "naming the change" carries this; see constraint C1.
- **E2 closed** (L452-455): `num_entries` is printed and `--entry-stop` caps the range. **Part A: CLEAN.**

## Part B — whole-artifact pass

### Unit §4 (m69a)
Checked against the owner's instruction and brief constraint 7.
- The oracle is the byte-identical original (sha256, r4) with real `higgs_dna` (LPC premise measured); ranges are
  1:1 with a comparator non-vacuous per leg (Part A); NanoEvents witnesses are measured; `validate_real.py` runs on
  the first GluGluH 2024 and DataC_2024 files; products are kept; no graphed change is needed.

Premises bought this round:
- Explicit `Partition` ranges through `aggregate_plan(partitions=)` drive coffea `mode="graphed"` reads
  (`reviews/plan_services_r5_partitions.py`). Per-range output `(100, 35017.0, 169)` and `(100, 35017.0, 133)`
  equals eager uproot on the same ranges (`EAGER (0, 100) … 169.0`, `(100, 200) … 133.0`). `nPhoton` tells the
  ranges apart.
- The data fixture's MET filters (`flashggMetFilters["data"]`) are all present in the MC fixture's branches
  (`DATA_FILTERS_MISSING_IN_FIXTURE []`), so the `--data` builder needs no new branches. The data-branch rows are
  pinned at freeze, and freeze is where a failure would surface.

Frozen files carry witnesses; commit bands ≤1.2k. **§4 verdict: CLEAN** (constraint C1 goes to the test author).

### Unit §1–3, §5–9 (services)
Cited code checked live:
- In graphed-executors: `_open_driver_endpoint`, `transport_peer.HOST`, `EscalatingHttpTransport`,
  `_require_importable`, `LocalPilots`, `TaskServer.lease`, and the dask pin path (`backend.py:83-84`).
- In graphed: `record_external` (both the session method and the `preserve.externals` export),
  `Session._externals`/`sources()`, `attach_run_report`, `_render_run_reports`, `_PartitionReduce`, and the
  `execute.py` External dispatch.
- In graphed-histogram: `_refuse_shortfall` (`boost.py:927`).
- The manifest key set is the plan's nine (`bundle.py` `manifest = {…}`), and `DurablePlan.to_bytes` has ten keys.
- `Histogram.__init__(*axes, storage, metadata)` has no `backing` yet, which matches the §5.1 addition.

**M4 · D4 + §3.4 · two frozen m68 pins forbid the site row that D4 and brief #11 plan to add.** D4 (L53-54) leaves
the LPC `services` EAF Triton row (`"triton": "<host>:<port>"`) for the owner to add to `SITES` in
`htcondor_backend/sites.py`. Brief #11 names exactly that as leg 2. But:
- `test_services_sites.py` (L336) pins `SITES` rows with "`services` empty".
- `test_services_packaging.py` (L341) pins `grep -rc "triton\|histserv"` over `htcondor_backend/` at 0.

Both are frozen, so the owner's row would fail two tests that nobody may edit. The control is live: `grep -rniE
"triton|histserv" src/graphed_executors/htcondor_backend/` → 0 today, while `sites.py` holds `SITES`.
Closed by: the sites pin covers only the measured D4 fields (`service_ports`, `worker_ports`, `service_hosts`) and
leaves `services` as data; the grep covers code files and excludes `sites.py`. Check: neither frozen row names
`services` empty for `SITES`, and the grep list does not include `sites.py`.

**M5 · §3.2 `graphed/services.py` + `debug/report.py` · mapping literal defaults on frozen dataclasses fail at
import on every Python version.** This is the second instance of r4 M2's shape. Cause: a dataclass field default
is written as a mapping literal. Three instances:
- `Launch(…, env: Mapping[str, str] = {}, resources: Mapping[str, float] = {})` (L279).
- `RunReport.endpoints: Mapping[str, str] = {}` (L303-304). `RunReport` is `@dataclass(frozen=True)`
  (`report.py:50`).

Probe (lane venv, py3.12): `@dataclass(frozen=True) class Launch: … env: Mapping[str, str] = {}` →
`LAUNCH REFUSED mutable default <class 'dict'> for field env is not allowed`. r4's probe refused `{}` on
3.11/3.12/3.14.

The `ServiceSet(…, endpoints=… = {})` function default at L217 is not an instance: `ruff --select B006` passes.
Decided (the cut is at the cause): every mapping default on a dataclass in this plan is
`field(default_factory=…)` (the M2 form). Closed by: L279 and L303-304 name `default_factory`, and
`grep -n "Mapping\[[^]]*\] = {}"` hits only L217 (the function default).

**M6 · §7 order · m69b depends on m69a, but the order omits it.** Executors m69b "adds to `examples/hgg/`" (L522),
and `test_hgg_diagnostics.py` uses the m69a `data/` and runs in the `test-hgg` job (L537). All three arrive only
through m69a's PR against `main`. m69b stacks on `lane/htcondor`, and L563-565 orders m69a only as "start now".
Closed by: the order line states that m69a is merged into `main`, and `main` merged into the stack, before
executors m69b.

**Services verdict: NOT CLEAN** (M4, M5, M6; each is a one-line plan edit with the decision given above).

## Exit-round (constraints for the dispatch)
- **C1 (§4 `test_hgg_compare.py`).** Each mutation asserts its own leg's entry: validity for the null, schema for
  the narrowing and the swap, values for the ulp, and so on. A non-empty result alone does not show the validity
  leg is needed (Part A probe).
- **C2 (§3.1 ladder L197).** The row reads "leased away from the service's host", but the body (L231) says "no
  placement kwarg, no lease filter". The body wins.
- **C3 (D1 L14).** The field list omits `timeout_s`, which §3.2 L280 defines and §3.1/§3.5 use.
- **C4 (§3.4/§7).** The m68 freeze commit(s) have no stated size, while ~2k test lines sit across frozen and
  extra. The test author keeps each freeze commit ≤2k.

## Overall
Part A is CLEAN. Unit §4 (m69a) is CLEAN. The services unit is NOT CLEAN on M4, M5, and M6. **Overall: NOT
CLEAN.** m69a can be dispatched on its own verdict.
