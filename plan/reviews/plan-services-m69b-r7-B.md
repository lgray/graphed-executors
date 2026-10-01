DELTA: CLEAN
WHOLE: CLEAN

# Review m69b-r7, unit B: delta (e23af1c → f61d22c) and whole-part pass of §5 opening, §5.1, §5.2

## Scope
- **Snapshot:** `reviews/plan-services-m69b-r7-B-snapshot.md` (= `plan-services.md` at f61d22c).
- **Delta:** `git diff e23af1c f61d22c -- plan-services.md`, one clause of the frozen `test_histserv_fill_path.py` row.
- **Whole part:** §5 opening, §5.1, §5.2, and the D1/D2/D8, §1, §6–§9 lines that bind them; prior unit-B reviews
  (r1–r4, r5-B, r6-B) and `m69b-exit-items.md` read as context.
- **Code (read-only):**
  - graphed d0ad16b: `services.py`, `aggregate.py` (`_PartitionReduce`, `aggregate_plan`, `_Collated`, `collate`),
    `session.py` `declare_service`;
  - graphed-histogram `4c4b79f` via `git show`: `boost.py`, `_spec.py`, `pyproject.toml`, `ci.yml`, frozen m48/m49;
  - executors `upstream/main` db8fb0a: `submit/{services,engine}.py`, `htcondor_backend/{backend,services,sites,announce}.py`,
    `examples/hgg/analysis.py`, frozen m68a (`test_services_packaging.py`, `services_harness.py`), frozen m69a,
    `ci.yml`, and the test-htcondor log of run 36731794292 (db8fb0a);
  - histserv 0.2.1 in `.venv-m69b` (`__main__.py`, `server.py`), PyPI metadata for histserv, grpcio, grpcio-tools,
    numcodecs, graphed-executors, hist.
- **Probes:** none new. One `python -c` import check in both venvs (exited); no process or container left running.

## Part 1: delta
**R6B-1 is closed.** The clause now reads "each 10⁴-bin local twin's histogram pickles over 64 KiB".
- Every backed storage's 10⁴-bin twin clears 65 536 B (`probe_twin_pickle_rv6b.txt`):
  - `Double`: 80 350 B;
  - `Int64`: 80 349 B;
  - `Weight`: 160 364 B, more with a variation axis.
- The 100×100 layout clears it too: 83 596–166 827 B.
- Receipts stay under 1 KiB (280–381 B, `probe_receipt_length_rv5b.txt`).
- The pair still discriminates. A histogram riding the tree fails "under 1 KiB" by more than 64×.

No other line of `plan-services.md` changed.

## Part 2: whole part
### Prior findings
R1-1…R1-7, R2-1…R2-3, R5B-1…R5B-3 and R6B-1 stay closed. The read found no regression.

### Checked and holding
- **Bind, require and resolve chain (graphed d0ad16b).**
  - `require_bound` loops on `UnboundService` with `tcp://unbound:0` placeholders, then raises naming every name.
    That is the `names` clause.
  - `_Collated.bind_services` binds each sub-process through `bind_externals`, and `_Collated.resolve_services`
    forwards per name. So a collated set of `_Served` plans binds and resolves per dataset.
  - `collate` merges equal specs by name and refuses an unequal one. Every server spec of one context is equal
    across plans.
  - `session.declare_service` accepts an equal re-declaration.
  - The engine:
    - builds `ServiceSet(plan.services, …)`;
    - binds before the broadcast;
    - pickles the process in the driver (`_fingerprint` → `backend.broadcast`);
    - calls `resolve_services(bound, value)` while the set is open.
- **Placement (§5.2).** It narrows the tuple that `_managed` and `host_service` already read.
  - `_managed` reads `backend.service_hosts`, defaulting to `("driver",)`.
  - `HTCondorBackend` attaches `host_service` only when `"cluster" in self.service_hosts`.
  - The refusal sits before `TaskServer(...)` and `launcher.start(...)`, so no pilot is submitted.
  - `ServiceJob` sets `request_memory` from `resources["memory_mb"]`.
  - On the cluster side, `announce.py`'s `free()` skips a port the task server or an earlier histserv holds.
- **Composition with m69a.**
  - `aggregate_plan(writes=)` hands the reduce the outputs' distinct values, then the paths. `Counters` zips the
    leading values, so marking counters first keeps m69a's counters and parts.
  - `test_hgg_conversion.py` is the only frozen m69a file that reads a plan's value.
  - The diagnostic columns `mass`, `pt`, `lead_pt`, `sublead_pt`, `lead_eta`, `sublead_eta`, `n_jets` and `weight`
    exist in the original's flat parquet (`diphoton_to_ak_array`).
- **The m48/m49 refreeze.**
  - The named tests exist at 4c4b79f. `freeze-m48-fixup` exists; `freeze-m48-fixup2` and `freeze-m49-fixup` are free.
  - `precommit --allow-refreeze` exists (`graphed_orchestrator/precommit.py`).
  - "Exactly twice `_single()`'s" holds in IEEE arithmetic, because doubling and the fold commute exactly.
- **CI legs.**
  - histserv 0.2.1 needs `hist>=2.9.0`, `boost-histogram>=1.7.1`, `grpcio`/`grpcio-tools>=1.7x` and
    `numcodecs>=0.13.1`. All have cp311–cp314 wheels for linux x86_64/aarch64, macOS universal2/arm64 and win_amd64.
    numcodecs 0.17 needs Python ≥ 3.12, and 0.16.5 covers 3.11. grpcio has no cp314t wheel, which matches the
    `.[dev]` 3.14t leg.
  - graphed d0ad16b is version 0.0.6. PyPI graphed-executors 0.0.4 (histogram CI's `EXECLOCAL`) needs
    `graphed>=0.0.6`, so the git pin resolves.
  - `import graphed`, `graphed.services`, `graphed.aggregate` and `graphed_histogram.boost` leave `grpc` and
    `histserv` unimported. As a control, `import histserv` loads both.
  - Windows histserv start-up stays the §9 risk the plan names. histserv 0.2.1 has no Unix-only construct: a grep
    for `resource`, `signal`, `fcntl`, `/proc`, `uvloop` and `fork` finds none.
- **Commits.**
  - histogram: refreeze ~120, freeze ~1.3k, then ~850, ~910 and ~350.
  - executors: ~40, ~850, ~170, ~450 and ~400.
  - Every commit is ≤ 2k.

## Design findings
None.

Three exit items are appended to `m69b-exit-items.md` under `## r7-B`.
