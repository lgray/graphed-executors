# m69b unit A implementation review, round 1: `freeze-m69b..m69b-opt-level` (graphed#64, 6a92362)

**Verdict: APPROVE.** Every gate I could run locally is green, and there is no High or Medium finding. CI is
checked separately. Two Low items and one note are below; none needs another round.

Setup: a scratch clone at 6a92362 with a fresh `maturin build` of its own Rust. The checkout's `.so`
predates the commit, so I did not reuse it. Runs used `~/vibe-coding/cloud/.venv-m69b-graphed` without
installing anything into it. pytest's `pythonpath = ["python", …]` makes the clone's `python/` win over the
editable checkout. The checkout was never written to. Probe scripts are in this session's scratchpad
(`probe_m69b.py`, `probe_seed.py`, `probe_hist.py`, `probe_incr.py`, `probe_types.py`). The probe flagged 3 results, and each was a mistake in my expectation, not in the code:
- arity `[4, 4]` is right: 3 distinct outputs plus 1 path;
- cone output order `[3, 2]` is the argument order;
- the byte difference against a fresh session is the Note at the end.

## Gates
| Gate | Result |
|---|---|
| frozen untouched | `git diff freeze-m69b..m69b-opt-level -- tests/frozen` is 0 lines. Control: the same command over `python/` gives 232 lines, and `d0ad16b..freeze-m69b -- tests/frozen` gives 3 files, +291. |
| frozen m69b | 12/12 pass on two runs. The 2 extra tests also pass. |
| `COV=1 ./scripts/run-tests.sh` | exit 0: 2661 passed, 33 skipped, 0 failed. Combined coverage is 96% (≥90). |
| per-file ≥90% | Touched files: `aggregate.py` 99%, `debug/replaying.py` 100%, `execute.py` 98%. Four files are under 90%: the jax, pytorch, tensorflow and xgboost external plugins. Their frameworks are not installed locally, CI installs them, and this PR does not touch them. |
| diff-cover vs origin/main | Python: 32 lines, 100%. Rust (llvm-cov with Homebrew LLVM 22, lib.rs excluded): 46 lines, 100%. Per-file Rust gate: 7 files, 0 under 90%, `store.rs` 96.51%. |
| lint/types | `uvx prek@0.4.5 run --all-files` passes ruff, ruff format, mypy (strict), cargo fmt and clippy `-D warnings`. |
| cargo | `cargo test`: 51 passed, `cone_keeps_what_the_outputs_reach_one_to_one` among them. Loom passes. |
| sphinx | `sphinx-build -W -b html docs …` exits 0. |
| precommit | `graphed_orchestrator.precommit . --fast --no-coverage` reports `PRECOMMIT-GATE: ok`, integrity-scan ok. |
| commit | One commit with 217 insertions and 37 deletions. Conventional message, author `Lindsey Gray <lindsey.gray@gmail.com>`, no trailers. The `+` lines have no `type: ignore`, `noqa`, `except`, `skip` or `xfail`. The only `unwrap` calls are in the cargo test. |

## Probes (a)–(f)
- **(a) The cone is exact.** The probe used outputs `(w, w*1.0, x+1)`, a write of `w+2` and a metadata
  `x.sum()`. The opt-0 plan's `node_map` keys equal the union of the `lower(opt_level=0)` cones of all 5
  arrays. The shipped IR equals `_compile_cone` of those arrays, and its node count equals the cone size,
  which is smaller than the session's store. Record ids map in ascending order to `(0..n-1, None)`. The plan
  runs, and its columns are projected to `["w", "x"]`, so the unread `z` node and the raising node never
  ship.
  - Session history: recording 50 more nodes and running an optimized compile plus another opt-0 plan
    leaves the opt-0 IR byte-identical, and `store.outputs()` stays empty.
  - `compile_ir(optimize=False)` still covers the whole arena with identity `node_map`. The diff only moves
    its tail into `_compiled`.
  - Incremental sessions behave the same at both levels.
- **(b) Every compile site uses the plan's level.** I grepped `python/` for `compile_ir(`, `.reduce(`,
  `.serialize(`, `.cone(`, `process.ir` and `_PartitionReduce`. Only two sites produce or re-derive an
  aggregate plan's IR: `aggregate_plan` and `replay`/`Replay`. Both go through `_compile_at`.
  - The other `compile_ir` callers are other plan types: shuffle, awkward/numpy io, and `serialized_ir`.
  - `bind_services` uses `replace`, so it keeps `opt_level`.
  - `plan_services`, `external_evaluators`, `refuse_chunk_partials` and `on_compiled` all receive the
    level's own `CompiledGraph`.
