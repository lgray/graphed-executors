# m68b HTCondor surface — results and plan consequences

Pool: `htcondor/mini` 25.13.2 (containers `surf-*`; `surf-priv` `--privileged` for MOUNT_UNDER_SCRATCH and
Apptainer; `surf-pool`/`surf-life`/`surf-dag` with `NUM_CPUS = 40` so concurrent DAGs and SERVICE nodes do not starve
for slots, `surf-pool` also with `probes/m68b/sim_gpu.config`); bindings 25.13.2 and, for L7, the PyPI wheel 25.14.1 that `test-htcondor` installs. Row ids are
`NEEDS.md`'s; probe ids are the line prefixes of `probe_surface_<area>.txt`. "Match" = observed as the docs say.
Consequences assume the owner's redesign: a fresh `log_dir/<run_nonce>/` per run, and the service child in an
isolated directory holding only its declared inputs. **Plan-affecting rows are in bold.**

## S — submit description
| ID | Observed | Docs | Consequence for the plan |
|---|---|---|---|
| S-01 | relative `executable` with `initialdir` holding it, cwd not: held 13, reading `<cwd>/svc.sh` (S1a); absolute runs (S1b) | match | no change (absolute already) |
| S-02 | lands as `scratch/svc.sh`, argv `service.json` (S1b) | match (name U) | no change |
| S-03 | `initialdir` absent → `schedd.submit` raises `HTCondorException … No such directory` (S3a) | P | state: `log_dir/<nonce>/` and each `service-<key>/` are made before `submit`, and the raise is a `host_service` failure path (forget the key) |
| S-04 | bindings submit pre-creates only `log` — not `output`/`error` (S3d); missing subdirs of `output` created at transfer (S3c) | **mismatch** (`file-transfer.rst` says zero-length output/error at submit; that is `condor_submit`'s) | an absent `service.out` means the job never produced output (e.g. held at input); `host_service`/`RunHandle.logs()` must not assume the file exists |
| **S-05** | no `PATH` in the job env; sh falls back to its builtin `/usr/local/bin:/usr/bin`; Python then has `os.environ["PATH"]` unset (Popen searches `os.defpath`) and **`sys.executable == ''`** for a bare `exec python3` (S4a, S4b, S4e); `TMPDIR=TMP=TEMP=<scratch>` (S4d) | P (PATH absence U) | **`announce.py` must never use `sys.executable`; "a relative `{python}` made absolute" must apply only to a path with a separator (`./env/bin/python`) — `abspath("python3")` would give `<job>/python3`; a bare `{python}`/argv[0] is resolved with `shutil.which` (defpath) or left bare; say that a recipe's argv[0] is absolute or on `/bin:/usr/bin` outside a container** |
| S-06 | new-syntax `environment` and a `getenv` matchlist work (S4c) | match | no change |
| S-07 | file, dir (under its name), `dir/` (contents), dir with spaces, empty dir, symlink-to-file (copied as a file) all land (S5) | match | no change |
| **S-08** | a symlink to a directory — top-level input or anywhere inside a transferred dir — holds the job 13 "Transfer of symlinks to directories is not supported" (S5a, S5b) | match (the hold is U) | **`ServiceJob` refuses at construction an input that is, or contains (walk without following), a symlink to a directory, naming it; else attached = held → `RuntimeError`, DAG = held SERVICE node → driver times out 3×** (a model repository is exactly where such links occur) |
| **S-09** | a `,` in a path splits the list → held 13, "2 total failures" (S5c) | match | **refuse inputs (and `user_modules`, which m66/m67 join the same way) containing `,`** |
| S-10 | `service.json` then two user `service.json`: the last listed silently wins, exit 0 (S6a) | P | confirms the duplicate-basename refusal; no change |
| S-11 | an input named like the executable: the executable wins, the input vanishes (S6b) | U | confirms reserving `service.sh`; no change |
| S-12 | a user `.job.ad`/`.machine.ad` **replaces condor's file that `$_CONDOR_JOB_AD`/`$_CONDOR_MACHINE_AD` name** (identity read by `machine_host()`/announce is then the user's); `_condor_stdout` is overwritten by stdout; `tmp`/`var` land as plain dirs where nothing is mounted (S6c) | U | confirms the `.`/`_condor_` reservation (it also guards the announced identity — say so); no change |
| S-13 | missing input: held 13, subcode 2, before running (S7) | match | no change |
| S-14 | `preserve_relative_paths=True` lands `service/models`, `service/cfg.json` (relative to `initialdir`) under `service/`; an absolute input still lands flat (S8) | match | redesign 2: condor cannot place the recipe's (absolute) inputs into `service/`; keep `announce.py` moving them; do not set `preserve_relative_paths` |
| **S-15** | a `transfer_output_files` entry missing at exit holds the job 12 for exit 0, exit 1, SIGKILL, under `ON_EXIT` and `ON_EXIT_OR_EVICT`; a SIGKILLed job whose file exists is not held (leaves with `ExitBySignal`); `ON_SUCCESS`+`success_exit_code=0` never holds but returns nothing on exit 3 (S9) | match | **decide: `driver.sh` writes placeholder `result.pkl` and `driver.log` before it execs python, so every driver death transfers, is not held, and reaches `RETRY`/`max_retries` (today a driver killed before writing `result.pkl` — OOM, SIGKILL, interpreter missing — holds the node for ever, `probe_r12_dag_held_node`, and the m67 plain job likewise is held instead of retried); `RunHandle.result()` maps the placeholder to "driver died before writing a result"** |
| S-16 | `MY.X='"v"'` → string, `True` → bool, unquoted → expression evaluating UNDEFINED (S10) | match | no change |
| S-17 | `request_cpus="1.0"` kept as `1.0`, `request_memory="64.0"` → 64, `request_gpus=0` adds no GPU requirement (S11) | P | `str(int(v))` stays (harmless either way); no change |
| S-18 | `request_gpus=1` → `AssignedGPUs`, `CUDA_VISIBLE_DEVICES` set; `=2` on a 1-GPU pool idles (no hold) (S12a/b) | match | no change for B1 (timeout path); B2: see D-06 |

