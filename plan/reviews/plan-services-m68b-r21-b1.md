**NOT CLEAN**

# Review r21-B1: `plan-services.md` §3.3 part B1 (attached cluster hosting), whole-part read

## Scope
- **Snapshot:** `reviews/plan-services-m68b-r21-b1-snapshot.md`, identical to the plan at review time.
- **Read in full, as implementer and test author:**
  - the §3.3 preamble and its B1 ladder rows (L415–431);
  - the shared subsection "HTCondor behaviour relied on" (L432–453);
  - "#### B1 — attached cluster hosting" (L454–593);
  - the harness, the three B1 frozen rows, "Fails on (B1)" and the B1 commits (L714–753);
  - D2, D3 and D10 (L15–123), plus the §3.1 `recipes`, `ServiceSet`, engine and `htcondor_backend/` bullets where B1 consumes them, and §6 (`test-htcondor`, the all-OS job).
- **Checked against:**
  - `condor_surface/NEEDS.md` and `RESULTS.md`, including the appended section (S-19, D-08a, Q-04);
  - `probes/m68b/announce_proto.py`;
  - graphed-executors `c2298d7`: `htcondor_backend/{launch,server,backend,sites,__init__}.py`, `.github/workflows/ci.yml` (`test`, `test-htcondor`), `.coveragerc-htcondor`, `pyproject.toml` (ruff `py311`, selected rules; mypy).
