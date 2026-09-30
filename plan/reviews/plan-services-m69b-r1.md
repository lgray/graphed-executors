**NOT CLEAN**

# Review m69b-r1: `plan-services.md` §5 (m69b) plus the lines it binds, whole-part pass (f199b22)

## Scope
- **Snapshot:** `reviews/plan-services-m69b-r1-snapshot.md` (= `plan-services.md` at f199b22). Read in full: §5, and the
  D1, D2, D8, D10, "Measured for this plan", §1, §3.1, §6–§9 lines. `git diff 8341ec4 f199b22` gave the redesign's hunks.
  The replaced §5 is `reviews/plan-services-m69b-r0-snapshot.md`.
- **Code:** graphed d0ad16b (`services.py`, `session.py`, `aggregate.py`), graphed-histogram 4c4b79f (`boost.py`,
  `_spec.py`, `ci.yml`, `pyproject.toml`), executors `upstream/main` db8fb0a (`submit/services.py`, `submit/engine.py`,
  `htcondor_backend/{services,announce}.py`, `examples/hgg/analysis.py`, `tests/frozen/m69a/`, `ci.yml`), histserv 0.2.1.
- **Probes (new, `probes/m69b/*_rv1.*`):** `probe_require_bound_shared`, `probe_composed_shortfall`,
  `probe_standin_axes`, `probe_same_name_contexts`, `run_memory_pythons_rv1.sh` → `probe_memory_pythons_rv1.txt`,
  `probe_reuseport` / `probe_reuseport_off`. Python probes ran in `~/vibe-coding/cloud/graphed-histogram/.venv`, read-only.
  Docker probes ran in `python:3.1x-slim`. Every container and process was removed.

## Design findings

### R1-1 — `require_bound` of an unbound plan on ≥ 2 servers raises the shared-endpoint `ValueError`, not `UnboundService`
- **Where:** §5.1 "Served process": `bind_services` refuses shared endpoints. "What the context guarantees" refuses two
  server names bound to one endpoint "at bind". The frozen row `test_histserv_lazy_init.py` says "`require_bound`
  unbound → `UnboundService`".
- **Why it changes code:** graphed's `require_bound` loops. Each time the process refuses a name, it re-binds with that
  name added, mapped to the placeholder `tcp://unbound:0`. Its last pass therefore maps every server to that one
  placeholder, and the shared-endpoint check fires on that pass. `SequentialRunner`, `ThreadExecutor`,
  `ProcessPoolExecutor` and `transport_run_plan` call `require_bound` (§3.1). On an unbound served plan with two or more
  servers they would raise the wrong error, naming a placeholder.
- **Measurement:** `python probes/m69b/probe_require_bound_shared_rv1.py` uses a stand-in `_Served` that binds as §5.1
  says. Output:
  ```
  1 server(s): require_bound raised UnboundService: service 'histserv-0' has no endpoint: …
  2 server(s): require_bound raised ValueError: two histserv servers bound to one endpoint: {'histserv-0': 'tcp://unbound:0', 'histserv-1': 'tcp://unbound:0'}
  ```
- **The refusal is not needed.** §5.1 already puts legs 1–2 outside the guarantee. Two managed servers of one run never
  share a port:
  - Driver-hosted: `_on_driver` holds `_PORT_LOCK` from the scan until the child is ready (`submit/services.py`).
  - Cluster-hosted: `ServiceSet.start` resolves specs in order (`[self._resolve(spec, stack) for spec in self.specs]`),
    and `host_service` returns only when the service is up (D10).
  - histserv is never a DAG SERVICE node: it has no `image` and no GPUs, so the driver job hosts it (§3.3 B2).
- **Closed when:** the shared-endpoint refusal is deleted from `bind_services` and §5.1 (preferred). The alternative is
  to move it to first use, before any `init` RPC, where only real endpoints exist.
- **Test:** make `test_histserv_lazy_init.py`'s `require_bound` row use a plan packed onto ≥ 2 servers. It must raise
  `UnboundService` whose `names` lists every server. Drop, or move to first use, the "shared endpoints refused" clause in
  `test_histserv_fill_path.py`.

### R1-2 — `analysis.plan()` without a context must stay m69a's plan; the frozen m69a suite pins its value to the counters alone
- **Where:** §5.2 says "`dataset_plan(…, context=None)` … without one, `gh.boost`". That means the six diagnostics
  always enter the plan and its value.
