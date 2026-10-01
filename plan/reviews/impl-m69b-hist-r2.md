# m69b graphed-histogram implementation review, round 2 (PR #24, head 6ddb1b1, delta from b3a6a84)

## Verdict: APPROVE

Every local gate is green on 6ddb1b1. Both of round 1's Blockers are closed by the owner-authorized refreeze
(`freeze-m69b-fixup` = 1d432af), and the constants in src follow it. The delta pass found no design findings, and
neither did the whole-PR pass. One Minor finding (M1) answers the watch item. It is not in the delta and does not
block. For the driver's fold: CI run 36866406828 on 6ddb1b1 shows 19/19 jobs `success`. The ubuntu-latest py3.12
leg ran 410 passed, 1 skipped (memory model included). windows-latest and macos-latest py3.12 ran 405 passed,
6 skipped.

| Gate | Result | Evidence |
|---|---|---|
| frozen + extra, macOS arm64 py3.12, clean worktree | 410 collected: 405 passed, 5 skipped (memory model, Linux only) | `probes/m69b/gates_hist_rv2.txt` |
| frozen + extra, Linux arm64 py3.12, `python:3.12-slim` + `.[dev,histserv]` (pandas 3.0.6, pyarrow 25.0.1) | 410 passed, 1 skipped (correctionlib); the memory-model rows run | same |
| m69b frozen + extra, Linux arm64 py3.14 (round 1's failing arm leg) | 64 passed | same |
| per-file ≥ 90 % | lowest `_spec.py` 95.9 %; `histserv.py` 100 % | same |
| diff-cover vs origin/main | 369 lines, 0 missing | same |
| ruff, format, mypy (src+tests+scripts, 76 files), sphinx -W, `graphed_orchestrator.precommit --fast` | clean / ok | same |
| frozen unchanged after `freeze-m69b-fixup` | `git diff --stat 1d432af 6ddb1b1 -- tests/frozen` is empty; the control `56992b7..6ddb1b1` shows 6 files | same |
| integrity `scan_diff` | delta: 0 findings. Whole PR: only the advisory `ci_config_modified`. Control: 2 findings | `probes/m69b/integrity_hist_rv2.txt` |

## Checks asked

1. **Refreeze scope and discrimination.**
   - **Scope.** It stays inside the owner's scope.
     - 88d4a8e touches `histserv_harness.py`, `test_histserv_surface.py`, `test_histserv_packing.py`,
       `test_histserv_memory_model.py`, the README two-size row and the two dispute files.
     - 1d432af touches `test_histserv_fill_path.py` and its dispute.
     - The tag is annotated (object c1d4aa3) and is on origin.
     - The README has no stale absolute size: `grep -w` for 129/136/140/160/162/128 found 0 matches. The control,
       `-w B`, found 5.
   - **Discrimination.** `probes/m69b/mutants_hist_rv2.py` runs round 1's 30 mutants and 5 new ones against the old
     suite (b3a6a84) and the refrozen suite (6ddb1b1). It runs without `-x` over each mutant's tests plus packing,
     fill_path and surface (`mutants_hist_rv2.txt`).
     - All 35 mutants are killed on both suites.
     - Every kill set is identical with one exception: `oversize-shared` is no longer killed by fill_path's
       two-names-one-endpoint row. That row's own property is unaffected. Its designated killers, the packing
       two-size row and fill_path's receipts row, still kill it.
     - The new mutants are `stale-B` (129), `stale-b` (3.0), `ffd-reversed-tie`, `drop-fill-b-workers` and
       `below-B-accepted`, and all five are killed.
       - `stale-B` fails 9 packing/fill_path rows, and `stale-b` fails 5. So the frozen rows pin src to the harness
         constants.
       - The new slot sizes (`m` 1.375, `only_l` 2.75) still kill ascending order, insertion order and the reversed
         tie.
   - **Surface `_digest`.** `probes/m69b/probe_digest_order_hist_rv2.txt` hashes all 7 directories:
     - The new key in `PureWindowsPath` order equals the POSIX digest, and both equal `FROZEN_BEFORE_M69B`.
     - The old case-folded order reproduces CI's five Windows digests (3b599cbd, 282d0acc, 96e0d0cd, 2d49a3df,
       48587884).
     - Mutating one byte changes each digest.
   - **The refreeze author's evidence.** I sampled `model-maxima.txt`, `digest_check.txt` and `sim_new_vs_old.txt`.
     Each matches what I re-derived independently above. The 8 MODEL lines in `probe_histserv_memory.gha.txt` equal
     the log of run 36811610103 (lgray/graphed-histogram, `m69b-probe-ci`, success).
