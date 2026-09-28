# `graphed` — Project Plan (Gated Three-Role Pipeline Edition)

This supersedes the previous single-agent-per-milestone plan. Each milestone is now executed
by a **gated pipeline of three isolated agent contexts** — `test-author`, `implementer`,
`reviewer` — coordinated by a **deterministic orchestrator** (a script/state machine, NOT an
LLM). The roles never converse; they hand off through frozen artifacts. All stall and
escalation decisions are made mechanically by the orchestrator from git and CI evidence, never
from an agent's self-report.

Document map:
- **Part A** — Shared context (paste atop every role prompt), incl. A.8 reference analysis corpus.
- **Part B** — Orchestration, gates, and the stall/escalation/pause subsystem. *Read this first.*
- **Part C** — The three reusable role-prompt templates.
- **Part D** — Per-milestone payloads M0–M9 (incl. M0.5 corpus study; the data the templates consume).
- **Part E** — MVP Definition of Done. **Part F** — Phase 2 (do not build).

---

# PART A — SHARED CONTEXT (prepend to EVERY role prompt)

## A.1 Project thesis (do not deviate)

> Prior HEP task-graph systems (dask-awkward) recorded one graph node per array operator,
> producing graphs of many thousands of nodes (O(10000) under systematics). The bottleneck was
> not execution but *graph optimization*: dask's blockwise fusion was effectively O(N^2) and
> dominated wall time, and the low-level graph was so large and nested that the Python
> interpreter itself became a cost. coffea 2025 escaped by discarding the schedulable graph and
> running eagerly. `graphed` takes the middle path: keep an explicit, serializable,
> schedulable, debuggable graph, but **reduce it to a concise set of stage-nodes incrementally
> as the user builds it**, so a large un-reduced graph never exists. Reduction runs in a Rust
> extension. A "stage" is a maximal fused run of array ops between boundaries (source,
> reduction, repartition, checkpoint, external/opaque op). The optimized graph minimizes
> Python-interpreter touchpoints and maximizes time inside array kernels (awkward by default).

## A.2 Established techniques to USE (names so you can look them up)

