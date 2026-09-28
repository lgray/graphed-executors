# Review r10 — `plan-services.md`, unit m68a (delta vs `plan-services-r9-snapshot.md`)

**Verdict: NOT CLEAN — 1 design finding (N6): a small reader-side cut plus one frozen leg, which the dispatch can carry.**
r9's N5 is closed for its measured member. The repair's class admits a member it does not close, so no whole-unit pass
was run.

Probes were read-only against `~/vibe-coding/lanes/driverless/graphed-executors` (head 386d65d). They were run with
`PYTHONDONTWRITEBYTECODE=1`, using the driverless `.venv` python except where noted. The new probes are in
`probes/services-code/`:
- `probe_result_env_r10.{py,txt}`;
- `probe_triton_exc_r10.{py,txt}` (run on the workdir `.venv`, because the driverless venv has no tritonclient).

## r9 findings
- **N5 closed for its measured member.** §3.1 makes the refusals pass their constructor arguments to
  `super().__init__` and gives them a `__str__`.
  - probe_result_blob_r9 (`ArgsForm`, `Unavailable`) shows that form loading with its fields and a reason-bearing
    `str`.
  - The plan's premise holds: StageError's `__reduce__` exists for a keyword-only constructor. `graphed/debug/errors.py`
    `StageError.__init__(self, *, op, …)` is keyword-only.
  - `_result_blob` now round-trips inside its existing `try`. The new leg (an exception that takes more constructor
    arguments than it passes on comes back as the text `RuntimeError`) fails against m67, where the load raises
    `TypeError` (probe_result_blob_r9, `_result_blob Natural`). So the leg discriminates.
- **D10 consistency (m68b/m70).** The delta touches no `host_service` line.
  - Every mention still returns `(endpoint, identity)`: L103, L251, L273, L367-368, L412, L421-426.
  - m68b's `RETRY driver 2 UNLESS-EXIT 3` (L395) agrees with D6 and with the owner ruling: a plan StageError exits 3,
    and worker loss exits 1.

## Design findings

**N6 · `_result_blob` round-trips in the driver job's environment, but `RunHandle.result()` loads in the submitter's ·
a payload that loads in the job and not at the submitter still breaks collect.**
- The plan's own rule on L306 fails a run on "a `result.pkl` that dumps but does not load". The round-trip tests
  loading in the one process where it is most likely to succeed.
- Task exceptions reach `result.pkl` unwrapped (probe_exit_code_r8 F: `type=ValueError is_StageError=False`).
  `submit_driverless(image=)` runs the driver in an image whose packages the submitter need not have. For example,
  graphed imports `tritonclient` lazily, so a submitter without it builds a Triton plan
  (`graphed/preserve/externals/triton_external.py`).
- A member the class admits, found by probe_result_env_r10:
  - an exception class that is importable only in the job passes the plan's round-trip (`driver-side round trip:
    ImageOnlyError`);
  - `pickle.loads` in a process without that class fails (`ModuleNotFoundError: No module named 'imageonly'`);
  - so `RunHandle.result()` (`driverless.py:101`, a bare `pickle.loads`) raises `ModuleNotFoundError` in place of the
    run's error.
- Not this member: tritonclient's own `InferenceServerException`. tritonclient builds it with keywords
  (`grpc/_utils.py`, `msg=…, status=…`), so the driver-side round-trip already turns it into text
  (probe_triton_exc_r10: `TypeError … missing … 'msg'`).
- The cause is the reader. `driverless.py:101` is the one place every `result.pkl` passes through, and the only
  process whose environment matters.

**Closed by:**
1. Factor out the load at `driverless.py:101` so that a failed `pickle.loads` raises a `RuntimeError`. The message
   names the load error and points at `driver.log`: `main` already writes the full traceback there (`driver.py:124`),
   and `RunHandle.logs()` returns it.
   - Keep the driver-side round-trip. It is what carries the reason text into `result.pkl` in the common in-image case.
2. A frozen leg in `test_driverless_endpoints.py` that needs no bindings:
   - write `result.pkl` holding an exception from a temporary module, then drop that module from `sys.modules` and
     `sys.path`;
   - assert that the factored load raises `RuntimeError` naming `ModuleNotFoundError` and `driver.log`;
   - the leg is discriminating: under the plan as written, the load raises `ModuleNotFoundError`
     (probe_result_env_r10).

## Exit-round constraints (to the implementer)
- **E12** In the text fallback, "did not pickle" is also used for a blob that pickled but did not load. Say "did not
  round-trip through pickle", or similar.
- **E13** The L306 Fails-on item should read "a `result.pkl` the submitter cannot load" once N6 lands.
- Considered, not raised: `_result_blob(True, result)` now loads the whole `ExecResult` a second time in the driver
  job. The cost is one extra deserialization at the end of the run. A success result that does not load still falls
  back to `(False, RuntimeError)` with exit 0, which is m67's existing behaviour for a dump failure.
- r9's E10 and E11, r8's E8 and E9, and r7's E1–E7 still stand.
