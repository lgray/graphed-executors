# m69b plan review: §5.2 "Ordering" (939e49d), round 1

## Verdict: REJECT

One design finding is open (O1): the abort path misses a Ctrl-C that lands inside `close()`'s own drain, which is
where the documented `submit()` form waits now that `close()` keeps its contract. Everything else holds:

- Pilot deferral, the later-plan pilot hold and the claims-aware match are the smallest mechanism that meets the
  ruling and M4. No deadline and no knob is added.
- The rejected alternative (pilots submitted `hold = True`) cannot be used at either production site.
- The refreeze list is complete and minimal for the whole design, and each edit stays discriminating.

| Item | Result | Evidence |
|---|---|---|
| 1. Ruling + M4; rows (a) (b) (c) | (a) and (b) pass in principle. (c) passes for `run()` and `submit().result()`, but not for `submit()` followed by leaving the block → O1 | `probe_close_sigint_order_rv1.txt` |
| 2. Proportion | The design is the smallest. The alternative fails at lpc and lxplus | below; `probe_hold_order_rv1.txt` 3 |
| 3. Premises | Every premise is measured. One premise was implicit: a Hold matching no job returns, it does not raise | `probe_hold_order_rv1.txt` 1, 4 |
| 4. Refreeze list | Complete for the full design: the same five ids on macOS and the pool. Each edit is killed by its mutant | `probe_suites_order_rv1.txt`, `probe_refreeze_order_rv1.txt` |
| 5. New rows | Each row has a killing mutant (listed). Row 8 lacks the O1 form | below |
| 6. Commit sizes | Plausible. df4d059 (a fix of this size) added 251 lines; 4759ba8 added 509 | `git log --shortstat` |

## Findings

### O1 — Major: Ctrl-C while `close()` drains a submitted plan leaves its waiting service job, and any pilots, in the queue

- **Defect.**
  - §5.2 ends a wait only when `HTCondorRunner.__exit__` receives an exception.
  - The documented `with htcondor_runner(...) as runner: runner.submit(plan)` form leaves the block normally.
    `__exit__` then gets none, and `close()` waits for the plan without bound (M4: that is the contract).
  - The user's way out is Ctrl-C. Its `KeyboardInterrupt` lands in `PlanQueue.close()`'s `Thread.join`, inside
    `close()`. `SubmitRunner.close` never reaches `backend.close()`.
  - CPython 3.12's interrupted join marks the still-running plan thread stopped. `threading.py`
    `_wait_for_tstate_lock` releases the thread's lock and calls `_stop()`; its comment cites bpo-45274. So the
    interpreter exits without waiting for that thread.
  - Nothing removes the service job. Nothing removes the pilots either, when a later plan waits.
  - df4d059 avoided this by ending every wait in `close()`. M4 rightly removes that, so the abort path must now
    cover the drain itself.
- **Probe.** `probe_close_sigint_order_rv1.py`, on 40470e6's stand-in pool from the extra row. Every job stays idle.
  The stand-in submits its pilots at construction: cluster 70 is the pilots', 71 the service's. Each leg patches
  `HTCondorRunner` at run time. "plan" is §5.2 as written. "fix" adds `try: _plans.close() finally:
  backend.close()`. Output:
  ```
  leg=plan POLL_S=0.5: exited -2 0.1 s after SIGINT; Remove acts=[]
  leg=fix POLL_S=0.5:  exited -2 0.6 s after SIGINT; Remove acts=['Remove ClusterId == 70', 'Remove ClusterId == 71']
  leg=plan POLL_S=5:   exited -2 0.1 s after SIGINT; Remove acts=[]
  leg=fix POLL_S=5:    exited -2 0.1 s after SIGINT; Remove acts=['Remove ClusterId == 70']
  ```
  - The plan as written leaves both clusters queued.
  - Reaching `backend.close()` is not enough. The service job is removed by the waiting thread at its next poll, and
    at any `POLL_S` longer than the exit (production: 10 s) that poll never comes. 71 was removed at
    `POLL_S = 0.5` only because the poll won the race.
  - So the removal must not depend on the waiting thread getting another poll before the process exits.
- **Closed when** row 8 (Ctrl-C, minicondor, POSIX) gains a third form, and it passes:
  - The child runs `with htcondor_runner(...) as runner: runner.submit(plan)` and leaves the block normally, while a
    blocker leaves its server no room.
  - SIGINT is sent after the first "waits for a slot" line, so it lands in `close()`.
  - The child exits within 3 × `POLL_S`. The service job is in history unrun (`NumJobStarts == 0`). Nothing of the
    child is left in the queue.
  - The row must run at `POLL_S` ≥ 5 s, as the default 10 s does. At 0.5 s the "fix" leg passes only because the
    poll wins the race.
  - The "plan" leg (both clusters left) and the "fix" leg (the service job left) must both fail it.
  - The "Fails on" list gains "an interrupt in `close()`'s drain leaving a waiting job or the pilots queued".

## The judged items

**1.** The ruling holds: in plan 1 a server's job precedes the pilots' submit, and pilots are submitted only at the
first need after the announces. No deadline or knob is added. `N_WORKERS_WAIT_S` and `min_pilots` already exist.

- (a) `close()` drains, so a fresh job's first negotiation is no longer cut short.
- (b) r1's sizes: two 7168 MiB pilots and one 2048 MiB server in 15 973 MiB.
  - Plan 1: the server starts, then one pilot fits beside it.
  - Plan 2, both pilots running: whole − own = 1637 MiB < 2048, so it is refused.
  - No state waits on the runner's own pilots.
