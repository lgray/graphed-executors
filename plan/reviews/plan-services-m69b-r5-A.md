**NOT CLEAN**

# Review m69b-r5-A: unit A (§5.0), delta pass (06ec18b → eea3f4f)

## Scope
- **Snapshot:** `reviews/plan-services-m69b-r5-A-snapshot.md` (= `plan-services.md` at eea3f4f).
- **Delta read:** `git diff --word-diff 06ec18b eea3f4f -- plan-services.md`: the §5 opening sentence, §5.0 and its
  frozen row, and §7's size line, plus what they reference.
- **Code (read-only):**
  - graphed d0ad16b: `debug/replaying.py`, `aggregate.py`, `execute.py` (`compile_ir`, `_frames_by_key`,
    `evaluate_ir` keys), `src/lib.rs` (`map_err`, `serialize`), `src/store.rs` (`BadNodeId`, `mark_output`,
    `from_reduced`), `src/optimizer/mod.rs` (`dead_code_elimination`), and the frozen m65 replay tests.
  - graphed-histogram 4c4b79f `boost.py`.
  - executors `upstream/main` = db8fb0a, `src/`.
- **Probe (this round):** `probes/m69b/probe_opt0_rv5a.{py,txt}`. It ran in `graphed-histogram/.venv`, whose graphed
  `aggregate.py`, `execute.py`, `debug/replaying.py` and `debug/lowering.py` are byte-equal (`cmp`) to d0ad16b's.
  - It patches module attributes in-process only, and its temp dir is removed.
  - No process or container remains. Both repos' `git status` is clean.

## R4-1: closed at its cause
- **The rule is at the cause.** "Every site that produces or re-derives a plan's IR compiles at that level" names
  the operation, and the plan gives `_PartitionReduce.opt_level` as the level's carrier.
- **Fresh search: `compile_ir` / `serialize(` / `reduce(` / `process.ir` / `_PartitionReduce` / `aggregate_plan`.**
  - **graphed `python/`:** `compile_ir` is called in these places:
    - `aggregate.py` `aggregate_plan`: covered.
    - `replaying.py` `replay`: covered.
    - `replaying.py` `Replay.__init__`: the whole arena, which the plan says stays.
    - `shuffle.py` `shuffle_plan` and `join_plan`, `awkward/io.py` `_write_varied` and `to_parquet`, and
      `numpy/io.py` `to_parquet`: each builds its own process, so no `_PartitionReduce` level applies.

    `session.serialized_ir` is session-level and is used by preserve, not by a plan. `collate` does not compile.
  - **graphed-histogram `src/`:** its only other compile is `boost.py` `_refuse_shortfall`, which §5.1 removes (line
    1019).
  - **executors db8fb0a `src/`:** no `compile_ir`, `process.ir`, `_PartitionReduce` or `GraphStore` hit.
    `aggregate_plan` appears once, in a comment (`submit/engine.py`). The same grep hit five `opt_level` lines, so the
    instrument was live. Those five are literal `StageError(opt_level=0)` values on KilledWorker and probe errors.
    They are infrastructure errors, not IR sites.

  The rule's enumeration is complete for IR.
- **The repair runs** (`probe_opt0_rv5a.txt`, on the frozen row's fixture: `w` and `w * 1.0` marked; `z * 3.0` and
  `x[x > 100][0]` unmarked; `store=`):
  - d0ad16b's replay at 0 raises the `ValueError`.
  - With the check made at the plan's level, `diff.equal=True`, recorded `(2, 6.0)` and replayed `(2, 6.0)`.

## New frozen clauses
- **Replay diff at 0:** writable, and it fails against d0ad16b in its direction (the `ValueError` above). What it
  asserts holds only for distinct outputs (R5A-1).
- **`user_frame` after unmarked nodes:**
  - Evaluation keys every node `(shipped id, None)` or `(stage id, member)` (`execute.py` `evaluate_ir`), and the
    frames are re-keyed by `_frames_by_key`. `StageError.user_frame` exists.
  - A record-id keying names an unmarked node's line (`probe_opt0_replay_rv4.txt`: 68 against 67).
  - The literal `opt_level=1` fails the `0` leg.
  - Writable and discriminating.