## X — execute scratch (EP-configuration dependent; the plan cannot read the EP's config from the submit side)
| ID | Observed | Docs | Consequence |
|---|---|---|---|
| X-01 | nested (default 25.x): cwd `…/dir_N/scratch`, siblings `htcondor/`, `user/`; `STARTER_NESTED_SCRATCH=false`: cwd `…/dir_N` (X[A], X[B]); lxplus: `/srv` (Singularity target, `m67-driverless.txt`) | match | `announce.py` uses its cwd only, never a layout; no change |
| X-02 | condor's own scratch entries in **both** layouts: `.job.ad`, `.machine.ad`, `_condor_stdout`, `_condor_stderr`, the executable, plus `.chirp.config` when not nested (X[A,B,C,F]); under Apptainer also `.docker_sock`, `.update.ad`, `scratch/`, `tmp/`, `var/`, `var_tmp/` (X[F2,G,H]); `condor_ssh_to_job` adds `.condor_ssh_to_job_N` (N3) | **mismatch**: `global.rst` `STARTER_NESTED_SCRATCH` says `.job.ad` and metadata go to `user/`; `env-of-job.rst` says scratch (observed) | the set is open-ended and version-dependent: redesign 2 (child in `service/` holding only inputs) is required, not optional; no reserved-name list can be the isolation mechanism |
| X-03 | `x509userproxy` lands in scratch under the source basename (`x509up_u1001`), `X509_USER_PROXY` = its absolute scratch path, both layouts (X[*/proxy]) | P (location U) | reserve the basename of the profile's `x509userproxy` (lpc: `x509up_u<uid>`); no change |
| X-04 | `MY.SendCredential=True` on a pool without credd/credmon: matched, never starts, **idles for ever, no hold** (X[A,C/cred]; ShadowLog "SEC_CREDENTIAL_DIRECTORY_KRB not defined", `probe_surface_scratch_logs.txt`); at lxplus the cache is `/srv/<user>.cc` in scratch, `KRB5CCNAME` set (`m67-driverless.txt`) | match (scratch location); idle-forever U | attached drop of `SendCredential` stands; a watch-mode node on a profile without it is fine; never add it to `generic` (CI would idle) |
| X-05 | unprivileged starter: no `tmp/`,`var/` (X[A]); privileged default: `tmp/`, `var/tmp/` bind-mounted over `/tmp`,`/var/tmp` (X[C]); `""`: none (X[D]); `"/tmp,/var/tmp,/dev/shm"`: also `dev/shm` (X[E]) | match (the unmountable case U) | **the `tmp`/`var` reservation assumes the default list and bare EPs: under Apptainer condor also creates `scratch`, `var_tmp` (X-02) and a site list can add roots (`dev`). State the assumption, extend the reserved set by `scratch`, `var_tmp`, `dev`, and add a runtime guard — `announce.py` exits 3 naming an input whose scratch entry is a mount point (`os.path.ismount`) before moving it** |
| X-06 | an input dir `tmp` under MOUNT_UNDER_SCRATCH merges into the job's `/tmp` (`/tmp/USERFILE` exists) (X[C,G/tmpin]) | U | confirms reserving `tmp`/`var`; the move into `service/` would move a mount point — covered by X-05's guard |
| X-07 | bare EP: `TMPDIR`/`TMP`/`TEMP` = scratch root, `HOME` = the user's home (S4d, X[A,B]); Apptainer: `TMPDIR=/tmp` (a scratch-backed `-S` mount), `HOME` = scratch (X[F2,G,H]) | U | a service's temp files never land in `service/`: not served; a service must not assume `HOME` is writable/persistent; no change |
| X-08 | see "Singularity" below | P | see below |

