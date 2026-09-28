# CLAUDE.md — root (graphed-project)

This is the **root** guidance for the `graphed` project. The project is a set of GitHub
repositories under the **`graphed-org`** organization, created incrementally as milestones
progress. This repo (`graphed-project`) is the **meta / superproject**: it holds this root
`CLAUDE.md`, the authoritative plan, and the package repos as **git submodules**.

## Precedence (read this first)

When guidance conflicts, the higher authority wins:

1. **`graphed-project-plan-gated.md` (the project plan) — ALWAYS wins.**
2. **This root `CLAUDE.md`** — wins over any sub-repo `CLAUDE.md`.
3. **A sub-repo's `CLAUDE.md`** — local detail only; never contradicts 1 or 2.

If you find a conflict, follow the higher authority and say so explicitly in your response. Do not
silently resolve it.

## Repository layout

The plan's M0 literally says "Monorepo." **We deviate deliberately: this project is multi-repo.**
Everything M0 asks for (per-package CI, lint/types/tests on the full §A.5 matrix, wheels, release
workflow, Sphinx skeleton with `improvements.rst`, `CONTRIBUTING.md` encoding §A.7 + the pipeline)
still applies — it is replicated **per repository** rather than once in a workspace.

```
graphed-org/
  graphed-project        meta/superproject — root CLAUDE.md + the plan + submodules   [EXISTS]
  graphed-orchestrator   Part B deterministic state machine, gates, escalation        [EXISTS]
  graphed-corpus         M0.5 Required Operations Catalog + Canonical Analyses + refs  [EXISTS]
  graphed-core           M1/M4/M7-contract/M8-plan: Rust+PyO3 IR, optimizer, plan      [lazy]
  graphed                M2/M3: Python frontend, deferred proxy, builder, provenance   [lazy]
  graphed-awkward        M3/M5: reference backend (awkward typetracer)                 [lazy]
  graphed-numpy          M2: trivial backend proving the seam                          [lazy]
  graphed-debug          M6: sourcemaps, opt-level lowering, tracebacks, viz           [lazy]
  graphed-exec-local     M7: reference executor                                        [lazy]
  graphed-checkpoint     M8: content-addressed store, manifest, resubmission           [lazy]
  graphed-preserve       M9: analysis preservation bundle                              [lazy]
```

`[lazy]` repos do **not** exist yet — they are created when their milestone begins (see below).
All repos default to **private**; flip to public deliberately when a package is publishable.

### Milestone → repository map

| Milestone | Primary repo(s) | Notes |
|---|---|---|
| M0 (spine) | every repo, at creation | each repo bootstraps its own CI/tooling/wheels/Sphinx spine |
| M0.5 | `graphed-corpus` | requirements + fixtures only, no framework code |
| M1 | `graphed-core` | interned thread-safe IR |
| M2 | `graphed` + `graphed-numpy` | frontend + backend protocol + trivial backend |
| M3 | `graphed-awkward` (+ `graphed`) | typetracer forms + provenance |
| M4 | `graphed-core` | optimizer: DCE/CSE + equality-saturation stage fusion |
| M5 | `graphed-awkward` (+ `graphed-numpy`) | column projection |
| M6 | `graphed-debug` | opt-level lowering + source-mapped tracebacks |
| M7 | `graphed-exec-local` (+ `graphed-core` contract) | executor + exec protocol |
| M8 | `graphed-checkpoint` (+ `graphed-core` plan) | plan serialization + checkpoint/resume |
| M9 | `graphed-preserve` | preservation bundle |
| (all) | `graphed-orchestrator` | drives the gated pipeline for every milestone |

## Working across submodules

```bash
# clone the whole project
git clone --recurse-submodules git@github.com:graphed-org/graphed-project-mvp.git
# or, after a plain clone:
git submodule update --init --recursive
# pull latest of everything
git pull && git submodule update --init --recursive
```

When a submodule advances, commit the updated submodule pointer in `graphed-project` so the
superproject pins a known-good revision of each package.

The root `README.md` is **generated** from `.graphed/state.json` + the submodule pins by
`scripts/gen_readme.py` — never edit it by hand. **Do meta-repo bookkeeping through
`scripts/bookkeep.py`**, which regenerates the README (gen_readme is hooked in), then stages the
state, the README, and every submodule pointer:

```bash
python scripts/bookkeep.py --set-current M6 --touch --commit "M5 DONE: ..." \
    --trailer "Assisted-by: ClaudeCode:<model>" [--push]
```

Per-milestone status/evidence edits stay explicit in `.graphed/state.json`; run `bookkeep.py`
afterwards to sync + stage. The `readme-sync` CI workflow runs the generator/bookkeeping tests and
`gen_readme.py --check`, failing if the committed README drifted. Optional local guard:
`git config core.hooksPath scripts/hooks` enables a pre-commit check that mirrors CI.

