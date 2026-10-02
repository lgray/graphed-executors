# TEST_SANITY: m69b ordering refreeze (executors 6225cd5, parent 84e6fb7)

## Verdict: PASS

The commit can be tagged. All ten new ids fail on today's src on an assertion. All ten pass together on a
conforming implementation, on macOS and on a pool. Two runs give the same outcomes. The scope is what the
2026-10-02 ruling covers. F1 and F2 are not test defects; they must land before the implementer is dispatched.
F3 is a two-file reformat that is cheap only before the tag.

Evidence is in `probes/m69b/*_order_sanity.*`. `runs_order_sanity.txt` holds every run's PASSED/FAILED/E
lines.

## Checks

1. **Scope.** `git diff 84e6fb7 6225cd5 -- tests/frozen` changes three things:
   - Three test hunks, one inside each ruled function. Each matches the ruling's text.
   - The m68a, m68b and m69b READMEs.
   - Three new m69b files.

   No other frozen line changes. The m68a and m68b README edits each extend the ruled id's row only, naming
   §5.2 "Ordering" and the new tag. They are traceability. The m69b README edits add the ordering rows,
   gating notes and readings, and widen the opening line to name "Ordering".
2. **Disputes.** Each of the three `.graphed/m68a|m68b/disputes/*.md` names:
   - the test;
   - the §5.2 "Ordering" clause, quoting the owner ruling of 2026-10-01;
   - the exact diff;
   - `Status: CLOSED — owner ruling 2026-10-02: "m69b refreeze authorized"`, with the tag.

   The tag names `freeze-m68a-fixup2`, `freeze-m68b-fixup4` and `freeze-m69b-fixup` are unused. The latest
   existing tags are `freeze-m68a-fixup`, `freeze-m68b-fixup3` and `freeze-m69b`.
3. **Plan coverage.** All eight rows of §5.2's table are present, and each asserts its row's property:
   - The table's rows 1–5 are the five recorder tests.
   - Rows 6 and 7 are the free-slot test and the refused-beside-pilots test.
   - Row 8 is the Ctrl-C test, parametrized over `run`, `result` and `close`.

   Thirteen recorder mutants of the sanity variant are all killed (`mutants_order_sanity.txt`). These include
   the dispatch decision: a hold per service, or rv1's release at return, both fail plan 3's two-service
   assertion. They also include the HoldReason match: a Hold without a reason, or a Release of any user hold,
   both fail.

   Four pool mutants are killed (`runs_order_sanity.txt`):
   - `exit-no-stop`: the `result` child is still running 15 s after SIGINT.
   - `close-no-finally`: the `close` form leaves its `graphed-service-` job queued.
   - `close-signals-waiter`: likewise.
   - whole-slot match: plan 2 waits past `PLAN_S`.

   Beyond §5.2's table, row 1 asserts the r1 exit items 2–3 that the dispatcher ruled on: one Hold and one
   Release per plan, across plan 3's two services, the Release constrained on the Hold's reason. Row 4 asserts
   that the secret exists at construction, which follows from "`prepare` is `start` without the submit". Row 7
   adds "no `JobCurrentStartDate`". Nothing else goes beyond the plan.
4. **Non-vacuity.** Every id was run on the stub, 6225cd5 as committed, whose `src/` is identical to 84e6fb7's.
   - **Recorder rows (macOS):** 5 of 5 fail on an assertion. Four fail on "pilots at construction". Row 4 fails
     on a `pytest.fail` naming the construction-time spool. Row 5 fails on "close() returned while its plan's
     server waited".
   - **Pool, all ten ids:** all ten fail. Rows 1–5 fail as above. The free-slot row fails on "close() ended
     the plan … still waited for a slot". The refused row fails on "plan 1's server never started". All three
     Ctrl-C forms fail on "the child submitted a pilot job".
   - **No row** fails on collection, import or a fixture.
   - **Rest of the frozen tree (macOS):** the stub also fails the three refrozen m68b `…releases_in_order[*]`
     ids, which is by design. The two other ruled ids pass on the stub.