## L — lifecycle
| ID | Observed | Docs | Consequence |
|---|---|---|---|
| L-01 | 8/8 short jobs: 1→2→(leave)→history at once; 0 s in neither queue nor history (L1) | match | no change |
| **L-02** | `condor_rm`: SIGTERM reaches parent **and child at the same instant** (whole family); a parent that waits for a SIGTERM-ignoring child blocks; the job stays in the queue at JobStatus 3 until SIGKILL at **600 s** (`MachineMaxVacateTime`), or promptly with `job_max_vacate_time=5` (L2) | P (family-wide delivery U) | **`announce.py`'s SIGTERM path must bound the reap (the child already has SIGTERM from condor: wait ≤ a few s, then SIGKILL, then exit); `ServiceJob` sets `job_max_vacate_time` (e.g. 30) so a slow-stopping Triton cannot hold the slot/GPU for the site's vacate time; `stop()`/"queue empty" legs wait for the job to leave, not for `act` to return** |
| L-03 | a child left running when the top process exits (normally or on SIGTERM) is killed with the job (L2 exit-normally, exit-on-term) | U | "a service outliving its run" is prevented by condor as well; no change |
| L-04 | `condor_hold` = SIGTERM to every process at once, JobStatus 5 code 1 (L3a); release → back to idle (JobStatus 1), rescheduling time pool-dependent (not restarted within 60 s here); `NumJobStarts` trails the JobStatus it counts by seconds (L3b; L4 shows `(2, 0)` rows) | match (lag U) | read `NumJobStarts` from history only; no change |
| **L-05** | `periodic_remove = JobStatus == 5` removed held jobs **13 s** after the hold (L3c; 10 s in an earlier run), faster than `PERIODIC_EXPR_INTERVAL=60`; in a DAG it fired 14 s after the hold (D[svc-held-prm-long]) but not within 8 s (D[svc-held-prm-race]) | P | periodic_remove narrows but cannot close the DAG-end race (D-06); do not rely on it for DAG success |
| L-06 | `max_retries=2, retry_until=3`: `OnExitRemove = NumJobCompletions > JobMaxRetries \|\| ExitCode is 0 \|\| ExitCode is 3`; exit 1 ×3 starts; exit 3 once; SIGKILL retried (3 starts); idle (1) between tries (L4) | match (signal case U) | m67 no change — but see S-15 (a missing `result.pkl` holds instead of retrying) |
| L-07 | spooled: held 16 until `spool()`; stays at 4 after completion **and 10 s after `retrieve`**; outputs only via `retrieve`; removed without retrieve → outputs lost (L5a–f) | match | no change (plan retrieves, then removes) |
| L-08 | `act(Remove)` on an absent or finished cluster returns normally (L6) | U | no change |
| **L-09** | `act(Remove\|Hold, spec, reason=…)` **drops the reason** for every spec form, in 25.13.2 and the 25.14.1 wheel: no `RemoveReason` in history, `HoldReason == ''`; `condor_rm -reason` sets it (L7, `probe_surface_actreason.txt`) | **mismatch** (docstring: "a free-form justification") | **no plan text or test may read back graphed's own reason strings; `host_service`'s error names `HoldReasonCode` (and `HoldReason` only when condor set it)** |

