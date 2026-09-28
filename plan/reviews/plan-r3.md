# Plan review r3 (delta since r2, then the whole-artifact pass)

**Verdict: CLEAN.** The delta round has zero design findings, and the whole-artifact pass has
zero design findings.

## Delta (the r2 revision)
- Test 2's per-term sets: in each set the deciding term picks the winner, and the other two terms
  together rank the ads the other way. So a `schedd_weight` with term T removed picks the other
  winner in T's set. The ranking has no ties, so `min`'s first-item tie-break no longer decides the
  result, and running reversed order as well costs nothing. The r2 finding is closed.
- 8(b) is `SiteProfile(name="ci-spool", spool=True, …)`. Its premise is measured
  (`probes/ci-minicondor/spool.transcript`: spooled, then (5,16)→1→2→4 in 11.1 s, all four files
  retrieved, `queue after remove: 0`). The fallback text is gone.
- `set_result`/`set_exception` run after the `Condition` lock is released. That is correct: a
  done-callback re-enters the queue.
- `min_pilots: int = 1` is on the runner and the facade. `local_backend(n)` still waits for n
  pilots, so the frozen `n_workers() == n` cannot race.
- The harness copies every helper the copied bodies use, plus `PoisonUriProcess(uri)`. Test 4's
  4-leaf case now names its process.

## Whole-artifact pass
I re-read §§1–6 against `submit/engine.py` (`_run_fixed`, `_run_fixed_windowed`, `_task_slots`,
`_result`/`_translate`), `submit/protocol.py`, `parsl_backend/{_shim,backend}.py`, m42
`submit_backends.py` and the conformance body, `pyproject.toml` (pythonpath and omit), and the
ci.yml parsl job. No design findings. The engine contract holds:
- future args resolve before `fn` runs, through the dep rule;
- `add_done_callback` hands back the adapter;
- the monitor events of leaves in `_run_fixed` are dispatched when the combine's dep resolution
  calls `.result()` on the same `_ParslFuture` the engine passed;
- a worker death reaches `_translate` at any arity;
- `task_slots()` does not wait.

## Exit-round constraints (not findings)
- The main matrix runs `pytest tests/frozen tests/extra` on every OS (ci.yml line 54), so the m66
  `LocalPilots` tests run on Windows too. The stdlib `ThreadingHTTPServer.allow_reuse_address` is
  1 (probed). On Windows, `SO_REUSEADDR` can let the "first free port" scan re-bind a port that a
  still-open server holds. Set `allow_reuse_address = False` on `TaskServer`. This premise is
  unmeasured (no Windows host here).
- `log_dir=None`: state the default. Use a fresh directory under `sandbox_root` when the profile
  has one, and `tempfile.mkdtemp()` otherwise. Otherwise `site="lpc"` without `log_dir` has no
  defined sandbox check.
- A pilot runs one task at a time whatever `request_cpus` is. Say so in the `htcondor.rst`
  `request_cpus` line.