- **`GraphStore.cone` past the store:** discriminating, but "raises `BadNodeId`" is not writable as spelled
  (exit item 1).

## Design findings

### R5A-1: replay's partial disagrees with the run's whenever outputs repeat or merge, including at `opt_level=0`
- **Where:**
  - §5.0's replay sentence ("…and `debug.replay`'s recompile check").
  - The frozen row's replay clause.
  - Code: `replaying.py` `Replay.value`.
- **Why it changes code:**
  - `Replay.value` calls `self._process.reduce([out[i] for i in self._output_ids])`, which is one value per argument
    to `replay`.
  - The run's `reduce` receives one value per distinct IR output. `GraphStore::mark_output` skips an id it already
    holds, and `aggregate_plan` addresses the values through `order`/`slot`.
  - So a plan whose outputs repeat an Array (at either level), or merge under the optimizer (at 1), replays a
    different partial: `diff().equal` is False when nothing differs. A reduce that indexes by rank (the
    `_GroupReduce` layout) reads the wrong value.
  - §5.0 now freezes "replay agrees at `opt_level=0`", and a repeated output at 0 breaks that even after R4-1's
    repair.
  - This is R4-1's operation again: replay rebuilds a plan fact from the caller's outputs instead of from the plan's
    compile. The IR was the first such fact; the reduce's input order is the second and last. `Replay.__init__`'s
    record-level cone and arena are unfused by design.
  - The defect predates this delta: it is in d0ad16b at opt 1.
- **Measurement:** `probe_opt0_rv5a.txt`:
  ```
  opt 1: IR outputs 1; run (reduce arity, total) (1, 3.0); diff.equal=False (recorded); recorded (1, 3.0); replayed (2, 6.0)
  opt 0, replay checks at the plan's level, outputs (w, w): IR outputs 1; run (reduce arity, total) (1, 3.0); diff.equal=False (recorded); recorded (1, 3.0); replayed (2, 6.0)
  the cut (Replay.value per IR output of the plan-level compile):
    opt 0, outputs (w, w): diff.equal=True (recorded); recorded (1, 3.0); replayed (1, 3.0)
    opt 1, outputs (w, w): diff.equal=True (recorded); recorded (1, 3.0); replayed (1, 3.0)
    opt 1, outputs (w, w * 1.0): diff.equal=True (recorded); recorded (1, 3.0); replayed (1, 3.0)
    opt 0, outputs (w, w * 1.0): diff.equal=True (recorded); recorded (2, 6.0); replayed (2, 6.0)
  ```
- **Closed when:**
  - §5.0 states that `replay` compiles once, at `process.opt_level` (`_compile_cone` at 0), and takes both facts
    from that compile:
    - the IR check;
    - `Replay.value`'s `reduce` inputs: one value per IR output, in IR output order, mapped through
      `correspondence.node_map` as `aggregate_plan`'s `slot` does.
  - The extra m65 `test_m65d_replay_binding.py` constructs `Replay(process, task, (h,))` directly, so the compile
    enters `Replay` without breaking that call.
  - §5.0's and §7's src sizes grow by about 5 lines.
- **Test:** extend the frozen row's replay clause so that `diff().equal` holds for these as well:
  - the outputs `(w, w)` (one Array passed twice) at `0`;
  - the merged pair `(w, w * 1.0)` at the default.

  Against d0ad16b's `Replay.value`, even with R4-1's check repaired, both give `diff.equal=False`, recorded
  `(1, 3.0)` against replayed `(2, 6.0)`. With the cut, all four legs are equal.

## Loop note
- r4 had 1 design finding and r5-A has 1.
- R5A-1 was not introduced by the r4 repair. It surfaced when the repair's new frozen clause was driven with a
  repeated output.
- It shares R4-1's operation, so the cut above is the cause-level one. It makes replay's one compile the only
  source of plan facts.