## Q — queries
| ID | Observed | Docs | Consequence |
|---|---|---|---|
| Q-01 | a projection returns only the projected attributes that are *defined*, plus `ServerTime` (Q2); history the same (Q4) | match | code reads with `.get`; no change |
| Q-02 | `DAG_JobsHeld > 0` on a non-DAG ad matches nothing, no error (Q3) | match | no change |
| Q-03 | `history(…, match=2)` returns the most recently *recorded* matches, not ClusterId order; `since` works; positional `match` accepted (Q5, Q6) | match | no change (one proc per cluster) |

## D — DAGMan
| ID | Observed | Docs | Consequence |
|---|---|---|---|
| **D-01** | option keys are case-insensitive (`usedagdir` = `UseDagDir`); an unknown key raises `KeyError`; `from_dag` itself writes `run.dag.condor.sub` into the DAG dir at call time and, without `force`, raises `Unable to write condor_dagman output files` when that file exists (D1) | P | **per-run dir: submit with `from_dag(<abs run.dag>, {"UseDagDir": True})`; drop `force`, drop "removes a previous run's `driver.url`/`graphed-secret`/`service-svc*/`", drop the rescue-renaming rationale and `probe_r8_fromdag_force` citation; a failed `submit` after `from_dag` is retried in a new nonce dir, never the same one** |
| D-02 | fresh dir: descriptions with/without `force` differ only by `-force` in `arguments` (D1) | match | regenerate `data/from_dag-generic.txt` without `-force` |
| D-03 | `UseDagDir` from `~`: relative `driver.sub` and its relative `executable = driver.sh` resolve in the DAG dir (D[ok]) | P | no change |
| D-04 | first-run timeline: after `from_dag` `+run.dag.condor.sub`; after submit `+run.dag.dagman.log`; running `+.dagman.out .lib.out .lib.err .lock .nodes.log` + node logs/outputs; end: `.lock` gone, `+.metrics`; failure/abort `+run.dag.rescue001` (D[ok], D[retry-3]) | match | the per-run dir is DAGMan's and the nodes'; nothing to clean; no change |
| **D-05** | SERVICE running at end → removed ("…OtherJobRemoveRequirements = DAGManJobId =?= N…"), exit 0; exits 0 or 3 early → DAG exit 0 (DAG_Status 2 after exit 3); user-removed mid-run → exit 0, DAG_Status 2; **idle at end → DAG exit 1**, rescue, "Removed by DAGMan" (D[ok, svc-exit0, svc-exit3, svc-removed, svc-idle]) | **mismatch** (docs: "best-effort") | see D-06; never read `DAG_Status` (2 on success) |
| **D-06** | DAGMan exit **1** with the driver's `result.pkl` present when a SERVICE node is idle or held at the end under the default `DAGMAN_USE_STRICT=1` (D[svc-idle, svc-held, svc-userhold-end, svc-held-prm-race]); exit 0 with strictness 0 via `ConfigFile` (D[svc-held-strict0]) or **`AddToEnv: "_CONDOR_DAGMAN_USE_STRICT=0"`** for idle and held (D-S) | U | **the plan's `periodic_remove` fix covers held only, and only once it has fired; decide: (a) submit with `AddToEnv: _CONDOR_DAGMAN_USE_STRICT=0` (one option, no file; lowers all severe-warning checks for this DAG), and/or (b) `RunHandle(dag=True)` takes done/failed from the last `driver` node's history ExitCode rather than DAGMan's. (b) is site-config-proof; keep `periodic_remove` only as slot hygiene** |
| **D-07** | `DAG_NodesTotal` excludes SERVICE nodes, `DAG_JobsIdle` counts them; **all `DAG_*` ad counters refresh only every `DAGMAN_QUEUE_UPDATE_INTERVAL` = 300 s**: `JobsRunning` stayed 0 through whole runs, a held driver showed `DAG_JobsHeld=1` 293 s after the hold while a node query showed JobStatus 5 at once (D[*], D-S driver-held-counter) | **mismatch** (attribute docs say "currently"; the interval macro is undocumented) | **`RunHandle(dag=True).status()` detects `held` from a node query (`DAGManJobId == c && DAGNodeName == "driver"`, projecting `JobStatus`/`HoldReasonCode`), not `DAG_JobsHeld`; the frozen "`DAG_JobsHeld` in the projection" witness changes accordingly** |
| D-08 | `RETRY driver 2 UNLESS-EXIT 3`: [1,0] → 2 driver clusters, exit 0; [3] → 1 cluster, exit 1, rescue; [1,1,1] → 3 clusters, exit 1, rescue; each try is a new cluster (D[retry-*]) | match | `RunHandle` history lookups for the driver take the latest `driver` cluster; no other change |
| D-09 | driver held → DAGMan stays JobStatus 2 (release → NumJobStarts 2, exit 0) (D[driver-held]); driver SIGKILLed without `result.pkl` → held 12 until removed (D[driver-kill9-noresult]) | P | S-15's placeholder removes the second case; `held` via D-07's node query |
| D-10 | `condor_rm` DAGMan → nodes removed ("OtherJobRemoveRequirements…"), DAGMan history JobStatus 3, no ExitCode, DAG_Status 4, rescue written (D[dag-removed]) | match | no change |
| D-11 | node ads carry `DAGManJobId`, `DAGNodeName`; SERVICE `RemoveReason` is the OtherJobRemoveRequirements text on a normal end/removal but "Removed by DAGMan (by user …)" on DAGMan's abort path (D[svc-idle, svc-held]) | P | the B2 live witness ("RemoveReason names DAGManJobId") holds only on the success path — say so |
| D-12 | not probed (needs AFS) | D | owner site check |