- **Why it changes code:** `tests/frozen/m69a/test_hgg_conversion.py` calls `analysis.plan(fileset(*FIXTURES),
  year=…, out=…)` with no context. It asserts `value == expected`, where `expected` is the accumulated counters, and it
  also checks each value's keys and types. Adding histograms to the value fails this frozen test, and `test-hgg` runs
  `tests/frozen/m69a` on the m69b PR. The integrity rule forbids editing it.
- **Measurement:** `git -C ~/vibe-coding/cloud/m68a show upstream/main:tests/frozen/m69a/test_hgg_conversion.py | grep
  -n "value == expected\|analysis.plan(fileset(\*FIXTURES)"` →
  ```
  76:    plan = analysis.plan(fileset(*FIXTURES), year=h.YEAR, out=str(tmp_path))
  80:    assert value == expected
  ```
- **Closed when:** the diagnostics need an opt-in, either the context or an explicit flag. The call m69a makes then
  builds m69a's plan unchanged. Any m69b row that needs an unbacked twin (`test_hgg_live_pool.py`'s "sequential run")
  names that opt-in, or compares against the direct `bh` fill.
- **Test:** `tests/frozen/m69a` passes unmodified in the m69b PR's `test-hgg` job.

### R1-3 — composing `pieces()` defeats the optimizer-merge refusal, so the reduce reads another output's value
- **Where:** §5.1 `boost.py`: `pieces(...) -> HistogramPieces(…, on_compiled, …)`, "a composing plan lists
  `fill_nodes` first, hands `values[:n_values]` to `pieces.reduce`". §5.2's `HggReduce` composes it this way.
- **Why it changes code:** 0.0.4's refusal (`_refuse_shortfall`) compares **all** compiled outputs with the marked fill
  count. Once other outputs are listed after the fills, a merge of two fills is hidden: `outputs >= marked` holds. The
  shortened value list then shifts, and `pieces.reduce` receives a counter's value as a fill.
- **Measurement:** `python probes/m69b/probe_composed_shortfall_rv1.py`. Two fills differ only in `weight=[w]` versus
  `weight=[w * 1.0]`. Output:
  ```
  gh.plan: GraphedError: the optimizer merged fills that record as distinct nodes (2 marked, 1 compiled), …
  composed with one more output: accepted
  run: AttributeError: no field named 'axes'; reduce saw ['Histogram', 'Array']
  ```
- **Closed when:** the `on_compiled` that `pieces` returns counts only the compiled outputs that the fill nodes map to
  (through `compiled.correspondence.node_map`). It refuses a shortfall whatever other outputs the composing plan
  lists.
- **Test:** add to `test_pieces_composition.py`: the probe's two merged fills plus one counter output, composed, raise
  the `GraphedError` naming the histogram. The control is `gh.plan` of the same fills, which already refuses.

### R1-4 — the owner's "how many histograms per server" option is missing
- **Where:** §5.1 "Surface" gives `Context(*, memory_mb, workers, name, ports, timeout_s)`. "Sizing and packing" bounds
  a server by memory alone.
- **Why it changes code:** the owner direction (brief, verbatim) asks for "configuration options possible for how many
  histograms per server". The plan offers none. A count cap is also the only user knob for §9's unmeasured
  one-core fill rate per server.
- **Measurement:** `grep -n "per server\|histograms per\|max_hist" plan-services.md brief-m69b-plan.md` matches the
  brief's line 9 (the direction). In the plan it matches only "one `ServiceSpec` per server" (L99, L907, L917) and "six
  diagnostic histograms per dataset" (L1004). No count option exists.
- **Closed when:** `Context` takes an optional per-server histogram cap (default `None`, meaning memory is the only
  bound). First-fit opens a new server when either bound would be passed, and `ctx.servers()` reports both.
- **Test:** add to `test_histserv_packing.py`: `k` equal small slots under a cap `c` land on `ceil(k / c)` servers.
  With `None`, they land on the count memory alone gives.

### R1-5 — the category and Boolean refusals are self-inflicted, and the "transformed" refusal cannot be reached
- **Where:** §5.1 "Surface" accepts only `Regular`/`Variable`/`Integer`. The frozen `test_histserv_surface.py` row
  refuses "growth, category, transformed". §5.2 notes "(category axes are refused)".
