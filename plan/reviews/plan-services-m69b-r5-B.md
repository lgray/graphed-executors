**NOT CLEAN**

# Review m69b-r5, unit B: whole-part pass of §5 opening, §5.1, §5.2 (eea3f4f)

## Scope
- **Snapshot:** `reviews/plan-services-m69b-r5-B-snapshot.md` (= `plan-services.md` at eea3f4f).
- **Read:** §5 opening, §5.1, §5.2, and the D1, D2, D8, §1, §6, §7, §8, §9 lines that bind them. Also the m69b probes
  they cite, reviews r1–r4, and `m69b-exit-items.md`.
- **Code (read-only):**
  - graphed d0ad16b: `services.py`, `aggregate.py`, `session.py`, `core/execution.py` (`SequentialRunner`).
  - graphed-histogram 4c4b79f: `boost.py`, `_spec.py`, `ci.yml`, `pyproject.toml`, `.pre-commit-config.yaml`, frozen
    m48/m49/m64.
  - executors `upstream/main` db8fb0a: `submit/{engine,services}.py`, `htcondor_backend/{backend,services,pilot,driver}.py`,
    `local/_pinned_pool.py`, `examples/hgg/{analysis,run_local}.py`, `tests/frozen/m69a/*`, `ci.yml`, `pyproject.toml`,
    and its tags (`git ls-remote`).
  - histserv 0.2.1: `client.py`, `server.py`, `service.py`, `serialize.py`, `__main__.py`.
- **Probes (new, `probes/m69b/*_rv5b.*`):**
  - `probe_receipt_length_rv5b`, `probe_rpcerror_pickle_rv5b` and `probe_fold_order_rv5b` ran in
    `graphed-histogram/.venv`, read-only.
  - `probe_connections_rv5b` ran on macOS (`.txt`) and in `python:3.12-slim` (`.linux.txt`).
- **Cleanup:** every histserv subprocess and container was removed (`pgrep -fl histserv` → none; `docker ps -a | grep -c
  m69b-rv5b` → 0). graphed-histogram's `git status` is clean.

## Prior findings
- All r1–r4 findings in unit B are closed: R1-1…R1-7 (R1-4 by ruling 4) and R2-1…R2-3. The whole-part read finds no
  regression:
  - there is no shared-endpoint refusal;
  - fills are read at compiled positions;
  - the stand-in template is built from extents;
  - the name registry is process-scoped;
  - the constants are the maxima over the eight `MODEL` lines;
  - there is one `pieces` per plan.

## Design findings

### R5B-1: the receipt-length clause fails a correct `Receipt(spec, endpoint, hist_id)`
- **Where:** §5.1, frozen `test_histserv_fill_path.py`: "backed values are receipts …, pickled at one length for 10- and
  10⁴-bin twins".
- **Why it changes code:**
  - §5.1 puts `spec` in the receipt, and `resolve_services` needs it for `zero_of(spec)`.
  - `spec_of` writes `"bins":10` versus `"bins":10000`, so the twins' receipts differ by the spec text.
  - A test author writing natural twins (`Regular(10, 0, 1)` / `Regular(10000, 0, 1)`) therefore freezes an
    assertion the plan's own design fails, and the implementer can only file a dispute.
  - The property it guards is "no histogram rides the tree", which is a bound, not an equality.
- **Measurement:** `probe_receipt_length_rv5b.txt`:
  ```
  Regular(10,0,1) vs Regular(10000,0,1): receipt pickles 280 vs 283 B; histograms pickle 510 vs 160364 B
  Regular(100,0,1)x2 (10^4 bins) vs Regular(10,0,1): receipt pickles 280 vs 381 B; histograms pickle 510 vs 166827 B
  ```
- **Closed when:** the clause reads "each twin's backed value pickles under 1 KiB, while the 10⁴-bin local twin's
  histogram pickles over 100 KiB" (or any bound independent of the bin count).