## N — network and identity
| ID | Observed | Docs | Consequence |
|---|---|---|---|
| N-01 | `.machine.ad` `Machine` = the EP's name, resolves in the job (N1) | match | no change; Triton-image form is site check (1) |
| N-02 | a second job dials the first's port via `Machine` and `127.0.0.1` (shared namespace) (N2) | U | premise of the bind-scan holds on mini; per-job network namespaces at a site would change it — site check |
| N-03 | `condor_ssh_to_job` works, lands in scratch, creates `.condor_ssh_to_job_1` there (N3) | match | no change (the child is in `service/`) |
| N-04 | a job submits to the pool's schedd located by name (N4) | U | no change (m67 P5) |

## Singularity (X-08)
Configs (X[B2], X[F2], X[G], X[H]; apptainer command lines in `probe_surface_scratch_logs.txt`):
- `MY.SingularityImage` without an EP `SINGULARITY_JOB` expression is inert: the job runs on the host (X[B2]). Which
  image a site runs is site config, as the lpc/lxplus profiles already assume.
- The starter runs `singularity exec -S /tmp -S /var/tmp -W <scratch> --pwd <target> -B <dir_N>[:<target-root>] --home
  <scratch> -C <image>`: MOUNT_UNDER_SCRATCH becomes `-S` scratch mounts, so an input `tmp` does **not** merge into
  `/tmp` there (X[G,H/singall]) while condor/apptainer add `tmp/`, `var_tmp/`, `scratch/`, `.docker_sock` to scratch.
