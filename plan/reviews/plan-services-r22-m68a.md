# plan-services r22: m68a delta pass (submission scope, J2, readiness order)

**Verdict: NOT CLEAN. There is one design finding, K1 (unit m68a): the new per-run wrapper that records every plan-task future pins every consumed result in dask cluster memory until the run ends. Checks (a) through (c) pass.**

Delta read: `git diff --no-index --word-diff reviews/plan-services-r21-snapshot.md plan-services.md`. It touches D2, D10, the §3.1 `ServiceSet`, engine and driverless bullets, the `test_services_protocol.py` row and Fails-on, the §3.3 condor `host_service`, and the §3.4 dask `host_service` and m70 rows.

## (a) Submission scope: stated once, true of the code, stale-probe leg discriminates
- **Stated once.** The statement is in the §3.1 engine bullet ("A submission's scope is its run's `RunContext` … so no service, record or pending task of a submission outlives it or reaches another"). D2 and D10 point to it with "(§3.1)". The redundant D10, §3.1 and driverless sentences are deleted, and the remaining "overlap" hits are test rows only.
- **True of the code** (exec-main `submit/engine.py`):
  - `run` builds `ctx = self._context(uuid.uuid4().hex[:8], monitor)` once per call.
  - `submit` is `PlanQueue(self.run, …)`.
  - All four `_run_*` paths pass `ctx` as the first argument of `_leaf_task` and `_combine_task`, and the key carries `ctx.run_nonce` through `_key`.
  - Probe `probes/scope/probe_submission_scope.txt` S: two overlapping submissions gave 2 nonces over 22 tasks, with `key_carries_arg0_nonce=True`.
- **r20 stale-probe item: closed.** A probe submit registers `backend.cancel([fut])`, and the overlap leg asserts that "A's unanswered probe is cancelled before B's first task is leased (it never runs)". Probe C: the abandoned leg runs `['A-probe-0', 'B-first']` and the cancelled leg runs `['B-first']`. The leg discriminates whichever order the two probes queue in, because without the cancel A's probe runs before B's plan tasks either way.

## (b) J2: closed as decided
- The §3.4 dask `host_service` rule is now "the first [covering worker] that hosts none of this backend's live actors (its `key → (worker, future)` map, which `release_service` pops), else refused naming the worker table".
- The row asserts that the overlapping pair's actors are on different addresses and that both `host_service` calls return within `timeout_s`. It also asserts that an all-covering-workers-hosting call refuses. Fails-on adds "two actors on one worker".
- The premise comes from `probe_dask_first_cover_r21.txt`: first-cover gave `same=True, not ready within 5s`, and skip-hosting gave `same=False, ready after 0.01s`.

## (c) r21 readiness clause: applied
All three r21 exit items are now in the §3.1 driver-hosted bullet:
- "ready = the check passing and then `proc.poll() is None` (a pass with a dead child … fails at once naming its returncode)";
- the lock is "released in a `finally`, its wait outside `timeout_s`";
- the parenthetical now names "another driver process's on one host, only the post-check poll guards".

## Design finding

**K1 (m68a): the plan-task cancel wrapper "records each future", so every consumed leaf and combine result stays in dask cluster memory until `run` ends.**
- **Where:** the §3.1 engine bullet: "a `backend.cancel` of its plan tasks not done (the four `_run_*` paths submit through one per-run wrapper recording each future)".
- **Why it changes code:** three of the four paths deliberately drop a future once they have consumed it:
  - `_run_adaptive` and `_run_adaptive_windowed` call `outstanding.pop(fut)`;
  - `_run_fixed_windowed` calls `node_of.pop` and `ready.pop(a)`/`ready.pop(b)` when a combine takes its inputs.
  
  A distributed key is freed only when no client future references it. A wrapper that keeps every future holds every leaf and intermediate on the workers for the whole run. That brings back §A.3 #4 (high memory) on the streaming paths. Only `_run_fixed` already keeps all of `futs`.
- **Measured** (`probes/scope/probe_recorded_futures_r22.{py,txt}`, distributed 2026.8.0, 20 leaves of 1 MB each, each consumed and its local reference dropped):
  - `record=False`: 0 keys still in cluster memory;
  - `record=True`: 20.
- **Closed when:** the wrapper holds only futures that are not yet done, for example by discarding each one in its done callback under a lock. That is enough, because the stack cancels only futures that are not done.
- **Test that shows it closed:**
  - Setup: a dask-marked leg (`importorskip("distributed")`, run in the `test-dask` CI job) runs an adaptive plan of N ≫ slots leaves through `SubmitRunner(DaskBackend(LocalCluster))`. Its `next_tasks` records, at each call, how many of this run's `-leaf-` keys `client.who_has()` holds.
  - With the fix: the maximum is at most the in-flight slots.
  - Without the fix (record-every-future): the count grows to N, as in the probe.
  - The existing "third leaf `submit` raises" leg still pins the cancel itself.

## Exit items (constraints for the implementer; no round)
- **Overlap leg, nonces.** Assert that A's and B's `run_nonce`s differ. The "keys released are exactly those minted" check passes even with a shared nonce, because each key also carries `token_hex`. A raises before it submits any plan task, so "plan tasks' `RunContext` carry its own `run_nonce`" is a check on B only.
- **User-held scope.** Mint it the way `run` mints a nonce (`uuid.uuid4().hex[:8]`), so every key and probe-key form has one shape.