- (c) Both forms in the row end:
  - `run()`: the exit stack of `_host_service` removes the job, measured in `probe_sigint_exec_rv2.txt`.
  - `submit().result()`: `__exit__(KeyboardInterrupt)` calls `stop_waiting()`, then the drain.
- A third abort form does not end cleanly: O1.

**2.** The rejected alternative fails at both production sites:
- HTCondor refuses `hold = True` on a spooled submit:
  `Submit:-1:Cannot set hold to 'true' when using -remote or -spool` (`probe_hold_order_rv1.txt` 3).
- `SITES["lpc"]` and `SITES["lxplus"]` both set `spool=True`.
- Unspooled, it works (row 2: held 15 s in a free slot as `(5, 15)`, then running once released). So it would serve
  only `generic`.
- Holding right after the submit races the first negotiation.

I pick the planner's deferral. Ladder for the later-plan case:
- (1) It must exist. Without it, a later plan's server can wait forever on its runner's pilots, and M4 forbids
  ending that wait in `close()`.
- (2) The match reuses `match_refusal` and `_as_whole`, plus one schedd query.
- (3) Hold and Release are HTCondor's own.
  - Job priority does not help: an unmatchable job is passed over (`probe_order_fifo.txt` C).
  - A concurrency limit cannot express "room my running pilots hold".
  - A `Requirements` toggle through qedit is a hold with more steps.

**3.** Premises and their evidence:

| Premise | Evidence |
|---|---|
| An unmatchable job does not block later ones | `probe_order_fifo.txt` C |
| The engine starts services per plan | `probe_order_trace.txt` |
| A held pilot stays unmatched while room frees, and starts once released | `probe_order_claims.txt` 3. On a spooled job: `probe_hold_order_rv1.txt` 4, `(5, 1, 0)` 15 s after the blocker left, then running |
| The schedd ad names `RemoteHost` and `*Provisioned` | `probe_order_claims.txt` 4 |
| A Hold whose constraint matches no queued pilot returns (implicit, unmeasured until now) | `probe_hold_order_rv1.txt` 1: returns `TotalSuccess 0`, does not raise |

**4.** The planner's run walked the deferral only. The claim covers the whole design, so I re-aimed the instrument.
- The variant is `probe_variant_full_order_rv1.txt`: the planner's `variant_dag`, plus hold/release, the
  claims-aware match, `alive()`, `close()` without `stop_waiting`, and `__exit__`.
- macOS: 338 passed and 5 failed, the same five ids.
- Pool: 357 passed and 5 failed, the same five ids; the queue was empty afterwards. The m69b busy-pool row passes
  through the real Hold and the claims-aware match.
- Each edited id passes on the variant. Each is killed by the mutant of what it guards (`probe_refreeze_order_rv1.txt`):

| Edited id | Killing mutant |
|---|---|
| m68a failed-spool | `spool-leaves-cluster` |
| m68b secret | `service-before-check`: a `graphed-service-` submit before the input check |
| m68b order ×3 | `pilots-at-construction` (the unpack of one submit). `url-not-task-server` fails the 200 announce, so dropping `cfg["url"] == pilot_desc[…]` loses no guard |

**5.** The killing mutant of each new row:

| Row | Killing mutant(s) |
|---|---|
| 1 | Pilots at construction. Pilots submitted between the service submit and its announce. Pilots resubmitted per plan. No Hold in plans 2 and 3 |
| 2 | The first need bounded by `timeout_s` |
| 3 | Deferral applied to `driver` or `LocalPilots` backends, or not applied to `announced` |
| 4 | The deferred submit's cluster removal unregistered. `close()` leaving the secret |
| 5 | `runner-close-stop` (df4d059). `exit-no-stop` |
| 6 | `runner-close-stop`. r2 measured that df4d059 fails it |
| 7 | Pilots at construction (plan 1 self-starves). A whole-slot match (plan 2 waits forever) |
| 8 | No `__exit__` override (the `submit().result()` form hangs). Pilots at construction ("submitted no pilot job") |

Row 8's third form is O1.

## Exit-round items (constraints for the dispatch; no round needed)

1. **The frozen recorders cannot answer a Hold.** Every frozen fake `JobAction` (m67, m68a, m68b, m68b's DAG
   harness, m68c) has only `Remove`; with pilots present, a Hold raises `AttributeError`, as the
   `pilots-at-construction` leg shows on the secret id. The recorder's `query` also pops a scripted answer, so the claims query takes one. Row 1 is built on
   m68a's recorder, so the new m69b file adds `Hold`/`Release` and scripts that answer itself. m68a's harness stays
   frozen.
2. **A gap between two services of one later plan.** The pilots are released when service A announces and held
   again before service B's submit. A negotiation in between lets a queued pilot start, and B can then be refused
   beside it. That is a refusal, never a hang. Releasing at the next need of a worker instead closes the gap and
   gives every plan one rule. The dispatcher decides.
3. **`HoldReasonCode == 1` also matches a hold the user placed.** Hold with a `reason=` and constrain both the
   Release and the hold count in `alive()` on that `HoldReason`.
4. **The pilot-hold count goes in `CondorPilots.alive()`, not in `counts_as_alive`.** `counts_as_alive` is shared
   with `_await_announce` and `driverless.py`, where a held job must still raise.
5. **`HTCondorBackend.n_workers()`'s docstring ("never waits") changes**: the first need waits.