- In-container scratch path: `SINGULARITY_TARGET_DIR` unset → the host path; `/srv` + nested scratch → `/srv/scratch`
  (X[H]); `/srv` + non-nested → `/srv` (X[F2]; = lxplus in `m67-driverless.txt`). `_CONDOR_SCRATCH_DIR`,
  `_CONDOR_JOB_AD`, `_CONDOR_MACHINE_AD`, `X509_USER_PROXY` are rewritten to the in-container paths and readable.
- `PATH` is the image's (`/usr/local/sbin:…:/bin`), `HOME` = scratch, `TMPDIR=/tmp`; the hostname stayed the EP's
  (no UTS namespace here; lxplus showed the node FQDN too).
- Consequence: nothing in `announce.py`/`service.sh` may hard-code a scratch path or `/srv`; derive from cwd /
  `$_CONDOR_SCRATCH_DIR`. The S-05 PATH/`sys.executable` hazard is a bare-EP one (image-less recipes on `generic`/lpc);
  under Apptainer bare names resolve through the image's PATH.

## Mismatches and undocumented behaviours found
Mismatches (docs say one thing, 25.13.2/25.14.1 does another):
1. `STARTER_NESTED_SCRATCH` (`configuration/global.rst`): ".job.ad and other metadata" go to `user/` — they are in scratch (X-02).
2. `file-transfer.rst`: zero-length output/error are created at submit — not by `htcondor2.Schedd.submit` (S-04).
3. `htcondor2.Schedd.act(reason=)`: the reason is dropped (no `RemoveReason`, empty `HoldReason`), wheel too (L-09).
4. SERVICE node "best-effort" (`dagman-advance-functionality.rst`): an idle or held SERVICE node at DAG end fails the DAG under the default strictness (D-05/D-06).
5. `DAG_Jobs*` "currently …" (`job-classad-attributes.rst`): refreshed only every `DAGMAN_QUEUE_UPDATE_INTERVAL` (300 s), an undocumented macro (D-07).

Undocumented behaviours graphed hits: no `PATH` in a job's env and `sys.executable == ''` for a bare `python3` (S-05);
the hold on directory symlinks (S-08); which of two same-named inputs wins, executable over input, and user files
replacing `.job.ad`/`.machine.ad`/`_condor_stdout` (S-10–S-12); an input `tmp` merging into `/tmp` (X-06); the
Apptainer-only scratch entries (X-02); `TMPDIR`/`HOME` values (X-07); a SendCredential job idling for ever without
a credd (X-04); family-wide SIGTERM on remove/hold and orphan kill at exit (L-02, L-03); `periodic_remove` firing in
~10 s rather than the 60 s interval (L-05); `act` on absent jobs not raising (L-08); `DAG_NodesTotal` excluding and
`DAG_JobsIdle` counting SERVICE nodes (D-07); SERVICE `RemoveReason` wording by path (D-11); shared network
namespace between jobs on one EP (N-02).