**Equality saturation over e-graphs** is the *technique* for canonicalization and
stage-forming rewrites with cost-based extraction (Willsey et al. 2021; precedent: Tensat).
The e-graph *engine* is an implementation detail and MUST sit behind an internal
`RewriteEngine`/`Optimizer` trait (see M4) so it is swappable. **Default engine for the MVP:
the `egg` Rust crate** — chosen for a stable API, first-class in-Rust cost-function extraction
(`CostFunction`/`Extractor`), easy determinism, and dense public examples (lower risk for less
capable agents). `egglog` (egg's more general Datalog-unifying successor) is a Phase-2 swap
candidate, NOT the MVP default (see Part F for the exact switch criteria). Do NOT hand-roll a
fixpoint rewriter before using the chosen engine. NOTE: the e-graph earns its weight ONLY for
canonicalization + cost-based stage fusion; **DCE and CSE live OUTSIDE the engine** — DCE is a
plain reachability pass and CSE falls out of hash-consing on construction. Hash-consing/
interning for dedup on construction. Logical-vs-physical plan; Volcano/Cascades cost-based optimization. Operator
fusion + morsel-driven parallelism (a file's chunks as morsels on one worker = the HDD
file-fusion strategy). Tracing to an IR via typetracer abstract evaluation (cf. JAX jaxpr,
PyTorch FX) — reuse awkward's typetracer; do NOT reimplement type inference. Dynamic task
graphs + futures (Ray, Legion, PaRSEC) for executor-driven task generation; structured
concurrency + work-stealing + tree reduction for safe, non-blocking accumulation.
Content-addressed memoization (Nix, Bazel, ccache) for checkpoint/resubmission. Free-threaded
Python (PEP 703/779; CPython 3.14t) + PyO3 >= 0.28 + maturin for a thread-safe Rust core and
cross-platform wheels.

## A.3 dask failures this project MUST avoid (acceptance-relevant)

(1) Building a complete graph before optimizing reusable sub-components. (2) Recording intent
operator-by-operator. (3) Slow optimization that dominates wall time. (4) High local memory
from graph + optimization. (5) Unclear packaging of a large component (e.g. an NN over many
events) for parallel execution. (6) Low-level graphs so large the interpreter is a cost. (7)
Optimized graphs so nested with sub-graph-execute calls that interpreter time is a cost.
(8) Python execution errors and stack traces — especially as surfaced through dask-distributed
from remote workers — were opaque and confused users; a runtime error must instead point at the
user's analysis line wherever it is raised (see M6/M7 distributed-error surfacing).

## A.3.1 Reproducibility / analysis preservation (first-class requirement)

The optimized graph is not only a thing to execute — it is intended to be a **publishable,
reproducible scientific artifact**. `graphed` must be able to emit a self-contained
**Preservation Bundle** capturing everything that determines the scientific result: the graph
IR (the analysis logic in programmatic, inspectable form), the user-source provenance/sourcemap
(so the artifact is human-auditable, not just runnable), every auxiliary payload (neural-network
weights, scale-factor / correction sources, calibrations), input dataset identities + content
hashes, the software environment, and configuration/seeds — all content-addressed so the bundle
uniquely fingerprints the computation and any changed input changes the bundle hash. Target
audience: someone who is NOT the author, possibly years later, re-running or reinterpreting the
analysis (cf. CERN Analysis Preservation, REANA, RECAST; the 2025 LPCC reinterpretation report).
This is distinct from M8 checkpoint/resume (which is same-environment execution portability) and
is built in M9. Design consequences that bind earlier milestones:
- **The serializable IR — not cloudpickle — is the canonical durable representation.** cloudpickle
  is version-fragile, opaque, and non-auditable; reserve it ONLY for genuinely opaque user
  callables, and FLAG any such node as a preservation risk in the bundle.
- **`External` nodes carry a full payload descriptor** (kind, content hash, framework+version,
  I/O schema, preprocessing reference) — this is also the fix for A.3 failure (5).
- **Large payloads are referenced by content hash**, stored in the M8 content-addressed Store,
  never inlined into a plan blob. One IR, two resolution modes: *execution plan* (references
  resolve locally) vs *preservation bundle* (self-contained or pinned to a durable archive).
- **Align with HEP standards, do not invent formats**: corrections via correctionlib (JSON),
  models via ONNX, histograms via UHI, statistical models via HS3, environment via container
  digest, datasets via IDs + hashes. Determinism (B.3.3) is the prerequisite for reproduction.

## A.4 Ecosystem packages (fixed names)

`graphed-core` (Rust+PyO3: IR, thread-safe interned store, optimizer via egg, plan
serialization, abstract execution protocol; MUST NOT import awkward) · `graphed` (Python
frontend: deferred proxy, single array interface, builder, provenance) · `graphed-awkward`
(reference backend) · `graphed-numpy` (trivial backend proving the seam) · `graphed-debug`
(sourcemaps, opt-level lowering, tracebacks, viz) · `graphed-exec-local` (reference executor) ·
`graphed-checkpoint` (content-addressed store, manifest, resubmission) · `graphed-preserve`
(analysis preservation bundle: self-contained, content-addressed, standards-aligned export).

## A.5 Build matrix (every package)

OS {Linux, macOS, Windows} × arch {x86_64, arm64}; CPython {3.11, 3.12, 3.13, 3.14, 3.14t}.
Rust packages: abi3 where possible + a dedicated 3.14t free-threaded wheel; maturin +
cibuildwheel; pinned, tested MSRV.

## A.6 Glossary

**Node** (IR entry) · **Stage** (fused schedulable node) · **Boundary op**
(source|reduction|repartition|materialize|external) · **Form** (awkward type/shape, propagated
at build) · **Plan** (serializable physical artifact for an executor) · **Partition** (unit of
input work, e.g. `(uri, tree, entry_start, entry_stop)`, may carry file-locality grouping) ·
**Provenance** (node/stage → user source location) · **Preservation Bundle** (self-contained,
content-addressed, standards-aligned export of a graph for reproduction/reinterpretation by
others — distinct from Plan) · **Payload descriptor** (the metadata an `External` node carries
to make its auxiliary input — model, correction set — reproducible: kind, content hash,
framework+version, I/O schema, preprocessing ref).

## A.7 Universal integrity rules (apply to ALL roles; violations are severe — see B.6)

Never weaken the bar to pass a gate. Specifically: never edit, delete, `skip`, `xfail`, or
weaken any test under `tests/frozen/**`; never lower a coverage/benchmark threshold; never edit
CI gate configuration to relax it; never stub, mock, or hard-code the specific thing a test is
meant to verify; never blanket-apply `# type: ignore` or `except: pass`. If you believe a
frozen test is wrong, do NOT route around it — file a Test Dispute (B.5). Honesty about
incompleteness is always preferred over a green gate obtained by cheating.

## A.8 Reference analysis corpus (ground-truth requirements + functional tests)

These real HEP analyses define what "real analysis" means for `graphed`. M0.5 distills them into
a **Required Operations Catalog** (the array operations, selection/weight/systematic/correction/
ML patterns the frontend must support) and a set of **Canonical Analyses** (runnable fixtures
with reference outputs) that later milestones use as functional tests. Do NOT design the op
surface or the tests from imagination — derive them from this corpus.

- **ADL benchmarks** (github.com/iris-hep/adl-benchmarks-index; coffea impls in
  github.com/CoffeaTeam/coffea-benchmarks, branches `coffea_2023_postrelease` (dask-awkward) and
  `master` (virtual arrays)). A set of **8 graded HEP query tasks** of increasing complexity
  (simple column histogram → MET cuts → object selection → jet/lepton combinatorics → the most
  complex dilepton+MET+combinatorics query). Ideal as a graded functional-test ladder for the
  frontend/optimizer/projection (M3/M4/M5). Comparing the dask-awkward vs virtual-array branches
  also documents the exact graph-bloat patterns `graphed` must avoid.
- **AGC CMS Open Data ttbar** (github.com/iris-hep/analysis-grand-challenge,
  `analyses/cms-open-data-ttbar`). The primary end-to-end fixture: a coffea `ProcessorABC` over
  ~9 processes in two regions (4j1b, 4j2b), histogrammed across a process×variation axis, with
  **weight systematics, kinematic (JES/JER) systematics that change selection and observables,
  b-tagging scale factors, and an optional ML inference step (ONNX / Triton) for ttbar
  reconstruction**, and an explicit preservation/reinterpretation goal. Drives M7 (executor,
  systematics, External nodes) and M9 (preservation must capture the NN + SF sources).
- **CMSDAS TTGamma long exercise** (github.com/nsmith-/TTGamma_LongExercise, with solutions). A
  teaching-grade full CMS analysis (ttbar+photon) with photon/lepton selection, scale factors,
  and systematics — a realistic single-analysis complexity reference.
- **PocketCoffea** (github.com/PocketCoffea/PocketCoffea, tutorials at
  github.com/PocketCoffea/Tutorials). A declarative config framework: skim → object calibration →
  preselection → categorization → weights → histograms, with a calibrator system for object
  corrections (JEC, energy scale) and **shape (kinematic) variations re-run after skimming** —
  the exact pattern that motivates systematics-as-axis vs template instantiation (Phase 2). Note
  its memory tactics (per-chunk column dumping to parquet; CartesianSelection beyond coffea's
  64-category PackedSelection limit) as real-world constraints on the executor.
- **boostedhiggs** (github.com/cmantill/boostedhiggs). A production boosted H→bb-style analysis
  (large-radius jets, substructure, triggers, corrections) — a reference for jet-substructure
  patterns and production-scale processor structure.

The Canonical Analyses M0.5 must yield (minimum): ADL queries 1–8, the AGC ttbar slice
(reduced file count), and a TTGamma-style selection+SF+systematics slice — each as a `graphed`
program plus a reference output (histogram) for bit-for-bit comparison.

---

# PART B — ORCHESTRATION, GATES, AND STALL/ESCALATION (the core of this edition)

The orchestrator is **deterministic code**, not a model. It owns the milestone state machine,
runs the mechanical gates, computes all stall signals from artifacts, and makes every
escalation/pause decision. Agents are invoked only for the five judgment steps (decompose,
author-tests, implement, review, adjudicate-dispute) and their self-reports are advisory only.

## B.1 Milestone state machine

```
PENDING
  -> DECOMPOSE            (strong model or human: split work, finalize acceptance criteria)
  -> TEST_AUTHORING       (test-author agent, fresh context, NO implementation present)
  -> TEST_SANITY          (mechanical gate: tests collect, are non-vacuous, deterministic)
  -> FROZEN               (orchestrator tags freeze commit; tests become read-only)
  -> IMPLEMENTING         (implementer agent loop; mechanical gates each iteration)
  -> REVIEW               (reviewer agent loop; can REJECT back to IMPLEMENTING)
  -> DONE                 (all gates green AND reviewer APPROVE)

Side states (any phase can transition here):
  TEST_DISPUTE  (implementer challenged a frozen test; adjudication required)
  ESCALATED     (same step re-run on a stronger model)
  PAUSED        (CIRCUIT BREAKER: all coding halted; explicit human resume required)
  ABORTED       (branch discarded; repo restored to last DONE milestone; human-only)
```

The next milestone's pipeline MUST NOT start until the current milestone is `DONE`.

## B.2 Context isolation (what each role sees)

Handoffs are artifacts, never conversation. Each role is launched in a **fresh context**
containing only:

- **test-author**: Part A + this milestone's Acceptance Contract (D) + (for M1+) the public
  interfaces of already-merged packages. **Not** any implementation of the current milestone.
- **implementer**: Part A + this milestone's Implementation Targets and Guardrails (D) + the
  **frozen test suite (read-only)** + the `attempts.md` failure log (B.4) + the latest
  structured Reject Report if re-entering from REVIEW. **Not** the reviewer's private reasoning.
- **reviewer**: Part A + this milestone's Review Focus (D) + the implementer's diff + **all
  mechanical gate artifacts** (CI logs, coverage report, clippy/mypy output, benchmark numbers,
  determinism result, integrity-scan report). **Not** a back-channel to the implementer except
  by emitting a structured Reject Report.

## B.3 The mechanical gates (run by the orchestrator; agents cannot self-grade)

Gates are evaluated from artifacts produced by CI, not from agent claims.

1. **TEST_SANITY** (once, after TEST_AUTHORING, before FROZEN):
   - (a) the suite collects/compiles with zero errors;
   - (b) **non-vacuity**: the suite, run against the empty/stub implementation, **fails** (a
     test that passes against no implementation is vacuous and is rejected) — every frozen test
     must be red before it can be made green;
   - (c) **determinism**: two consecutive runs against the stub yield identical results
     (flake-free);
   - (d) coverage instrumentation (codecov / `coverage.py`) is wired so diff coverage is
     measurable and attributable to the frozen suite later.
   Failing TEST_SANITY routes back to TEST_AUTHORING (not to the implementer).

2. **PER-ITERATION gates** (every implementer iteration):
   `frozen_tests` (all pass) · `coverage` — measured by **codecov** (or `coverage.py` +
   `diff-cover`) as **diff coverage >=90% line+branch on the new/changed lines**, AND the
   covering hits must come from the **frozen** suite (corpus/functional + unit), not only from
   `tests/extra/**`; a milestone whose new code is exercised only by implementer-added tests is
   rejected (the frozen tests must genuinely touch the code) · `lint`
   (`ruff` + `cargo clippy` clean) · `types` (`mypy --strict` clean) · `determinism` (B.3.5) ·
   `benchmark` (milestone benchmark within budget, where defined) · `integrity_scan` (B.6).

3. **DETERMINISM gate**: where the milestone produces an optimized graph or a serialized plan,
   identical input MUST yield byte-identical output across two runs.

4. **REVIEW gate**: the reviewer may emit `APPROVE` **only if every per-iteration gate is
   green**. The orchestrator refuses to record an APPROVE while any gate is red (defeats
   rubber-stamping). A reviewer `APPROVE` on red gates is itself an integrity violation by the
   reviewer.

## B.4 Iteration metrics and the attempt log

After every implementer iteration the orchestrator computes, from git + CI:

- `pass_count` — number of frozen tests passing.
- `fail_set_hash` — hash of the sorted set of failing test IDs.
- `tree_hash` — hash of the source tree excluding `tests/frozen/**`.
- `diff_lines` — lines changed vs the previous iteration.
- `coverage`, `benchmark_ok`, `lint_ok`, `types_ok`, `determinism_ok`, `integrity_ok`.
- `tokens_spent`, `wall_clock`, `iteration_index`.

These are appended to `.graphed/<Mx>/attempts.md` (one structured entry per iteration: what
was attempted, remaining failures, gate results, integrity flags, reviewer feedback if any).
Older entries are summarized to keep the log bounded; the log is the memory that survives a
context reset and is fed to the next implementer attempt.

## B.5 Stall signals → responses (the heart of this edition)

The orchestrator evaluates these every iteration. Thresholds are defaults; tune per project.
"Escalation ladder" levels are defined in B.7.

| # | Signal | Mechanical detection | Default threshold | Response |
|---|--------|----------------------|-------------------|----------|
| 1 | **No progress** | `pass_count` not strictly increasing | 3 consecutive iters | Ladder L0 → L1 |
| 2 | **Repeat failure** | identical `fail_set_hash` | 3 consecutive iters | Ladder L0 → L1 |
| 3 | **Oscillation** | `tree_hash`/`fail_set_hash` cycles (A,B,A,B…) over a window | window 6, cycle len ≤ 3 | Ladder L1 → **L2 PAUSE** |
| 4 | **Thrash** | `diff_lines` > 400 while `pass_count` flat or falling | 2 consecutive iters | Ladder L0 with smaller-scope instruction → L1 |
| 5 | **Gate-stuck** | functional tests green but `coverage`/`benchmark`/`determinism` red | 3 consecutive iters | Ladder L1 → L2 |
| 6 | **Budget exceeded** | `tokens_spent`/`wall_clock`/`iteration_index` over cap | per-milestone caps (D) | **L2 PAUSE** immediately |
| 7 | **Frozen-test tamper** | any change under `tests/frozen/**` vs freeze tag | 1 occurrence | **L2 PAUSE** immediately + integrity incident |
| 8 | **Integrity violation** | B.6 scan hit (weakened asserts, stub-of-tested-thing, `xfail`, threshold edits, `except: pass` floods) | 1 occurrence | **L2 PAUSE** immediately + integrity incident |
| 9 | **Review non-convergence** | reviewer reject count for this milestone; OR reviewer issue-set not shrinking across cycles | 3 rejects | Ladder L1 (stronger reviewer) → **L2 PAUSE** |
| 10 | **Flaky gate** | a gate flips pass→fail→pass on identical `tree_hash` | 1 detection | Quarantine the flaky test, flag it, do NOT count as progress/regress; if persists 2 more iters → L2 PAUSE |
| 11 | **Test dispute** | implementer files a dispute artifact (B.5 below) | 1 occurrence | → `TEST_DISPUTE` (coding paused for this milestone) |
| 12 | **Unsatisfiable suite** | even an L1 stronger implementer cannot move `pass_count` after escalation | after L1 exhausted | → `TEST_DISPUTE` or **L2 PAUSE** |

**Test Dispute mechanism.** The implementer may not edit a frozen test, but if it judges a
frozen test to be wrong (contradicts the spec, is internally inconsistent, or is impossible to
satisfy without violating a guardrail), it writes `.graphed/<Mx>/disputes/<test_id>.md` stating
the test, the spec clause it contradicts, and a proposed correction, then stops. The
orchestrator transitions to `TEST_DISPUTE` and routes to an **adjudicator** (the test-author
role on a stronger model, or a human). Adjudication outcomes: (a) **test upheld** → dispute
rejected, return to IMPLEMENTING with a note; (b) **test corrected** → test-author amends the
frozen suite, re-runs TEST_SANITY, re-freezes at a new tag, attempt log records the change.
Repeated disputes on the same milestone (>2) → L2 PAUSE.

## B.6 Integrity scan (defense against weak agents gaming the gates)

Run mechanically on every diff, in addition to reviewer judgment. Flags (any hit → signal #7/#8):
- Modifications to `tests/frozen/**`, CI config, coverage/benchmark threshold constants.
- New `@pytest.mark.skip`/`xfail`, `#[ignore]`, commented-out assertions, assertions weakened
  to tautologies (`assert True`, `assert x == x`).
- A symbol named in this milestone's Implementation Targets that is left as a bare
  `raise NotImplementedError`/`todo!()`/`pass` while its corresponding frozen test is reported
  green (indicates the test was neutralized or the thing was faked).
- Density spikes of `# type: ignore`, `except: pass`, `unsafe` (Rust) without an adjacent
  justification comment.
Integrity incidents are never auto-retried; they go straight to PAUSE with an incident report.

## B.7 Escalation ladder

- **L0 — Retry with notes.** Fresh implementer context; append the latest `attempts.md`
  summary and the last Reject Report; restate the frozen suite and guardrails. May include a
  narrowing instruction ("reduce scope: make tests T1–T3 pass only"). Allowed up to `R_retry`
  times (default 2) before L1.
- **L1 — Escalate model.** Re-run the failing role (implementer or reviewer) on a stronger
  model with the same artifacts. Used when L0 is exhausted or a complexity signal trips. One L1
  attempt before L2 unless otherwise stated.
- **L2 — PAUSE (circuit breaker).** Hard stop. Orchestrator transitions the milestone to
  `PAUSED`, writes `.graphed/<Mx>/incident.md` (the triggering signal, the full metric history,
  the last diff, the integrity scan), halts ALL coding on this milestone, and **requires an
  explicit human `resume`/`abort` decision**. No agent can self-clear a PAUSE. The orchestrator
  must also PAUSE the whole pipeline (not just the milestone) on any integrity incident, so a
  human can decide whether the run is trustworthy.
- **L3 — Abort/rollback.** Human-only, from PAUSED: discard the milestone branch, restore to
  the last `DONE` milestone tag, archive the incident.

**Global circuit breakers** (independent of any single signal): a project-wide cap on
cumulative `tokens_spent` and on consecutive PAUSEs (default 2) — exceeding either halts the
entire run for human review. The orchestrator checkpoints its own state (current milestone,
phase, metric history) after every transition so a paused run resumes exactly where it stopped.

## B.8 What the orchestrator must guarantee (test the orchestrator itself)

The orchestrator is software and gets its own test suite: simulate agent behaviors (a faker
that makes steady progress; one that oscillates; one that tampers with frozen tests; one that
stalls; one that files a dispute; a flaky gate) and assert the correct transition/response for
each. A pipeline that cannot detect a tampering faker in test must not be used to run real
agents.

---

# PART C — REUSABLE ROLE-PROMPT TEMPLATES

Each template is launched with Part A + the named milestone payload from Part D. Fill `<Mx>`
and the bracketed payload references.

## C.1 `test-author` template

```
ROLE: Test author for milestone <Mx> of `graphed`. You write the acceptance test suite. You
will NOT see or write the implementation. Your tests become read-only ("frozen") and define
done-ness for this milestone.

INPUTS: Part A. The Acceptance Contract for <Mx> [Part D]. The public interfaces of merged
packages [provided]. There is no implementation of <Mx> yet.

DO:
1. Translate every clause of the Acceptance Contract into concrete tests: unit, property-based
   (`hypothesis`) where a property is stated, concurrency/stress tests where thread-safety is
   claimed (incl. a 3.14t free-threaded run), and the named functional tests verbatim.
2. Each test must be NON-VACUOUS: it must fail against an empty/stub implementation. Write tests
   so that the stub fails them for the RIGHT reason (assertion, not import error where
   avoidable).
3. Make tests deterministic. Seed randomness. Quarantine nondeterminism behind explicit markers
   only with written justification.
4. Place all tests under `tests/frozen/<Mx>/`. Add a short `tests/frozen/<Mx>/README.md` mapping
   each Acceptance Contract clause to the test IDs that cover it (traceability matrix).

DO NOT: write any implementation; weaken a clause to make it easier to test; assume an
interface not in the provided public interfaces (if one is missing, state the gap and stop).

OUTPUT: the test files + the traceability README. Then STOP. The orchestrator runs TEST_SANITY.
```

## C.2 `implementer` template

```
ROLE: Implementer for milestone <Mx> of `graphed`. Make the frozen test suite pass without
weakening it.

INPUTS: Part A (incl. A.7 integrity rules). Implementation Targets + Guardrails for <Mx>
[Part D]. The frozen test suite under `tests/frozen/<Mx>/` — READ ONLY. The `attempts.md` log.
The latest Reject Report, if present.

DO:
1. Implement ONLY this milestone's Implementation Targets, exactly as named. Use the techniques
   in A.2; do not invent alternatives to e.g. `egg` before trying it.
2. Run the gates locally before submitting (frozen tests, coverage >=90% new code, ruff/clippy,
   mypy --strict, determinism, benchmark where defined).
3. You MAY add tests under `tests/extra/<Mx>/` (e.g. to raise coverage). You MUST NOT modify
   anything under `tests/frozen/**`.
4. If you believe a frozen test is wrong, DO NOT route around it. File a Test Dispute per B.5
   and STOP.
5. Write your iteration entry to `.graphed/<Mx>/attempts.md`: what you changed, which tests pass
   now, which remain and why, and any risks.

DO NOT (A.7, restated, severe): touch frozen tests; lower thresholds; edit CI; stub or hardcode
the thing under test; flood `# type: ignore`/`except: pass`/`unsafe`. These trip the integrity
scan and PAUSE the run.

OUTPUT: a diff + a PR description with the Definition-of-Done checklist [Part E.0] ticked
honestly (tick only what is truly green). Then STOP. The orchestrator runs the gates.
```

## C.3 `reviewer` template

```
ROLE: Reviewer for milestone <Mx> of `graphed`. You judge what the mechanical gates cannot.
You have authority to REJECT. You may APPROVE only if the orchestrator confirms all gates green
(it will refuse to record an APPROVE otherwise).

INPUTS: Part A. The Review Focus for <Mx> [Part D]. The implementer's diff. ALL gate artifacts
(CI logs, coverage, clippy/mypy, benchmark, determinism, integrity scan).

ASSESS (non-mechanical judgment only — the gates already covered pass/fail):
1. INTENT: does the code satisfy the SPIRIT of the Acceptance Contract, not just the letter?
   Did any test pass because the implementation matches the spec, or because the behavior was
   narrowed to the exact test inputs (overfitting to tests)?
2. GUARDRAILS: was anything in the Implementation Targets quietly stubbed, deferred with a TODO,
   or faked while its test was made to pass another way?
3. TECHNIQUE: were the A.2 techniques actually used where required (e.g. is the M4 optimizer
   genuinely an `egg` equality-saturation pass, or a hand-rolled rewriter mislabeled)?
4. ABSTRACTION/MAINTAINABILITY: is the package boundary respected (e.g. `graphed-core` free of
   awkward)? Is the design extensible per the "improvements" doc?

OUTPUT one of:
- `APPROVE` with a one-paragraph justification (only meaningful if gates are green), OR
- a structured REJECT REPORT: a numbered list of specific, actionable defects, each tied to a
  file/line and to the Contract clause or guardrail it violates. Do NOT add scope beyond the
  milestone. Keep your issue set STABLE across cycles — re-raise unresolved issues by their
  number; only add a new issue if the implementer's change introduced it. (Issue-set growth
  without resolution is a non-convergence signal that PAUSEs the run.)
Then STOP.
```

---

# PART D — PER-MILESTONE PAYLOADS (M0–M9, incl. M0.5)

Each payload has: **Acceptance Contract** (for test-author) · **Implementation Targets +
Guardrails** (for implementer) · **Review Focus** (for reviewer) · **Budget caps** (override
B defaults). Technical specifics are unchanged from v1; only the framing is re-bucketed.

## M0 — Repository spine
- **Acceptance Contract.** Each package in A.4 is independently installable from a freshly
  built wheel on every A.5 matrix entry. `import graphed_core; graphed_core.version()` returns a
  string under both GIL and 3.14t interpreters. `make html -W` succeeds per package (zero
  warnings). CI runs lint/types/tests/wheel-build on the full matrix; a release workflow targets
  TestPyPI on tag and PyPI on release.
- **Implementation Targets + Guardrails.** Monorepo; workspace `Cargo.toml`; per-package
  `pyproject.toml` (maturin for Rust, hatchling for pure-Python); dev tooling (ruff, mypy,
  pytest+cov+xdist+hypothesis, clippy, pre-commit); a trivial `graphed_core.version()` PyO3
  function to prove the Rust→Python→wheel path; CI + release workflows; Sphinx skeletons incl.
  empty `improvements.rst` + `Design` stub; `CONTRIBUTING.md` encoding A.7 + the pipeline.
  *Guardrail:* NO IR or analysis logic — pure infrastructure.
- **Review Focus.** Is the matrix truly exercised (no silently-skipped targets)? Are wheels
  actually built, not faked? Is the release path safe (no accidental PyPI publish on PR)?
- **Budget caps.** iterations ≤ 8; this is plumbing — gate-stuck here usually means a real CI
  problem, escalate early.

## M0.5 — Reference corpus study & Required Operations Catalog (decompose/strong-model milestone)
This milestone is executed by the strong/human decompose role, not the weak implementer loop —
it produces the requirements and fixtures every later test-author step consumes. Output is
documents + runnable fixtures, not framework code.
- **Acceptance Contract.** A committed **Required Operations Catalog** (`docs/requirements/ops_catalog.md`)
  enumerating every array operation, selection/weight/category construct, systematic pattern
  (weight vs kinematic), correction type (correctionlib), and ML-inference pattern (ONNX/Triton)
  observed across the A.8 corpus, each tagged with the corpus analysis it came from and the
  milestone that must support it. A committed **Canonical Analyses** fixture tree
  (`tests/corpus/`) containing, at minimum: ADL queries 1–8, a reduced AGC ttbar slice, and a
  TTGamma-style selection+SF+systematics slice — each expressed first as plain
  coffea/awkward (the reference) producing a stored reference histogram, so later milestones can
  assert `graphed` reproduces it bit-for-bit. A short **graph-bloat note** comparing the
  dask-awkward vs virtual-array coffea-benchmark branches, quantifying the node-count explosion
  `graphed` must avoid (feeds M4's reduction targets).
- **Implementation Targets + Guardrails.** Read the A.8 repos; extract, do not invent. Produce
  the Catalog, the fixtures, and the reference outputs. Fixtures live in a dev-only shared
  location importable by all packages' test suites (e.g. `tests/corpus/`, no published package).
  *Guardrail:* no `graphed` implementation here; this is requirements + reference data only. If a
  corpus analysis needs an op the later op surface can't reasonably support in the MVP, record it
  in the Catalog as "Phase 2" with a rationale rather than silently dropping it.
- **Review Focus.** Is the Catalog faithful to the corpus (spot-check against the actual repos),
  or imagined? Do the reference histograms actually run and reproduce? Is each catalog entry
  mapped to a milestone, so nothing real is left untested?
- **Budget caps.** iterations ≤ 6. Coverage/benchmark gates N/A (no framework code); the gate is
  reviewer sign-off that the Catalog and fixtures are faithful and runnable.

## M1 — `graphed-core`: thread-safe interned graph IR (Rust+PyO3)
- **Acceptance Contract.** Interning returns identical `NodeId` for structurally identical
  inputs (incl. float edge cases `0.0`/`-0.0`/`NaN`) and distinct IDs otherwise. After random op
  sequences, `node_count` == number of distinct structural keys (property test). Many Python
  threads building overlapping subgraphs concurrently (under GIL and 3.14t) yield exactly the
  distinct-key count with no panic/race. `to_dot()` is byte-stable across runs (determinism).
  Two `External` nodes with identical payload descriptors intern to one node; changing any
  descriptor field (e.g. a model content hash) yields a distinct `NodeId`.
- **Implementation Targets + Guardrails.** `Node` enum (`Source|Op|Reduction|External|Stage`);
  the `External` variant MUST carry a `PayloadDescriptor` (kind, content hash, framework+version,
  I/O schema, preprocessing ref — per A.3.1) so external inputs are reproducibly identified, and
  this descriptor participates in the node's structural hash; arena (`slotmap`/Vec+generation);
  `GraphStore` with intern table keyed on structural hash; `Send+Sync` with a documented locking
  discipline (sharded locks or `RwLock`); deterministic `ParamMap` (sorted keys, total-order
  float hashing); PyO3 bindings (`Bound` API, PyO3>=0.28, module marked free-threading-safe)
  exposing `add_source/add_op/add_reduction/add_external/mark_output/node_count/to_dot`. Include
  a Rust `loom` test of the locking discipline (or a written rationale if impractical).
  *Guardrails:* no optimization (M4); no awkward; graph lives in Rust, not Python.
- **Review Focus.** Is the locking discipline actually sound (not just "passed the stress test
  once")? Is the float-hashing total order correct? Is `unsafe` justified line-by-line?
- **Budget caps.** iterations ≤ 12; concurrency correctness is the risk — on any race signal,
  prefer L1 (stronger model) over many L0 retries.

## M2 — `graphed` frontend + backend protocol + `graphed-numpy`
- **Acceptance Contract.** Each supported op records exactly one interned node + one form;
  repeated identical sub-expressions record zero additional nodes. A 20-line numpy-backend
  program (map/filter/arith/reduce) builds a small correct graph. Swapping to a second toy
  backend changes results but NOT recorded graph structure (backend-independence). An ill-typed
  op raises at the user line that wrote it (filename+lineno).
- **Implementation Targets + Guardrails.** `Backend` Protocol (`op_form`, `eval_stage`,
  `project`, `boundary_ops`, and `external_payload(node) -> PayloadDescriptor | None` — backends
  declare the reproducibility metadata for any external/opaque op they emit) + opaque `Form`
  protocol; deferred `Array` proxy recording into the M1 store, computing forms via the backend,
  calling a `provenance.capture()` hook (stub here); `graphed-numpy` backend (numpy ufuncs /
  arbitrary callables over a bag; no HEP — its `external_payload` returns a descriptor for any
  wrapped opaque Python callable, flagged as a preservation risk). *Guardrails:* no fusion (M4);
  no awkward (M3); provenance is a stub.
- **Review Focus.** Is the IR genuinely backend-agnostic (no numpy/awkward leakage into
  `graphed` core types)? Does the proxy intern correctly through the frontend?
- **Budget caps.** iterations ≤ 10.

## M3 — `graphed-awkward`: typetracer forms + provenance capture
- **Acceptance Contract.** The dimuon smoke analysis (read events → dimuon pairs → invariant
  mass → mass-window cut → 1D histogram fill) records WITHOUT reading event data (metadata only),
  forms correct at each step. **In addition, ADL Canonical Analyses (M0.5) queries 1–8 and the
  AGC ttbar object-selection slice each record successfully** (forms correct, metadata-only),
  exercising the Required Operations Catalog — any catalog op the frontend cannot record is a
  failure, not a silent gap. Every node maps to a user-code line, never a `graphed*` line; the
  dimuon-mass node maps to its exact source line. `op_form` touches only the branches actually
  used (sets up M5). Provenance-on vs -off build overhead is reported within budget. A
  correctionlib scale-factor application and an ONNX model evaluation each record an `External`
  node whose payload descriptor content-hashes the correction JSON / model file (sets up M9).
- **Implementation Targets + Guardrails.** `AwkwardBackend` using awkward typetracer for
  `op_form` and real awkward for `eval_stage`; `from_root`/`from_parquet` sources reading only
  metadata; real `provenance.capture()` (first non-`graphed*` frame; `stack_data`/`executing`
  for sub-expression text; thread-safe side-table; toggleable + benchmarked). Implement
  `external_payload` for the two HEP-standard external inputs: corrections/scale-factors via
  **correctionlib** (descriptor = the correction-set JSON's content hash + correction name +
  schema version) and ML models via **ONNX** (descriptor = model content hash + opset + I/O
  schema); a `from_root` source's descriptor records dataset ID + file content hashes.
  *Guardrails:* reuse awkward typetracer (do not reimplement); reuse correctionlib/ONNX (do not
  invent correction or model formats); no optimization yet.
- **Review Focus.** Does provenance survive realistic call patterns (helper functions, list
  comprehensions)? Is "metadata only" truly enforced (no accidental data read)?
- **Budget caps.** iterations ≤ 12.

## M4 — `graphed-core` optimizer: DCE, CSE, canonicalization, stage fusion via equality saturation
- **Acceptance Contract.** Executor output is identical on reduced vs un-reduced graphs
  (canonical analysis + numpy backend). Canonical analysis reduces to < 10 stages regardless of
  intermediate-variable count. A 10,000-node systematics graph with heavy shared substructure
  reduces in < 1 s to O(stage) nodes. **The real AGC ttbar slice (M0.5) with its full systematic
  set — the realistic source of the O(10000)-node case — reduces to a concise stage-graph whose
  node count scales with stages, not with systematics count**, and the reduction wall time is
  reported against the M0.5 graph-bloat note as the headline win. **A CI benchmark FAILS if
  reduction wall time grows super-linearly across sizes {1k,2k,4k,8k}** (guards against
  re-introducing O(N^2)). Identical input graph → byte-identical optimized graph (determinism).
  Property: DCE never drops a node on a path to an output; fusion never merges across a boundary op.
- **Implementation Targets + Guardrails.** Define an internal **`RewriteEngine` trait**
  (the e-graph engine boundary): inputs = the op IR + a rule set + a cost function; output =
  the canonicalized, fused stage-graph. Implement `dead_code_elimination` and `cse` as plain
  passes OUTSIDE this trait (DCE = reachability from outputs; CSE = already provided by M1
  hash-consing — assert it, don't re-derive it). Implement `canonicalize` + `stage_fusion` as an
  **equality-saturation pass behind `RewriteEngine`, using the `egg` crate as the MVP engine**
  (op `Language`, rewrite rules incl. mask-fusion/field-collapse/const-fold/sound commutativity,
  saturation budget, `CostFunction`/`Extractor`-based extraction rewarding fewer stages + more
  ops/stage, penalizing boundary crossings). Also implement `reduce_incremental(graph,
  new_nodes)` so reduction runs as the user builds (A.3 #1; egg e-graphs are additive, so
  re-run on the existing e-graph) and `reduction_report()`. *Guardrails:* the engine MUST be
  reachable only through `RewriteEngine` (no `egg` types leaking past the trait — this is what
  lets Phase 2 swap in `egglog`); use the engine before any bespoke rewriter; keep optimization
  in Rust.
- **Review Focus.** Is it genuinely equality saturation (e-graph + cost-based extraction), or a
  relabeled greedy pass? **Is the `RewriteEngine` boundary clean — no `egg` types leaking past
  the trait, and are DCE/CSE genuinely outside the engine?** Is the cost function defensible?
  Are the rewrite rules SOUND (no semantics change)? The super-linear benchmark is the single
  most important guard — scrutinize it.
- **Budget caps.** iterations ≤ 16 (hardest milestone). The cost-function exact weights are
  EXPECTED to need a Test Dispute / human input — that is normal here, not a failure.

## M5 — Necessary-buffer (column) projection
- **Acceptance Contract.** Canonical analysis projects to only the muon branches used (e.g.
  pt/eta/phi/charge), not the whole event record. Against a real NanoAOD file, projected reads
  transfer dramatically fewer bytes (assert a ratio threshold). An opaque op triggers the
  configured on-fail policy (`pass|warn|raise`) exactly.
- **Implementation Targets + Guardrails.** `project` hook: `graphed-awkward` builds a reporting
  typetracer per source, runs stages symbolically, collects touched form-keys, attaches
  `read_columns`; `graphed-numpy` returns trivial all-inputs. Mirror dask-awkward on-fail
  semantics. *Guardrail:* column selection only (no predicate pushdown in MVP).
- **Review Focus.** Does projection stay correct after M4 fusion (touch-tracking through fused
  stages)? Is the on-fail policy honored on genuinely opaque ops, not silently passed?
- **Budget caps.** iterations ≤ 10.

## M6 — `graphed-debug`: opt-level lowering, source-mapped tracebacks, visualization
- **Acceptance Contract.** Injecting an out-of-range index into the mass calc yields a formatted
  traceback whose top user frame is the exact analysis line; under `opt_level=0` the identical
  source location is reported with a 1:1 op↔node mapping. **`StageError` survives serialization
  across a process boundary: an error raised in a separate worker process is re-raised in the
  driver as the SAME formatted traceback pointing at the user's analysis line — never a raw,
  opaque worker/distributed traceback** (directly addresses A.3 failure #8). Canonical analysis
  renders to a small, legible stage-graph (snapshot the structure).
- **Implementation Targets + Guardrails.** `lower(graph, opt_level)` (0 = no fusion + sample +
  inter-op assertions; ≥1 = fused); `StageError` carrying failing op + provenance + input forms
  + partition, and **picklable so it round-trips intact from a remote worker** (the source
  location and user-frame chain must serialize, not just a string); `format_traceback`
  collapsing `graphed*` frames; `visualize` (Graphviz/Mermaid annotated with provenance +
  projected columns). *Guardrail:* no interactive debugger/replay (Phase 2).
- **Review Focus.** Does the mapping hold for errors raised DEEP inside a fused kernel, not just
  the first op? Does it survive the process boundary (pickle round-trip) without degrading to an
  opaque string? Is `opt_level=0` truly 1:1?
- **Budget caps.** iterations ≤ 10.

## M7 — Execution-layer contract + `graphed-exec-local`
- **Acceptance Contract.** **The full AGC ttbar slice (M0.5) — two regions, weight AND kinematic
  (JES/JER) systematics, b-tagging scale factors via correctionlib, and the ONNX ML-inference
  step — runs end-to-end and reproduces the stored reference histograms bit-for-bit** (this is
  the headline functional test; the dimuon smoke analysis and ADL queries also pass, invariant to
  `opt_level` and projection). A simulated workload of thousands of tiny tasks with injected
  variable delays completes with NO deadlock, NO stall (assert monotonic accumulator progress),
  NO race (repeated runs under stress/xdist and 3.14t); a single artificially-slow straggler does
  NOT block reduction of others (tree reduction). A probe-driven scenario resizes later
  partitions from observed timings and folds resized-task outputs correctly. A multi-chunk
  single-file task with `open_once` opens the file exactly once per worker (counting fake reader).
  **An error raised in a worker PROCESS (not thread) surfaces in the driver via M6's
  `format_traceback` pointing at the user's analysis line — never a raw worker traceback**
  (A.3 #8).
- **Implementation Targets + Guardrails.** Abstract `Executor` protocol in `graphed-core`:
  `submit(plan)`; `next_tasks(context) -> Iterable[Task]|DONE` (bidirectional adaptive-reshaping
  hook); stopping conditions (data exhausted / target events / precision / wall-clock / error
  budget); associative tree reduction; file-locality `open_once` directive; **a defined
  error-propagation obligation — executors MUST return remote `StageError`s intact (picklable,
  per M6) so the driver renders the user-source traceback, not the worker's opaque one**.
  Reference executor in `graphed-exec-local`: thread-safe worker pool AND a process-pool mode
  pulling from the generator, structured-concurrency join, work-stealing, tree reduction into
  `hist`. *Guardrails:* single machine only (no cluster — Phase 2); keep the published contract
  minimal and mark it **provisional until exercised by a real adapter**.
- **Review Focus.** Concurrency correctness is the risk: are the no-stall and no-block-on-
  straggler properties genuinely guaranteed by the design, or did the test just not trigger the
  bug? Does the AGC kinematic systematic genuinely alter selection (not just reweight)? Does the
  remote-error path degrade to an opaque string anywhere? Is the contract small enough to be
  stable, yet sufficient for adaptive reshaping?
- **Budget caps.** iterations ≤ 16. Any stall/deadlock test flake → treat as real (signal #10
  → escalate), never dismiss.

## M8 — `graphed-checkpoint`: plan serialization, content-addressed checkpoint/resume, error harvesting
- **Acceptance Contract.** Kill a run halfway; re-run; final histogram equals an uninterrupted
  run AND the second run does measurably less work (skipped tasks logged). A serialized plan
  deserializes and runs on a machine with NO source files present. An injected per-partition
  failure lands in the dead-letter set with a reproducible descriptor; `retry_smaller_chunk`
  succeeds where the original OOMed (simulated). Identical plan → byte-identical serialization.
- **Implementation Targets + Guardrails.** Versioned deterministic `Plan` serialization. The
  **canonical durable form is the serializable IR** (typed ops + params + `External` payload
  descriptors + references); cloudpickle is used ONLY for genuinely opaque user callables that
  cannot be expressed in the IR, and every such cloudpickled node is **tagged
  `opaque=True` / preservation-risk** so M9 can surface it. The `Plan` carries read_columns,
  partitions, reduction spec, stopping conditions, file-locality, resource hints; content-addressed
  `task_id`; `Store` (content-addressed outputs + append-only manifest/journal + partial
  accumulator) consulted by the executor to skip completed work — this same Store backs M9's
  payload references; error harvesting (dead-letter set with `StageError` + reproducible
  descriptor + provenance) and policies `retry_n|retry_smaller_chunk|retry_elsewhere|quarantine`
  with an error budget as a stopping condition. *Guardrail:* local filesystem store only (no
  distributed store in MVP); M8 stays scoped to checkpoint/resume — analysis preservation is M9.
- **Review Focus.** Is resume truly correct under partial/interrupted writes (no double-count,
  no lost partition)? Is `task_id` actually content-addressed (cache-poisoning-safe)?
- **Budget caps.** iterations ≤ 12.

## M9 — `graphed-preserve`: analysis preservation bundle (reproducible scientific artifact)
- **Acceptance Contract.** A **Preservation Bundle built for the AGC ttbar slice (M0.5)** — chosen
  precisely because it contains an ONNX model, correctionlib scale factors, and systematics —
  reproduces its histograms **bit-for-bit on machine B that has NO access to the original user
  code, environment, author, or input files** (inputs resolved only via the bundle's
  content-addressed references to a durable archive). The bundle is **complete and
  self-fingerprinting**: changing any auxiliary input — a correctionlib JSON, the ONNX model
  weights, a dataset file, a config value, or a seed — changes the bundle's top-level content
  hash; changing nothing reproduces an identical hash. `inspect(bundle)` renders the analysis
  logic (the graph IR + the M6 user-source provenance/sourcemap) as human-readable output WITHOUT
  executing anything, and lists every `External` payload with its descriptor (the model and each
  correction set) and every `opaque=True` node flagged as a preservation risk. A bundle whose
  referenced payloads are missing from the archive fails `reproduce()` with a precise "unresolved
  payload <hash>" error, never a silent wrong result.
- **Implementation Targets + Guardrails.** `build_bundle(graph, env, datasets) -> Bundle`
  capturing: the canonical serializable IR (from M4/M8, NOT cloudpickle except flagged opaque
  nodes); the M6 provenance/sourcemap; every `External` `PayloadDescriptor`; auxiliary payloads
  by content hash in the M8 `Store` (embedded for small, pinned-reference for large — never
  inlined into the manifest); input dataset IDs + file content hashes; the software environment
  (lockfile AND/OR container digest); config + seeds; and a top-level **manifest** (a
  bill-of-materials binding every component by hash, itself hashed = the bundle fingerprint).
  `reproduce(bundle)` re-instantiates and runs via the M7 executor; `inspect(bundle)` renders
  logic + payload inventory + risk flags. *Guardrails:* reuse HEP standards — corrections stay
  correctionlib JSON, models stay ONNX, histograms serialize via UHI, statistical models (if
  any) via HS3; do NOT invent formats; do NOT embed large payloads in the manifest; the bundle
  MUST be runnable from references alone (prove the no-original-files property in test). Builds
  on M8's determinism and Store; this milestone is the reproducibility requirement of A.3.1.
- **Review Focus.** Is the bundle TRULY self-contained — does the machine-B test genuinely lack
  the originals, or did a path leak? Does the fingerprint actually change on every
  result-determining input and NOT on irrelevant ones (no over- or under-sensitivity)? Are opaque
  cloudpickled nodes honestly surfaced as risks rather than hidden? Is `inspect` faithful to what
  `reproduce` runs (no drift between the auditable view and the executed graph)?
- **Budget caps.** iterations ≤ 14. The embed-vs-reference size threshold and the exact
  environment-capture mechanism (lockfile vs container digest) are EXPECTED to need a Test
  Dispute / human input — normal here, not a failure.

---

# PART E — MVP DEFINITION OF DONE

## E.0 Per-milestone DoD checklist (implementer ticks honestly; reviewer + gates verify)
```
[ ] Implementation Targets done exactly as specified (nothing stubbed/faked)
[ ] All frozen tests pass; frozen tests UNMODIFIED since freeze tag
[ ] Coverage >= 90% line+branch on new code
[ ] Named functional tests pass; property/concurrency tests pass (incl. 3.14t where required)
[ ] Determinism gate green; milestone benchmark within budget (where defined)
[ ] ruff + clippy clean; mypy --strict clean; integrity scan clean
[ ] Sphinx builds with -W (zero warnings), incl. inheritance diagrams + improvements.rst
[ ] CI green on full A.5 matrix; wheels build on all targets
[ ] attempts.md updated; reviewer APPROVE recorded
```

## E.1 MVP outcome
A user writes ordinary awkward-style analysis; `graphed` records it into a Rust-backed
thread-safe store, reduces it to a handful of stages via equality saturation in near-linear time
(a 10,000-node systematics graph reduces in under a second and never exists un-reduced),
projects the minimal columns, executes locally through the published contract to a bit-for-bit
match with plain awkward, points any runtime error at the exact user source line, serializes the
plan, and resumes a killed run while harvesting and resubmitting failed partitions; and it emits
a self-contained, content-addressed **Preservation Bundle** — graph IR + source-map + every
correctionlib/ONNX payload by hash + dataset IDs + environment — that reproduces the histogram
bit-for-bit on a clean machine with no access to the original code, files, or author, and is
human-inspectable without execution — with per-package Sphinx docs, green CI, and wheels across
the full matrix incl. 3.14t — and every milestone was produced through the gated
test-author/implementer/reviewer pipeline with a clean escalation history (no unresolved
integrity incidents). Throughout, correctness is validated against the A.8 reference corpus —
the ADL benchmark queries and the AGC ttbar slice (with its kinematic systematics, b-tag scale
factors, and ONNX inference) reproduce stored references bit-for-bit — and any runtime error,
including one raised in a remote worker process, surfaces as a traceback pointing at the user's
analysis line rather than an opaque distributed stack trace.

---

# PART F — PHASE 2 (scope only; do NOT build in the MVP)

`graphed-exec-taskvine` (the M7 contract against TaskVine: in-cluster storage, fine-grained
allocation, dynamic task shaping), then HTCondor/Slurm adapters. Systematics as a graph axis
(named axes for weight-only variations; template instantiation, not subgraph copies, for
kinematic ones; cf. RDataFrame `Vary`). Advanced adaptive reshaping (full probe-job models,
accelerator-aware allocation). Predicate pushdown beyond column projection. Interactive
debug / time-travel replay of stage execution.

**Preservation & reinterpretation export (from M9).** Export a Preservation Bundle to a
**REANA** reproducible-workflow spec so it runs on the CERN/IRIS-HEP preservation platform;
register bundles in **CERN Analysis Preservation** and archive to **Zenodo** with a minted DOI
so the optimized analysis becomes a citable scientific artifact. Add a **RECAST-style
reinterpretation entrypoint**: swap a bundle's dataset reference or model/correction payload for
a new one and re-run the otherwise-frozen preserved graph, enabling theorists to test new models
through a published analysis. Optionally emit the statistical model via **HS3** for likelihood
publication. All of these consume the M9 bundle unchanged — they are exporters, not new graph
machinery.

**`egglog` as the production `RewriteEngine` (the intended final optimizer; from M4).** `egg` is
the MVP engine; **`egglog` is the intended final/production optimizer.** Replace the `egg`
implementation behind the M4 `RewriteEngine` trait with `egglog` (egg's Datalog-unifying
successor; more general, faster relational e-matching, native incremental execution). Switch
ONLY when at least one trigger fires: (1) the rewrite rule set begins needing **conditional /
analysis-gated rewrites** — e.g. "apply this rewrite only when a form/shape lattice analysis
proves property P" — which is egglog's Datalog strength and which `egg` expresses only awkwardly;
(2) **incremental
re-optimization** as the user edits an already-built graph becomes a measured bottleneck and
egglog's incremental execution materially beats re-running `egg`; or (3) the systematics-as-axis
work above wants cooperating analyses to drive variation-aware fusion. Do NOT switch for raw
saturation speed alone — at the MVP's small, kept-small rule set that is not the bottleneck.
Switch cost/risk to budget: egglog is language-first (the engine must be driven via egglog
programs/AST rather than a typed Rust `Language`), its extraction is less ergonomic than egg's
in-Rust `CostFunction`, its API is younger (the "batteries-included" stdlib ships as the
explicitly *unstable* `egglog-experimental`), and the byte-identical-determinism gate (B.3.3)
must be re-validated against the new engine. Because M4 confined the engine behind
`RewriteEngine`, the swap is local to one trait impl; the determinism, super-linear-scaling, and
reduced-vs-unreduced-equivalence tests are engine-agnostic and gate the swap automatically.
