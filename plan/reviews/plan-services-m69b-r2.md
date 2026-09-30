**NOT CLEAN**

# Review m69b-r2: delta pass (b21f1b7 → dc66fe0)

## Scope
- **Snapshot:** `reviews/plan-services-m69b-r2-snapshot.md` (= `plan-services.md` at dc66fe0).
- **Delta read:** `git diff --word-diff b21f1b7 dc66fe0 -- plan-services.md`, plus the lines it references: §5.1,
  §5.2, D2 leg 3, §7, §9. Also read: `probe_merged_leaves.{py,txt}`, `run_memory_probe.sh` and both
  `probe_histserv_memory*.txt`.
- **Code:**
  - graphed d0ad16b: `aggregate.py` (`aggregate_plan`, `_PartitionReduce`, `collate`) and `services.py`
    (`require_bound`, `Bindable`).
  - graphed-histogram 4c4b79f: `boost.py`, `_spec.py`, and frozen m48/m49.
  - executors db8fb0a: `htcondor_backend/{backend,sites}.py`, `submit/services.py`, `examples/hgg/analysis.py`,
    `tests/frozen/m69a/*` and `ci.yml`.
  - `graphed_orchestrator/precommit.py`.
- **New probes:** `probes/m69b/*_rv2.{py,txt}`. `probe_context_scope_rv2`, `probe_positions_reuse_rv2` and
  `probe_m69a_each_rv2` ran in `graphed-histogram/.venv`, read-only; `probe_m69a_each_rv2` loads coffea's
  `accumulator.py` by path. `probe_overhead_row_rv2` ran in `python:3.1x-slim` (amd64, emulated). No container or
  histserv process remains: `docker ps -a | grep -c m69b` → 0, `pgrep -fl histserv` → none.

## R1 findings under the owner's rulings
- **R1-1: closed.**
  - The shared-endpoint refusal is gone from `bind_services` and from "What the context guarantees".
  - `require_bound`'s last pass maps every server to `tcp://unbound:0`, then raises `UnboundService(*sorted(missing))`.
    `names` is therefore every server (`services.py` `require_bound`).
  - The lazy-init row now uses ≥ 2 servers. The fill-path row runs two names on one endpoint.
- **R1-2: closed (ruling 2).**
  - The fixup's description matches the frozen file: `value == expected` (L80) and the leaf-type map over `value[ds]`
    (L81–82).
  - `--allow-refreeze PREFIX` exists (`precommit.py` `--allow-refreeze`, `action="append"`).
  - `freeze-m67-fixup` is annotated, and `.graphed/<m>/disputes/*.md` has precedent (m65, m67).
  - `test_each_dataset_run_on_its_own_collects_into_the_same_product` needs no change. It uses the same mechanism:
    collate + `SequentialRunner` against per-dataset plans on `ThreadBackend(2)`, coffea's `accumulate`, two
    partitions per dataset, lognormal × random-sign float32 weights on Weight histograms. Measured:
    `probe_m69a_each_rv2.txt` → `collected == one: True`; control, one bin changed → `False`. With two partials per
    dataset, every combine order gives the same bits.
  - The other m69a files read no analysis value.
- **R1-3: closed at the read** (`probe_merged_leaves.txt` B, counter first and counter last). Two defects sit around
  the repair; see R2-2 and R2-3.
- **R1-4: closed by ruling 4.** No count cap is added.
- **R1-5: closed.**
  - The template is built from extents.
  - `probe_standin_axes_rv1.txt` covers StrCategory overflow (axis mode), IntCategory overflow and Boolean
    (siblings): all `equal_to_local=True`.
  - `gh.boost` records all seven storages (`_spec._STORAGES`), so the `Mean`/`WeightedMean`/`Unlimited`/`AtomicInt64`
    refusals can be reached.
  - Transform, circular and category `overflow=False` are refused by `gh.boost` itself (`_axis_spec`).
- **R1-6: repaired as ruling 6 says, but the repair has no scope.** See R2-1.
- **R1-7: closed (ruling 7).**
  - Eight `MODEL` lines, 3.11–3.14 × arm64/amd64.
  - Maxima: B = 129 MiB, O = 4000 B, I = 160 B, a = 5.5, b = 3.0.
  - The new O sub-row is looser than §9 and the "Fails on" list claim. This is exit item 1.

## Design findings

