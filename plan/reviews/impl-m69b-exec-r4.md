# m69b executors implementation review, round 4 (PR #44, delta 67ba8f2..0008028)

## Verdict: REJECT

O1 and O2 are closed. The traces that showed them now show the plan's order (below). Two design findings remain:
- **G1 (Major).** A pilot move that a need asked for during a server's wait runs when that server ends, even when
  it ends because the run is closing. With a need recorded, Ctrl-C submits a pilot cluster. A Ctrl-C in `close()`,
  or a direct `backend.close()`, leaves that cluster queued after `close()` has returned. 78df2e9 introduced this.
- **G2 (Major, needs the plan's decision).** The gate covers one `host_service` call, not a plan's services. A need
  between two services of one later plan releases that plan's hold, and the next service holds again.

Both findings have one cause, stated under G2. One test gap (T1) is also open.

| Gate | Result | Evidence |
|---|---|---|
| frozen tree vs `freeze-m69b-fixup2` (22df587; m68a/m68b tags at eb8691d) | byte-equal: 0 of 256 files differ. de99c57, 78df2e9 and 0008028 touch no `tests/frozen`. 22df587 changes only the ruled row's two comparisons and the dispute's status (control: 67ba8f2 differs in `test_service_order.py`) | `probes/m69b/frozen_exec_rv4.txt` |
| macOS py3.12, frozen + extra, `--cov-branch` | 1154 passed, 39 skipped. Lowest file 93.02 % (`local/shuffle.py`, as in r3; attempts.md's "98.33 % minimum" is not what this venv measures, but the gate is 90 %). diff-cover: 44 lines, 0 missing | `probes/m69b/gates_exec_rv4.txt` |
| Linux pool (graphed a51bee4), CI test-htcondor line | 528 passed, 10 skipped (dask, parsl, coffea, Triton), queue empty afterwards. htcondor scope per-file gate: lowest 98.80 % (`server.py`). diff-cover: 264 lines, 0 missing | same |
| test-hgg equivalent | 73 passed, 5 skipped (dask, classad2, the htcondor bindings) | same |
| ruff, ruff format, mypy (also win32), sphinx -W | clean | `probes/m69b/lint_integrity_exec_rv4.txt` |
| integrity `scan_diff` | `67ba8f2..0008028`: 0 findings. `upstream/main...0008028`: the known advisory `ci_config_modified`. Control: 2 | same |

## Closed

**O2.** I re-ran `probe_hold_release_exec_rv3.py` at 0008028 (`probe_hold_release_exec_rv4.txt`). Plan A's task no
longer releases plan B's hold while B's server waits:
```
    0.00s act             7001 Hold ClusterId == 7001 && JobStatus == 1 graphed: a service of this run waits for a slot
    0.00s submit-service  7002 planB-a5c1d120d840516c
    1.06s mark             plan B's server waits; plan A submits a task
    2.06s mark             plan B's server still waiting: True
    2.06s act             7002 Remove ClusterId == 7002 graphed: run closed
    2.52s act             7001 Release ClusterId == 7001 && JobStatus == 5 && substr(HoldReason, 0, 47) == …
```
At 67ba8f2, the Release came at 1.06 s. Here it comes at 2.52 s, once B's server has ended. That server ended
because of the probe's `close()`, which is G1's path.

**O1.** I re-ran `probe_driver_order_exec_rv3.py` (`probe_driver_order_exec_rv4.txt`). `driver.main` exits 0, and
the order is now the plan's:
```
    0.00s mark           ServiceSet asks for the SERVICE node's announce
    3.05s announce       svc0
    3.07s submit-pilots
pilots submitted after the SERVICE node's announce
```

**The gate sits at the operation.** Every deferred submit and every release goes through `_move_pilots`. It has
two callers: `_need`,
which every `n_workers()`, `submit()` and `wait_for_pilots()` poll reaches, and `_announcing`'s `finally`.
`_host_service` holds the pilots itself under `_pilots_lock` and raises no need. `_await_announce` and
`match_refusal` raise none either. So no path moves pilots while a call is counted.

The driverless `pilots="local"` form starts its pilots at construction (`deferred` is False), so its gate never has
anything to move. That form needs nothing: its pilots run in the driver's slot.

**The mutants you named: all killed but one.** Results are in `mutants_exec_rv4.mac.txt`; the control passes.
- Killed: `release-on-any-need`, `last-server-does-not-move`, `driver-waits-before-services`,
  `wait-inside-the-run-try`, `closing-after-ad-check`, `any-wait-is-the-first-need`, `no-wait-is-the-first-need`,
  `unlink-every-stop` and `unlink-outside-the-lock`. The last two die on the row's "a later stop repeats nothing" check;
  the Windows unlink race itself shows only on Windows, and CI on 0008028 is that confirmation.
- Not killed: `deadline-from-the-call`. See T1.

**r3 exit items.** Items 1, 2 and 4 are closed: the message assertion, the `_waited` row, and the docs.
Item 3, `record-after-submit`, still survives. r3 left that row optional, and the design stands by reading.

**Known limit: a failed deferred move is only logged. Reachable, but not a design finding.** Take a plan A whose
needs were recorded while B's server waited. The next need retries the move: B's probe after its announce, or A's
engine, which re-reads `n_workers()` every `_PAUSED_WAKE_S` (0.05 s) through `_fill`/`_task_slots` while its
window holds work. So A sits only when all of these happen together:
- B's server ends by raising, so no probe follows it;
- the Release act fails at that moment;
- no pilot is running;
- every task of A is already in flight.

The first two can share one cause, a schedd outage: `job.ad()` raising ends B's wait, and the act then fails too.
`alive()` counts the held pilots as alive, so A is not failed as pilot-less. Ctrl-C still removes everything.

Each remedy costs more than the case: raising in B fails a plan whose server came up, and making A's need wait
blocks A while B waits on a busy pool. Drop, as not worth its cost.

## Findings

### G1 — Major: a server that ends because the run is closing submits the pilots a need asked for

- **Defect.**
  - `_announcing`'s `finally` runs `_move_pilots` when `_wanted` is set. It does so however the call ended,
    including by `_await_announce`'s "still waited for a slot when the runner closed". `wait_for_pilots`'s poll
    calls `_need()` after a close in the same way.
  - Neither `_move_pilots` nor the poll reads `_closing`, and `CondorPilots.start` has no stopped state. A deferred
    submit after `backend.close()` therefore makes a cluster that nothing removes.
  - At 67ba8f2 the same need submitted at once, which was O1/O2, so `close()` still removed it.
  - What breaks:
    - frozen row 8, "the child submitted no pilot job … exits within 3 × `POLL_S`", in a form that adds one need;
    - the plan's "`close()` … An exception anywhere … removes every job the runner submitted before it leaves
      `close()`".
  - The amendment's sentence ("the last of them to return or raise then submits or releases") states the rule with
    no exception for closing. The plan needs "unless the backend is closing" there.
- **Reachable through the runner.**
  - In the first plan, a user thread can call `runner.wait_for_pilots()` while a submitted plan's server waits.
    A direct `runner.run(plan)` beside a submitted one does the same, and m68b's live row runs that form.
  - Either one polls `_need()`, which sets `_wanted`.
  - In a notebook, a Ctrl-C landing in `close()` leaves the process running, so the leaked cluster sits there.
- **Probe.** `probe_close_need_exec_rv4.py` drives a runner over `OrderSchedd`. The server stays idle, and a real
  SIGINT is sent 1 s after the mark. Output, condensed to the events after the mark (in full in
  `probe_close_need_exec_rv4.txt`):
  ```
  == result-control          … 2.53s act Remove 7001 · 3.00s KeyboardInterrupt left the block
    pilot clusters submitted=[] left in the queue=[]
  == result-need             … 2.52s act Remove 7001 · 2.52s submit-pilots 7002 · 22.59s act Remove 7002 · 23.04s left the block
    pilot clusters submitted=[7002] left in the queue=[]
  == close-control           … 2.06s act Remove 7001 · 2.50s KeyboardInterrupt left the block
    pilot clusters submitted=[] left in the queue=[]
  == close-need              … 2.06s act Remove 7001 · 2.50s left the block · 2.52s submit-pilots 7002
    pilot clusters submitted=[7002] left in the queue=[7002]
  == direct server raised=[… still waited for a slot when the runner closed …] need thread alive 3s after close=True
    1.06s act Remove 7001 · 1.50s close() returned · 1.51s submit-pilots 7002
    pilot clusters submitted=[7002] left in the queue=[7002]
  ```
  - In the result form, the exit takes 20 s longer than the control: `CondorPilots.stop` waits `CLOSE_WAIT_S`
    (2 × the server's `POLL_S` of 10 s) for the idle pilots it just submitted.
  - In the direct form, the waiting need now runs `N_WORKERS_WAIT_S` from that post-close submit.
- **Closed when** the three need cases of `probe_close_need_exec_rv4.py`, as recorder rows, show all of:
  - `submit-pilots` never comes after the SIGINT or after `close()`;
  - the result form leaves the block about as fast as its control;
  - the direct form's need raises within about a second of `close()` (`_await_announce` ends at close in the same
    way), instead of waiting on a submit that will not come.

  The controls stay as they are.

  A cut that also refuses releases once `_closing` is set would strand a queued plan. After `stop_waiting()`,
  `PlanQueue.close()` still runs queued plans (`shutdown(wait=True)` does not cancel pending futures), and such a
  plan may need the held pilots.

### G2 — Major (needs the plan's decision): the gate spans one `host_service` call, not a plan's services

- **Defect.**
  - §5.2 "Later plans": the queued pilots "stay held across all of that plan's services". Frozen row 1 asks for one
    Hold and one Release per later plan.
  - `ServiceSet.start` resolves its specs one after another (`[self._resolve(spec, stack) for spec in self.specs]`).
    `_serving` is 0 between two calls, so a need landing there releases the hold, and the next `_host_service`
    holds again.
  - The gap is whatever runs before the next call. That includes a site leg's `check_ready` (LPC's profile names a
    `triton` endpoint) and a driver-hosted spec's readiness wait, each bounded by `timeout_s`.
  - A plan beside it whose window holds work calls `n_workers()` every 0.05 s, so a gap of that size is hit.
  - A pilot that starts in the gap is counted by the next service's claims-aware match. If it took the room that
    service needs, the service is refused with `ServiceUnavailable` where the plan would have waited.
  - The amendment's own wording, "no `_host_service` … in progress", allows this, so the plan contradicts itself
    here.
- **Probe.** `probe_set_gap_exec_rv4.py` runs a later plan's two-service `ServiceSet` with a need every 0.1 s from
  another thread. Service 2's site leg is a listener that never answers, with `timeout_s=2`. Output
  (`probe_set_gap_exec_rv4.txt`):
  ```
    0.01s act             7001 Hold ClusterId == 7001 && JobStatus == 1
    0.01s submit-service  7002 planB-d850d16d24332aba
    2.01s announce         planB-d850d16d24332aba
    2.02s act             7001 Release … HoldReason …
    4.03s act             7001 Hold ClusterId == 7001 && JobStatus == 1
    4.04s submit-service  7003 planB-919ad3674535575c
    6.05s announce         planB-919ad3674535575c
    6.06s act             7001 Release …
  inside the set: Holds=2 Releases=2 service submits=2
  ```
- **One cause for G1 and G2.** The gate decides from `_serving`, the count of `host_service` calls in flight. That
  count stands in for the two states the plan's rules name:
  - a plan's services being started, which is one `ServiceSet` resolve spanning several calls;
  - the run ending, which is `_closing`.

  So a move fires in the gap between a set's calls, and at a server's end that the close caused.

  The cut is to make the gate read those two states:
  - count `ServiceSet` resolve phases in place of calls, for example through an optional backend context that
    `ServiceSet.start` enters around its `_resolve` loop. The `_probe` stays outside that context, since it needs a
    worker itself;
  - once `_closing` is set, submit no pilot and end the waits that depended on one.

  In `src`, `ServiceSet` is constructed in two places, `SubmitRunner._run_scoped` and `driver.main`, and
  `ServiceSet._managed` is `host_service`'s only caller.
- **Closed when** `probe_set_gap_exec_rv4.py`, as a recorder row, shows one Hold and one Release inside the set,
  with the Release after service 2's announce. Today it shows two of each.

### T1 — Minor: the deadline row cannot tell "from the submit" from "from the call"

- **Defect.** `test_a_need_beside_a_waiting_server_counts_its_timeout_from_the_pilots_submit` uses a 0.2 s timeout
  and checks only the message.
  - Mutant `deadline-from-the-call` (`now > called + timeout`, still only once something is submitted) survives.
    Under it, a need deferred longer than its timeout raises at the first poll after the submit, giving the pilots
    no time to start. That is what "counts from that submit" exists to prevent.
  - The row does kill 67ba8f2's form, where the deadline from the call also runs while the submit is put off
    (`deadline-from-the-call-unguarded`, killed).
  - The `max` has no row on its other side either. `deadline-from-the-submit` (`now > submitted + timeout`)
    survives `test_m69b_schedulable.py`, the gate file, the four recorder rows and m66/m67 frozen + extra. Under
    it, a later `wait_for_pilots` on pilots submitted more than `timeout` ago raises at its first poll.
- **Closed when** both sides of the `max` have a row that times the raise:
  - the deferred need (for example timeout 1.0 s, deferred more than 1 s) raises about 1.0 s or more after
    `stop_waiting()`, not at the first poll after the submit;
  - a wait called more than `timeout` after the pilots' submit, with no pilot live, raises about `timeout` or
    more after the call.

## Exit-round items (constraints for the next dispatch; no round needed)

1. **Docs.** `htcondor.rst` "Schedulability" states the gate per call: "a need that comes while one of its servers
   waits to announce is put off until the last of them has announced or failed". Its two bullets should say what
   the G1/G2 cut makes true (a plan's services, and no pilot submitted once the run closes) in the same commit.
2. **Plan text.** The 5aa9413 sentence needs the closing exception (G1) and the span you choose (G2). That is a
   plan edit that goes with the dispatch, not an implementer item.
3. **`record-after-submit`.** Unchanged from r3: a row is optional.
