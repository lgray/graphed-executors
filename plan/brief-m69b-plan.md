# Brief: redesign and converge the m69b plan (histserv-backed histograms)

The artifact is `plan-services.md` §5 (m69b), plus the lines of D8, §1, §6 CI, §7 partition, §8 docs and §9 that
bind m69b. The §5 being replaced is `reviews/plan-services-m69b-r0-snapshot.md`. Project rules: `meta/CLAUDE.md` and
`meta/graphed-project-plan-gated.md`; the project plan wins. Loop rules: `brief-m68b-plan.md` "Loop".

## Owner direction (fixed)
- "histserv is integrated naturally into graphed-histogram as a backend variant that implicitly requests a service be
  made in by the graphed executor, with configuration options possible for how many histograms per server, and other
  user-facing service topology concerns."
- "Make a graphed-histogram histserv context that specifies memory per server so that the number of servers can be
  scaled according to expected usage (which can be calculated *before* running an analysis) and each histogram can be
  allocated in a way that won't crash a server, and you pass this to graphed-histograms so they know what server to
  talk to. This is a rough sketch."
- Earlier planner notes (inputs, not decisions): expected bytes per histogram = bins incl. flow × storage bytes/bin
  (× the variation axis) + per-histogram overhead; overhead and server baseline measured by a histserv probe; growth
  axes cannot be pre-sized (refuse, or require a cap); deterministic packing (sorted, first-fit decreasing); a
  histogram larger than a server is refused naming both sizes; one `ServiceSpec` per server, with
  `Launch.resources.memory_mb` from the context.
- Owner rulings that bind (from §3): services live per run (warm only through a user-held `ServiceSet`); a
  submission's scope is its run's `RunContext`/`run_nonce`.

## Code (read-only; never touch other sessions' worktrees)
- graphed main d0ad16b (service surface #58/#61/#63, unreleased; PyPI is 0.0.6): `~/vibe-coding/cloud/graphed-d0ad16b`
  (`python/graphed/services.py`, `session.py` `declare_service`, `aggregate.py` `aggregate_plan(services=)`).
- graphed-histogram main 4c4b79f (0.0.4): `~/vibe-coding/cloud/graphed-histogram` (`boost.py`, `_spec.py`,
  `docs/design.rst`; CI pins graphed 0.0.6).
- graphed-executors main 0e48380 (m68a merged) and the m68b head 1d79b80 (#40, in the merge queue; m69b plans against
  main once it merges): read through `git -C ~/vibe-coding/cloud/m68a show <rev>:<path>`, never in
  `~/vibe-coding/cloud/m68b`. Executors CI installs `graphed-histogram @ git+…@main`.
- histserv 0.2.1 from PyPI in a scratch venv; docker is available.

## Rules
- The plan states decisions, never measurements: every sizing figure comes from a driven probe of the real histserv,
  `probes/m69b/*.{py,txt}`, which the plan points at.
- No ledgers, dispositions or figures beside lists in the plan; commits ≤2k lines; frozen tables give property,
  witness and fixture, and each test must be able to fail in the direction it guards.
- m69a's carried constraint: the m69b test author's MC fixture uses varied ± genWeight (nNeg > 0), as
  `reviews/impl-r1-probe_ranges.py` (copied from the hgg lane) does.
- Measured traps the test author and implementer must be told: a frozen harness's bounded call copies
  `tests/frozen/m66/htcondor_harness.py::run_bounded` (daemon thread + `join(timeout)`; a `ThreadPool` per call
  deadlocks 3.14t); any new HTTP server subclasses `graphed_executors.local._transport.LookupFreeHTTPServer`; the
  integrity gate refuses `pytest.skip(` (use `skipif`); htcondor has no macOS arm64 wheel (pool legs run in Linux).
- Kill every process and container you start.