- **(c) `replay` equals the run.**
  - Levels 0 and 1, outputs repeated `(w, w)`, merged `(w, w*1.0)` and interleaved `(x+1, w, w*1.0, x+1)`,
    with the run captured or not: `diff()` is `("recorded"|"re-evaluated", True)` for both tasks.
  - Direct `Replay(process, task, outputs)` equals `process(partition)` in every case.
  - graphed-histogram merged fills (`weight=w` and `weight=w*1.0`): at 0 they fill twice (sumw = 2×), and
    replay equals the run. At 1, gh's shortfall refusal fires as before.
  - A varied gh plan (`vary(w, "jes", …)`) runs and replays equal at both levels, carries variation labels,
    and its histograms are equal between levels.
  - A `writes=` plan is still refused by replay at both levels. Reordered outputs are refused at 0.
- **(d) StageError and frames.**
  - A failing op recorded after the unmarked nodes reports `opt_level` 0 or 1 and the op's own line.
  - A varied failing universe (`down`) reports `variation` containing `down` at both levels.
  - At 0, every shipped key's frame equals the provenance of the record id that maps to it, and there is
    one frame per key.
- **(e) Determinism.** Three child interpreters ran with `PYTHONHASHSEED` 1, 2 and 3; the `str` hashes
  differ. The sha256 of IR plus pickled plan is identical across seeds for six plans: plain, varied gh with
  two histograms, and writes with metadata, each at both levels.
- **(f) Rust `cone` from Python.**
  - Output order follows the arguments, and duplicates are deduplicated by `mark_output`.
  - `node_map` is `None` for dropped ids. Empty `outputs` gives an empty store.
  - Ids 4, 2^31 and 2^32−1 raise `ValueError("no node with id …")`. Ids −1 and 2^64 raise `OverflowError`.
    No `PanicException` occurs.
  - The store is unchanged afterwards.
  - Two `expect`s remain in `from_reduced`. Neither can be reached, because the arena is topological by
    construction: `intern` validates inputs, including through `deserialize`.
- **Discrimination of the extra test.** I ran two mutants in the scratch clone and restored it afterwards;
  `git status` was clean.
  - Direct `Replay` compiling optimized: `test_direct_replay_…[0]` fails.
  - One reduce value per argument, as on d0ad16b: `[1]` fails, along with frozen `w-twice-at-0` and
    `w-and-w-times-1-by-default`.

## Intent, technique, proportion
- §5.0 and R5A-1 are implemented as written:
  - `GraphStore.cone` validates, then runs `dead_code_elimination`, then `from_reduced`.
  - `_compile_cone` shares `compile_ir`'s tail.
  - `_PartitionReduce.opt_level` feeds `StageError`.
  - `replay` compiles once and feeds both the IR check and `Replay`, which reduces one value per IR output
    in slot order.
  - The r5-A docstring rewording is done.
- Ponytail: each piece is the smallest reuse available.
  - `_compile_at` is one line. `_slot_of` was lifted rather than duplicated.
  - `arena_holding` is the validation `reduce_with_outputs` already had, now shared.
  - Nothing was added that the plan did not call for.

## Low
- **L1. `opt_level` accepts `True`, `False`, `0.0` and `1.0`, and keeps them as given.**
  - `aggregate_plan(opt_level=0.0)` compiles the cone, and `process.opt_level` is `0.0`. `True` compiles
    optimized and stores `True`. The value flows into `StageError.opt_level` unchanged.
  - Reason: `opt_level not in (0, 1)` compares by equality.
  - Fix: refuse non-`int` values (`type(opt_level) is not int`) under the same message.
  - Shown closed when: `[True, 0.0]` raise `ValueError`.
- **L2. One comment breaks the owner's comment rule.** The `_PartitionReduce.opt_level` comment describes
  what other code does ("every site that produces or re-derives a plan's IR (`graphed.debug.replay`)
  compiles at it, through `_compile_at`"). Cut it to the field's meaning. This is a constraint for the next
  touch of the file, not a round.

## Note (no action)
At level 0 the IR is ordered by ascending record id, as §5.0 specifies. Its bytes therefore depend on the
order the cone's own nodes were recorded, and level 1 canonicalizes this away.
- Example: the fixture records `events.x` before `events.w`. A fresh session that records `w` first ships
  different opt-0 bytes for the same outputs.
- The same program still gives the same IR, so determinism holds.
- Recording more unrelated nodes does not change the IR.
