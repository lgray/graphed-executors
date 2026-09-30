**NOT CLEAN**

# Review m69b-r3: delta pass (75ccd35 → 4e825e8)

## Scope
- **Snapshot:** `reviews/plan-services-m69b-r3-snapshot.md` (= `plan-services.md` at 4e825e8).
- **Delta read:** `git diff --word-diff 75ccd35 4e825e8 -- plan-services.md`, plus the lines it references: §5.0,
  §5.1 (mechanism table, Surface, `boost.py`, the m48/m49 refreeze, the frozen table, Fails on, commits), §5.2's
  m69a refreeze and frozen header, §6 graphed, §7, §9. New probes `probe_session_scope.{py,txt}` and
  `probe_opt_level0.{py,txt}`.
- **Code:**
  - graphed d0ad16b: `aggregate.py` (`aggregate_plan`, `_PartitionReduce._attribute`), `execute.py` (`compile_ir`,
    `evaluate_ir`, `refuse_chunk_partials`), `debug/lowering.py` (`lower`), `debug/replaying.py`, `src/lib.rs` and
    `src/serialize.rs` (`serialize_with`), `scripts/run-tests.sh`, frozen m22/m49/m50.
  - graphed-histogram 4c4b79f: `boost.py` (`_SumFills`, `_GroupReduce`, `Histogram.plan`, `plan`, `_on_compiled`,
    `_refuse_shortfall`, `_variation_labels`), frozen m48/m49 and their READMEs, tags.
  - `uproot5-pbm/src/uproot/_graphed.py` (a Session per call), `graphed_orchestrator/precommit.py`.
