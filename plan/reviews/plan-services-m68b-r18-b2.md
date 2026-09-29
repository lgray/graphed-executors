**CLEAN**

# Review r18-B2: plan-services.md §3.3 part B2, delta round after r17-B2

Snapshot: `plan/reviews/plan-services-m68b-r18-b2-snapshot.md`. Delta read: `git diff --no-index --word-diff
plan/reviews/plan-services-m68b-r17-b2-snapshot.md plan/plan-services.md` and `git diff 6000b48 --
plan/probes/m68b/condor_surface/RESULTS.md` (the appended section with rows S-19 and D-08a). Code checked:
graphed-executors `c2298d7` (`htcondor_backend/driverless.py` `RunHandle._poll`/`result`, `sites.counts_as_alive`,
`docs/htcondor.rst` 276–296).

No design finding. Two exit items are appended under "## r18-B2 exit items" in `m68b-exit-items.md`.

## M45-B2 is closed at its cause
- **Every DAGMan state that B2 can meet now has a rule** (L644–650). The rules are:
  - JobStatus 3 → `removed` and 5 → `held`, from DAGMan's own ad as in m67.
  - JobStatus 1/2 → one driver-node query: `held` (other than spooling), `running`, else `queued`.
  - JobStatus 4, queued or in history → the latest driver try, the highest `ClusterId` from
    `history(<driver-node constraint>, [...], match=3)`.
- **The rules agree with the matrix rows.**
  - L-01: an unspooled DAGMan leaves the queue at completion. The queued-4 case is reachable only in the recorder, and
    the plan now gives it a rule that the leg exercises.
  - D-07: held is read from the node query, never from `DAG_*`.
  - D-08: each try is a new cluster, and `RETRY driver 2` means at most three ads.
  - Q-03: history returns ads in recorded order, and "highest `ClusterId`" makes that order irrelevant.
  - D-05/D-06: no DAGMan `ExitCode` or `DAG_Status` is read.
- **The rules fit m67's code.**
  - `_poll` today maps queued 4 by the DAGMan ad's own `ExitCode`.
  - `result()` retrieves whenever `in_queue and spool` (`driverless.py:74-76,99-100`). The `dag=True` rule replaces
    both.
  - The "held other than spooling" clause reuses `counts_as_alive`'s `HoldReasonCode` test.
- **The spool leg now discriminates** (L708). A queued DAGMan ad at 4, beside a driver history ad with `ExitCode 0`
  and a `result.pkl`, must give `done` and return the value with no `retrieve` logged. Each wrong implementation
  fails it:
  - Reading (a), queued 4 read as running or queued, fails "done".
  - Reading the DAGMan ad's own `ExitCode` fails "done" whether the fixture's ad has `ExitCode 1` or none.
  - Keeping m67's `in_queue and spool` retrieve fails "no retrieve".
- **The `dag=False` control really runs m67's path.** m67's `_poll` returns `done` or `failed` for any 4. Both reach
  `retrieve` under `in_queue and spool`, so the control holds whatever `ExitCode` the fixture gives.
- **The added `JobStatus 1`, no driver ad → `queued` leg pins the idle branch.**

## r17-B2 exit items: all taken
- History read bound: `match=3`, with the reason (L648).
- Recorder order: the highest-`ClusterId` ad is returned last (L708).
- `sh` sub-leg: `skipif(shutil.which("sh") is None)` (L708).
- Docs commit: it now carries m67's changed behaviour, the killed-driver retry, the `result()` message and the
  "killed" row in the exit table at `docs/htcondor.rst` 279–296. That table exists at those lines in `c2298d7`.
  Its size is ~190, and §7's ~1.5k total still holds.
- `announce_only` default: `[]` reads as `{}` (L626 agrees with §2 L168, and `run.get(...) or {}` accepts both).
- `job_root` definition: "read and write" (L581).
- Signal-retry citation: `probe_r17_b2_sigretry.txt`, now row D-08a in RESULTS' appended section. The preamble
  (L436–437) points to that section.
- Fixture version citation: `probe_r17_b2_fromdag_wheel.txt`.

## Other delta
- **The shared "Secrets"/inputs edits are B1's** (the `{python}` and `argv[0]` rules, relative `transfer_input_files`
  entries, and an `env.tgz` symlink in `initialdir`). As they bind B2's watch-mode SERVICE nodes, they add nothing a
  DAG node cannot meet:
  - `initialdir` is the absolute `service-svc<i>/` under the DAG dir.
  - The `env.tgz` symlink is followed at submit on the submit host, where `job_root` holds the target.
  - No `graphed-secret` is listed in watch mode.
- **RESULTS' appended section contradicts nothing B2 relies on.** It lists the superseded consequence lines and rows
  S-19 and D-08a.

## Evidence
No new probe was needed: the closure rests on existing rows L-01, Q-03, D-07, D-08 and D-08a. No container was
started, and scratch `/tmp/claude-0/review-r18-b2/` was not created.
