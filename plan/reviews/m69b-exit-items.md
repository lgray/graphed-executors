# m69b exit items

## r1
From `reviews/plan-services-m69b-r1.md` (whole part, f199b22). These are constraints for the implementer and test
author. None of them makes a round unclean.

- **`plan.services` order (§5.1 "Server specs").** The plan says "the plan's own ∪ the servers its slots landed on".
  Write it as sorted by name, as `aggregate_plan` and `collate` do. A set union of `ServiceSpec`s orders by string
  hashes, which fails the frozen `PYTHONHASHSEED` pickle row.
- **The memory test's concurrency (`test_histserv_memory_model.py`).** Release the "4 concurrent fillers" with a
  `threading.Barrier`, as the probe's E scenario does.
  - The row's lower bound, `> warm + (chunks + 1) × dense + M`, is met by one fill: C/F measures 4.4–7.4 × M. So the
    bound shows the transient ran, but not that four fills were in flight together.
- **§9 risk: gRPC's `SO_REUSEPORT`.**
  - `probes/m69b/probe_reuseport_rv1.txt`: on Linux, two `python -m histserv` on one port both stay up, and new
    connections split between them (the `histogram_count` values seen were 1–5 over 8 inits).
  - `announce.py`'s "a child that exits moves on to the next port" therefore never fires for histserv.
  - Within one run no collision is possible: `_PORT_LOCK` covers the driver-hosted leg, cluster starts are sequential,
    and histserv is never a DAG SERVICE node.
  - Two concurrent runs by one user can collide in the scan→bind window, on one login node or one worker node. The
    result is a loud `NOT_FOUND` on fills, not wrong sums.
  - `probes/m69b/probe_reuseport_off_rv1.txt` is the measured remedy, if wanted: a 3-line launcher adding
    `("grpc.so_reuseport", 0)` makes the second child exit 1 ("Failed to bind").
- **§9 risk: sequential cluster start.** `ServiceSet.start` resolves specs one after another, and `host_service`
  returns only when the service is up. So N cluster-hosted servers start in series, and start-up grows with
  `len(ctx.servers())`. This is unmeasured at LPC. The LPC transcript should record each server's start and ready
  times.
- **LPC evidence (§5.2 `probes/site-lpc/m69-hgg.txt`).** Record each server's history `MemoryUsage` (or
  `ResidentSetSize`) beside `RequestMemory` and the context's prediction. `RequestMemory` alone does not show that
  "won't crash a server" held at the site. That includes condor's accounting of `announce.py` and `service.sh`.
- **Lazy imports and ruff.** graphed-histogram's ruff config selects `PLC0415`. A function-level `import histserv` /
  `import grpc` takes `# noqa: PLC0415`, the repo's idiom (`boost.py`'s `import awkward as ak  # noqa: PLC0415`).
- **First use in the driver (§5.1 "Served process").** "Every runner" rests on four measured runners. For
  `SubmitRunner` it also follows from the code: the engine pickles the process in the driver (`engine.py`
  `_fingerprint` → `backend.broadcast`). Cite that for the condor, dask and parsl backends.
- **Placement as a topology option.** The owner's direction mentions "other user-facing service topology concerns".
  The plan reaches cluster placement only through a site-profile copy (`service_ports=None`), and that is `run_lpc.py`'s
  `--placement`, not the Context. If the owner wants it on the Context, it needs a D2 change. List it among §9's owner
  items.

## r2
From `reviews/plan-services-m69b-r2.md` (delta, dc66fe0). These are constraints for the implementer and test author.
None of them makes a round unclean.

- **The O sub-row of `test_histserv_memory_model.py` is looser than §9 and "Fails on" claim.**
  - Measured by `probes/m69b/probe_overhead_row_rv2.txt` (amd64, 3.11–3.14): 2000 one-bin slots, one fill each,
    `O = 4000`, `I = 160`. The row passes with a 10.7–16.8 % margin (Weight) and 19.0–28.4 % (Double).
  - It still passes for any `O` of at least 3283–3545 B (Weight) or 2807–3200 B (Double). The pre-R1-7 value of
    3700 passes on every Python.
  - So the row guards against a missing or mis-scaled `O` term, not the ≤ 12 % shortfall R1-7 was about. Ruling 7
    settles that shortfall by the max-over-`MODEL` rule instead.
  - Fill the slots with Weight storage, the storage that sets `O`.
  - §9's "checks `O`" and "Fails on: … an under-estimated model constant" should say "a missing or mis-scaled term".
- **The m69a fixup leaves `test_each_dataset_run_on_its_own_collects_into_the_same_product` unmodified.**
  `probes/m69b/probe_m69a_each_rv2.txt` shows that the collated and per-dataset values stay equal with local
  histograms in them. Say so in §5.2's refreeze paragraph, so the test author does not touch it.
- **The m69a `README.md` traceability row** for `test_one_plan_writes_every_part_and_returns_the_totals` should name
  the `"diagnostics"` key the refrozen assertions exclude and check.

## r3
From `reviews/plan-services-m69b-r3.md` (delta, 4e825e8). These are constraints for the implementer and test author.
None of them makes a round unclean.

1. **The m48/m49 refreeze rewrites the docstrings that describe the refusal.** The plan says "the module docstring
   … stay(s)", but these sentences become false:
   - m48 `test_optimizer_merge_guard.py` L8–13 ("OPTIMIZER collapse is REFUSED …");
   - m48 L49–50 (the instrument's "the refusal below");
   - m49 `test_merge_shortfall.py` L1 and L14–16 ("Both refusals are BUILDER-side …");
   - m49 L129–130 ("every refusal above").

   Keep the instruments' assertions, and reword only the refusal sentences.
2. **`pieces.on_compiled` returns `_variation_labels(items, compiled)`, as 0.0.4's `_on_compiled` hook does.** `gh.plan`
   now builds through `pieces`, and frozen m49 `test_variation_labels_payload.py` pins the payload on `gh.plan`
   (L34, L138–139). A composing plan gets StageError variation attribution the same way.
3. **In `test_pieces_composition.py`, the second `aggregate_plan` over one `pieces` marks a different composition**
   (counter last).
   - A same-composition rebuild records identical positions, because compiles are history-independent (frozen m22).
   - So an implementation that records and then refuses, which is the order §5.1's prose gives ("records … and
     refuses a second firing"), would pass the "first plan run afterwards" clause.
   - Check before recording.
4. **Lock the context registry and packing state.** Both are module state, mutated at `Context(...)` and at
   `pieces.serve`. Hold one module lock around the name lookup/insert and the first-fit placement. The no-server
   files run on the 3.14t leg. §5.1 mentions a lock only for `_Handles`.
5. **The different-arguments refusal names the remedy** (pass a fresh `name=`, or use a new process), and
   `design.rst` "Filling on histserv servers" states the process scope. A notebook re-run with a changed `memory_mb`
   under the default name meets this refusal.
6. **`test_histserv_surface.py`'s "0.0.4's value bit for bit" needs a named oracle**, since 0.0.4 is not importable
   beside the PR. Use the per-partition direct `bh` fill folded in partition order, or m48's goldens.
7. **§5.0's freeze commit follows graphed's frozen convention:**
   - `tests/frozen/frontend/m69b/README.md` (traceability) and a freeze tag;
   - the cross-seed clause asserts each child printed a digest, as frozen m49 `test_varied_plan_determinism.py` does
     through `check=True` and a line count.
