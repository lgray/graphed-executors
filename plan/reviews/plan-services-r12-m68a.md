# Review r12 — `plan-services.md`, unit m68a (delta vs `plan-services-r11-snapshot.md`)

**Verdict: NOT CLEAN — 1 design finding (N8).** The finding is in N7's own repair: its wording covers the processes of
earlier specs but leaves out the process of the spec that is failing. Fixing it takes one clause and one frozen leg,
and the dispatch can carry both. Because the delta returned a design finding, no whole-unit pass was run.

The new probe is `probes/services-code/probe_inflight_start_r12.{py,txt}`. It ran with the driverless `.venv` python
and `PYTHONDONTWRITEBYTECODE=1`, and it wrote nothing into any lane clone. The executors head is 386d65d.

## r11 findings
- **N7 is closed for the member it named.**
  - L259-260: "`start()` owns what it has started: any exception from a later spec runs `close()` over the services
    already up, then re-raises."
  - The frozen row (L295) adds the two-spec leg: a managed `http_server`, then a spec with no `launch`. `run` raises
    `ServiceUnavailable`, and without a `close()` call the pid is gone and the port is free.
  - Fails-on (L305) adds "a failed `start`".
  - probe_partial_start_teardown_r11 already shows that the leg discriminates: with teardown `pid_alive=False
    port_free=True`, without it `pid_alive=True port_free=False`.
- **D10 consistency (m68b/m70).** Every `host_service` mention returns `(endpoint, identity)`: L103, L251, L257, L371,
  L429. The delta touches none of them.
- **D6** matches the owner ruling. A plan `StageError` exits 3. Worker loss (a `StageError` from `KilledWorker`) exits 1
  and is retried.
- **D7** matches the merged key: `(kind, content_hash, endpoint, load_params)`.

## Design findings

**N8 · The repair's wording leaves out the spec that is failing, so its own `Popen` outlives a failed `start`.**
- The rule is scoped to "an exception from a **later** spec" and "the services already **up**".
- Leg 3 is "`Popen(argv)` …, poll the check" (L250), and the plan does not say what a failed poll does.
- That leaves a managed spec whose child starts but whose check never passes within `timeout_s`, for example a
  recipe that binds a different port or never listens. Its failure is not "from a later spec", and its child is not
  "up". An implementation that records a child only once it is ready therefore follows the plan and still orphans
  the child. On an attached run that orphan sits on the login node.
- probe_inflight_start_r12 drives this case. Both legs run `close()` before re-raising `Unavailable`:
  - `register_at_popen=False` (the plan's "already up") leaves `child_alive=True`;
  - `register_at_popen=True` leaves `child_alive=False`.
- This is the second finding of N7's shape. Both come from the same operation: **`start()` spawns a child that only
  `start()` can reach.** So the cut belongs where the child is recorded, not in a third clause.

**Closed by:**
1. Replace L259-260 with this rule: `start()` records each managed child in the set at `Popen`, before its check
   runs, and any exception out of `start()` runs `close()` over everything recorded, then re-raises. The same rule
   covers an earlier spec's child and the failing spec's own child. A failed leg-3 check is a `ServiceUnavailable`
   whose `legs["managed"]` gives the check's reason.
2. Add a frozen leg in `test_services_protocol.py`: one managed spec whose `launch` argv is
   `{python} -c "import time; time.sleep(60)"`, with `check="http:/"` and a small `timeout_s`.
   - `run` raises `ServiceUnavailable`, and `legs["managed"]` names the check.
   - With no `close()` call, the child's pid is gone.
   - The two probe legs show that this discriminates.

## Exit-round constraints (to the implementer)
- **E14 still stands.** L263 still says `graphed.bind_services`. Use `graphed.services.bind_services`.
- **E15 still stands.** L285 still says "`driver.log`, which holds the traceback". Point at `driver.log` without
  promising a traceback, because an `ok=True` blob that fails to load has none.
- E16 and the earlier E1–E13 stand as r11 left them.