### Creating a new package repo (lazy, when a milestone starts)

Only create a repo when its milestone enters `DECOMPOSE`/`TEST_AUTHORING`. Recipe:

```bash
gh repo create graphed-org/<name> --private --description "<one line>"
# build the M0 spine for that repo (CI matrix §A.5, pyproject/Cargo, tooling, Sphinx,
# CONTRIBUTING.md encoding §A.7, a distilled CLAUDE.md that defers to this root), commit, push.
# then register it in the superproject:
git -C <graphed-project> submodule add git@github.com:graphed-org/<name>.git <name>
git -C <graphed-project> commit -am "Add <name> submodule (M<x>)"
```

Each new sub-repo gets its own `CLAUDE.md` distilled from the relevant Part D milestone payload(s),
opening with: *"Defers to the root `graphed-project/CLAUDE.md`; the project plan always wins."*

---

The rest of this file is the project-wide spec digest. It binds every repo. Repo-specific detail
lives in that repo's `CLAUDE.md`; the authoritative source is always the plan.

## What `graphed` is (§A.1)

A schedulable, serializable, debuggable HEP task-graph system that **reduces the graph to a
concise set of stage-nodes incrementally as the user builds it**, so a large un-reduced graph
never exists. Reduction runs in a Rust extension via **equality saturation over e-graphs**. A
"stage" is a maximal fused run of array ops between boundaries (source, reduction, repartition,
checkpoint, external/opaque op). Goal: minimize Python-interpreter touchpoints, maximize time
inside array kernels (awkward by default). The middle path between dask-awkward (kept a huge
graph; O(N²) optimization dominated wall time) and coffea 2025 (discarded the schedulable graph).

## dask failures we must NOT repeat (§A.3)

1. Build a complete graph before optimizing reusable sub-components. 2. Record intent
operator-by-operator. 3. Slow optimization dominating wall time. 4. High local memory from graph +
optimization. 5. Unclear packaging of a large component (e.g. an NN) for parallel execution.
6. Low-level graphs so large the interpreter is a cost. 7. Optimized graphs so nested with
sub-graph-execute calls that interpreter time is a cost. 8. Opaque remote/distributed tracebacks —
a runtime error must point at the user's analysis line.

## Techniques to USE (§A.2) — do not hand-roll alternatives

- **Equality saturation over e-graphs** for canonicalization + cost-based stage fusion. MVP engine
  is the **`egg` Rust crate**, behind an internal `RewriteEngine`/`Optimizer` trait so it is
  swappable. `egglog` is the **Phase-2** swap — do NOT build it in the MVP.