- **Probes (this round):** everything ran read-only in `graphed-histogram/.venv` (graphed there is byte-equal to
  d0ad16b's `aggregate.py`/`execute.py`).
  - `probe_opt0_cone_rv3.{py,txt}`
  - `probe_opt0_pickle_rv3.py` (+ `probe_opt0_pickle_fns_rv3.py`), `.txt`
  - `run_refuse_shortfall_rv3.sh` (+ `probe_refuse_shortfall_plugin_rv3.py`) → `probe_refuse_shortfall_rv3.txt`
  - No server, container or background process was started or remains. graphed-histogram's `git status` is clean.

## r2 findings
- **R2-1: closed.**
  - The scope is now stated: a name holds its packing state for the life of the process.
  - Rows that are not about sharing name their contexts uniquely, in both repos.
  - The sharing clause asserts the second plan's slot → server map and recomputes each shared server from both
    plans' maps.
  - The refusal is pinned in a later test.
  - Why process lifetime is the smallest scope that holds:
    - A session scope fails: m69a builds a session per dataset (`uproot/_graphed.py`: `graphed.Session(backend)` per
      call), and `collate` merges equal specs across sessions (`probe_session_scope.txt`:
      `collated services: ['histserv-0']`).
    - A weak-reference scope loses ctx1's servers once ctx1 is dropped while plan1 still lives.
  - The different-arguments refusal carries weight, and is not only a UX choice. `workers` is not in the
    `ServiceSpec`, so two contexts that differ only in `workers` produce equal specs, which `collate` would merge
    without a word.
  - Consequences, deterministic and loud:
    - A notebook cell re-run with a changed `memory_mb`, or a second unrelated analysis with other arguments under the
      default name, is refused. The remedy is a fresh name or a new process.
    - An equal re-run shares the state. It over-counts phantom slots: never under memory, sometimes one server more.
    - The warning is deterministic under `pytest.warns`. Python's default filter shows it once per message and site.
  - Thread safety is unstated; see exit item 4.
- **R2-2: closed, subsumed by ruling A.**
  - A backed or unbacked `gh.plan` builds from a fresh `pieces`, and `_refuse_shortfall` goes.
  - `test_pieces_composition.py` has the backed merged-fill clause. The instrument (the pair compiles to one output)
    replaces the refusal control.
- **R2-3: closed.**
  - `on_compiled` refuses a second firing naming `pieces`, and `gh.plan` builds a fresh `pieces` per call.
  - The row adds the refusal and the first plan's run afterwards. One strengthening of the second clause is exit
    item 3.
  - The shared cause (build-time state held past its plan) now has a stated scope at each instance in the delta:
    - positions: one plan;
    - packing: the process;
    - `_Handles`: one bind;
    - `serve`: one plan;
    - `opt_level`: carried on the plan's own `_PartitionReduce`.

## Design findings

### R3-1 — `opt_level=0` ships the whole session arena, not the marked outputs' cone
- **Where:**
  - §5.0: "`0` compiles with `compile_ir(optimize=False)`, the 1:1 lowering graphed already calls `opt_level=0`
    (`debug/lowering.py`, `execute.py`), so every marked output stays its own compiled output".
  - The frozen row `tests/frozen/frontend/m69b/test_aggregate_opt_level.py`.
  - The size in §5.0 and §7 (~30 src).
- **Why it changes code:**
  - **`compile_ir(optimize=False)` serializes every node the session ever recorded.** It calls
    `session._store.serialize(outputs=ids)` → Rust `serialize_with`, which writes all nodes and only flags the
    outputs. Frozen m22 `test_serialized_ir_is_output_scoped_on_optimized_and_raw_paths` pins exactly this:
    "optimize=False serializes the WHOLE store but flags only the requested output".
  - **Downstream, everything reads the whole IR, except the projection.**
    - `evaluate_ir` evaluates every node in the IR.
    - `external_evaluators`, `plan_services` and `refuse_chunk_partials` all scan the whole IR.
    - `read_columns` projects only the marked arrays' columns.
  - **What an opt-0 plan does as written:**
    - It evaluates every unmarked recorded node.
    - A node over a column no output reads fails, because the projection never read that column.
    - A node that raises on the data fails.
    - A consumed reduction anywhere in the session refuses the plan.
    - Unmarked Externals' services join `plan.services`.
    - The IR grows with the session's history, which is §A.3 #6.
  - **The plan's authority is the cone.** M6's `opt_level=0` is `lower()`: "the graph reaching `array`", walked by
    `session.walk`.
  - **graphed already filters the arena to that cone in one place.** `replaying.py` `Replay.__init__` does it:
    `self._nodes = [n for n in arena.nodes() if n["id"] in cone]`, under the comment "it is the whole arena, so only
    the cone is evaluated", and evaluates that list with `preserve.interpreter.iter_ir`. That is the rung-2
    precedent for the repair.
  - **The frozen row cannot see the difference.** Its fixture records only the marked outputs, so its session is
    the cone.
  - **So the implementer must decide what the opt-0 IR carries, and where it is built.**
    `compile_ir(optimize=False)` cannot change: m22 freezes it, and the preserve bundle and replay rely on it.
- **Measurement:** `probe_opt0_cone_rv3.txt`. The session reads `x` and `w`, and only `ev.x * 2.0` is marked:
  ```
  none  opt_level=1: IR nodes  2; value 12.0
  none  opt_level=0: IR nodes  3; value 12.0
  cols  opt_level=1: IR nodes  2; value 12.0
  cols  opt_level=0: IR nodes 54; StageError: AttributeError: no field named 'w'
  raise opt_level=1: IR nodes  2; value 12.0
  raise opt_level=0: IR nodes  6; StageError: IndexError: cannot slice NumpyArray (of length 0) with 0: index 0 is out of bounds
  ```
- **Closed when:**
  - §5.0 states that an opt-0 plan ships the cone of its outputs, writes and metadata arrays, 1:1, with
    `correspondence.node_map` taking record id → shipped id and frames re-keyed onto it.
  - It states where the cone is built, in `aggregate_plan`'s opt-0 branch, selecting the nodes replay's filter
    selects.
  - It states the mechanism. Replay's list keeps sparse record ids, and the shipped IR is a serialized `GraphStore`,
    so it is either a renumbered cone store or a cone-aware evaluation.
  - `compile_ir(optimize=False)` keeps its frozen whole-store contract.
  - The src estimate is re-sized to the repair.
- **Test:** the frozen row's fixture session also records, unmarked:
  - (i) a node over a column no output reads;
  - (ii) a node that raises on the fixture's data.

  At `opt_level=0`, the plan runs and its totals equal the default's. The shipped IR's node count equals the cone's.
  The control is `compile_ir(session, *outputs, optimize=False)` of the same outputs, which holds more nodes.

## Checked and holding (the delta)
- **Ruling A: the named frozen assertions are the files' own.**
  - m48 `test_optimizer_merge_guard.py` L59–66: `pytest.raises(GraphedError)` around `gh.plan({"met":
    _merging(events)})`, then three message asserts.
  - m49 `test_merge_shortfall.py`:
    - L86–92 (group builder), L95–99 (`.plan()`) and L102–107 (both, at the builder) are the three refusals.
    - L110–125 is the positive control that builds `want` (two direct fills) and `one = _single().plan()`.
    - L128–140 is the instrument.
  - m48 `README.md` H5 L34–37 and m49 `README.md` L18 are the rows to rename.
  - Tags: `freeze-m48-fixup` exists, so `freeze-m48-fixup2` is needed. `freeze-m49` exists, with no fixup yet.
  - `.graphed/m48/disputes` and `.graphed/m49/disputes` exist.
- **Ruling A: the replacement assertions fail in the direction they guard.**
  - Against 0.0.4, all three raise.
  - With the refusal gone but a static rank kept:
    - m48 and m49's group builder hit the worker `IndexError`, which the frozen docstrings describe (m48 L10–11,
      m49 L7–8).
    - `.plan()`'s `_SumFills` under-sums by half (m49 L9–12), which fails against `want` and "exactly twice".
  - "Exactly twice `_single()`'s" is bit-exact for a correct read. `h + h = 2h` and `2a + 2b = 2(a + b)`, because
    IEEE scaling by 2 is exact.