- **Test:** that clause.
  - A receipt passes at about 0.3 KB.
  - A histogram in the tree fails at about 160 KB, so the clause can fail in the direction it guards.

### R5B-2: no CI job runs the two H→γγ rows
- **Where:**
  - §5.2 frozen `test_hgg_diagnostics.py` (`test-hgg`) and `test_hgg_live_pool.py` (minicondor: "two local pilots").
  - §6: `test-hgg` "also installs `histserv`", and `test-htcondor` runs `tests/frozen/… m69b`.
- **Why it changes code:**
  - Only `test-hgg` has the analysis's stack (`env.COFFEA`, `env.UPROOT`, `vector`, `correctionlib`, `pyarrow`,
    `HIGGS_DNA --no-deps`). Its pytest line is `tests/frozen/m69a`, and §6 does not add m69b to it.
  - Only `test-htcondor` starts a pool, and it installs none of that stack.
  - Without the stack, the m69a harness's convention (`importorskip` unless `GRAPHED_HGG_REQUIRED=1`) skips the file.
    So `test_hgg_live_pool.py` skips in `test-htcondor`.
  - `test-hgg` has no pool for it.
  - As planned, both rows pass by skipping everywhere, and the diagnostics' bit-for-bit guard never runs.
  - The implementer must decide which job gets the stack or the pool.
- **Measurement:**
  - `git -C ~/vibe-coding/cloud/m68a show upstream/main:.github/workflows/ci.yml | grep -n 'env.COFFEA\|env.HIGGS_DNA\|pytest
    tests/frozen/m69a\|Start a personal HTCondor pool\|^  [a-z-]*:$'` →
    ```
    284:  test-htcondor:
    304:      - name: Start a personal HTCondor pool
    394:  test-hgg:
    410:            "${{ env.COFFEA }}" "${{ env.UPROOT }}" vector correctionlib pyarrow
    412:          python -m pip install --no-deps "${{ env.HIGGS_DNA }}"
    414:        run: pytest tests/frozen/m69a
    ```
  - `hgg_harness.py`: `if os.environ.get("GRAPHED_HGG_REQUIRED") != "1": pytest.importorskip("coffea")`. The variable is
    set only at `test-hgg`'s job level.
- **Closed when:** §6 names one job per row that has every prerequisite.
  - `test-hgg` runs `tests/frozen/m69a` plus the m69b hgg files under `GRAPHED_HGG_REQUIRED=1`.
  - The live-pool row either uses `LocalPilots` (no pool, so it runs in `test-hgg`), or `test-htcondor` installs the hgg
    stack and sets `GRAPHED_HGG_REQUIRED=1` for that file.
  - §6 and the row's leg label agree.
- **Test:** in the CI log, each of the two files' tests is reported passed, not skipped (`-rs`). With
  `GRAPHED_HGG_REQUIRED=1`, a missing stack is an import error rather than a skip.

### R5B-3: the size model has no term for client connections, which grow with `workers`
- **Where:** §5.1 "Sizing and packing": `B + Σ (O + I × tasks + (chunks + 1) × dense) + (a + b × workers) × M`.
- **Why it changes code:**
  - Clients are cached per endpoint per process (§5.1), so each worker process that ships to a server holds one gRPC
    connection to it. A run's connections per server therefore grow with its worker processes, which `workers`
    bounds.
  - The probes never measured this:
    - `B` is a warm server with one client;
    - scenario E's `Client`s are in one process with identical channel args, so they share gRPC's global subchannel
      pool and one connection.
  - So a server packed to `memory_mb` exceeds its prediction by about `K × workers`. The term is invisible for small
    histograms (`b × workers × M` is about 3 KB at `M` = 1 KB), and these are exactly the slots first-fit packs
    densely.
  - This is the "missing model term" that §5.1's "Fails on" list claims to guard.