- **DCE and CSE live OUTSIDE the engine**: DCE = reachability from outputs; CSE falls out of M1
  hash-consing (assert it, don't re-derive it).
- Hash-consing/interning for dedup on construction. Logical-vs-physical plan; Volcano/Cascades
  cost-based optimization. Operator fusion + morsel-driven parallelism.
- IR via typetracer abstract evaluation — **reuse awkward's typetracer, do NOT reimplement type
  inference.** Dynamic task graphs + futures; structured concurrency + work-stealing + tree
  reduction. Content-addressed memoization (Nix/Bazel/ccache) for checkpoint/resubmission.
- Free-threaded Python (CPython 3.14t) + PyO3 ≥ 0.28 + maturin.

Invent no formats: corrections = **correctionlib** JSON, models = **ONNX**, histograms = **UHI**,
stat models = **HS3**, environment = container digest, datasets = IDs + content hashes.

## Reproducibility is first-class (§A.3.1)

The serializable **IR — not cloudpickle — is the canonical durable representation.** cloudpickle is
reserved ONLY for genuinely opaque user callables; any such node is flagged `opaque=True` as a
preservation risk. `External` nodes carry a full `PayloadDescriptor` (kind, content hash,
framework+version, I/O schema, preprocessing ref). Large payloads are referenced by content hash in
the M8 Store, never inlined.

## Package boundaries (§A.4) — hard rules

`graphed-core` (Rust+PyO3: IR, interned store, optimizer, plan serialization, exec protocol) **MUST
NOT import awkward.** `graphed` frontend is backend-agnostic (no numpy/awkward leakage into core
types). `graphed-awkward`/`graphed-numpy` reuse awkward typetracer / numpy respectively.
`graphed-exec-local` is single-machine only (MVP). `graphed-checkpoint` is local-filesystem store
only. `graphed-preserve` reuses HEP standards, invents no formats.

## Build matrix (§A.5)

OS {Linux, macOS, Windows} × arch {x86_64, arm64} × CPython {3.11, 3.12, 3.13, 3.14, 3.14t}. Rust
packages: abi3 where possible + a dedicated 3.14t free-threaded wheel; maturin + cibuildwheel;
pinned/tested MSRV.

## The development process is a GATED THREE-ROLE PIPELINE (Part B)

Each milestone runs through three **isolated agent contexts** that never converse — they hand off
through frozen artifacts — coordinated by the **deterministic `graphed-orchestrator`** (a state
machine, NOT an LLM). Roles:

- **test-author** — writes the acceptance suite. Never sees/writes implementation. Tests under
  `tests/frozen/<Mx>/` + a traceability README. Frozen = read-only thereafter.
- **implementer** — makes the frozen suite pass without weakening it. May add `tests/extra/<Mx>/`;
  MUST NOT touch `tests/frozen/**`. Logs each iteration to `.graphed/<Mx>/attempts.md`.
- **reviewer** — judges what gates cannot (intent, guardrails, technique, abstraction). May REJECT;
  may APPROVE only when every mechanical gate is green.

State machine: `PENDING → DECOMPOSE → TEST_AUTHORING → TEST_SANITY → FROZEN → IMPLEMENTING →
REVIEW → DONE`; side states `TEST_DISPUTE`, `ESCALATED`, `PAUSED`, `ABORTED`. **The next milestone
must not start until the current is `DONE`.** Orchestrator detail lives in `graphed-orchestrator`.

## Integrity rules — NON-NEGOTIABLE (§A.7, §B.6)

Violations are severe and PAUSE the entire run. Never:
- edit, delete, `skip`, `xfail`, or weaken any test under `tests/frozen/**`;
- lower a coverage/benchmark threshold or relax CI gate config;
- stub, mock, or hard-code the specific thing a test verifies;
- leave a named Implementation Target as bare `NotImplementedError`/`todo!()`/`pass` while
  reporting its test green;
- blanket-apply `# type: ignore`, `except: pass`, or unjustified `unsafe`.

If a frozen test seems wrong, **do NOT route around it** — file a Test Dispute at
`.graphed/<Mx>/disputes/<test_id>.md` (the test, the spec clause it contradicts, a proposed
correction) and STOP. Honesty about incompleteness beats a green gate obtained by cheating.

## Mechanical gates (§B.3) — every implementer iteration

`frozen_tests` all pass · `coverage` ≥ 90% line+branch **diff** coverage on new/changed lines, with
covering hits from the **frozen** suite (not only `tests/extra/**`) · `lint` (`ruff` + `cargo
clippy` clean) · `types` (`mypy --strict` clean) · `determinism` (identical input → byte-identical
optimized graph / serialized plan across two runs) · `benchmark` (within budget, where defined) ·
`integrity_scan` clean. TEST_SANITY (pre-freeze): suite collects, is **non-vacuous** (fails the
stub for the right reason), deterministic across two runs, coverage instrumentation wired.

## Definition of Done (§E.0) — tick only what is truly green

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

## Milestones (Part D) — build strictly in order

- **M0** spine (per repo). **M0.5** corpus → `graphed-corpus`. **M1** thread-safe interned IR
  (`External` carries `PayloadDescriptor` in its structural hash). **M2** frontend + `Backend`
  protocol + `graphed-numpy`. **M3** awkward typetracer forms + real provenance + correctionlib/ONNX
  `External` nodes. **M4** optimizer: `RewriteEngine` trait (no `egg` types leak past it),
  incremental reduction, **CI benchmark FAILS on super-linear reduction time across
  {1k,2k,4k,8k}** — the single most important guard against O(N²); hardest milestone. **M5** column
  projection (no predicate pushdown). **M6** `StageError` **picklable across a process boundary**,
  re-raised pointing at the user's line (fixes §A.3 #8); `opt_level=0` is 1:1. **M7** full AGC ttbar
  slice end-to-end bit-for-bit; no deadlock/stall/race under thousands of tiny tasks; straggler
  doesn't block tree reduction; remote `StageError` surfaces via M6. **M8** deterministic versioned
  `Plan` (IR canonical, not cloudpickle) + content-addressed Store/resume + dead-letter/retry.
  **M9** self-contained content-addressed Preservation Bundle reproducing histograms bit-for-bit on
  a clean machine; `inspect()` without executing.

## Out of scope — Phase 2 (Part F), do NOT build

TaskVine/HTCondor/Slurm executors; systematics-as-a-graph-axis; advanced adaptive reshaping;
predicate pushdown; interactive debug/time-travel; REANA/CAP/Zenodo/RECAST/HS3 export; **swapping
`egglog` in behind `RewriteEngine`** (egg is the MVP engine).

## Glossary (§A.6)

**Node** (IR entry) · **Stage** (fused schedulable node) · **Boundary op**
(source|reduction|repartition|materialize|external) · **Form** (awkward type/shape) · **Plan**
(serializable physical artifact for an executor) · **Partition** (unit of input work, e.g.
`(uri, tree, entry_start, entry_stop)`) · **Provenance** (node/stage → user source location) ·
**Preservation Bundle** (self-contained content-addressed export, distinct from Plan) · **Payload
descriptor** (reproducibility metadata an `External` node carries).
