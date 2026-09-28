# Review r11 — `plan-services.md`, unit m68a (delta vs `plan-services-r10-snapshot.md`)

**Verdict: NOT CLEAN — 1 design finding (N7), a one-clause teardown rule plus one frozen leg that the dispatch can carry.**
r10's N6 is closed at its cause, and the delta returned zero design findings, so the whole-unit pass was run. N7 comes
from that pass.

Probes were read-only against `~/vibe-coding/lanes/driverless/graphed-executors` (head 386d65d), run with the driverless
`.venv` python and `PYTHONDONTWRITEBYTECODE=1`. The new ones are in `probes/services-code/`:
`probe_reader_r11.{py,txt}` and `probe_partial_start_r11.{py,txt}`. Merged graphed was read at `origin/main` cf4520d
in `lanes/svc-graphed/graphed`.

## r10 findings
- **N6 closed at the cause.** §3.1 now makes the submitter's load the authority: `RunHandle.result()` loads inside one
  `try`, and a failed load raises `RuntimeError` naming the load error and `driver.log`. `driverless.py:101` is the only
  reader of `result.pkl` (the other `pickle.loads` hits under `src/` are the task plane and the pilot).
  - probe_reader_r11 uses r10's member, an exception class that is importable only in the job:
    - m67's `RunHandle.result()` (with `_located` and `_poll` faked) raises `ModuleNotFoundError`;
    - the plan's reader raises `RuntimeError … (ModuleNotFoundError: …); see driver.log`, for both `ok=False` and
      `ok=True` blobs.
  - So the new frozen leg discriminates.
  - `raise payload` must stay outside the `try`. m67's frozen `test_result_re_raises_the_pickled_exception_intact`
    already pins that.
  - The leg can drive `result()` without real bindings. m67's harness does this through `record_bindings`, and
    `test_run_handle.py` already calls `result()` that way.
- **The delta adds no other design finding.**
- **D10 consistency (m68b/m70).** The delta touches no `host_service` line. Every mention returns
  `(endpoint, identity)` (L103, L251, L257, L370-371, L428).
- **D6.** It agrees with the owner ruling: a plan StageError exits 3, and worker loss exits 1 and is retried.
  m68b's `RETRY driver 2 UNLESS-EXIT 3` matches it.

## Design findings

**N7 · `ServiceSet.start()` leaves a managed process running when a later spec raises.**
- The shape paragraph (L128) says the set "closes what it started", and Fails-on lists "a service outliving `close`".
  But §3.1 has the engine call `ServiceSet(...).start()` as one expression and says nothing about a start that raises
  partway through.
- A plan with two specs, the first managed (`http_server`) and the second unresolvable, raises `ServiceUnavailable`
  after the first `Popen`. That child is reachable only from inside `start()`.
- On an attached run, the submitting host is the login node. There the orphan outlives the interpreter and keeps its
  port: probe_partial_start_r11 shows `parent rc 1 | managed child … alive after parent exit: True`.
- The frozen rows pin `pid gone after close` only for a start that succeeded, so an implementation without the
  teardown passes the suite.

**Closed by:**
1. `start()` runs its own `close()` on what it has started (callbacks, `terminate`, `release_service`) before
   re-raising any exception from a later spec. The cause is `start` owning its partial state, so the fix goes there,
   not in the engine.
2. A frozen leg in `test_services_protocol.py`: a two-spec plan, the first a managed `http_server` and the second
   with no `launch` and no endpoint.
   - `run` raises `ServiceUnavailable`.
   - With no `close()` call, the first spec's pid is gone and its port is free.
   - The leg discriminates: without the teardown, the pid is alive (probe_partial_start_r11).

## Exit-round constraints (to the implementer)
- **E14** In the §3.1 engine line, `graphed.bind_services` does not exist at the top level. `graphed/__init__.py` at
  origin/main has no `services` or `bind` match; control: 16 import lines. Use `graphed.services.bind_services`.
- **E15** The "`driver.log`, which holds the traceback" clause is true only for a failed run: `main` prints the
  traceback only `if error is not None`. An `ok=True` blob that fails to load has no traceback there. The message
  should point at `driver.log` without promising one.
- **E16** In the `test_driverless_endpoints.py` row, "with no bindings" means under m67's `record_bindings` fake,
  because `result()` calls `_located()` → `launch._htcondor()`.
- Considered, not raised: graphed #61 (cf4520d) adds `require_bound`. It is called only from `SequentialRunner`
  (`core/execution.py:536`), and `_PluginEvaluator.bind_services` now raises `UnboundService` for a name missing from
  the map. The engine binds every name in `plan.services`, which is the set `referenced_services` collects, so
  m68a's bind sees no refusal.
- r10's E12 and E13 are folded into the plan. r9's E10 and E11, r8's E8 and E9, and r7's E1–E7 still stand.
