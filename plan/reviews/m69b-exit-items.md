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
