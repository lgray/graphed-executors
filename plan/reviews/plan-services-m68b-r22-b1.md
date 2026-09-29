**NOT CLEAN**

# Review r22-B1: `plan-services.md` §3.3 part B1, delta round

## Scope
- **Snapshot:** `reviews/plan-services-m68b-r22-b1-snapshot.md` (plan at 36040d7), diffed against the r21-b1 snapshot.
- **Read:** the delta (shared-subsection Q-04 citation; B1 `ServiceJob` paths, `service.json` secret, the L17 reap rule; the B1 `test_cluster_service_job.py` and live rows; "Fails on (B1)") and what it references: the rest of the `ServiceJob` and `announce.py` bullets, the B1 harness, B2's DAG bullet where it calls `files()`.
- **Probes:** `git diff b0e2ea7 36040d7 -- plan/probes` (`announce_proto.py`, `probe_announce_rules.{py,txt}`), the new `probe_r22_b1_{python_witness,held_port,relative_paths}`, and "## decisions (round 16)".
- **Code:** executors c2298d7 (`htcondor_backend/{launch,backend,driverless}.py`, `.github/workflows/ci.yml`, `tests/frozen/m66`, `m67`).
- **Answers:** r21-B1's M38-B1 and M39-B1 and its five exit items.

One design finding, M40-B1. Two exit items are appended under "## r22-B1 exit items" in `m68b-exit-items.md`.

## Design findings

### M40-B1: the M39 repair resolves the relative `log_dir` against the cwd at `host_service` time, not the cwd `_stage` wrote `env.tgz` into
- **Where:** B1 `ServiceJob` bullet: "`submit()` does that in a new `service-<key>/` under `os.path.abspath(launcher.log_dir)`" and "the pilots' `env.tgz` under `os.path.abspath(launcher.log_dir)`". The B1 row's new leg: "under `monkeypatch.chdir(tmp_path)` with a relative `log_dir` … `os.path.isfile` holds for `<initialdir>/env.tgz`".
- **Why it changes code:**
  - `HTCondorBackend.__init__` calls `launcher.start` (c2298d7 `backend.py`). That call `_stage`s `env.tgz` into `log_dir` as given, relative to the cwd at runner construction.
  - `host_service` runs later, once per run. The live row itself runs two sequential runs on one runner.
  - So a runner built in cwd A and then used after a `chdir` to B (a notebook `%cd` between cells) gets `os.path.abspath("logs")` = `B/logs`. There are two outcomes:
    - **B has no `logs/`:** `service-<key>/` with `exist_ok=False` raises `FileNotFoundError`. With parents made, the link dangles and the job is held with code 13.
    - **B has another runner's `logs/env.tgz`:** the link resolves to that file, and the service silently runs with the other environment.
  - The new leg cannot see this. It changes cwd once, before staging, so the plan's spelling and the correct one agree, and `isfile` also passes the wrong-environment case.
  - This is M39's shape a second time. The M39 repair moved the failure instead of closing it. The operation that produces the shape: `CondorPilots` stores `log_dir` as given, so each later reader resolves it against its own call-time cwd. Round 16 already dropped another instance of it (`CondorPilots.stop` unlinking the secret after a cwd change).
- **Measurement:** `probes/m68b/probe_r22r_b1_cwd_between_runs.{py,txt}` (htcondor/mini 25.13.2, container `r22r-mini`, removed). It runs the real `CondorPilots.start` from A with `log_dir="logs"`, then changes cwd to B:

  | Case | What happened |
  |---|---|
  | plan/B-empty | `mkdir(exist_ok=False)` → `FileNotFoundError`; link → `B/logs/env.tgz`, `isfile` False, job `HoldReasonCode` 13 |
  | plan/B-other | link → `B/logs/env.tgz`, `isfile` True, job `ExitCode` 0, `service.out` `env-of-another-runner` |
  | control (absolute path taken when `start()` returned) | job `ExitCode` 0, `service.out` `env-of-A` |