## Plan consequences (one line each)
Each line: what the plan (with the two redesigns) must state or change. "Refuse" = in `ServiceJob`'s constructor
(so B2's `files()` too), before any file or bindings call.
1. **DAG outcome (D-05/D-06):** an idle or held SERVICE node when the driver ends turns DAGMan's exit into 1 although `result.pkl` is good; `periodic_remove` covers only an already-removed held node. Submit with `AddToEnv: "_CONDOR_DAGMAN_USE_STRICT=0"` and have `RunHandle(dag=True)` decide done/failed from the last `driver` node's ExitCode (history), not DAGMan's.
2. **Held detection (D-07):** `DAG_JobsHeld` lags up to 300 s; `RunHandle(dag=True).status()` queries the driver node (`DAGManJobId == c && DAGNodeName == "driver"`) for JobStatus 5; the frozen "projects `DAG_JobsHeld`" witness becomes "queries the driver node".
3. **Missing outputs hold (S-15, D-09):** `driver.sh` writes placeholder `result.pkl`/`driver.log` before exec'ing the interpreter so a killed driver is a failed try (RETRY / `max_retries`), never a node held for ever; `RunHandle.result()` names the placeholder as "driver died before writing a result". Same for any future `transfer_output_files` entry.
4. **`from_dag` in a per-run dir (D-01/D-02):** `from_dag(<abs run.dag>, {"UseDagDir": True})` — no `force`, no pre-submit cleanup, no rescue-rename rationale; a failed submit retries in a new nonce dir; regenerate `data/from_dag-generic.txt`.
5. **Per-run dir creation (S-03):** make `log_dir/<nonce>/` and every `initialdir` before `submit` (the bindings raise otherwise); that raise is a `host_service` failure path.
6. **SIGTERM/vacate (L-02):** `announce.py` bounds its reap on SIGTERM (child already signalled by condor; wait ≤ a few s, SIGKILL, exit); `ServiceJob` sets `job_max_vacate_time` (e.g. 30) so a stuck service cannot hold the GPU for the EP's `MachineMaxVacateTime` (600 s default); "queue empty" legs wait for the job to leave.
7. **Interpreter/argv resolution (S-05):** `announce.py` never uses `sys.executable`; only a `{python}` containing a path separator is made absolute; a bare name is resolved with `shutil.which` (defpath on a bare EP) or passed bare; docs: a recipe's argv[0] is absolute or on `/bin:/usr/bin` outside a container.
8. **Directory symlinks (S-08):** refuse an input that is, or contains, a symlink to a directory, naming it.
9. **Commas (S-09):** refuse an input path (and a `user_modules` path) containing `,`.
10. **Reserved names (S-10–S-12, X-02, X-05):** keep the set, justify `.`/`_condor_` by identity spoofing (`.machine.ad`), add `scratch`, `var_tmp`, `dev`, state that the list assumes default MOUNT_UNDER_SCRATCH, and add `announce.py`'s runtime guard (an input whose scratch entry is a mount point → exit 3 naming it).
11. **Isolation (X-02, S-14):** condor's scratch entries are version/config dependent and open-ended; the child's `service/` dir holding only moved inputs is the mechanism (condor cannot land absolute inputs there; do not use `preserve_relative_paths`).
12. **Reasons (L-09):** no plan text or test reads back graphed's own `reason=`; errors name `HoldReasonCode` (+ `HoldReason` when condor set one).
13. **SERVICE RemoveReason witness (D-11):** "names `DAGManJobId`" only on the success path; say so in the B2 live row.
14. **`DAG_Status` (D-05):** 2 on a successful DAG whose SERVICE node failed/was removed — never read it.
15. **`service.out` may not exist (S-04):** error paths name `service-<key>/` without assuming the file.
16. **Paths inside containers (X-08):** derive every job-side path from cwd/`$_CONDOR_SCRATCH_DIR` (nested → `/srv/scratch`, flat → `/srv`).
17. **SendCredential (X-04):** on a pool without a credmon the job idles silently for ever; never put it in `generic`; the attached drop stands.
No change (probes match the plan's assumptions): S-01, S-02, S-06, S-07, S-13, S-16–S-18, X-01, X-03, L-01, L-03, L-04, L-06–L-08, Q-01–Q-03, D-03, D-04, D-08, D-10, N-01, N-03, N-04.

## Config values the plan must not assume, and owner site checks
Knobs varied on minicondor whose value the plan must **not** assume (it cannot read the EP/schedd config):
`MOUNT_UNDER_SCRATCH` (X-05), `STARTER_NESTED_SCRATCH` (X-01/X-02), `SINGULARITY_JOB`/`SINGULARITY_TARGET_DIR`
(X-08), `DAGMAN_USE_STRICT` (D-06 — override it per DAG instead), `DAGMAN_QUEUE_UPDATE_INTERVAL` (D-07),
`PERIODIC_EXPR_INTERVAL` (L-05), `MachineMaxVacateTime` (L-02 — bound it per job instead), credd/credmon presence
(X-04), per-job network namespaces (N-02).

Owner site checks (need a live site; fold into m68b site checks (1)/(2)):
- (1) lxplus Triton `ServiceJob`: `ls -A` of scratch and `service/` (expect `/srv` layout, ticket cache, Apptainer
  entries), `echo $PATH $TMPDIR $HOME`, `python3 -c 'import sys; print(repr(sys.executable))'` inside the image,
  `condor_status -af MachineMaxVacateTime` for a GPU slot, and whether a removed Triton leaves the slot within
  `job_max_vacate_time`.
- (2) lxplus DAG: `condor_config_val -schedd DAGMAN_USE_STRICT DAGMAN_QUEUE_UPDATE_INTERVAL` (or the DAG's
  `dagman.out` "DAGMAN_USE_STRICT setting"), that `AddToEnv: _CONDOR_DAGMAN_USE_STRICT=0` is accepted, the SERVICE
  node reading `dag_dir` on AFS (DAGMan itself gets an AFS token, no Kerberos cache: `file-and-cred-transfer.rst`),
  `klist`/`$KRB5CCNAME` in the node.
- lpc: `x509up_u<uid>` landing name and `X509_USER_PROXY` in a job (X-03 on the real proxy), EP `MOUNT_UNDER_SCRATCH`
  effect (`ls -A` of scratch).
- Both: whether two jobs on one node share ports (N-02), and `act(reason=)` on the site schedd (L-09).

## Superseded consequences and added rows (appended by the m68b planner, round 12)
The plan's round-10/11 design (the service child's inputs reach the job as one submit-side `service/` directory of
file symlinks, transferred once; nothing is moved in the job) replaces these consequence lines, which describe the
earlier in-job move: S-14's "keep `announce.py` moving them", X-05's reserved set and "guard … before moving it",
X-06's "confirms reserving `tmp`/`var`", and plan consequences 10 (reserved names) and 11's "moved inputs". Under the
plan, no scratch name is reserved and no user input is listed at scratch top level; X-02/X-05/X-06 remain the
reason for that design. Consequence 9 applies to the listed paths (the plan lists every `ServiceJob` entry relative
to `initialdir`), not to names inside `service/` (`probes/m68b/probe_r17_b1_comma.txt`).

| ID | Behaviour | Observed | Probe |
|---|---|---|---|
| S-19 | a submit-side directory whose files are symlinks (dirs real), listed once, lands with its link names, contents followed, file modes kept, spooled and not; an input named like a job file or `.machine.ad` stays inside it | match (S-07 extended) | `probes/m68b/probe_input_dir.txt` (mirror-plain, mirror-spool), `probe_r17_b1_input_exec.txt`, `probe_r18_b1_envlink.txt` (a relative top-level file-symlink entry, spooled and not) |
| D-08a | `RETRY driver 2 UNLESS-EXIT 3` with a driver killed by SIGKILL, or failing to exec (rc 127), while a placeholder `result.pkl` exists: retried three times, never held, DAGMan exits 1 | match | `probes/m68b/probe_r17_b2_sigretry.txt` |
| Q-04 | a removed running job's history ad carries `JobBatchName`, `JobCurrentStartDate` and `EnteredCurrentStatus` (the removal second, truncated, JobStatus 3); a time `t` taken in the job lies between them at whole-second resolution: `JobCurrentStartDate ≤ t` and `int(t) ≤ EnteredCurrentStatus` (a removal in `t`'s own second stamps `int(t) < t`) | match | `probes/m68b/probe_r19_b1_history_times.txt`, `probe_r24r_b1_history_seconds.txt` |
