# Review r16: `plan-services.md`, unit m68a (delta over the r15 snapshot)

**Verdict: NOT CLEAN. 1 design finding (N16).**
- r15's N14 and N15 are closed at their causes.
- N16 is not an ExitStack or failure-path member, so the adjudication's stop rule does not route it to the owner.
- The count fell again (r14 4, r15 2, r16 1), so this is not non-convergence under the rule.
- The delta has a finding, so no whole-unit pass was run. A walk of `SubmitRunner`'s surface was run instead (see "Shape").
- Code: exec-main b966a28, graphed origin/main 6e9e55e.
- Probe: `probes/class/probe_concurrent_runs_r16.{py,txt}`. It left no process running (`pgrep` empty).

## r15 findings, checked at their causes
- **N14 (resolve reaches only the outermost process): closed.**
  - The fix is §3.2's "resolve walk", which is option (a):
    - graphed adds `Resolvable` and `resolve_services(plan, value)`.
    - `_PartitionReduce` forwards to `reduce`, and `_Collated` forwards per name.
  - The set of composites comes from `git grep -n "def bind_services" -- python` on origin/main. It returns `_PartitionReduce`, `_Collated`, `_WritePart`, `_VariedWritePart`, `CheckedExternal` and `_PluginEvaluator`, the same set the plan names.
  - The `-2` tag precedent exists: `freeze-preserve-m68-2` is on origin.
  - The engine now calls graphed's function (engine line). The frozen legs cover `collate` and `aggregate_plan`.
- **N15 (`start_services` skips the pilot wait): closed.**
  - The wait moves into an `HTCondorRunner.start_services` override. `grep -rn "(SubmitRunner)" src` → `backend.py:154` only.
  - `driver.main`'s explicit `wait_for_pilots()` sets `_waited` first (`driver.py:108`, `backend.py:173-176`), so the override does not wait twice.
- **New `require_bound` clause: sound.**
  - graphed's `require_bound` exists (`services.py`), and `SequentialRunner.run` calls it first (`core/execution.py:536`).
  - The regex population is `engine.py:296`, `backend.py:179`, `local/executors.py:757`, `transport_run_plan` and `parsl_run_plan`.
  - The `run_repartition`/`run_join` functions take blocks, not plans. Checked `dask_backend/api.py:51` and `local/shuffle.py:522`.
- **m68b and m70:** §3.3 and §3.4 are byte-identical to the r15 snapshot. Every `host_service` there still returns `(endpoint, identity)` (L414-415, L459-482).

## Design finding

**N16. The runner's held service set is shared by runs that `SubmitRunner` lets overlap, and nothing orders them.**
- **Where:** the §3.1 engine line (L272-279). It says `start_services` "starts … the specs … the set does not hold, by name … and hands the stack to the set only after the probe passes".
- **The race:** the check ("does the set hold this name?") and the hand-over are seconds apart, because start, readiness and the probe all happen between them. If two runs both find a name not held, each starts its own instance. The plan does not say what the second hand-over of a held name does:
  - if it replaces the first, the first instance is orphaned past `close()`;
  - if it is kept alongside, there are two instances, `Endpoints`/`statuses()` hold one of them, and a run may bind the other.
- **Measured** (`probes/class/probe_concurrent_runs_r16.txt`):
  - `SubmitRunner(ThreadBackend(4))`: a queued `submit(plan_a)` and a direct `run(plan_b)` overlap. Result: `True`.
  - Control, `ThreadExecutor(4)`: result `False`. Its `_run_lock` (`local/executors.py:757-759`) serializes runs "because the kept pool and the peer state belong to the executor, not to the run" (`docs/design.rst:245`).
  - `SubmitRunner` holds no lock (`engine.py:256-330`).
- **This is an instance of the r16 rule itself.** "Each obligation a run gains is kept by the code that already keeps its model." The model for state a runner keeps across runs is `_BaseExecutor`'s kept pool and its `_run_lock`. The held set is that kind of state, and it does not take over the lock.
- **Cut, one decision for the implementer:** `start_services` holds one runner-level `threading.Lock` from its read of the held names through the hand-over. A second run for the same name then waits and finds the name held.
  - Serializing all of `SubmitRunner.run` would also close N16. But it changes the overlap that runs have today, which nobody asked for.