2. **src constants = max over the three probe files.** This command:
   ```
   grep -ho 'MODEL B=[0-9]* MiB O=[0-9]* B I=[0-9]* B a=[0-9.]* b=[0-9.]*' probe_histserv_memory{,.amd64,.gha}.txt | awk '…max…'
   ```
   prints `lines 16 B 164 O 4000 I 160 a 5.5 b 3.5`. src has `_BASE = 164 * MiB`, `_PER_HIST = 4000`,
   `_PER_TASK = 160`, `_FILL_A = 5.5` and `_FILL_B = 3.5`. `K` was not touched.
3. **design.rst.**
   - The "Filling on histserv servers" blocks run verbatim against 6ddb1b1 src: 3/3 MATCH, including
     `docs-0 512 435.0 MiB 2`.
   - Control: the b3a6a84 text run against 6ddb1b1 src refuses its 160 MiB context (`… below the 164 MiB …`).
     Evidence: `probes/m69b/probe_docs_blocks_hist_rv2.txt`.
   - No stale constant is left in `docs/*.rst`, `src`, `README.md` or `tests/extra`. `grep -w` for 129/136/140/160
     matches only the true `I = 160 B`. The control, `164`, matches 2 lines.
   - Round 1's exit item (name the environment `B` was measured in) is closed in both `design.rst` and the
     `histserv.py` comment.
4. **Regression of round 1's APPROVE surface.** None found.
   - Round 1's 30 frozen-suite mutants are killed, as above.
   - The 12 extra-suite mutants (`mutants_extra_hist_rv2.txt`) are killed, including `refusal-after-placement`
     against the rewritten 1024 MiB extra row.
   - Lazy import, pickled `HistservError`, receipts, resolve/unpack and positions are all re-killed.
5. **Watch item.** See M1. Stalls are diagnosable inside 240 s in one case only, so this is a finding. It is Minor.

## Findings

### M1 — Minor (non-blocking; predates the delta): a stall on an established channel surfaces in the frozen bound as a bare `HARD TIMEOUT`
- **Defect.**
  - Every RPC carries `timeout=_RPC_TIMEOUT_S` = 600 s, as §5.1 says ("each RPC bounded at 600 s").
  - The harness's `run_bounded` fails at 240 s with no stack.
  - histserv's client sets no keepalive and no `wait_for_ready`. So a server that hangs after the channel
    connected yields only `HARD TIMEOUT` inside the frozen bound: no endpoint, no RPC, no thread.
  - A server that hangs before the HTTP/2 handshake is diagnosable. gRPC's 20 s connect timeout raises a
    `HistservError UNAVAILABLE` naming the endpoint, through `ProcessPoolExecutor`, inside the bound.
  - None of this explains the CI 36809889213 hang. The failure log carries no stack, so that phase is unknown.
- **Probes.**
  - `probes/m69b/probe_rpc_stall_hist_rv2.py` runs the frozen pool row's plan, SIGSTOPs one server, and puts a
    30 s `run_bounded` around the call. Run against `git archive 6ddb1b1`; output in
    `probe_rpc_stall_hist_rv2.txt`:
    ```
    as-built 20.1s HistservError histserv at tcp://127.0.0.1:62556 answered UNAVAILABLE: … timed out before receiving SETTINGS frame
    connected 30.0s AssertionError HARD TIMEOUT: call did not finish within 30.0s          (endpoint named: False)
    connected-rpc5 5.0s HistservError histserv at tcp://127.0.0.1:63381 answered DEADLINE_EXCEEDED: Deadline Exceeded
    ```
  - `probes/m69b/probe_faulthandler_hist_rv2.py` runs the `connected` stall under pytest with
    `-o faulthandler_timeout=10`. Output in `probe_faulthandler_hist_rv2.txt`: at 10 s the dump names the stalled
    frame,
    `grpc/_channel.py … _blocking ← histserv.py line 375 in <lambda> ← line 279 in _call ← line 375 in _ship ← line 453 in __call__`,
    and the `HARD TIMEOUT` follows at 20 s. Spawned pool workers' stacks are not in that dump; the driver's are.
  - `pyproject.toml` `[tool.pytest.ini_options]` sets no `faulthandler_timeout`. A grep found 0 matches; the
    control, `addopts`, found 1.
- **Test that shows it closed.** Run `probe_faulthandler_hist_rv2.py` under the repo's own pytest config, with no
  `-o`. It must print the stalled thread's `_ship`/`_call` frames before the `HARD TIMEOUT`. The cheapest
  mechanism is pytest's built-in `faulthandler_timeout`, below 240, in `[tool.pytest.ini_options]`. It changes no
  gate and no frozen file. Whether to add it is the dispatcher's call.

## Exit-round items
- None from the delta.
