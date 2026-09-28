# Brief: build m68a in graphed-executors (cloud session)

You work in `lgray/graphed-executors`, a fork of `graphed-org/graphed-executors`. Your checkout starts at the
fork's `main`. Build **m68a only**, through the gated three-role pipeline, and stop at reviewer APPROVE with green CI.

## Read first
- The plan branch: `git fetch origin plan/m68 && git worktree add ../plan origin/plan/m68`. Paths below are under
  `../plan/plan/`. Paths the plan itself cites (`probes/…`, `reviews/…`) are relative to that directory; local paths
  such as `~/vibe-coding/...` or `lanes/htcondor/...` in it name the author's machine and do not exist here.
- The project rules: `git clone https://github.com/graphed-org/graphed-project-mvp ../meta`, then read
  `../meta/CLAUDE.md` (root rules) and `../meta/graphed-project-plan-gated.md` (the project plan, Part B = the
  pipeline). Precedence: project plan > root `CLAUDE.md` > this repo's `CLAUDE.md` > this brief.
- The design: `plan-services.md` §1 (shape) and §3 (m68: D1–D10, then §3.1 = m68a), plus the §6 CI, §7 commit
  partition, §8 docs and §9 lines that bind m68a. `plan.md` is m66's base plan, which `plan-services.md` extends.
- Constraints for the implementer that are not in the plan text: every section of
  `reviews/m68a-exit-items-r8-r10.md`.
- Owner rulings, which are fixed: services live per run (opt-in warm through a user-held `ServiceSet`); overlapping
  runs are kept (patched, not serialized); a submission's scope is its run's `RunContext`/`run_nonce`.
- Out of scope: m68b, m69b, m70, and any graphed change. graphed's service surface has merged: graphed#58, #61.

## Pipeline (each role is a separate subagent; roles communicate only through committed artifacts)
1. **Test author** writes `tests/frozen/m68a/`: the §3.1 frozen table, its harness `services_harness.py`, and a
   README traceability table (test → plan clause). It never reads or writes the implementation.
2. **Sanity** checks that the suite collects, and fails against the unimplemented tree for the right reason
   (missing planned names, not syntax or fixture errors). It is deterministic across two runs, and coverage is wired.
   Loop with the test author until sane.
3. **Freeze:** commit `test(m68a): frozen m68a acceptance suite` and an annotated tag `freeze-m68a`. If the proxy
   refuses tag pushes, record the sha in `.graphed/m68a/attempts.md`.
4. **Implementer** makes the frozen suite pass in the §7 commits, each ≤2k lines, as conventional commits. It may
   add `tests/extra/m68a/` and logs each iteration in `.graphed/m68a/attempts.md`. It never touches
   `tests/frozen/**`. If a frozen test is wrong, it writes `.graphed/m68a/disputes/<test>.md` (the test, the clause it
   contradicts, the proposed fix) and stops that line of work.
5. **Reviewer** (a fresh subagent each round) judges intent, guardrails, technique and abstraction. It may APPROVE
   only when every gate below is green; otherwise REJECT with findings, the implementer repairs, and it reviews again.

## Gates (every implementer iteration)
- Install the way `.github/workflows/ci.yml` does (its `GRAPHED` pin and extras). Building graphed from git needs a
  Rust toolchain (maturin).
- `pytest tests/frozen tests/extra`: all pass; skips only where `ci.yml`'s legs skip.
- Coverage: every source file ≥90% line+branch, and ≥98% diff coverage (diff-cover) against `upstream/main`
  (`git remote add upstream https://github.com/graphed-org/graphed-executors`).
- `ruff check`, `ruff format --check`, and `mypy` on `src` and `tests` (the pyproject config).
- The precommit gate before every commit:
  `pip install git+https://github.com/graphed-org/graphed-orchestrator` then
  `python -m graphed_orchestrator.precommit . --fast --no-coverage`.
- The docs build with `-W` (the `docs` job).
- The `test-htcondor` leg (minicondor, docker Triton): docker is available here. Run it if you can; else rely on CI.

CI: open a PR from your branch to **`lgray/graphed-executors` `main`** (Actions are enabled on the fork) and iterate
until `ci-required` is green. Do not open a PR against `graphed-org`.

## Rules
- Commits by Lindsey Gray <lindsey.gray@gmail.com>, as conventional commits, with **no** Co-Authored-By, Assisted-by
  or session trailers. The PR body starts with the line `:robot: _AI text below_ :robot:`. Never force-push.
- Integrity (§A.7), non-negotiable. Never edit, skip, xfail or weaken a frozen test. Never lower a threshold. Never
  stub or hard-code what a test checks. Never leave a bare `NotImplementedError`/`pass` behind a green test. Never
  blanket-apply `# type: ignore` or `except: pass`.
- Tests assert and do not narrate. Each must be able to fail in the direction it guards, and must witness the
  mechanism engaging, not only the result.
- Stop every process you start: dask clusters, servers, docker containers.

## Not here
The LPC site check (EAF Triton) needs the owner's cluster access. Leave it for the owner's terminal.

## Final message
The branch, the PR URL, the `freeze-m68a` sha, the gate results (test counts, coverage, lint and type status, CI),
the reviewer's verdict and rounds, any dispute files, and what the LPC site check must exercise.