- **Closed when:** a frozen `test_services_protocol.py` leg does the following on one `SubmitRunner(ThreadBackend)`:
  - Two threads each run a plan that declares the same new managed spec.
  - The recipe's child sleeps about 1 s before it listens, so both runs are inside `start_services` together.
  - Assert that exactly one managed pid was started, and that both spies were bound to the same endpoint.
  - Without the lock, two pids start.

## Shape (the class behind N7..N16)
- **The operation:** m68a turns `SubmitRunner` from a per-run engine into a holder of resources that outlive a run: the held set, keyed by name, released at `close()`.
- **What each round then finds:** one more invariant of the runner that the held state must meet:
  - the failure path (N7-N9, cut once by the ExitStack rule);
  - the key across plans;
  - the value outliving the service (N10, N14);
  - a subclass precondition (N15);
  - overlapping runs (N16).
- **What r16's rule does and does not do:** it names the right cause, but it was applied to the instances reviewers found. It was not applied by walking the runner's surface.
- **The walk, done here once, over `SubmitRunner`'s surface** (`engine.py:256-330`, `_plan_queue.py`, `HTCondorRunner`, `driver.main`):
  - `__init__`/facades: `services=`, covered.
  - `submit`/`PlanQueue`: N16.
  - `run`'s cancel early return: exit item below.
  - monitor/control: nothing is held.
  - `close`: covered, set before backend.
  - subclass: N15, closed.
  - `driver.main` phases: covered.
  - The walk found no further member.
- **Owner option, not a finding:** a per-run lifetime removes the held-set class outright. `run` would start, resolve and release its own services, and the adjudication's stack would close at the end of `run`. That deletes the name key, the unequal-spec refusal, N16's lock and the ordering in `close()`. It became possible when r15 moved resolution inside `run` (N10/N14).
  - Its cost is a restart per plan: Triton loads its model on every restart. Nobody has measured that cost.
  - The runner lifetime is the analogue of `persistent=True`, "paying the spawn cost once" (`docs/design.rst:207-213`).
  - Three lines:
    - Task: services that live exactly as long as the runs that need them.
    - By hand: start in `run`, stop at the end of `run`.
    - Rung: (2), `run`'s own stack, unless the owner wants services kept warm across plans. Keeping them warm is what the runner-held set buys, and N16's lock is its price.

## Exit-round constraints (to the implementer)
- **Resolve through the bound plan.** `resolve_services(plan, value)` must take the plan that `bind_services` returned. r14's text said "the bound process's". The `test_driverless_endpoints.py` leg discriminates this, because its `resolve_services` GETs the endpoint.
- **Cancelled runs start nothing.** `run` checks `control.state is CANCELLED` before `start_services`.
- **The 1 s wait bound.** `HTCondorBackend.wait_for_pilots(n, timeout=N_WORKERS_WAIT_S)` binds its default at `def` time (`backend.py:81`). The N15 leg therefore wraps `backend.wait_for_pilots` with `timeout=1`. Patching the constant would not bound the wait.
- **§7 wording.** "graphed: the m68 PR (~360 src…)" is already merged: graphed#61 is `cf4520d` on main. Only the resolve walk is still to be written.
- **Carried from r15:**
  - `ExecResult.value` is what `resolve_services` returns.
  - D2's `ServiceUnavailable` sentence versus the frozen raw `OSError`: the table governs.
  - The injected `ServiceUnavailable` for a check that never passes.
  - One shared `CLOSE_WAIT_S` deadline per launcher.
  - The LIFO order of `launcher.stop`.
  - `CondorPilots` records `_schedd` together with `cluster`.
  - `proc.poll()` as the Windows witness.
  - m70's "a stop never acknowledged" wording.
  - E15, "which holds the traceback".
