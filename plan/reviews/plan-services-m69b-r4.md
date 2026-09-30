**NOT CLEAN**

# Review m69b-r4: delta pass (4a9bd22 → 27adfb9)

## Scope
- **Snapshot:** `reviews/plan-services-m69b-r4-snapshot.md` (= `plan-services.md` at 27adfb9).
- **Delta read:** `git diff --word-diff 4a9bd22 27adfb9 -- plan-services.md`, plus the lines it references: §5.0 whole,
  §5.1 Surface/`boost.py`/refreeze/frozen table/commits, §7 sizes. Probe `probe_opt0_cone_store.{py,txt}`.
- **Code (read-only):** graphed d0ad16b `src/optimizer/mod.rs`, `src/store.rs`, `src/lib.rs`, `src/serialize.rs`,
  `python/graphed/{execute,aggregate,services}.py`, `debug/{replaying,errors}.py`, frozen m22; graphed-histogram
  4c4b79f `boost.py` and frozen m48/m49 docstrings; executors 0e48380 `src/`.
- **Probe (this round):** `probes/m69b/probe_opt0_replay_rv4.{py,txt}`, in `graphed-histogram/.venv` (its graphed
  `aggregate.py`/`execute.py`/`debug/replaying.py` are byte-equal to d0ad16b's). Temp dirs removed; no process or
  container started; both repos' `git status` clean.

## R3-1: closed at its cause
- **Rust premises hold (quoted, d0ad16b):**
  - `optimizer::dead_code_elimination(nodes, outputs) -> (Vec<NodeKey>, Vec<usize>, Vec<usize>)` is `pub`: a stack
    walk over `nodes[i].inputs()`, then "compact, preserving topological (ascending-id) order" with
    `node.with_inputs(new_inputs)` and a `remap` vector (`DROPPED = usize::MAX`, private) returned.
  - `GraphStore::from_reduced(red: optimizer::Reduced)` is `pub(crate)`; it re-interns each key with remapped
    inputs, `mark_output`s `red.outputs`, and composes `red.node_map` through the same `map`. `Reduced`'s four fields
    are `pub` and `ReductionReport: Default`, so the binding can hand DCE's output to `from_reduced` directly
    (`node_map` from `remap`, `DROPPED` → `None`). The arena is interned and DCE's remap is injective, so the
    re-intern is the identity: 1:1 holds.
  - Size: the binding (validate, snapshot, DCE, `Reduced`, `from_reduced`) and `_compile_cone` (the optimized branch's
    tail over `session._store.cone(outputs=ids)`) fit ~30 Rust + ~35 Python.
- **Python premises hold:** `compile_ir` calls `_frames_by_key(session, node_map)` after both branches, so the
  optimized branch re-keys frames that way; `unreached_labels`/`shift_after_weight` carry over the same way.
- **Consumers of the shipped cone** (`probe_opt0_replay_rv4.txt` unless noted):
  - `writes=` + a metadata reduction, 20 unmarked nodes: opt 0 ships 6 nodes, opt 1 ships 5; the parts are equal.
  - Externals: `external_evaluators` keys by `external_key` (payload hash + params, no id); the fills case of
    `probe_opt0_cone_store.txt` runs and equals two direct fills.
  - Services: `referenced_services` reads `params["service"]` only.
  - `refuse_chunk_partials`: an unmarked consumed `sum(x)` is refused on the whole store and builds on the cone.
  - Provenance: a marked op failing after 20 unmarked nodes (record id 25, shipped id 4) raises `StageError` at its
    own line (68) at both levels. A record-id keying would have named line 67 (record 4, an unmarked node).
- **Frozen row:** it is writable (`plan.process.ir`, public `graphed.debug.lower`), and each clause fails in the
  direction it guards. The whole store fails "runs" and the count; the optimized graph fails the arity and the count;
  the control shows the unmarked nodes exist.
- **r3 exit items as applied:** they introduce no defect. The refusal sentences are docstrings (m48 module L8–13, the
  instrument L49–50; m49 L129–130). `_variation_labels(items, compiled)` exists (`boost.py`). No `freeze-m69b` tag
  exists in graphed yet.

## Design findings

### R4-1: `graphed.debug.replay` refuses every opt-0 plan with a false message
- **Where:** §5.0: `aggregate_plan(opt_level=0)` composed with `store=`. §5.0 neither refuses `store=` at 0 nor names
  `debug/replaying.py`.
- **Why it changes code:**
  - `replay()` checks `bytes(compile_ir(outputs[0].session, *outputs).ir) != process.ir`. That is always the
    optimized compile, so an opt-0 plan's cone never matches.
  - The user gets "these outputs do not recompile to the plan's IR: pass the outputs given to aggregate_plan, in
    order", having passed exactly those outputs.
  - Replay is graphed's opt-0 step-through debugger. `store=` exists to feed it, and the plan leaves `store=` open
    at 0.
  - The defect is not new in this delta: r3's whole-store IR failed the same check. The delta makes it reachable
    only through the plan as written.
  - Class search: consumers that re-derive or compare `_PartitionReduce.ir`, over graphed `python/`, executors
    0e48380 `src/` and graphed-histogram `src/`. Single occurrence (`replaying.py` `replay`).
- **Measurement:** `probe_opt0_replay_rv4.txt`:
  ```
  opt 1: diff.equal=True (recorded); replayed 12.0
  opt 0: ValueError: these outputs do not recompile to the plan's IR: pass the outputs given to aggregate_plan, in order
  opt 0, replay checks at the plan's level: diff.equal=True (recorded); replayed 12.0
  ```
- **Closed when:** §5.0 says that `replay`'s recompile check compiles at `process.opt_level`, using `_compile_cone`
  at 0 (about 2 src lines, the leg the probe's third row drives). `Replay.__init__`'s `compile_ir(optimize=False)`
  arena filter stays. The alternative is a refusal of `store=` at 0 that names `opt_level`, but it removes the one
  consumer `store=` has.
- **Test:** add a clause to the frozen row. A `store=` plan at `opt_level=0` is run, and then
  `graphed.debug.replay(plan, 0, *outputs).diff().equal` holds. Against d0ad16b's `replay` the clause raises the
  `ValueError` above.

## Loop note
r3 had 1 design finding and r4 has 1. By `brief-m68b-plan.md` Loop 3 that is non-convergence. R4-1 is local to §5.0
and predates the r3 repair.