- **Closed when:** the directory `_stage` wrote into is the one every later reader names. The cut at the cause is one line in `CondorPilots.start`: store `self.log_dir` absolute before `_stage` and the secret use it. m68b already edits `launch.py` for B2.
  - No m66 or m67 frozen test pins a relative `log_dir` or `initialdir`. m66's all use `tmp_path`; driverless already assigns an absolute one.
  - B1's `os.path.abspath(launcher.log_dir)` spellings then reduce to `launcher.log_dir`.
  - The round-16 drop of `CondorPilots.stop`'s secret closes with the same line.
  - If the plan keeps m66 untouched instead, it has to state why the cut at the cause is unavailable.
- **Test:** in `test_cluster_service_job.py`, under the recorder:
  1. `monkeypatch.chdir(A)`, `log_dir="logs"`, `start()` (whose `_stage` writes `A/logs/env.tgz`).
  2. `monkeypatch.chdir(B)`, where B holds its own `logs/env.tgz`.
  3. `ServiceJob.submit()`.
  4. Assert `os.path.samefile(<initialdir>/env.tgz, A/logs/env.tgz)` and that `initialdir` lies under `A/logs`.

  Resolving at submit time fails this (the plan/B-other row), and capturing the path at start passes it (the control row). `isfile` alone would not fail it.

## Checked and holding
- **M38-B1 is closed.** The no-`PATH` leg compares the child's recorded `sys.executable` with `P`, and the `./env/bin/python` leg is an `sh` wrapper that writes a marker. I re-ran `probe_r22_b1_python_witness.py` on this Mac with a third harness (miniforge 3.12.10, scratch `/private/tmp/r22r-b1/witness_rerun_mac312.txt`):
  - the prototype passes both legs;
  - mutant A (`sys.executable`) fails both;
  - mutant B (bare name → `sys.executable`) fails leg 1;
  - mutant C (left as given) fails leg 2.

  The skip ("`P` absolute and ≠ harness `sys.executable`") does not fire on the CI runners. Every main-matrix and `test-htcondor` job uses `actions/setup-python`'s interpreter (`ci.yml`), while `P` is `/bin/python3` on Linux and the Xcode path on macOS. Windows skips all subprocess legs.
- **The M39 members as the r21 finding stated them are closed.** In the relative-path probe, the `rel` and `input-rel` spellings fail the new `isfile` leg and the absolute spelling passes it. M40 is what remains.
- **Held-port leg.** `free()` reports p as taken on macOS for a wildcard listener in every form a test author might write: plain `bind(("", p))`, with `SO_REUSEADDR`, `socket.create_server(("", p))`, and dual-stack IPv6. A `127.0.0.1` listener is the control and reads as free (scratch `/private/tmp/r22r-b1/listener_kinds.py`, Python 3.12.10 and 3.9.6).
- **L17 and the secret file.** The prototype skips `hard_reap` when `returncode` is set, and reads `./graphed-secret` in attached mode, as the plan's text says. Re-running `probe_announce_rules.py` on macOS `/usr/bin/python3` 3.9.6 reproduces L1–L17, including L17 (reaped child: no `os.kill`; unreaped control: one SIGTERM). Output: scratch `/private/tmp/r22r-b1/rules_mac396.txt`.
- **Claims about c2298d7.** These hold:
  - `CondorPilots.__init__` keeps `Path(log_dir)`;
  - driverless sets `launcher.log_dir` to an absolute `out`;
  - `run["log_dir"]` is absolute (m67 frozen `test_driverless_payload.py` asserts it).
- **B2 check (shared code).** The delta changes `ServiceJob.files()`'s link targets and the watch-mode secret wording. B2's text and rows still hold:
  - B2's launcher `log_dir` is already absolute, so the change is a no-op there, and its row's `isfile(<run dir>/service-svc0/env.tgz)` stands.
  - Watch mode reads `<watch>/graphed-secret` as before.
  - L17 touches only the SIGTERM path.
  - `_stage` is unchanged.
  - M40's cut, in `CondorPilots.start`, is not on B2's submit path, and the in-job driver's `log_dir` is already absolute.
