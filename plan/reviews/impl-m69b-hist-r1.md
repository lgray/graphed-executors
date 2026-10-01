# m69b graphed-histogram implementation review, round 1 (PR #24, head b3a6a84, base 4c4b79f)

## Verdict: REJECT

The local gates are green. CI run 36809889213 (head b3a6a84) is red on 9 legs, each failing one frozen row.
Both causes are in the frozen suite or the plan's constants, not in the implementation, so both go through
Test Disputes and a refreeze. I found no defect in the implementation code.

| Gate | Result | Evidence |
|---|---|---|
| frozen m69b/m48/m49 byte-unchanged since `freeze-m69b` (56992b7), `freeze-m48-fixup2`/`freeze-m49-fixup` (67131cb) | empty diffs | `git diff --stat <tag> b3a6a84 -- tests/frozen/<m>`; control `4c4b79f..b3a6a84 -- tests/frozen/m48` = 2 files |
| frozen + extra, local (macOS arm64, py3.12, graphed a0638719) | 405 passed, 6 skipped (5 memory-model rows run on Linux only; correctionlib absent) | `probes/m69b/gates_hist_rv1.txt` |
| per-file ≥ 90 % | lowest is `_spec.py` at 95.9 %; `histserv.py` 100 %, `boost.py` 98.9 % | same |
| diff-cover vs origin/main | 369 lines, 0 missing | same |
| ruff, format, mypy (src+tests+scripts) | clean locally and in CI's prek step | same; CI log "mypy (strict)…Passed" |
| sphinx -W | exit 0 | same |
| integrity shape scan (`scan_diff` over `origin/main...b3a6a84`, with a positive control) | one finding, the advisory `ci_config_modified` (pin + extra). No gate is relaxed. Control: 2 findings | `probes/m69b/integrity_hist_rv1.py` |
| **CI frozen rows** | **red: 4 windows legs (B2), 4 ubuntu-latest legs + ubuntu-24.04-arm py3.14 (B1)** | `probes/m69b/ci_run_36809889213_hist_rv1.txt` |

## Findings

### B1 — Blocker: the model's `B` is too small for a server in an environment where pandas can be imported
- **Defect.**
  - `B` = 129 MiB was fitted in `python:3.1x-slim` containers that had only histserv installed.
  - At import, histserv imports `hist`. `hist.interop` runs `try: import pandas` at module level, and pandas
    imports pyarrow when it is installed.
  - So wherever pandas is installed, the server at rest outgrows `B`. That includes CI's `.[dev,histserv]`
    environment (the `dev` extra requires pandas) and any coffea environment at a site.
  - Frozen `test_histserv_memory_model.py` fails `warm < BASE` in all 5 rows:
    - every ubuntu-latest leg: warm 132.6–140.5 MiB;
    - ubuntu-24.04-arm py3.14: 129.8 MiB;
    - the limit, `BASE`, is 135266304 B (129 MiB).
  - This is the tripwire §9 placed ("the ubuntu legs' memory test catches a … mis-scaled … server part of `B`"),
    firing as designed.
  - Beyond CI, a cluster-hosted server's `RequestMemory` would sit below its real footprint.
  - The growth assertions of those rows never run on amd64, because the warm assertion fails first.
- **Probes.**
  - `probes/m69b/ci_run_36809889213_hist_rv1.txt`, for example:
    ```
    == test ubuntu-latest py3.11 … test_a_64_mib_double_slot_… - assert 140140544 < 135266304
    == test ubuntu-24.04-arm py3.14 … - assert 136073216 < 135266304   (arm py3.11–3.13 pass)
    ```
  - `probes/m69b/probe_pandas_rss_hist_rv1.py`: the harness's argv, the model probe's warm-up, run by
    `docker run --platform linux/<arch> python:3.12-slim`.
  - Output, `probe_pandas_rss_hist_rv1.txt`:
    ```
    arm64 histserv only: warm VmRSS 59.4 MiB; pandas mapped: False    + pandas pyarrow: 122.0 MiB; pandas mapped: True
    amd64 histserv only: warm VmRSS 88.9 MiB; pandas mapped: False    + pandas pyarrow: 176.0 MiB (emulated)
    ```
  - The import chain, from `python -X importtime -m histserv` in the PR venv:
    `histserv.chunked_hist → hist → hist.basehist (291 ms cumulative) → pandas → pyarrow`.
    Source: `hist/interop.py` `try: import pandas as pd`.
