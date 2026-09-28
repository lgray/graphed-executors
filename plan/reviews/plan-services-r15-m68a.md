# Review r15: `plan-services.md`, unit m68a (delta over the r14 snapshot)

**Verdict: NOT CLEAN. 2 design findings (N14, N15).**
- Both findings sit in seams that the r14 repair added. Neither is an ExitStack member, so the adjudication's stop rule does not apply to them.
- The count fell from r14 (4) to r15 (2), so this is not non-convergence.
- The delta has findings, so no whole-unit pass was run.
- Code checked: exec-main b966a28 and graphed origin/main 6e9e55e.
- Probes are in `probes/class/*_r15.{py,txt}`. They were read-only, and no process outlived its run.

## r14 findings, checked at their causes
- **N10 (result outlives the job's services): closed for a plan whose outermost process is the backed one.**
  - `run` resolves the value while the services are up (engine line).
  - `driver.main` pickles the value only after it is resolved (§3.1 driverless bullet).
  - The driverless frozen leg loads `result.pkl` after the job has exited.
  - The part that remains open is N14.
- **N11 (m68a needs histogram code that does not exist yet): closed.**
  - The m68a driverless leg now uses `recipes.http_server` with a resolving spy.
  - The in-job histserv leg moved to m69b's `test_histserv_managed.py`.
  - §6 installs histserv for `test-htcondor` only from the m69b PR on.
- **N12 (service-phase exceptions exiting 3): closed at the cause, by phase.**
  - `start_services` runs after `wait_for_pilots()` and outside the `runner.run` try. That try is `driver.py:110-113`. Its outer `except` exits 1 (`driver.py:120-121`).
  - `_exit_code` is unchanged.
  - Two frozen legs pin exit 1: port range held → exit 1 with `OSError`, and a probe `submit` that raises worker loss.
- **N13 (a raising `launcher.stop` skips `server.shutdown`): closed.**
  - `HTCondorBackend.close`, `LocalPilots.stop` and `CondorPilots.stop` now each close the stack they kept.
  - The sites row has a leg for this: a raising `stop` still frees the port.
- In m68b and m70, every `host_service` still returns `(endpoint, identity)`, as D10 requires (L392-395, L437-451).

## Design findings

**N14. `resolve_services` only runs on the outermost process. graphed's composite processes pass `bind_services` down to their parts but not `resolve_services`.**
- **Where:** the §3.1 engine line (L276-278) says: "the bound process's `resolve_services(value)` when that hook exists (duck-typed like `bind_services`)". D8 (L100-101) relies on it.
- **The model it cites works differently.** `bind_services` is a traversal. graphed's own wrappers forward it:
  - `_PartitionReduce.bind_services` binds `reduce` (`aggregate.py:124-127`).
  - `_Collated.bind_services` binds each sub-process (`aggregate.py:381-382`).
  - Both go through `Bindable` and `bind_externals` in `services.py:158-180`.
  - Nothing forwards `resolve_services`.
- **`collate` is built to carry service-backed plans.** It takes the union of the plans' `services` and refuses a name declared with two different specs (`aggregate.py` `collate`).
- **Measured** (`probes/class/probe_resolve_reach_r15.txt`):
  - Collating two backed spy plans: `bind` reaches both sub-processes, but `getattr(plan.process, "resolve_services", None)` is `None`.
  - Control, a single plan: the hook is found.
- **Harm:** in a collated plan that includes an m69b backed plan, `run` returns receipts that were never resolved. `unpack` after `close()`, or in the submitter after a driverless job, then dials a server that has already been released. That is N10's harm again.
- The same gap applies to a backed reduce composed into `aggregate_plan` (m69b `test_pieces_composition.py`), where `_PartitionReduce` is the outermost process.
- **Decide one of:**
  - (a) Resolving follows the same traversal as binding. graphed adds `graphed.services.resolve_services(plan, value)`, mirroring `bind_services(plan, endpoints)`.
    - `_Collated` forwards it for each name over `{name: value}`.
    - `_PartitionReduce` forwards it to `reduce`.
    - The engine calls that function.
    - It lands in graphed before the m68 release that executors pin. No `v*` tag contains `cf4520d` yet, so the floor is still open.
  - (b) `collate`, and a composed `aggregate_plan`, refuse a part that has `resolve_services`. The refusal names the rule.
- **Closed when:** a frozen m68a leg runs `collate({"a": spy_a, "b": spy_b})` through `SubmitRunner(ThreadBackend)`.
  - Under (a): each spy's `resolve_services` is called once with its own sub-value while the child is alive.
  - Under (b): the plan is refused at `collate`.
  - The current text fails both versions of the leg, because the hook is not found and nothing refuses.

**N15. The new public step `start_services` skips `HTCondorRunner`'s pilot wait. On a pool whose pilots never start, the probe hangs instead of refusing.**
- **Where:** the §3.1 engine line calls `start_services(plan)` "its own public step". The frozen leg "`start_services(plan)` then `run(plan)`" calls it directly.
- `HTCondorRunner` guards only `run` with its wait (`backend.py:179-184`: `if not self._waited: self.wait_for_pilots()`). Its docstring says the wait exists so that "pilots that never start are an error instead of a queue that never drains".
- `driver.main` waits first (L300-302). An attached `runner.start_services(plan)` does not.
- The probe's `backend.submit` futures have no deadline in the plan. The 5 s limit is the check inside the task.
- **Measured** (`probes/class/probe_start_before_wait_r15.txt`):
  - A task submitted to an `HTCondorBackend` with no pilot has no answer after 3 s (`done = False`).
  - The wait on `run`'s path raises `RuntimeError: 0 of 1 pilots connected after 2s`.
- **Cut, one line:** `HTCondorRunner.start_services` does the same `if not self._waited: self.wait_for_pilots()` before calling `super()`. Alternatively, the wait moves into one method that both `run` and `start_services` call.
- **Closed when:** a frozen leg calls `HTCondorRunner(...).start_services(plan)` over a launcher that never starts a pilot, with a short wait timeout. It must raise the wait's `RuntimeError` within that timeout. The current text blocks on the probe future.

## The shape (for the owner's question)
- **What the two have in common:** the r14 repair added two seams to `SubmitRunner` and named an existing seam as each one's model: "duck-typed like `bind_services`", and a public step beside `run`. It specified only the engine's call into each.
- **What went missing:** the model seam's contract lives on its other side. For binding, that is graphed's composites forwarding `bind_services` through `Bindable`. For running, it is `HTCondorRunner` guarding `run` with its pilot wait. The new seams did not take those over.
- **The same operation produced N13:** "as in `HTCondorBackend.__init__`" copied a stack that is only used on the error path.
- **Cut at the cause:** each seam m68a adds names its other side in the plan: who forwards it (N14 (a)) and who overrides it (N15). The instances above are that cut.
- **Scope of the search:**
  - Searched all analogy clauses in the unit (`like`, `as in`, `idiom`, `precedent`, `same rule`, `'s rule`) at D1–D10 and §3.1.
  - Checked each against its authority. D10's "m47 precedent / like `site_services`", "`driver.main`'s rule" and "m67's refusal idiom" hold.
  - The instances found are N13 (closed), N14 and N15.

## Exit-round constraints (to the implementer)
- **`run`'s return value.** "`run` returns what it returned" means `ExecResult.value` is what `resolve_services` returned. `run` still returns an `ExecResult` (`engine.py:296`, `execution.py` `ExecResult`).
- **A held port range surfaces as a raw `OSError`.** D2 says "Nothing left → `ServiceUnavailable`", but the frozen table asserts a raw `OSError` for a held port range. The table governs. Make D2's sentence match it.
- **"The injected exception" for a check that never passes** is the `ServiceUnavailable` that leg 3 raises.
- **Launcher releases.** Keep one shared `CLOSE_WAIT_S` deadline across a launcher's children when `stop()` becomes a stack close.
- **Carried from r14:**
  - Register `launcher.stop` so that LIFO order reproduces `server.close` → `launcher.stop` → `server.shutdown`.
  - Register `launcher.stop` before a partial `start`.
  - `CondorPilots` records `_schedd` together with `cluster` before spool.
  - Use `proc.poll()` as the Windows witness.
  - m70's "a stop never acknowledged is the refusal" wording.
  - E15: L307 still says "which holds the traceback".
