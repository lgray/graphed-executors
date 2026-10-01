# m69b unit A implementation review, round 2 (delta): `6a92362..18c1160` (graphed#64)

**Verdict: APPROVE.** L1 and L2 are closed. Every local gate on the touched files is green. There is no
High, Medium or Low finding.

Setup: a scratch clone at 18c1160 with its own `maturin build --release`. The `.so` was taken from that
wheel. Rust is unchanged in the delta: `git diff --stat 6a92362 18c1160 -- src Cargo.toml` is empty. A probe
test printed `aggregate.py` and `graphed_core.abi3.so` from the clone's `python/`, so pytest's `pythonpath`
wins over the editable checkout. Nothing was installed into `.venv-m69b-graphed`. The checkout is untouched:
status is clean and HEAD is 18c1160. None of my processes remain.

## L1 closed: only the ints 0 and 1 are accepted
- `aggregate.py` `aggregate_plan` now checks `type(opt_level) is not int or opt_level not in (0, 1)`, with
  the same message as before.
- I called `aggregate_plan` directly with each candidate value:
  - Accepted: `0` and `1`; each is stored as the int.
  - Refused with `ValueError`: `True`, `np.int64(0)`, `np.True_`, `Fraction(1)`, `Decimal(0)`, `0j`, an
    `IntEnum` member equal to 0, `"0"`, `None` and `2`.
  - I tried to build a value that passes the check without being 0 or 1, and could not.
- **The new extra test discriminates.** I swapped in `git show 6a92362:python/graphed/aggregate.py` in the
  scratch clone, then restored it; `git status` was clean afterwards.
  - With the old check, `test_m69b_level_type.py` fails 4 of 4, each with `Failed: DID NOT RAISE ValueError`.
    That is the right reason.
  - The same run passes all 12 frozen m69b tests and both `replay_direct` tests, so the failure comes only
    from the check.
  - At 18c1160 it passes 4 of 4.
  - A partial fix would fail part of the parametrization (worked out from the parameters, not run):
    - refusing `bool` only lets `0.0` and `1.0` through;
    - `isinstance(x, int)` lets `True` and `False` through.

## L2 closed
The `_PartitionReduce.opt_level` comment now reads "`aggregate_plan(opt_level=)`: the level `ir` was
compiled at." It describes only the field.

## Gates (scratch clone, 18c1160)
| Gate | Result |
|---|---|
| frozen untouched | `git diff freeze-m69b..18c1160 -- tests/frozen` is 0 lines. Controls: the same command over `python/` gives 231 lines, and `git diff --stat d0ad16b..freeze-m69b -- tests/frozen` gives 3 files, +291. The delta touches only `attempts.md`, `aggregate.py` and the new extra test. |
| frozen m69b | 12 of 12 pass, on two runs. |
| extra m69b | 6 of 6 pass. |
| frontend and debug subtrees | All 31 pytest processes exit 0: each `tests/frozen/frontend/<milestone>` alone, then `tests/extra/frontend`, then `debug` (frozen and extra together). |
| coverage, touched files, these subtrees | `aggregate.py` 94%, `debug/replaying.py` 100%, `execute.py` 96%. Each is ≥90%. The new line 302 has no partial branch. |
| diff-cover vs origin/main (d0ad16b) | 32 lines, 0 missing, 100%. `--fail-under=98` exits 0. |
| prek | `uvx prek@0.4.5 run --all-files` passes ruff check, ruff format, mypy (strict), cargo fmt and clippy `-D warnings`. mypy's `files` setting includes `tests`. |
| precommit | `graphed_orchestrator.precommit . --fast --no-coverage` reports `PRECOMMIT-GATE: ok`, and the integrity scan is ok. |
| commit | Conventional message, author `Lindsey Gray <lindsey.gray@gmail.com>`, no trailers. |

## Note (no action)
`attempts.md` iteration 2 reports `aggregate.py` at 98% and `execute.py` at 98% over the same subtree set.
I measured 94% and 96%, the uncovered lines being `aggregate.py` 129–137, 411, 416 and 453–454. Both figures
clear the 90% gate, and r1 measured 99% on the full `COV=1` run, so no decision depends on the difference.
