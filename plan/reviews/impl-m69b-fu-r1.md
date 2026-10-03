# m69b follow-ups implementation review, round 1 (PR #48: 3b02317..5fdb3c0)

## Verdict: REJECT, with one BLOCKING finding (F1)

#45 and #47 are closed as asked. #46 now gives each holder the right lifetime. But the message words it
"held", which is HTCondor's job-state word. In that same call, the pilots' cluster is put on hold and then
released (F1).

| Gate | Result | Evidence |
|---|---|---|
| new and changed rows, main src (3b02317) vs 5fdb3c0, Linux pool | main: all 3 fail on the old text `(cluster N), which keep their slots until the run ends`; 5fdb3c0: 3 passed | `probes/m69b/rows_fu_rv1.txt` |
| both m69b modules + frozen m69b row 7, 5fdb3c0, Linux pool | 44 passed, 0 skipped; queue empty afterwards | same |
| frozen row 7's `names_cluster` on the live 5fdb3c0 text | `True` for the pilots' cluster; control `False` for another number | `probes/m69b/names_cluster_fu_rv1.txt` |
| `git diff 3b02317 5fdb3c0 -- tests/frozen` | 0 files. Control: the same command lists both `tests/extra` files | `probes/m69b/frozen_fu_rv1.txt` |
| ruff, `ruff format --check`, mypy strict (also `--platform win32`), sphinx -W | clean | `probes/m69b/gates_fu_rv1.txt` |
| macOS py3.12, `tests/extra` + frozen m68a/m68b/m69b | 485 passed, 31 skipped, 0 failed (the classad2 rows skip on macOS) | same |
| mypy on `services.py` without the assert, darwin/linux/win32 | clean. Control: an added `self.cluster + 1` errors on all three | `probes/m69b/mypy_control_fu_rv1.txt` |
| local precommit `check_integrity` | FAIL, `assertion_removed` on `services.py`, naming the dropped assert. Control: keeping that line gives 0 findings | `probes/m69b/integrity_fu_rv1.txt` |
| CI on #48 (run 37127304342, head 5fdb3c0) | 27 of 27 checks pass, test-htcondor included | `gh pr checks 48 -R graphed-org/graphed-executors` |

## Findings

**F1 (BLOCKING): the refusal message uses "held" for slot lifetimes. In this call, "held" is also the
state the pilots' cluster is put into.** This is in `HTCondorBackend._host_service`'s holder labels
(`backend.py`):

- `the runner's running pilots (cluster N, held until it closes)`
- `its server 'web1' (cluster M, held until the run ends)`

A later plan's `_host_service` call is the one that builds the pilots' label. It first calls
`hold_queued()` on cluster N, under `HOLD_REASON`, and the services' failure releases that hold again.
The docs say exactly this:
"A later plan's servers wait with the runner's queued pilots held … the pilots are released once those
services have started or failed" (`docs/htcondor.rst`, the bullet before "One plan's services start at a
time").

The new row's own scenario shows the collision (`probes/m69b/probe_held_fu_rv1.txt`):
```
MESSAGE: ... beside the runner's running pilots (cluster 70, held until it closes): RequestMemory=600, ...
SCHEDD ACT: ('act', 'Hold ClusterId == 70 && JobStatus == 1')
SCHEDD ACT: ('act', 'Remove ClusterId == 71')
SCHEDD ACT: ('act', 'Release ClusterId == 70 && JobStatus == 5 && substr(HoldReason, 0, 47) == "graphed: a service of this run waits for a slot"')
```
A user who reads the refusal against `condor_q` reads it as: cluster 70 is held until the runner closes.
The schedd log says the hold was released right after the refusal. Elsewhere this same diff says the
lifetime in slot words: `match_refusal`'s docstring says "keep their slots", `_host_service`'s says "kept
until", and the docs say "keep their slots until the runner closes". The message is the only place that
uses "held".

- **Class.** `grep -rn "held until" src docs tests/extra` finds the two labels and the three row
  assertions on them: `test_m69b_schedulable.py` (the new row and the set's-earlier-server row) and
  `test_m69b_sibling_room.py`. The other two hits are unrelated comments, in `driver.py` and in a m65
  test.
- **Closed when** the three rows assert lifetime words that name the slot, not a job state, and fail on
  5fdb3c0's text. Frozen row 7 keeps matching as long as the label keeps `(cluster N` first, since
  `names_cluster` allows up to 16 non-digits after "cluster".

## The judged items

1. **#46.** The old text claimed one lifetime for every holder. That clause is gone from `match_refusal`,
   and each label now names its own lifetime. Apart from F1's wording, the lifetimes are the ones the docs
   give ("the pilots keep their slots until the runner closes, the servers until the run ends"). Both
   docstrings are fixed. Running the rows against main's src shows they discriminate: each fails on
   the old message, and the sibling-room row fails on a live minicondor slot (`cluster 1, which keep their
   slots until the run ends`). All three pass at 5fdb3c0. The sibling row's split assertion still checks
   `'other' not in managed`, so it was not weakened.
2. **#45.** Dropping the assert is correct:
   - `match_refusal` has one runtime caller, `_host_service`, and it calls it after `job.submit()`.
     `ServiceJob.cluster` is assigned only in `__init__` (`None`) and in `submit` (an `int`, or it
     raises). No path reaches the query with `None`.
   - The one test caller sets `job.cluster = 4242`.
   - mypy needs no narrowing on any of the three platforms (the control shows the file is checked under
     win32).

   The PR body's precommit claim is N1.
3. **#47.** The new clause matches r8's probe: plan b submits nothing while plan a's server waits. sphinx
   -W is clean.

## Non-blocking

**N1: the PR body misattributes the precommit's finding.** The body says the local precommit's
`assertion_removed` "is that ruled removal", meaning the owner-ruled removal of the pilots-only assert.
That is not what the scan reports:

- The scan's detail is `assert self.cluster is not None, "matched only once submitted"`, which is #45's
  own drop, and its status is FAIL, not advisory.
- The pilots-only assert (`"claims are the submitted pilots'"`) already left in #44. It has 0 hits at
  3b02317 (control: `245d0c6:services.py:185`), so it is not in this diff.

The disclosure is honest in substance: the finding is named, and CI does run no integrity scan (0 hits in
`.github/workflows`, with pyproject's 3 hits as the live control). The removal is right. Only the
attribution is wrong.

## Pre-existing

None found.
