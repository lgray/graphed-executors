**CLEAN**

# Review r18-B1: `plan-services.md` §3.3 part B1 (attached cluster hosting), delta round

## Scope
- **Snapshot:** `reviews/plan-services-m68b-r18-b1-snapshot.md`, identical to the plan at review time.
- **Delta:** `git diff --no-index --word-diff` of the r17-B1 snapshot against the plan. It covers the shared subsection's S-19/D-08a pointer (L436–437), Secrets (L458–461), the `service/` rules (L474–487), `ServiceJob` keys (L500–505), the two B1 frozen rows (L706–707), "Fails on (B1)" (L719–721), and RESULTS' appended section (`git diff 6000b48`).
- **Also read:** the round-12 decisions in `m68b-exit-items.md`, and `announce_proto.py` with `probe_announce_rules.{py,txt}` (L10–L12).
- **Code:** graphed-executors main `c2298d7` (`htcondor_backend/launch.py`, `sites.py`). No other B1 line changed, and D2/D3/D10 are untouched.
- **New evidence:** `probes/m68b/probe_r18_b1_envlink.{py,txt}`, from htcondor/mini 25.13.2 in container `r18b1-mini`, which has been removed.

There are no design findings. Four exit items are appended under "## r18-B1 exit items" in `m68b-exit-items.md`.

## M34–M36 are closed at their causes
- **M34-B1 (argv[0] base, raising `Popen`): closed.**
  - L478–484 splits the two bases:
    - `{python}` is resolved against `announce.py`'s cwd (the job dir) before rendering.
    - A literal argv[0] is left as written, so POSIX `Popen(cwd=service/)` resolves it where the inputs are.
  - A `Popen` that raises exits 3, naming argv[0] and the error.
  - The row carries the `./serve.sh` leg and the `./missing` leg, and "Fails on" names both wrong bases and the traceback exit.
  - Re-run of `probe_announce_rules.py`: L1–L12 give the same outcomes as the committed `.txt`, differing only in pids and ports.
    - L10: `{python}` becomes absolute, and the control raises from `service/`.
    - L11: `./serve.sh` announces.
    - L12: exit 3 naming `./missing`, with no traceback.
- **M35-B1 (dead live witness): closed.** The replacement is decidable, and it discriminates.
  - **Checked on the pool:** a running job removed later keeps `JobBatchName`, `JobCurrentStartDate` and `EnteredCurrentStatus` in its history ad, and `JobCurrentStartDate ≤ t ≤ EnteredCurrentStatus` held for a `t` taken while the job ran. This was a scratch check in `r18b1-mini`.
  - **The integer-second truncation cannot flip either comparison.** Run 2's `t` comes after run 2's submit, negotiation and announce, which is seconds after run 1's removal.
  - **What the leg fails:**
    - A cached endpoint means no run-2 cluster is found.
    - A service outliving its run makes run 1's `EnteredCurrentStatus` greater than `t`.
  - **The 404 control keeps the old witness from coming back.**
- **M36-B1 (`,` on the wrong paths): closed.**
  - Every `transfer_input_files` entry is now relative to `initialdir` (`announce.py,service.json,graphed-secret[,env.tgz][,service]`), and `env.tgz` is a file symlink in `initialdir`. The input refusal is dropped with its reason, the row carries `a,b` accepted and "no absolute entry", and "Fails on" names an absolute entry.
  - **Not pinned before, now pinned:** whether condor follows a relative top-level file-symlink entry when spooled. S-07/S5 covered only an absolute entry, unspooled. This matters on the real sites, because lpc and lxplus are both `spool=True, ship_env=True` (`sites.py:57-58,77-78`).
    - `probe_r18_b1_envlink.txt` lists `env.tgz,service` relative to `<log_dir>/service-k`, with `env.tgz` a symlink to `<log_dir>/env.tgz` (absolute target).
    - It covers `log_dir` with and without `,`, spooled and not.
    - All four cases ran, and `env.tgz` arrived as a regular file that untars.

## Checked and holding
- **The RESULTS appended section is consistent with the plan.** S-19 matches `probe_input_dir.txt` and `probe_r17_b1_input_exec.txt`, and the superseded consequence 9 is restated for listed paths, matching L486–487. The shared subsection's "cites a row only where it matches or pins" rule holds.
- **Secrets (L458–461) are consistent with L9/L8.** The child cannot serve the secret from `service/`, and the file is unlinked before start.
- **The round-12 decisions in `m68b-exit-items.md` match the plan text** on all three B1 points.

## Evidence
- `probes/m68b/probe_r18_b1_envlink.{py,txt}` (M36-B1 closure on spooled and unspooled pools).
- A re-run of `probes/m68b/probe_announce_rules.py`, with the same outcomes.
- Container `r18b1-mini`, started and removed. Scratch was `/tmp/claude-0/review-r18-b1/`.