- **Why it changes code:**
  - Category axes fail only because P1's server template copies the real axes, so histserv keys them as chunks and
    drops their overflow.
  - The fill path ships flow views and resolves by placing views into `zero_of(spec)`, so the server needs only each
    dense axis's flow **extent**.
  - A template of no-flow `Regular(extent, 0, 1)` stand-ins, plus the fill-time variation axis as the chunk axis, carries
    `StrCategory`, `IntCategory` and `Boolean` slots bit for bit, overflow included.
  - Growth stays refused, because its extent cannot be sized.
  - `gh.boost` already refuses a transformed axis at construction with its own message, so a histserv refusal of it
    can never be reached.
- **Measurement:**
  - `python probes/m69b/probe_standin_axes_rv1.py`:
    ```
    slot=('strcat_reg', None) axes=['StrCategory', 'Regular', 'StrCategory'] … equal_to_local=True
    slot=('intcat_bool', 'nominal') axes=['IntCategory', 'Boolean'] … equal_to_local=True   (and sf_up, sf_down: True)
    ```
    The fixtures fill each category axis's overflow bin. The control is `probe_histserv_fillpath.txt` P5: with the real
    axis in the template, the total goes from 2.0 to 1.0.
  - `python -c "…gh.boost.Histogram(bh.axis.Regular(10, 1, 1000, transform=bh.axis.transform.log))"` →
    `TypeError: Regular axis: the histogram spec cannot carry transform`.
- **Closed when:**
  - The template is built from extents.
  - Backing refuses only growth axes and the storages that cannot add by view (`Mean`/`WeightedMean`, and `Unlimited`
    if kept).
  - The surface row drops "category, transformed".
  - §5.2's parenthesis goes.
- **Test:**
  - `test_histserv_surface.py`: category and Boolean slots are accepted, and growth is refused naming histserv.
  - `test_histserv_fill_path.py`: a `StrCategory` slot with a filled overflow bin equals the local twin bit for bit.
    With a real-axis template it would not (P5).

### R1-6 — two contexts built with equal arguments name the same servers, and a collated run starts one server for both
- **Where:** §5.1 "Server specs": server `i` is named `f"{ctx.name}-{i}"`, with `name="histserv"` by default. Packing
  state lives on the context.
- **Why it changes code:** each context packs its own servers to within `memory_mb`. However, graphed accepts an equal
  re-declaration (`Session.declare_service`), and `collate` unions equal specs by name. So `histserv-0` of context A and
  `histserv-0` of context B become one process holding both contexts' slots, and its load can reach `2 × memory_mb`.
  That is the crash the owner's direction rules out. Building one context per dataset is a natural call, since §5.2's
  `dataset_plan` takes a `context` argument.
- **Measurement:** `python probes/m69b/probe_same_name_contexts_rv1.py` →
  ```
  declare_service twice (equal specs): accepted; declared ['histserv-0']
  collate of two plans each on its own context's histserv-0: ['histserv-0']
  ```
- **Closed when:** two contexts in one process never declare the same server name. One way is to refuse a second live
  context with a used name. Another is a deterministic per-process context index in the server names, deterministic
  because program order fixes it. Either keeps the two-interpreter pickle test green.
- **Test:** add to `test_histserv_packing.py`: two `Context(memory_mb=m, workers=1)` with equal arguments each fill one
  server, and their plans are collated. Either `plan.services` holds two distinct server names, or the second context
  is refused naming the name.

### R1-7 — the model's per-histogram overhead `O` falls below the value measured on three of the four CI Pythons
- **Where:** §5.1 "Sizing and packing": the constants are "each the larger of the `MODEL` lines of
  `probe_histserv_memory.txt` and `.amd64.txt`". Both files are Python 3.12 runs, giving `O = 3700 B`. §9 says that
  "other Pythons … are checked by the ubuntu-leg memory test".
- **Why it changes code:**
  - On 3.11, 3.13 and 3.14 (arm64), `O` is 3800–4000 B.
  - The frozen memory test cannot catch this. Each scenario holds one slot, so `O` contributes about 4 KB against
    margins of 100+ MiB.
  - The constant the implementer writes is therefore under what the CI Pythons measure, and nothing would catch it. The
    other constants hold: `B` ≤ 86 MiB, `a` ≤ 5.5, `b` ≤ 2.5, `I` ≤ 140 on every Python measured.