- **Route.**
  - A Test Dispute against the five rows and the harness's `BASE`, with a plan amendment: re-run
    `run_memory_probe.sh` with pandas and pyarrow installed beside histserv on both arches and on Pythons
    3.11–3.14.
  - `B` becomes the maximum over the new MODEL lines. Re-check `O`, `I`, `a`, `b` and `K` in the same run.
  - The refreeze changes the harness constants. `histserv.py` `_BASE` and `design.rst` follow.
  - The implementation cannot close this alone: the frozen packing rows recompute predictions from the
    harness's constants.
- **Test that shows it closed.** All five rows pass on every ubuntu leg of the matrix at the new `B`, with
  CI's `.[dev,histserv]` environment unchanged. The growth assertions are then reached on amd64.

### B2 — Blocker: on Windows, the frozen digest row orders files differently from POSIX
- **Defect.**
  - `test_histserv_surface.py::_digest` iterates over `sorted(Path, …)`.
  - `WindowsPath` compares case-insensitively, so `README.md` sorts after `behavior_toy.py` and the
    directory digest changes.
  - `test_the_frozen_suites_before_m69b_are_unmodified_but_for_the_refreeze` fails on all 4 windows legs.
  - CRLF is already normalised, so line endings are not the cause.
- **Probe.**
  - `probes/m69b/probe_windows_digest_hist_rv1.py` hashes the files of `freeze-m69b`, taken with `git show`,
    in both orders.
  - Output, `probe_windows_digest_hist_rv1.txt`:
    ```
    m23 posix 7cc9...60930f4      m23 windows-casefold 3b59...e2def9d
    m49 posix c00f...94d08f0      m49 windows-casefold 96e0...b1b33f2
    ```
  - CI printed `{'m23': '3b59...b1b33f2', ...} == {'m23': '7cc9...94d08f0', ...}`, which matches the
    case-insensitive order: m23's prefix and m49's suffix.
- **Route.** A Test Dispute, followed by a refreeze in which `_digest` sorts on `f.relative_to(root).as_posix()`.
  The expected digests stay the POSIX values. An untracked dispute file for this row already exists in the
  checkout (`.graphed/m69b/disputes/test_histserv_surface__…refreeze.md`); I did not write it.
- **Test that shows it closed.** The row passes on windows-latest py3.11–3.14 with the expected digests unchanged.

## Reported deviations (judged against §5.1)
1. **Merged-fill read in commit 1.** Accepted. `pieces` and the refrozen m48/m49 rows need it, and the plan
   assigns no commit to the `boost.py` change.
2. **`_Served` split across commits.** Accepted. Commit 1 needs the wrap so that `serve` can return a served
   plan. Commit sizes are 752, 447 and 292 lines changed, each well under 2k.
3. **Extra tests sit with their commits.** Accepted. This matches §5.1's per-commit "extra tests" figures.
4. **graphed floor stays `>=0.0.5`.** Accepted.
   - `boost.py` already used `compiled.correspondence.node_map` on base 4c4b79f, and the floor line is
     unchanged.
   - The changelog says that the services surface is unreleased.
   - The plan defers the floor to the release that holds services.
5. **`bind_services` merges held endpoints.** Accepted. This is graphed's `Bindable` contract ("raises …
   when `endpoints` lacks the name and the part holds no endpoint of its own"): `require_bound` calls
   `bind_services({})` on a bound plan. The mutant `bind-no-merge` is killed by the frozen lazy-init row.
6. **Clients cached per (pid, endpoint) under a lock.** Accepted; it is the plan's "per endpoint per process".
   A cached client survives a server restart on the same port (`probe_stale_client_hist_rv1.txt`: three
   cached calls succeed, 0.00 s each).
7. **m48 extra refusal witness rewritten as a positive witness.** Accepted. The owner's ruling removed the
   refusal. The rewritten witness kills the `positions-dedup` mutant on its own.

