# Brief: build m69b through the gated pipeline (three PRs)

Design: `plan-services.md` §5 (§5.0 graphed `aggregate_plan(opt_level=)`, §5.1 graphed-histogram histserv backend,
§5.2 executors diagnostics + placement + LPC run) and the §1/D1/D2/D8/§6–§9 lines binding them. Constraints the plan
text does not carry: `reviews/m69b-exit-items.md` (every section) and the dispatch you were given. Project rules:
`meta/CLAUDE.md`, `meta/graphed-project-plan-gated.md` (Part B = the pipeline); the project plan wins.

## Checkouts and venvs (never `uv run`/`uv venv`/`pip install` into another lane's venv)
| PR | checkout (branch) | base | venv |
|---|---|---|---|
| graphed §5.0 | `~/vibe-coding/cloud/graphed-m69b` (`m69b-opt-level`) | graphed-org/graphed main d0ad16b | `~/vibe-coding/cloud/.venv-m69b-graphed` (editable) |
| histogram §5.1 | `~/vibe-coding/cloud/graphed-histogram` (`m69b`) | graphed-org/graphed-histogram main 4c4b79f | `~/vibe-coding/cloud/graphed-histogram/.venv` (graphed d0ad16b, histogram editable, histserv 0.2.1) |
| executors §5.2 | `~/vibe-coding/cloud/m69b` (`m69b`, a worktree of `~/vibe-coding/cloud/m68a`) | graphed-org/graphed-executors main db8fb0a | `~/vibe-coding/cloud/.venv-m69b` (histogram + executors editable, histserv) |
Remotes: graphed-m69b and graphed-histogram `origin` = graphed-org, `lgray` = the fork; the executors worktree
`upstream` = graphed-org, `origin` = the lgray fork. Never touch `~/vibe-coding/cloud/{m68a,m68c-*,docs-*,fix-lxplus-submit,plan}`,
`~/vibe-coding/integ/mains/*`, `~/vibe-coding/m52`, or containers you did not start (e.g. `fixlx-pool`).

## Roles (each a fresh subagent; they communicate only through committed artifacts)
1. **Test author** writes the frozen suite + README traceability table (test → plan clause → what it shows → the wrong
   implementation it fails). Never reads or writes the implementation; throwaway stubs live outside the repo.
2. **Sanity** (independent): collects; non-vacuous against a NotImplementedError stub and discriminating against two
   wrong-but-plausible implementations of its own; deterministic across two runs; diff touches only the frozen dir;
   every frozen row and "Fails on" item maps to a test.
3. **Freeze**: `test(m69b): …` commit + annotated tag pushed to graphed-org over SSH.
4. **Implementer**: makes the frozen suite pass in the plan's commits (≤2k lines each); may add `tests/extra/m69b/`;
   logs every iteration in `.graphed/m69b/attempts.md`; never touches `tests/frozen/**` after the freeze — a wrong
   frozen test gets `.graphed/m69b/disputes/<test_id>.md` and that line of work STOPS.
5. **Reviewer** (fresh each round): intent, guardrails, technique, abstraction; probes, not only reads; APPROVE only
   when every gate is green.

## Gates (every implementer iteration)
- `pytest` over the repo's frozen + extra suites the way its CI runs them (graphed: `scripts/run-tests.sh`).
- Every source file ≥ 90% line+branch; diff-cover ≥ 98% vs `upstream/main` (origin for graphed/histogram).
- `ruff check`, `ruff format --check`, `mypy` on src AND tests; graphed also `cargo clippy` + `cargo test`.
- Sphinx `-W`.
- Before EVERY commit: `RUSTUP_TOOLCHAIN=stable PATH=<venv>/bin:$PATH ~/vibe-coding/graphed-workdir/.venv/bin/python -m graphed_orchestrator.precommit . --fast --no-coverage`.

## Measured traps (tell every test author and implementer)
1. A frozen harness's bounded call copies `graphed-executors/tests/frozen/m66/htcondor_harness.py::run_bounded`
   (daemon thread + `join(timeout)`); a `ThreadPool` per call deadlocks free-threaded 3.14t.
2. Any new HTTP server subclasses `graphed_executors.local._transport.LookupFreeHTTPServer` (macOS runner `getfqdn` stall).
3. The integrity gate refuses `pytest.skip(`; use `skipif` markers / `importorskip`.
4. htcondor has no macOS arm64 wheel: pool legs run in a Linux container (`m68b-minicondor:local`) or CI.
5. grpcio has no cp314t wheel: histserv legs skip on 3.14t only (asserted importable wherever the GIL is enabled).

## Rules
- Commits by `Lindsey Gray <lindsey.gray@gmail.com>`, conventional, with NO trailer lines of any kind. Never amend
  or force-push pushed commits. Never enqueue. Push branches only to the `lgray` fork; tags to graphed-org.
- Integrity §A.7: never edit/skip/xfail/weaken a frozen test; never lower a threshold; never stub or hard-code what a
  test checks; no bare `NotImplementedError`/`pass` behind a green test; no blanket `# type: ignore`/`except: pass`.
- Tests assert, they do not narrate; each can fail in the direction it guards and witnesses the mechanism engaging.
- Kill every process and container you start. Append concise findings (newest last) to
  `~/vibe-coding/graphed-workdir/lanes/htcondor/journal.md`.
