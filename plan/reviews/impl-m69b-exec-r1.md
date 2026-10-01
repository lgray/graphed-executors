# m69b executors implementation review, round 1 (PR #44, head d3f2820, base b0dfd2e)

## Verdict: REJECT

The local gates are green: frozen byte-equality, macOS, the Linux pool, test-hgg, ruff, format, mypy, sphinx and
the integrity scan. CI run 36896324617 is red on test-dask (B1). Three Major findings and two Minor ones remain.
M1 needs a decision: the hang comes from §5.2's own "no deadline while idle". M3 and B1 are already dispatched.

| Gate | Result | Evidence |
|---|---|---|
| frozen m69b @ `freeze-m69b`, m69a @ `freeze-m69a-fixup`, m68c @ main | byte-equal | `probes/m69b/gates_exec_rv1.txt` |
| frozen m68b | the 3 refrozen files equal `freeze-m68b-fixup3`; the rest equal `freeze-m68b-fixup2` (= main, #41) | same |
| impl commits b512adc, 4759ba8, 429706e, d3f2820 vs `tests/frozen` | empty diffs (control: the freeze commit shows 2 files) | same |
| macOS py3.12, `pytest tests/frozen tests/extra --cov=graphed_executors --cov-branch` | exit 0, 1136 passed; per-file lowest 93.02 % (`local/shuffle.py`); diff-cover 44 lines, 0 missing | same |
| Linux pool (`m68b-minicondor:local`, CI test-htcondor line) | 503 passed, 7 skipped (no dask/parsl/coffea/Triton); htcondor scope per-file ≥ 98.31 %; diff-cover 98 lines, 0 missing | same |
| test-hgg equivalent (`GRAPHED_HGG_REQUIRED=1`) | 59 passed, 0 skipped | same |
| ruff, ruff format, mypy (src+tests+examples; also `--platform win32`) | clean | same |
| sphinx -W | exit 0 | same |
| integrity `scan_diff` over `upstream/main...d3f2820` | 1 advisory `ci_config_modified` (pins and test lists; no gate relaxed); control 2 | `probes/m69b/integrity_exec_rv1.txt` |
| **CI 36896324617** | **red: test-dask py3.12 and py3.14 (diff-cover)**; the other 24 jobs, Windows included, green | `probes/m69b/ci_run_36896324617_exec_rv1.txt` |

## Findings

### B1 — Blocker: test-dask's diff-cover gate is red on both legs
- **Defect.**
  - test-dask gates the `src/graphed_executors/submit/**` diff at 98 %.
  - It runs no m69b test, so `submit/services.py`'s new lines reach 65.9 % there.
  - The missing lines are the Windows branch of `physical_memory_mb`, the `_resolve` fall-through and refusal, the
    refusal merge, and `_driver_refusal`'s message.
- **Probe.** The CI job logs (`ci_run_36896324617_exec_rv1.txt`):
  ```
  src/graphed_executors/submit/services.py (65.9%): Missing lines 176,178-179,191-195,466-469,483-484,499
  ```
- **Premise of a remedy, measured.**
  - `tests/extra/m69b/test_m69b_schedulable.py` alone, under `.coveragerc-dask`, executes 14 of the 15 lines.
  - The 15th, line 467 (the managed-leg refusal), is reached by frozen `test_histserv_managed.py`'s
    `ThreadBackend` + `driver_memory_mb = 64` row.
- **Closed when** test-dask's "Diff coverage gate" step is green on both legs, with `--fail-under=98` and its
  `--include` list unchanged.

### M1 — Major (the plan's decision): with no deadline while idle, `run()` and `runner.close()` never return when the run's own pilots hold the room a server needs
- **Defect.**
  - `_await_announce` sets no deadline until `JobStatus == 2`.
  - The match counts a partitionable slot at its totals, so a job is admitted even when the only claims in the
    way are this run's own idle pilots.
  - Those pilots keep their slots until `close()`. `SubmitRunner.close` "finishes every submitted plan" first.
  - So the run and `close()` both wait forever. With `with htcondor_runner(...)`, which `run_lpc.py` uses, the
    process hangs.
  - Before m69b, `timeout_s` ended this run.
  - `docs/htcondor.rst` "Schedulability" says a run is "never left waiting on a slot that will not come". That
    sentence is false.
- **Probe.** `probes/m69b/probe_self_starve_exec_rv1.py` in the pool (10 CPUs, 15 973 MiB): two pilots of 7474 MiB,
  one 2048 MiB server, `timeout_s=20`, `service_hosts=("cluster",)`, no other job. Output
  (`probe_self_starve_exec_rv1.txt`):
  ```
  t= 90.1s done=False queue=[(43, 'graphed-pilots-…', 2), (43, 'graphed-pilots-…', 2), (44, 'graphed-service-a7328292', 1)]
  after 90s (timeout_s=20.0): done=False; wait-log lines=3
  ```
  - `runner.close()` then did not return within the remaining ~500 s, and `timeout 600` ended the process.
  - Both pilots were still running and the service job was still idle afterwards.
- **Route.** §5.2's "no deadline while the job is idle" admits this state. Which bound applies, or which ordering
  prevents it, is a plan decision for the dispatcher. The false docs sentence is the implementer's.
- **Closed when** a pool row (pilots leave less than the server's size free, no other job) passes:
  - a one-server `htcondor_runner(..., service_hosts=("cluster",))` run ends within a stated bound, refused or
    timed out naming the job's key;
  - `runner.close()` returns;
  - the queue is empty afterwards.

### M2 — Major: a busy node's Disk counts as the slot's free Disk, so a job behind it is refused "busy or not"
- **Defect.**
  - `_as_whole` substitutes `TotalSlotMemory`/`TotalSlotCpus`/`TotalSlotGPUs`, but not `TotalSlotDisk`.
  - A job's `Requirements` carry `TARGET.Disk >= RequestDisk`.
  - So a job that would run once the node's jobs leave is removed and refused with "matches no slot of the pool,
    busy or not".
  - This pool's partitionable ad carries `TotalSlotCpus`, `TotalSlotDisk`, `TotalSlotGPUs` and `TotalSlotMemory`
    (`condor_status -l`). The plan's enumeration omits one of these consumable resources.
  - At the LPC a histserv job's inputs include `env.tgz`: the profile has `ship_env`, and the recipe has no image.
    Its `RequestDisk` is therefore the env's size. **Unmeasured.**
- **Probe.** `probes/m69b/probe_disk_match_exec_rv1.py`: a running blocker leaves 512 MiB of the slot's disk, and
  a queued job asks for 1 GiB. Output (`…_disk_match_exec_rv1.txt`):
  ```
  slot after _as_whole: Memory [15973] Cpus [10] Disk [523868]
  match as shipped (Memory/Cpus/GPUs at totals): False
  control, Disk also at TotalSlotDisk: True
  ```
- **Closed when** both hold:
  - `_as_whole` of a partitionable ad with `Disk < TotalSlotDisk` gives `Disk == TotalSlotDisk`, while a static ad
    stays unchanged (a unit row like `test_a_partitionable_slot_is_matched_at_its_totals`);
  - the probe's "as shipped" line reads `True`.

### M3 — Major: `run_lpc.py`'s default `--out` fails at the LPC
- **Defect.**
  - The default `root://cmseos.fnal.gov//store/user/<user>/hgg/` goes to `parquet_write` as a URI pyarrow cannot
    open.
  - §9 names the fallback for exactly this case: a local dir + `output_destination`.
  - Already dispatched.
- **Evidence.** The driver's site transcript `lanes/htcondor/probes/site-lpc/m69-hgg.txt` attempt 1:
  `pyarrow.lib.ArrowInvalid: Unrecognized filesystem type in URI: root://cmseos.fnal.gov//store/…parquet`.
  The run passed with a local `--out`.
- **Closed when** `run_lpc.py`'s default command writes its parts at the LPC (site transcript), and an extra test
  pins the default's form.

### m1 — Minor: `run_lpc.py` logs no submit or ready time, though its docstring and `htcondor.rst` say it does
- **Defect.**
  - `main()` calls `logging.basicConfig(level=INFO)`.
  - The status record's message names leg, host and endpoint only. `started_at`/`ready_at` live in
    `extra={"status": …}`, which that format drops.
  - The site transcript has them only because the site wrapper formatted `status` itself (`m69-hgg.txt` L37
    `| status=ServiceStatus(… started_at=…, ready_at=…)`).
  - §5.2's evidence and the r1 exit item need these times per server.
- **Probe.** `probes/m69b/probe_lpc_status_log_exec_rv1.py` (run_lpc's logging over a one-service set). Output:
  ```
  INFO:graphed_executors.services:service 'rv-log': managed leg (driver) at tcp://127.0.0.1:10000
  ```
- **Closed when** an extra row checks `run_lpc.main`'s own output, with a stand-in runner that emits a status
  record, for each server's `started_at` and `ready_at`. The row must fail on the d3f2820 runner.

### m2 — Minor: §5.2's "no Machine ads at all → it submits and waits" has no test
- **Defect.**
  - The guard `job.match_refusal(machines) if machines else None` is the only thing implementing it.
  - Without the guard, `match_refusal([])` reaches `max()` over no slots.
- **Probes.**
  - Mutant `no-ads-guard-gone` survives the extra suites on macOS and the frozen+extra suites in the pool
    (`mutants_exec_rv1.{mac,pool}.txt`).
  - `probes/m69b/probe_no_ads_exec_rv1.py`: `match_refusal([]) raises ValueError max() iterable argument is empty`.
- **Closed when** a row whose collector stand-in lists no Machine ad drives `_host_service` past submit into the
  announce wait (an announce returns the endpoint). The row must fail on that mutant.

## Reported deviations (judged against §5.2/§6)
- **`user_modules=[examples/hgg/analysis.py]`: accepted.**
  - Pickled parts name the module `analysis`.
  - A directory input lands as `hgg/` in the pilot's scratch dir, so `import analysis` would fail.
  - `analysis.py` imports no sibling module.
- **Positional manifests: accepted.** The plan names no flag.
- **`HISTOGRAM` keeps `[histserv]`, and test-experimental strips it: accepted.**
  - `bash -c '…${HISTOGRAM/\[histserv\]/}'` prints the bare requirement.
  - The 3.14t leg is green, and §6 wants histserv on every GIL leg.
- **test-htcondor lists `tests/extra/m69b`: accepted.** The job already lists each extra dir by name, so this
  equals §6's `tests/extra/m6*`.
- **`GRAPHED` 7e048bf: accepted.** `git log a0638719..7e048bf` is one commit (#65, m68c graphed), which #42's
  m68c tests need.
- **`run_local.report()` + `--histograms`: accepted.**
  - It implements §5.2's "histograms saved as UHI JSON" once, for both runners.
  - Extra mutant `report-drops-histograms` is killed.

## §5.2 decisions, each with a killed mutant
`probes/m69b/mutants_exec_rv1.py`. macOS 13/14 killed, pool 3/5, hgg 7/7; survivors are listed after the table.

| Decision | Mutant → killed by |
|---|---|
| `service_hosts` refusal (ValueError naming the offered hosts, before any pilot) | `narrow-refusal-gone` → frozen `test_a_host_the_profile_does_not_offer_is_refused_before_any_pilot` |
| narrowing gates the cluster capability | `narrow-not-gating-cluster` → extra placement |
| driver check sums the set's driver-hosted servers | `driver-each-not-sum` → frozen `test_a_driver_job_holds_its_servers_to_its_slot_memory` |
| limit = `driver_memory_mb`, `<=` | `driver-limit-ignored` → frozen managed; `driver-fit-strict` → extra |
| default = physical memory (POSIX pages; Windows DWORDs) | `posix-pages-wrong` → frozen managed; `win-dword-c_ulong` → extra |
| driver job: slot `Memory` from `$_CONDOR_MACHINE_AD` | `injob-slot-ignored` → frozen managed driver-job row |
| backend refusal merged beside the earlier legs | `refusal-legs-dropped` → extra |
| whole-ad `symmetricMatch` (not the request alone) | `match-always` → frozen oversized row; `match-request-only` → frozen `OpSysMajorVer == 99` row |
| partitionable totals, dynamic slots dropped | `as-whole-noop-unit`, `dynamic-slots-kept` → extra |
| `timeout_s` from the first `JobStatus == 2`; log every `IDLE_LOG_S` | `deadline-from-submit(-live)` → extra and frozen busy-pool row; `idle-log-every-poll` → extra |
| seven diagnostics, binnings, Weight, `weight`; `context=` through `plan()` | `njets-binning`, `unweighted`, `resolve-skipped`, `context-not-passed` → frozen `test_hgg_diagnostics.py` |
| LPC runner: placement and a driverless slot holding the servers | `lpc-placement-ignored`, `lpc-slot-without-servers` → extra run_lpc |

Survivors:
- `no-ads-guard-gone`: finding m2.
- `as-whole-noop` against the frozen busy-pool row in the pool. The extra unit row still kills it; see exit item 6.

## Exit-round items (constraints for the next dispatch; no round needed)
1. **The m68a flake is not m69b's.**
   - `test_a_child_that_exits_after_its_check_passed` comes from #39 (0e48380). It gives `python -c pass` a 1.0 s
     window to exit.
   - Under test-htcondor's coverage `.pth`, the child takes 0.227 s median and 0.276 s max idle
     (`probe_child_exit_exec_rv1.txt`).
   - It passed in this review's pool run. m69b adds nothing inside that window.
2. **The driverless "managed leg (driver)" then "user leg" for the same endpoint, 44 ms apart, is by design**
   (§3.1 `driver.main`). The outer `ServiceSet` starts it; `runner.services = eps` gives the run's own set leg 1.
3. **HggCombine dropping b's receipts is harmless on served runs, not hidden.**
   - `Receipt.__add__` returns `self` unless `other` is the empty receipt.
   - The fills are already on the server.
   - The one case where the drop would lose data, `combine(empty, x)`, is killed by the extra empty-identity row.
4. **`match_refusal`'s refusal text is reached only by the frozen pool rows.** That holds, and it suffices:
   - pool diff-cover is 100 % of 98 lines;
   - `match-always` and `match-request-only` are killed there, by the rows' 600 s hard timeout.
5. **Windows `physical_memory_mb`.**
   - The fake-`windll` rows cover control flow and `dwLength` only.
   - The struct's offsets match MEMORYSTATUSEX: size 64, `ullTotalPhys` at 8. The control is `c_ulong` on LP64:
     size 72, wrong offsets (`probe_memstatus_layout_exec_rv1.txt`).
   - The real call ran on all four Windows legs: histserv 0.2.1 installed, the frozen host-memory row green, and
     `services.py` missing only the pre-existing line 340.
6. **The frozen busy-pool row's witness of the substitution depends on timing.**
   - The collector's partitionable ad lags about 1 s behind a claim (`probe_collector_lag_exec_rv1.txt`:
     `(0.0, 15973) ... (1.0, 7909)`).
   - So the row can query a stale, unclaimed ad. For the record only: the frozen row stays as it is, and the
     extra unit row carries the discrimination.
