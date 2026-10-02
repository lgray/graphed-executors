# m69b plan review: §5.2 "Ordering", round 2 (delta 902d11f..413aa9a)

## Verdict: REJECT

- **O1 is closed.** Its premise is measured below.
- **One design finding is open, O2.** The repair rests on "`ServiceJob.stop()`, idempotent across threads".
  Today's `stop()` is not that, and the plain reading of "idempotent" (a second call returns at once) leaves the
  same leak O1 closes. The repair is one phrase in §5.2 and one extra row.
- **The gap decision holds.** The dispatcher's ruling (queued pilots stay held across all of a later plan's services
  and are released at that plan's next need of a worker) is not wrong. Every path after a hold reaches either a need
  (`_probe`'s `n_workers()`, or a task `submit()`) or `close()`, and `close()` removes the pilots. A plan whose
  service is refused leaves its pilots held until the next plan's need, which is harmless.

## O1 — closed

`probe_close_sigint_order_rv2.py`, on the stand-in pool from round 1 (40470e6), at `POLL_S = 5`. SIGINT lands in
`close()`'s drain in the `with … runner.submit(plan)` form. Two runs per leg:
```
leg=repair POLL_S=5.0:               exited -2 0.6 s after SIGINT; submitted={'70': 'pilots', '71': 'service'} removed=['70', '71'] queue-left={}
leg=close-signals-waiter POLL_S=5.0: exited -2 0.6 s after SIGINT; submitted={'70': 'pilots', '71': 'service'} removed=['70'] queue-left={'71': 'service'}
```
(Each line repeated identically on the second run.)
- **The repair works.** `repair` records the job at submit, and `backend.close()` stops every recorded job in the
  calling thread before the server and pilots. The service job is removed unrun, and the queue is empty.
- **The mutant still fails.** `close-signals-waiter` leaves the service job queued.
- **So row 8's third form discriminates at `POLL_S` ≥ 5.**

## O2 — Minor design: `stop()` from two threads; the second caller returns before the removal is done

- **Defect.** `probe_stop_threads_order_rv2.py` compiles 40470e6's `ServiceJob.stop` and calls it from two threads,
  with the `release_quietly(..., _remove)` callback `_submit` registers. Output:
  ```
  3.12.10 (GIL) race x20000: raised=0; removals per trial: {1: 20000}
     early: B returned at 0.055 s, A's removal completed at 0.210 s -> B returned BEFORE the removal
  3.14.6 (free-threaded) race x20000: raised={'IndexError': 1}; removals per trial: {1: 20000}
     early: B returned at 0.053 s, A's removal completed at 0.210 s -> B returned BEFORE the removal
  ```
- **What is fine.** There is never a double removal.
- **The raise.** On 3.14t, `ExitStack.close()`'s check-then-`pop()` raised `IndexError` once in 20 000 trials. Every
  call site wraps `stop()` in `release_quietly`: the waiter's exit stack, close(), and the engine's
  `release_service` callback. So it is logged, not raised.
- **The leak.** The early return can leave the job queued:
  - The waiter's `POLL_S` wait can end while `close()` is in its loop. It then sees `_closing` and enters `stop()`.
  - If it wins the pop, `close()`'s `stop()` returns at once.
  - `close()` then finishes: about 0.5 s of server shutdown, and on plan 1 no pilots to drain.
  - The interrupted join already marked the waiter stopped, so the process can exit before the waiter's `act`
    completes.
  - An early-return flag, which satisfies "idempotent", keeps this window. The plan's own sentence ("No removal waits
    on a waiting thread's") is then false in that window.
- **Repair (§5.2, one phrase).** Replace "idempotent across threads" with "serialized: from any thread, a second
  call returns only after the first call's removal has run, and never raises".
- **Closed when** an extra row passes:
  - Two threads call `stop()` on one job whose removal blocks on an `Event`.
  - The second caller has not returned while the first's removal is blocked.
  - After the event is set, both return, one Remove is `act`ed, and neither raises.
  - The row is deterministic, not a race. 40470e6's `stop()` fails it (B returns at once), and so does an
    early-return flag.