5. **Passability.** The variant is 6225cd5 plus `variant_order_sanity.diff`: rv1's design, plus the four
   additions the test author listed, plus a serialized `stop()` and a refusal naming the pilots' cluster. It
   passes:
   - the ten ids on the pool, twice;
   - the whole macOS frozen tree, m66–m69b: 348 passed, 0 failed;
   - the `test-htcondor` frozen list plus `test_service_order.py` on the pool: 372 passed, 0 failed.

   The 5 skips are dask, parsl and Triton. No id is unpassable.
6. **Determinism.** The two runs gave identical outcome sets:

   | Tree | Recorder rows (macOS) | Ten ids (pool) |
   |---|---|---|
   | Stub | 5F/5S both runs | 10F both runs, same messages |
   | Variant | 5P/5S both runs | 10P both runs |
7. **CI reachability.** See F1. The recorder rows run in the main matrix and in the 3.14t job. The five pool ids
   skip in every main-matrix job, because there are no bindings, and no job runs them.
8. **Hygiene.**
   - `ruff check tests/frozen` is clean.
   - mypy with the repo config (strict) reports "no issues in 325 source files", and is clean on the five
     touched files alone.
   - There are no `file:line` pins. The grep's positive control matched.
   - There is no narration: the only comments are two constant notes and two `noqa` reasons.
   - `ruff format --check tests/frozen` is vacuous, because the repo excludes `tests/frozen/**` from the
     formatter. See F3.
   - **Private access.** Row 3 reads `backend._server.announce_secret(["svc0"])` and `backend._server.url`.
     This is the first frozen use of `HTCondorBackend._server`. src's `driver.py` makes the same two calls to
     publish a DAG's announce secret and url, and the plan renames neither. The row therefore freezes a name
     src already depends on, and I judge it acceptable. `launcher.cluster` and `TaskServer.forget_announce`
     already have m68b frozen precedent.
9. **Integrity.** The ordered `precommit … --fast --no-coverage --allow-refreeze ×3` on the committed tree
   reports `PRECOMMIT-GATE: ok`. That run is vacuous, because nothing is staged. On 84e6fb7 with 6225cd5
   staged, the same command lists every `REFREEZE:` path and reports ok. The control, without
   `--allow-refreeze`, reports `integrity-scan FAIL frozen-modified:…`.

## Findings

**F1 — the pool rows run in no CI job.**
- **Defect.** `test-htcondor`'s pytest line in `ci.yml` names `tests/frozen/m69b/test_histserv_cluster.py` and
  `test_histserv_managed.py` but not `test_service_order.py`. Plan §6's `test-htcondor` bullet likewise names
  only `test_histserv_*.py`. As a result:
  - the free-slot, refused and Ctrl-C×3 ids skip in every main-matrix job and run in none;
  - `htcondor_backend/` is omitted from the main matrix's coverage, so the recorder rows' frozen hits on the new
    deferral and hold code count nowhere.
- **Closed when** `tests/frozen/m69b/test_service_order.py` is on that pytest line (in the implementer's commit
  2 or 3) and in §6's list. The `variant-ci-htcondor` leg shows the list passes with it.

**F2 — §5.2's prose contradicts the frozen release rule.**
- **Defect.** Two §5.2 sentences disagree with the frozen rows:
  - The "Later plans" bullet says `_host_service` "releases them (`JobStatus == 5 && HoldReasonCode == 1`) when
    it returns or raises". The frozen row 1 and the dispatcher's ruling on r1 exit items 2–3 require one Hold per
    plan before its first service submit (with a `reason=`), and one Release at that plan's next need of a
    worker, constrained on that reason. An implementer who follows the sentence fails row 1: the
    `release-at-return` and `release-any-user-hold` mutants are killed.
  - The `alive()` sentence names `HoldReasonCode == 1` alone, where exit item 3 adds the `HoldReason`.
- **Closed when** both sentences state the ruling. This is a plan edit, not a test change.

**F3 — two new frozen files are not `ruff format` clean (minor; cheap only before the tag).**
- **Defect.** `ruff format --check` on the files themselves reports two files:
  - `m69b_order.py`: the `with open(...), open(...)` line and the `claim = {...}` line;
  - `test_service_order.py`: the `assert waiting.is_set(), f"…"` line.

  The directory-level check hides this. Every other m69b frozen file is clean.
- **Closed when** `ruff format` is run on the two files before tagging. The change is whitespace only.
