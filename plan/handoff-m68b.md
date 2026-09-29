# Handoff: m68b plan convergence (cloud session → local agent)

Branch `plan/m68` of `lgray/graphed-executors`, planning only: **do not implement anything**. The brief is
`plan/brief-m68b-plan.md`. The project rules are `plan/meta/CLAUDE.md` and `plan/meta/graphed-project-plan-gated.md`;
the project plan wins over everything. Commits are conventional (`docs(plan): …`), authored by Lindsey Gray
<lindsey.gray@gmail.com>, with no Co-Authored-By, Assisted-by or session trailers. Push after every round. Stop every
process and container you start.

## Where it stands
- The unit is `plan/plan-services.md` §3.3, which is split into:
  - a shared subsection, "HTCondor behaviour relied on (both parts)";
  - **B1**, attached cluster hosting: `ServiceJob`, `announce.py`, `/announce`, `host_service`/`release_service`;
  - **B2**, DAG driverless, `SiteProfile.job_root` and the lxplus GPU/Triton run;
  - one frozen table, the "Fails on" lines and a commit list, where every row is labelled B1 or B2.
- **B2 has converged.** r18 was a clean delta and r19 a clean whole-part read. The r20 check after its exit items
  were applied was also clean. Don't change B2's design.
- **B1 is NOT CLEAN at r21**, the whole-part read after a clean r20 delta. It has two design findings. Both are
  small, and neither reopens an earlier family:
  - **M38-B1: the tests can't tell which interpreter the child got.** The `{python}` legs only check that argv[0]
    is absolute, so a child started through `announce.py`'s own `sys.executable` passes. Fix: in the no-`PATH` leg,
    assert argv[0] ≠ `sys.executable` (on Linux it equals python3 found on `os.defpath`). In the
    `./env/bin/python` leg, use a wrapper script that writes a marker file. Evidence:
    `probes/m68b/probe_r21_b1_python_witness.{py,txt}`.
  - **M39-B1: the `env.tgz` link breaks when `log_dir` is relative.** Its target is `<launcher.log_dir>/env.tgz`,
    and `CondorPilots` keeps `log_dir` as given (`launch.py:127`). With `log_dir="logs"` the link dangles and the
    job is held with code 13. Fix: an absolute link target, plus a leg with a relative `log_dir` that asserts
    `os.path.isfile` on the link. Evidence: `probes/m68b/probe_r21_b1_envlink_relative.{py,txt}`.
  - r21-B1 also left 5 exit items, under "## r21-B1 exit items" in `plan/reviews/m68b-exit-items.md`:
    - the secret file name in `service.json` doesn't match the prototype;
    - the pid reap can `os.kill` a stale pid once the child is already reaped;
    - the in-process handler leg must restore pytest's SIGTERM handler;
    - the held-port leg should bind its listener to the wildcard address;
    - the shared subsection should cite matrix row Q-04.

## Next steps
1. **Planner:** close M38-B1 and M39-B1 at their causes and apply the r21-B1 exit items. Put decisions in the plan,
   measurements in `plan/probes/m68b/*.{py,txt}` (driven probes against executors main c2298d7), and one-line
   reasons under "## decisions (round 16)" in `m68b-exit-items.md`. Change no B2 design.
   - The prototype of `announce.py` is `plan/probes/m68b/announce_proto.py`.
   - Re-run `probe_announce_rules.py` after any change. It must hold L1–L16 and run on Python 3.9.
2. **Reviewer, r22-B1 delta:** use a fresh subagent. Snapshot to `plan/reviews/plan-services-m68b-r22-b1-snapshot.md`
   and diff against the r21-b1 snapshot. Write `plan-services-m68b-r22-b1.md`, whose first line is CLEAN or NOT
   CLEAN. Number any findings from M40-B1.
3. **If r22 is clean: r23-B1, a fresh whole-part read.** If that is clean too, m68b has CONVERGED: B1 and B2 are
   both clean.
   - A small check of B2 is worth running only if B1's changes touch shared code. The SERVICE node runs
     `announce.py`, and `ServiceJob.files()` and `launch._stage` are shared.
4. **Commit and push after each round.** Then write the final message the brief asks for: the verdict, the design
   findings per round, the branch, the frozen-test list, the commit partition, and the owner items below.

Reviewer rules, in brief:
- A **design finding** changes a line the implementer or test author writes, or a decision they must make. Give
  where, why, the measurement, closed-when, and the test.
- Wording, labels, figures and citations are **exit items**, appended to `m68b-exit-items.md`. They never make a
  round unclean.
- A whole-part read happens in a part's first round and after any clean delta round; delta rounds review only the
  diff.
- Docker minicondor is `htcondor/mini`.