- **Measurement:** `probe_connections_rv5b.{txt,linux.txt}`. Each channel has its own subchannel pool, so each holds
  its own connection, as a separate process would:
  ```
  macOS arm64:          516 connections: rss 127.0 MiB, per extra connection 20.7 KiB   (25.8 KiB at 68)
  Linux (3.12-slim):    516 connections: rss  95.0 MiB, per extra connection 16.5 KiB   (18.0 KiB at 68)
  ```
  At `workers` = 1000 that is 16–26 MiB per server outside the prediction.
- **Closed when:**
  - The model gains `K × workers` (one connection per worker process, plus the driver's).
  - `K` is a module constant: the maximum of a new connection scenario's line in `run_memory_probe.sh` on 3.11–3.14,
    arm64 and amd64, like the other constants.
- **Test:** add a clause to `test_histserv_memory_model.py` (Linux legs).
  - Setup: one one-bin slot, `workers=N` with N ≥ 256, and N client channels, each with
    `("grpc.use_local_subchannel_pool", 1)`, each making one RPC.
  - Assert: VmHWM − warm ≤ prediction − `B`.
  - Without the term, prediction − `B` is about 16 KB against the measured ~4 MiB, so the clause fails.

## Checked and holding
- **Owner direction and rulings.**
  - A backend variant beside `gh.boost` that the executor provisions with no user declare or bind.
  - Memory per server and the server count, both known before the run (`ctx.servers()` after planning).
  - Rulings (1)–(7) and (A) as written.
  - `workers` is needed input: the transient scales with fills in flight.
- **Code claims.**
  - `require_bound`'s placeholder loop and `UnboundService(*sorted(missing))`.
  - `_Collated.bind_services`/`resolve_services` reach each `_Served`.
  - `SequentialRunner` is a key-order left fold and calls `require_bound` but not `resolve_services`.
  - `SubmitRunner.run` binds before the first submit and resolves while the services are up.
  - `_fingerprint` pickles the process in the driver (stdlib `pickle`).
  - `_on_driver` sets no memory limit and holds `_PORT_LOCK` from scan to ready.
  - `ServiceJob.request_memory` = `resources["memory_mb"]`.
  - `HTCondorBackend.__init__` reads `service_hosts` before attaching `host_service`, so narrowing it there is
    sufficient.
  - histserv binds `[::]`.
  - `unique_id` is stored as a sha256 digest, so `I` does not depend on the length of `str(partition)`.
  - The check, merge and remember steps of `FillMany` have no await between them, so concurrent duplicate attempts
    cannot both be counted.
  - The server and client message limits are 2²⁹ for a fill, with no limit on a snapshot.
- **Size model.**
  - Each `MODEL` line covers its own C/E/F rows, and the maxima cover all eight lines.
  - The memory row's bounds, 672 and 624 MiB against measured peaks of 470–560 and 358–501 MiB, have margin on every
    measured Python.
- **CI.**
  - Histogram:
    - Every job that installs `GRAPHED` has a Rust toolchain.
    - The git build of d0ad16b is version 0.0.6, which satisfies `graphed-executors` 0.0.4's `graphed>=0.0.6`.
    - The 3.14t leg runs `pytest tests/frozen` without coverage.
  - Executors:
    - The all-OS job collects `tests/frozen` whole, so the m69b server files run there.
    - `test-htcondor`'s pool runs jobs on the host's Python, where §6 installs histserv.
    - Tag `freeze-m69a-fixup` is free (`freeze-m69a` and `freeze-m72` exist).
- **m69a refreeze.**
  - The described assertions are L80–82.
  - `test_each_dataset…` uses two `RANGES`, and `probe_fold_order_rv5b.txt` shows 2–3 partials fold to identical bits
    in any order.
  - No other m69a test reads the value's keys or counts Externals in `analysis.plan`'s IR. The lumimask test uses its
    own session.
- **Commits.**
  - Histogram: ~120, ~1.3k, ~850, ~910, ~350.
  - Executors: ~40, ~850, ~170, ~450, ~550.
  - All are ≤ 2k, and the §7 totals match.