- **Measurement:** `probes/m69b/run_memory_pythons_rv1.sh` (the planner's probe, unchanged) →
  ```
  python 3.11.16  MODEL B=79 MiB O=3800 B I=140 B a=5.5 b=2.0
  python 3.13.15  MODEL B=83 MiB O=4000 B I=140 B a=5.5 b=2.0
  python 3.14.7   MODEL B=86 MiB O=3800 B I=140 B a=5.0 b=2.5
  ```
- **Closed when:** `run_memory_probe.sh` fits over the CI Pythons 3.11–3.14 on both arches, and each constant is the
  maximum over all those `MODEL` lines (`O` ≥ 4000 on the arm64 lines above). §9's claim is narrowed to what the memory
  test can see (`B`, `a`, `b`).
- **Test:** the regenerated probe files. Every `MODEL` line is ≤ the module constants.

## Checked and holding
- **Owner direction.**
  - A backend variant beside `gh.boost` (`histserv.Histogram` / `backed`), requested implicitly: the specs go on the
    session, `plan.services` carries them, and D2 leg 3 starts them.
  - Memory per server, and a server count computed before any run (`ctx.servers()`).
  - The slot → server map is decided at plan time and carried by the served process.
  - The requested options are covered except for R1-4.
  - `workers` is a needed input: the transient scales with fills in flight, which E measures.
- **Code claims.** Each was checked against the code:
  - `require_bound`'s placeholder re-bind (graphed `services.py`) and `_PartitionReduce`'s reduce receiving values only
    (`aggregate.py` `__call__`).
  - `_Collated` routes by `(uri, tree)` and passes the partition unchanged, so `str(partition)` is stable per task and
    retry.
  - `ServiceSet._on_driver` has no memory limit.
  - `ServiceJob` puts `request_memory` = `resources["memory_mb"]` (`htcondor_backend/services.py`).
  - histserv 0.2.1 has no health service. `Client.stats()` gives `histogram_count` and `histogram_bytes` = Σ chunk
    `nbytes`.
  - The local process pools are spawn-based (`local/__init__.py`), so there is no gRPC-after-fork hazard.
  - The engine pickles the process in the driver (`engine.py` `_fingerprint` → `backend.broadcast`), which puts first
    use in the driver on every `SubmitRunner` backend.
  - No executor splits a task's partition, so exactly-once by `unique_id` holds.
- **Determinism.**
  - Packing order is `(stored desc, str(slot))` and server names are indices, so it is deterministic.
  - An unordered `plan.services` union would be caught by the frozen `PYTHONHASHSEED` pickle row (exit item).
  - `Plan ==` of two `gh.plan` constructions is `True` and their pickles are equal (scratch check), so the surface row's
    "equals 0.0.4's construction" is writable.
- **Size model.**
  - `B`, `a` and `b` cover every C/E/F row on 3.11–3.14 arm64 as well as the fitted 3.12 rows.
  - The ceiling (H) and the prune default (I) are measured.
  - The refusals for a slot above `memory_mb`, the ceiling, `next_tasks`, a repeated partition and a double serve each
    guard a reachable state.
- **CI.**
  - histogram CI legs are {ubuntu, ubuntu-arm, macos, windows} × 3.11–3.14. grpcio and grpcio-tools 1.84 have wheels
    for all of them. numcodecs resolves 0.16.5 on 3.11, since 0.17 needs ≥ 3.12. No legs are cp314t.
  - The 3.14t leg installs `.[dev]` without histserv. graphed's import chain leaves `grpc` and `histserv` unimported.
  - The executors all-OS job already installs grpcio. `HISTOGRAM` and `GRAPHED` (d0ad16b) exist in executors' `ci.yml`.
  - `ProcessPoolExecutor` for the histogram lazy-init row comes from `EXECLOCAL` (graphed-executors 0.0.4 on PyPI). The
    venv shows it runs with graphed d0ad16b.
- **Commits.**
  - histogram: ~1.2k freeze, ~830, ~880, ~350.
  - executors: ~800 freeze, ~450, ~550.
  - All are under 2k, and the §7 totals match.