### R2-1 — the shared-context rule has no scope, and the frozen rows collide under the natural reading
- **Where:**
  - §5.1 "Surface": "a second context under a used `name` with equal arguments shares the first's servers and
    packing state and warns …, with other arguments is refused naming both".
  - The rows that build contexts: `test_histserv_packing.py` (every row), `test_histserv_fill_path`, `retries`,
    `lazy_init`, `composition`, `memory_model`, and executors `test_histserv_managed`, `test_histserv_cluster`,
    `test_hgg_diagnostics` ("the one-worker context run" and `ThreadBackend(3)`), `test_hgg_live_pool`.
- **Why it changes code:** the implementer must decide when a name stops being "used". The test author never talks
  to the implementer, and writes rows that build many default-name contexts in one pytest process. Under each
  reading, something breaks:
  - **Process lifetime.** This is what "used" says literally.
    - The packing row's monotonicity sweep over `workers` and `memory_mb` is refused as "other arguments".
    - An earlier test's equal context shares its packing, so the row "slots … land on the expected servers" depends
      on test order.
    - The same goes for executors rows "sized to two servers" that name `histserv-0/1`.
  - **Weak reference.** The outcome depends on whether some traceback, fixture or reference cycle still holds the
    first context.
- **Measurement:**
  - The plan never states the scope: `grep -n "used \`name\`\|registry\|lifetime\|alive\|in one process\|packing
    state" plan-services.md` matches only the Surface sentence (L925–926) and unrelated lines outside §5.
  - `python3 probes/m69b/probe_context_scope_rv2.py` implements the stated rule with the name held for the process:
    ```
    placement test alone:               {'a': 'histserv-0', 'b': 'histserv-0', 'c': 'histserv-1'}
    placement test after an equal one:  {'a': 'histserv-1', 'b': 'histserv-0', 'c': 'histserv-0'}  (same as alone: False)
    monotonicity sweep workers=2: ValueError: context name 'histserv' is used with (100, 1), not (100, 2)
    ```
- **Shape** (shared with R2-3): the rule holds plan-time state on an object that outlives the plan it describes. Each
  such state needs a stated scope. The packing state is shared across plans by design (ruling 6), so it needs a
  lifetime. A pieces' positions belong to one compile.
- **Closed when:** the plan states when a name is used, and the frozen rows are written against that choice. Either:
  - (a) process lifetime: every row that is not about sharing passes its own `name`, and the executors'
    `workers=1`/`workers=3` hgg contexts are named apart. A user gets fresh packing by using a fresh name. Or:
  - (b) the name is used while a context holding it is referenced, and the context holds no reference cycle, so
    CPython drops it at the last reference.
- **Test:**
  - A packing row pins the chosen scope:
    - Under (a): a later test's `Context(name=n, memory_mb=m2)` after an earlier `Context(name=n, memory_mb=m1)` is
      refused.
    - Under (b): after `del ctx`, with no `gc.collect()`, a context with other arguments under that name builds.
  - The sharing clause asserts the second plan's slot → server map: the slot that no longer fits lands on a server
    the first plan does not declare.
  - The same clause recomputes each shared server's prediction from both plans' maps. A check that reads
    `ctx.servers()` alone would pass on an implementation that does not share.

### R2-2 — a backed `gh.plan` still refuses an optimizer merge (ruling 3)
- **Where:** §5.1 `boost.py`: "`gh.plan` keeps 0.0.4's code path and its merge refusal (frozen m48/m49); a backed
  `gh.plan` refuses the same way, then builds from `pieces` and serves" (L984–985).
- **Why it changes code:**
  - Ruling 3 prefers keeping backed histograms apart to refusing them.
  - The frozen refusal (m48 H5, m49 `test_merge_shortfall`) pins only `gh.boost` histograms; no backed histogram
    exists there.
  - A backed `gh.plan` already builds from `pieces`, whose position read handles the merge. So refusing first is a
    line the implementer writes against the ruling.
  - The §9 owner item on reading merged fills is needed only for the unbacked `gh.plan`.
- **Measurement:**
  - `grep -rn "histserv\|backed" tests/frozen/m48 tests/frozen/m49 | wc -l` → `0`.
  - Control: `grep -rn "gh.plan" tests/frozen/m48/test_optimizer_merge_guard.py tests/frozen/m49/test_merge_shortfall.py
    | wc -l` → `6`.
  - `probe_merged_leaves.txt` B: `fill positions [1, 1] counter [0]; … values equal=True variances equal=True`, and
    the same with the counter last.