- **Ruling A: removing `_refuse_shortfall` breaks exactly the four named tests.** `probe_refuse_shortfall_rv3.txt`,
  the whole histogram frozen suite as is, then with `_refuse_shortfall` a no-op:
  - baseline: `330 passed`;
  - no-op: `4 failed, 326 passed`. The four are m48's `…_merges_is_refused` and m49's three refusals.
- **Ruling A: `_variation_labels` keeps working.**
  - Merged varied fills return normally (`probe_positions_reuse_rv2.txt` B).
  - The payload stays pinned on `gh.plan` by frozen m49 `test_variation_labels_payload.py` (L30, L34, L138–139).
  - The plan text should say `pieces.on_compiled` returns it (exit item 2).
- **Ruling B: code claims.**
  - `aggregate_plan` has one `compile_ir` call, and `compile_ir` takes `optimize`.
  - `_attribute` builds `StageError(opt_level=1, …)` with a literal (`# aggregate_plan always compiles optimized`).
  - Every test construction of `_PartitionReduce` is by keyword (frozen m50 `test_external_attribution.py`, extra
    m49), so a defaulted `opt_level` field breaks none of them.
  - The opt-0 plan's IR and its stdlib pickle are seed-independent (`probe_opt0_pickle_rv3.txt`: seeds 1 and 2 give
    `79288734400b3b4f`/`d8b6c38ab2a75845` at 0, equal pairs at 1). So the determinism clause is writable with a
    fixed source path, in the subprocess pattern of frozen m49 `test_varied_plan_determinism.py`.
  - `tests/frozen/frontend/m69b` is run by `scripts/run-tests.sh`, since frontend runs per subdir, and its basename
    is unique.
  - Nothing in §5.1/§5.2 calls `opt_level`, so the PR stands alone.
- **New and changed frozen clauses fail in the direction they guard:**
  - the backed merged `gh.plan` (refusal, static rank or read-once all fail it);
  - the second `aggregate_plan` over one `pieces` (no refusal: it does not raise);
  - the sharing clause (a non-sharing context puts the overflow slot on `histserv-0`, which the first plan declares);
  - the process-scope refusal (a weakref scope builds the second context);
  - the Weight one-bin O row (r2 exit item folded in);
  - the m69a README row.
- **r2 exit items folded in:** the one-bin slots are `Weight`; §9 says "a missing or mis-scaled `O`, `a`, `b`"; the
  m69a each-dataset test stays; the README row names `"diagnostics"`.
