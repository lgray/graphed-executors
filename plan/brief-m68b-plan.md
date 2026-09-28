# Brief: converge the m68b plan (cloud session, planning only)

This checkout is branch `plan/m68` of `lgray/graphed-executors`, and holds only the plan under `plan/`. Your job is
to bring **m68b's plan** (`plan/plan-services.md` §3.3, plus the lines of §3, §6–§9 and D1–D10 that bind m68b) to a
clean review. Commit the converged plan to your working branch. **Do not implement anything.**

## Read first
- The project rules: `git clone https://github.com/graphed-org/graphed-project-mvp ../meta`, then
  `../meta/CLAUDE.md` and `../meta/graphed-project-plan-gated.md`. The project plan wins over everything.
- The code the plan names: `git fetch origin main && git worktree add ../code origin/main` (graphed-executors main,
  which includes m66 and m67). graphed: `git clone https://github.com/graphed-org/graphed ../graphed`.
- The m68b state: the last m68b review, `plan/reviews/plan-services-r7-m68b.md`, was NOT CLEAN (M11–M17), and
  `plan/notes-m68b.md` holds the redesign input the owner held back. m68a's plan (§3.1) has converged (r24 CLEAN)
  and is m68b's base; its implementer constraints are in `plan/reviews/m68a-exit-items-r8-r10.md`. m68a is being
  built in parallel, so treat §3.1 as fixed.
- Owner rulings, which are fixed: services live per run (opt-in warm through a user-held `ServiceSet`); overlapping
  runs are kept (patched, not serialized); a submission's scope is its run's `RunContext`/`run_nonce`. D6 exit codes:
  a plan-code StageError exits 3, and worker loss exits 1.

## Loop (planner and reviewer are separate subagents; a fresh reviewer each round)
1. **The planner** repairs r7's findings and folds in `notes-m68b.md`, editing §3.3 in place. The plan states
   decisions, never measurements: measurements go in `plan/probes/m68b/*.{py,txt}`, which the plan points to. It
   backs each premise with a driven probe against `../code`. Docker is available (minicondor:
   `htcondor/mini`). No dispositions or ledgers go in the plan.
2. **The reviewer** snapshots the plan to `plan/reviews/plan-services-m68b-rN-snapshot.md`. It reads the whole unit
   in the first round and after any clean delta round, and only the delta otherwise. It writes
   `plan/reviews/plan-services-m68b-rN.md`, leading with CLEAN or NOT CLEAN.
   - A **design finding** changes a line the implementer or test author will write, or a decision they must make.
     Each gets: where, why it changes code, the measurement, closed-when, and the test that shows it closed.
   - Wording, labels and restated figures are **exit items**. They go in `plan/reviews/m68b-exit-items.md` and never
     make a round unclean.
3. **Converged** means a clean delta round followed by a clean whole-unit pass.
   - **Non-convergence:** from round 3 on, a round whose design-finding count does not fall below the previous
     round's. Split the unit and review the parts separately. A second split stops the loop.
4. Commit after each round, as conventional commits (`docs(plan): …`), by Lindsey Gray <lindsey.gray@gmail.com>, with
   no Co-Authored-By, Assisted-by or session trailers. Push your working branch.

Stop every process and container you start.

## Final message
CONVERGED or STOPPED; the round count and the design findings per round; the branch; the m68b frozen-test list and
commit partition as planned; and any decision that is genuinely the owner's.