- **Re-run and new evidence:**
  - `probe_announce_rules.py` under **Python 3.9.25** (htcondor/mini's `/usr/bin/python3`, container `r21b1-py39`, removed). L1–L16 reproduce the committed text, including `pthread_sigmask`, `preexec_fn`, the pid-based `os.waitpid` reap (L14: exit 143 5.0 s after the SIGTERM, child gone) and L16. The prototype therefore runs on 3.9 as the plan requires. Output: `/tmp/claude-0/review-r21-b1/p39/rules_py39.txt`.
  - `probes/m68b/probe_r21_b1_python_witness.{py,txt}` (local): M38-B1.
  - `probes/m68b/probe_r21_b1_envlink_relative.{py,txt}` (htcondor/mini 25.13.2, container `r21b1-mini`, removed): M39-B1.
  - Scratch `/tmp/claude-0/review-r21-b1/thr_probe.{py,txt}`: see "Checked and holding".

There are two design findings, M38-B1 and M39-B1. Five exit items are appended under "## r21-B1 exit items" in `m68b-exit-items.md`.

## Design findings

### M38-B1: no leg can fail "a child started through `announce.py`'s own `sys.executable`"
- **Where:**
  - L474–478 say `announce.py` never uses its own `sys.executable` (S-05: that value is `''` for a bare `python3` in a PATH-less job).
  - "Fails on (B1)" (L738) lists "a child started through `announce.py`'s own `sys.executable`".
  - The B1 row (L725) has two legs for this:
    - "with `service.json.python` = `./env/bin/python`, a symlink in the job dir to `sys.executable`, the service announces … and the child's `argv[0]` … is absolute";
    - "with `PATH` removed from the env and `{python}` a bare `python3` on `os.defpath`, the service announces with an absolute `argv[0]`".
- **Why it changes a line the test author writes:**
  - In the harness, `announce.py` runs as `[sys.executable, "-m", …]`, so its `sys.executable` is a non-empty absolute path.
  - An implementation that renders `{python}` as `sys.executable` therefore starts a working child in both legs, and that child's `argv[0]` is absolute. Both witnesses ("announces", "absolute") pass.
  - The hazard only appears in a real PATH-less job (S-05). The live leg does not reach it either, because on `generic` `service.sh` execs the driver's absolute `sys.executable`.
  - So the one Fails-on property that guards S-05 has no leg that can fail. The assertions have to name the path the child should have been started through.
- **Measurement:** `probes/m68b/probe_r21_b1_python_witness.txt` runs the prototype and a mutant whose only change is `python = sys.executable`:

  | Run | Leg 1 (PATH removed, `python3`) | Leg 2 (`./env/bin/python`) |
  |---|---|---|
  | Prototype | `argv[0]` `/bin/python3`: absolute, equal to `shutil.which("python3", path=os.defpath)` | `<job dir>/env/bin/python`: absolute, equal to that path |
  | Mutant | `argv[0]` `/usr/local/bin/python3` (= `sys.executable`): absolute, not equal to the defpath python | `argv[0]` `/usr/local/bin/python3`: absolute, not equal to `<job dir>/env/bin/python` |

  The row's witness passes both implementations. The equality checks separate them.
- **Closed when:** the row's two legs assert where the child's interpreter came from, and both hold on Linux and macOS.
  - **Leg 1:** `argv[0] != sys.executable`. On Linux it also equals `shutil.which("python3", path=os.defpath)`. macOS's `/usr/bin/python3` shim re-execs, so equality is not portable there.
  - **Leg 2:** `env/bin/python` is a small `sh` wrapper that writes a marker file and then `exec`s `sys.executable` with `"$@"`. The leg asserts the marker exists. A symlink cannot tell the two paths apart once a framework build re-execs.
- **Test:** the mutant above fails both legs, and the prototype passes them.

### M39-B1: `env.tgz`'s link target is spelled from `launcher.log_dir`, which m66 keeps relative
- **Where:** L508–510 give `env.tgz` as "a file symlink in `initialdir` to the pilots' own `<launcher.log_dir>/env.tgz`". The B1 row (L725) checks only "`env.tgz` a file symlink in `initialdir`", on `tmp_path`, which is absolute.
- **Why it changes code:**
  - `CondorPilots` stores `log_dir` as given (`launch.py:127`, `Path(log_dir)`), so `htcondor_runner(log_dir="logs")` gives a relative one. m66's own paths work with that: the executable and `initialdir` are both resolved against the submitter's cwd (`launch.py:199–205`).
  - A link target spelled from it does not work. `os.symlink(launcher.log_dir / "env.tgz", <service-key>/env.tgz)` resolves relative to the link's own directory, so the link dangles.
  - The job is then held at input transfer (S-13). `host_service` raises `RuntimeError` on exactly the `ship_env` sites (lpc, lxplus) for any image-less recipe.
  - The target must be `os.path.abspath(...)` (or `../env.tgz`). The test must check that the link resolves, which the B2 row already does for its node (`os.path.isfile(<run dir>/service-svc0/env.tgz)`) and the B1 row does not.
- **Measurement:** `probes/m68b/probe_r21_b1_envlink_relative.txt`, run as submituser from `~/r21b1-relink` with `log_dir = Path("logs")`:
  - **A** (target `logs/env.tgz`): the link does not resolve on the submit side, and the job is held with `HoldReasonCode` 13, "reading from file …/logs/service-A/env.tgz: (errno 2)".
  - **B** (positive control, the absolute target): the job completes with `ExitCode` 0.
- **Closed when:** L508–510 say the link's target is the absolute path of the pilots' `env.tgz`.
- **Test:** the B1 row's `ServiceJob` keys leg adds `os.path.isfile(<initialdir>/env.tgz)` (the link resolves), run with a relative `log_dir` under `monkeypatch.chdir(tmp_path)`. A target spelled from the relative `log_dir` fails it.

## Checked and holding (no finding)
- **Surface reliance.** Every HTCondor behaviour B1 relies on maps to a matrix row that matches it, or to the "not assumed" table, or to a named owner site check (N-02).
  - **Submit description:** S-01, S-03/S-04, S-05, S-08/S-09/S-19, S-12, S-18.
  - **Lifecycle:** L-01/Q-03, L-02 (`job_max_vacate_time=30`), L-07, L-08, L-09.
  - **Scratch:** X-01/X-02/X-08 and X-04.
  - **Q-04** for the live row's history times.
  - No value on RESULTS' not-assumable list is read.
- **Python 3.9.** Everything `announce.py` uses is 3.9 stdlib: `shutil.which(path=)`, `signal.pthread_sigmask`, `preexec_fn`, `os.waitpid(WNOHANG)`, `hmac`, `urllib`, and `os.path.ismount`. The full rules probe passes on 3.9.25 (above).
  - Running it as `-m graphed_executors.htcondor_backend.announce` imports the package `__init__`. That starts no thread (`threading.active_count() == 1` after the import), so the single-thread premise behind blocking SIGTERM around `Popen` holds in the harness as well as in the job.
- **SIGTERM between fork and exec.** With `preexec_fn`, a family-wide SIGTERM can reach the child before exec, where the inherited Python handler raises inside `preexec_fn`. `Popen` then raises `SubprocessError`, which `announce.py` does not catch.
  - The parent received the same SIGTERM, which is pending while blocked. The `finally` unblocks it, `_Stop` replaces the `SubprocessError`, and the process exits 143.
  - That happens only on condor's family delivery (L-02), so the outcome is correct.
- **Concurrent bindings use.** Overlapping runs call one launcher's `htcondor2.Schedd` from two threads (`submit`, `query`, `act`, `history`), and `htcondor2_impl` does release the GIL (`PyEval_SaveThread`). 8 threads × 150 iterations on one `Schedd` gave 0 errors on 25.13.2 (scratch `thr_probe.txt`).
- **m66 seams:**
  - `write_secret` writes hex, and `announce.py` signs with `bytes.fromhex`.
  - `sign()` and `SIG_HEADER` are the pilots' (`server.py:41,54`).
  - `counts_as_alive` treats a held job with code 16 as alive (`sites.py:114`).
  - `submit_description` sets `initialdir` after `base` (`launch.py:167–169`), which is why the plan builds the `ServiceJob` keys itself (L497–498).
  - `LEASE_S`/`POLL_S` are 30/10.
- **CI:**
  - `test-htcondor` keeps `COVERAGE_PROCESS_START` and `sigterm = true`, and `announce.py`'s handler replaces coverage's. `sys.exit(143)` saves the data.
  - The main matrix runs `test_cluster_service_job.py` on Linux and macOS for its subprocess legs, as §6 states.
  - The `test-htcondor` diff-cover gate (98% of changed `htcondor_backend` lines) also covers `announce.py`. That is the implementer's to meet with `tests/extra`, not a plan change.
- **Commit sizes:** B1 commit 0 is ~750 lines and commit 1 ~790, both within 2k.