- **Closed when:** a backed `gh.plan` builds from a fresh `pieces` with no shortfall refusal, and the unbacked
  `gh.plan` keeps it (m48/m49 untouched).
- **Test:**
  - `test_pieces_composition.py` (or the surface row): `gh.plan({"h": backed})` of the probe's merged fills
    (`weight=[w]`, `weight=[w * 1.0]`), served and run, equals a direct boost fill done twice (values and variances).
  - Control: `gh.plan` of the unbacked twin still raises the `GraphedError`.

### R2-3 — one `pieces` compiled into two plans re-points the first plan's reads
- **Where:** §5.1 `boost.py`: "`pieces.on_compiled` records on `pieces.reduce` each marked fill's compiled position"
  (L977).
- **Why it changes code:**
  - `aggregate_plan` puts the reduce into the plan's `_PartitionReduce` by reference and calls `on_compiled` once
    per build (`aggregate.py` `aggregate_plan`). A second `aggregate_plan` with the same pieces therefore overwrites
    the positions the first plan reads.
  - This happens, for example, with a plan with `writes` and one without, or with a different set of its own
    outputs. The first plan then reads a counter as a fill (a loud failure). If the second composition permutes
    same-spec fills, it reads another histogram's fill without error.
  - "A plan served twice" is refused, but its compile-time twin is not.
- **Measurement:** `python probes/m69b/probe_positions_reuse_rv2.py` →
  ```
  A positions after building the counter-first plan: fills [1, 1] counter 0; after building a counter-last plan with the same pieces: fills [0, 0] counter 1
  A the counter-first plan run afterwards: AttributeError: no field named 'copy'
  ```
- **Closed when:**
  - A pieces' `on_compiled` refuses a second firing, naming `pieces`. One pieces per plan, the same invariant as the
    double-serve refusal.
  - The backed `gh.plan` (R2-2) builds a fresh pieces per call.
- **Test:** add to `test_pieces_composition.py`: a second `aggregate_plan` over the same pieces raises naming
  `pieces`. The first plan, run afterwards, still equals the direct fill.

## Checked and holding (the delta)
- **Compiled positions.**
  - `node_map[id][0]` into `outputs()` order is the same read `aggregate_plan` uses for its own `writes` slots.
  - With `writes`, the reduce receives `values[:n_values]` followed by the paths. Fills are outputs, so their
    positions stay below `n_values`, and hgg's `Counters` keeps reading `values[:k]`.
  - Under `collate`, each sub-plan's process keeps its own reduce.
  - `_variation_labels` on a varied histogram with merged fills returns normally (`probe_positions_reuse_rv2.txt` B:
    `3 marked, 2 compiled; … tuple of 10 keys`).
- **Equal contexts across two plans and a collate.**
  - `collate` unions equal specs by name, refuses unequal ones, and sorts (`collate`).
  - Equal arguments give equal specs, and `workers` is not in the spec.
  - The warning fires at construction, in program order.
- **`service_hosts`.**
  - `SiteProfile.service_hosts` is a property derived from `service_ports`/`worker_ports`.
  - `HTCondorBackend.__init__` copies it when attached, before `TaskServer(...)` and `launcher.start`.
  - `_managed` reads `"driver" in hosts`, and the attachment reads `"cluster" in self.service_hosts`, so a narrowed
    tuple works with no other change.
  - `htcondor_runner` builds `HTCondorBackend(pilots, n_pilots, host=, port_range=)`, so the kwarg threads through
    in one line.
  - `generic` offers both hosts and `lxplus` has `service_ports=None`, so the cluster row's three legs are
    constructible and the refusal precedes any pilot.
- **CI.** `test-hgg` installs `HISTOGRAM` (`ci.yml`), and §6 adds `histserv` to it.
- **New frozen clauses fail in the direction they guard:**
  - Merged fills with the counter first or last: a static rank reads the counter, and a dedup reads once.
  - ≥ 2 names on one endpoint: a restored refusal raises at the hand bind.
  - Category and Boolean accepted.
  - The `service_hosts` legs.
  - The no-context hgg row: `services == ()`.
- **Commit totals.** They match §7: histogram ~660 src / ~2.4k tests; executors ~20 src / ~1.3k tests.