## Findings per round
| Round | Unit | Design findings |
|---|---|---|
| r8 whole | m68b | 6 (M18–M23) |
| r9 delta | m68b | 1 (M24) |
| r10 delta | m68b | 0 |
| r11 whole | m68b | 3 (M25–M27); split into B1/B2 |
| r12 whole | B1 / B2 | 1 / 1 |
| r13 delta | B1 / B2 | 1 / 2 |
| r14 delta | B1 / B2 | 2 / 1; brief's rule stopped the loop, owner asked to continue |
| r15 delta | B1 / B2 | 1 / 0 |
| r16 | B1 delta / B2 whole | 0 / 1 (M44: stale `result.pkl` on `log_dir` reuse) |
| owner redesign | — | see below |
| r17 whole | B1 / B2 | 3 (M34–M36) / 1 (M45) |
| r18 delta | B1 / B2 | 0 / 0 |
| r19 whole | B1 / B2 | 1 (M37: unbounded orphan reap, SIGTERM deadlock) / **0, B2 converged** |
| r20 | B1 delta / B2 check | 0 / 0 |
| r21 whole | B1 | 2 (M38, M39) |

## Owner-directed redesign (after r16; fixed)
1. **Each run gets its own directory.** A DAG run lives in a new `<log_dir>/graphed-<nonce>/`. There is no `force`,
   no rescue handling and no pre-submit cleanup. m67's plain job keeps `log_dir`, because its frozen test requires
   `driver.log` there.
2. **The service child runs in an isolated `service/` directory holding exactly its declared inputs.** The
   directory is built submit-side as a mirror of file symlinks, is the only input transferred, and every
   `transfer_input_files` entry is relative to `initialdir`. This is isolation of concerns, not full sandboxing.
   It replaced an enumerated list of reserved names.
3. **graphed's HTCondor needs are defined from HTCondor's docs and probed over the whole surface.** The results are
   in `plan/probes/m68b/condor_surface/`:
   - `NEEDS.md`: 54 rows;
   - `RESULTS.md`: results, plus an appended "Superseded consequences and added rows" section with S-19, D-08a and
     Q-04;
   - `probe_surface_*`.

   The plan relies on nothing that matrix contradicts, and on no configuration value it lists as not assumable.
   Key consequences:
   - the DAG is submitted with `{"UseDagDir": True, "AddToEnv": "_CONDOR_DAGMAN_USE_STRICT=0"}`;
   - done/failed comes from the latest driver try's ExitCode;
   - held comes from a driver-node query, never from `DAG_*` counters or `DAG_Status`;
   - `driver.sh` writes a placeholder `result.pkl` (this changes m67's plain job; m67's frozen tests stay green);
   - `act(reason=)` is never read back.

## Planned m68b frozen tests (`tests/frozen/m68b/`)
- **B1:**
  - `test_announce_route.py` (all OS)
  - `test_cluster_service_job.py` (all OS; subprocess legs POSIX-only)
  - `test_cluster_services_live.py` (minicondor)
- **B2:**
  - `test_driverless_dag.py` (all OS; fixture `data/from_dag-generic.txt`)
  - `test_driverless_dag_live.py` (minicondor with one simulated GPU)

## Planned commits (each ≤2k, each part's freeze first)
- **B1:**
  - 0. `test(services): frozen m68b, attached hosting` (~750)
  - 1. `feat(htcondor): cluster-hosted services and /announce` (~790; includes CI running `tests/frozen/m68b` and
    the simulated-GPU pool line)
- **B2:**
  - 0. `test(services): frozen m68b, DAG driverless` (~550)
  - 2. `feat(htcondor): job_root and driverless DAG with SERVICE nodes` (~500)
  - 3. `docs(m68b)` (~170)

§7 has the totals. The PR stacks on m68a, on `main`.

## Owner items (not blocking the plan)
- **Site checks (1)–(3), in plan §3.3/§9:**
  - (1) the lxplus GPU/Triton run: the image's python3, the announced identity form, scratch layout, and whether a
    job without a credential is accepted;
  - (2) the lxplus DAG from `/afs`: `from_dag`/`AddToEnv` accepted, `klist` on the SERVICE node via
    `condor_ssh_to_job`, and the AFS ACL;
  - (3) lpc: the proxy's landing name and the `MOUNT_UNDER_SCRATCH` effect.
- **Custom profiles:** a custom profile without `job_root` can no longer self-submit, which it could under m67.
- **Change to m67's plain job:** a killed driver is now retried and then fails with the placeholder
  `RuntimeError`, instead of being held. The docs commit documents this.
- **Missing probe files:** two files the plan cites aren't in the checkout: `probes/services-lpc/p1-dag/…` (in the
  m67 row) and `probe_hgg_original_lpc.txt` (m69a).

## Local setup the cloud session used
- **Clones:** `../code` is a worktree of executors `origin/main` (c2298d7), and `../graphed` is a clone of
  `graphed-org/graphed`.
- **Docker:** `htcondor/mini` 25.13.2.
- **Python venvs:** m68b probes run with a venv holding `htcondor` bindings and executors installed in editable
  mode.