## Probe asks
- **Memory model on amd64.**
  - It fails, on all 4 ubuntu-latest legs. The cause is B1, not the implementation: the amd64 legs fail at
    `warm < BASE`, before any of the implementation's fills run.
  - ubuntu-24.04-arm py3.11–3.13 pass; py3.14 fails.
- **histserv on Windows.** Every histserv server row ran and passed on windows-latest py3.11–3.14: fill path,
  retries, lazy init and composition. Those legs show 404 passed and the same 6 skips as macOS. The only
  failure there is B2.
- **grpcio, histserv and the git build of graphed on every leg.**
  - All GIL legs installed `.[dev,histserv]` and the a0638719 build, and reached pytest.
  - The 3.14t leg passed on `.[dev]`.
  - grpcio 1.84.0 and grpcio-tools 1.84.0 ship wheels for cp311–cp314 on manylinux x86_64/aarch64, macOS
    and win_amd64, and none for cp314t. histserv 0.2.1 is pure Python.
- **Docs claim against executors db8fb0a.** It holds.
  - Read with `git show`: `submit/engine.py` binds through `graphed_services.bind_services` (L367) and
    resolves through `graphed_services.resolve_services` (L391). The local executors only call `require_bound`.
  - Run end to end (`probe_submitrunner_e2e_hist_rv1.txt`), with `git archive db8fb0a` on `PYTHONPATH` and
    `SubmitRunner(ThreadBackend(2))` over two histserv servers, nothing bound by hand:
    `value types: Histogram ×2; equal twin: True; histserv left after run: none`.
- **Is `test_concurrent_first_calls_create_each_histogram_once` statistical?**
  - In principle, yes: it races eight barrier-released threads against an Init round trip.
  - Measured (`probe_race_rate_hist_rv1.txt`): the real code failed 0/20 runs, and the lock-free `_Handles`
    mutant failed 20/20.

## §5.1 decisions (each checked by a killed mutant; `mutants_hist_rv1.txt`, 30/30 killed)

| Decision | Mutants killed |
|---|---|
| Size model, constants = max over MODEL lines (B 129 MiB, O 4000, I 160, a 5.5, b 3.0, K 19 KiB; verified against the four probe files) | drop task term, drop connection term, `chunks` not `+1`, size without flow bins |
| FFD packing per context | ascending order, insertion order, no reuse of open servers |
| Refusal only at the message ceiling | ceiling off by one, oversize slot refused, oversize server shared, largest offered size chosen |
| Equal contexts share and warn; different args refused | fresh pack per context, no warning, different args shared |
| `plan.services` sorted by name | unsorted |
| unique_id = partition | random id, `ALREADY_EXISTS` raised |
| Receipts through the tree, add by identity | a receipt adds anything |
| resolve deletes, unpack keeps | resolve keeps copies, unpack deletes |
| Picklable `HistservError` | one formatted message passed as the only arg |
| Lazy histserv import | eager import |
| Server-side histograms created once | worker creates, create at bind, no create at pickle, no lock (extra only, 20/20) |
| Merged fills read per marked fill; one `pieces` per plan | positions deduplicated (m48), second firing records first |
| Plaintext only | TLS/HTTP endpoint allowed |

The extra tests are non-vacuous on their own: `mutants_extra_hist_rv1.txt` kills 12/12 mutants run against
`tests/extra` alone. These include refusal after placement, the plan's own services dropped, no
`declare_service`, the empty value as a zero histogram, `__setstate__` creating, `grpc://` refused, and the
unbound call passing through. The design.rst blocks run verbatim and their printed output matches
(`probe_docs_blocks_hist_rv1.txt`: 3/3 MATCH). `pieces` composes at `opt_level=0` and `1`, reading merged fills
per marked fill (`probe_pieces_opt0_hist_rv1.txt`).

## Exit-round items (wording only, constraints for the next dispatch)
- `design.rst` "How a server is sized" says "`B` = 129 MiB (the server at rest, …)" and that the constants were
  measured "under CPython 3.11–3.14 on Linux arm64 and amd64". Restate both after B1's re-measurement, naming
  the environment the server was measured in. The same applies to `histserv.py`'s constants comment, which names
  the probe files.
