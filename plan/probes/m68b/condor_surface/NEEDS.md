# m68b — what graphed needs from HTCondor (the surface)

Scope: every HTCondor behaviour §3.3 B1/B2 (with the owner's two redesigns assumed: a fresh run directory
`log_dir/<run_nonce>/` per run, and the service child in an isolated directory holding only its declared inputs)
and the m66/m67 code it builds on (`htcondor_backend/{launch,driverless,driver,sites}.py`) relies on.
Docs = the HTCondor manual sources (`github.com/htcondor/htcondor` `docs/`, fetched 2026-09-29; paths below are
under `docs/`) and the `htcondor2` 25.13.2 docstrings. JDL = `man-pages/htcondor-jdl.rst` (the submit-command
reference). Status: **D** documented, **P** partially (the case graphed hits is not stated, or the docs disagree
with each other), **U** undocumented. Probe ids are the `<ID>` prefixes in `probe_surface_<area>.txt`
(S submit, X scratch, L lifecycle incl. `probe_surface_actreason.txt`, Q query, D dagman incl. `probe_surface_dagman_strict.txt` (D-S), N network). Pool: `htcondor/mini` 25.13.2.

## S — submit description semantics
| ID | Behaviour relied on | Why (plan) | Docs | St | Probe |
|---|---|---|---|---|---|
| S-01 | A relative `executable` resolves against the submitter's cwd, never `initialdir` | B1 `executable=<initialdir>/service.sh` absolute; m66 `CondorPilots.start` | JDL `executable`, `initialdir` ("not relative to initialdir"); `users-manual/file-transfer.rst` Example 3 | D | S1a, S1b |
| S-02 | The executable lands in scratch under its own basename; `arguments` reach argv verbatim | `service.sh` execs `announce.py service.json` | `file-transfer.rst` "Specifying What Files to Transfer" (placement only; name U) | P | S1b, S2 |
| S-03 | `initialdir` must exist when `schedd.submit` runs | per-run dir `log_dir/<nonce>/` (and `service-<key>/`) created before submit | `codes-other-values/hold-table.rst` code 14 (execute side only) | P | S3a |
| S-04 | `output`/`error`/`log` relative to `initialdir`; missing subdirs created; what exists right after submit | `service.{out,err,log}`, `driver.*`; `RunHandle.logs()` | JDL `error`/`output` ("create directories as necessary"); `file-transfer.rst` ("zero-length files are created" at submit) | D | S3b–S3d |
| S-05 | The job environment without `getenv`: which variables exist (PATH? TMPDIR? HOME?) | `service.sh` `command -v python3`; `announce.py` `Popen` of `{python}`/argv[0]; `sys.executable` in the job | `users-manual/env-of-job.rst` "Environment Variables", "Extra Environment Variables" (PATH not mentioned) | P | S4a, S4b, S4d, S4e |
| S-06 | `environment`/`getenv` syntax and precedence | m67 driver job keys; ServiceJob carries env in `service.json` instead | JDL `environment`, `getenv` | D | S4c |
| S-07 | `transfer_input_files`: a file/dir lands under its basename; a trailing `/` sends contents; absolute paths; spaces | recipe `inputs` made absolute with `abspath` (drops `/`); `models/` lands as `models` | JDL `transfer_input_files`; `file-transfer.rst` "File Paths for File Transfer" | D | S5 |
| S-08 | Symlinks: to a file → copied as a file; to a directory (top level or inside a transferred dir) → not supported | model repositories are directories that may hold symlinks | JDL `transfer_input_files` ("Transfer of symbolic links to directories is not currently supported") — outcome (hold) U | P | S5, S5a, S5b |
| S-09 | The list is comma-separated: a path with a comma splits | inputs joined with `,` | JDL `transfer_input_files` ("comma-delimited") | D | S5c |
| S-10 | Two inputs with one basename: which wins, is it an error | constructor refuses duplicate basenames | `file-transfer.rst` ("inputs must be uniquely named to avoid collision"; outcome U) | P | S6a |
| S-11 | An input with the executable's basename | reserved names `service.sh` etc. | — | U | S6b |
| S-12 | An input named like condor's own scratch entries (`.job.ad`, `.machine.ad`, `_condor_stdout`, `tmp`, `var`) | reserved `.`/`_condor_`/`tmp`/`var`; `machine_host()` reads `.machine.ad` | — | U | S6c, X (tmpin) |
| S-13 | A missing input holds the job (13) at transfer, before it runs | DAG refuses inputs outside `job_root`; `announce.py` skips absent inputs | `hold-table.rst` code 13; `hold-reason-codes.rst` | D | S7 |
| S-14 | `preserve_relative_paths=True` lands relative inputs under their relative path (a way to land inputs straight into `service/`) | isolated child dir (redesign 2) | JDL `preserve_relative_paths`; `file-transfer.rst` | D | S8 |
| S-15 | `transfer_output_files` naming a missing file holds the job (12) — for every exit code, signal and `when_to_transfer_output`; `ON_SUCCESS` avoids the hold but returns nothing on failure | driver `transfer_output_files=result.pkl,driver.log`; `RunHandle` held; DAG node held | JDL `when_to_transfer_output` ("In all three cases, the job will go on hold…"; ON_SUCCESS "prevents the job from going on hold"); `file-transfer.rst` | D | S9 |
| S-16 | `MY.X = "\"v\""` makes a string attribute; unquoted is an expression | `MY.SingularityImage` quoted; `MY.SendCredential = True` | JDL "MY.<attribute>" | D | S10 |
| S-17 | `request_cpus/memory/gpus` rendering (float strings, `request_gpus=0`) | `str(int(v))` from `Launch.resources`; no `request_gpus` at 0 | JDL `request_gpus` ("If not specified, no GPUs") | P | S11 |
| S-18 | `request_gpus=1` matches a GPU slot, `AssignedGPUs` + `CUDA_VISIBLE_DEVICES` set; an unmatchable request stays idle (never holds) | B1 timeout leg (2 GPUs); B2 live GPU leg | JDL `request_gpus`; `env-of-job.rst` CUDA_VISIBLE_DEVICES | D (idle-forever P) | S12a, S12b |

## X — the execute scratch directory (EP-configuration dependent)
| ID | Behaviour relied on | Why (plan) | Docs | St | Probe |
|---|---|---|---|---|---|
| X-01 | The job starts in scratch = `$_CONDOR_SCRATCH_DIR`; its layout (nested `…/dir_N/scratch` vs `…/dir_N`) | `announce.py` makes `service/` in cwd | `env-of-job.rst` `_CONDOR_SCRATCH_DIR`; `admin-manual/configuration/global.rst` `STARTER_NESTED_SCRATCH` | D | X[*] pwd lines |
| X-02 | What condor itself puts in scratch: `.job.ad`, `.machine.ad`, `_condor_stdout/err`, `.chirp.config`, executable | the child must not serve them (isolated dir) | `env-of-job.rst` (`_CONDOR_JOB_AD`/`_CONDOR_MACHINE_AD` "in the job's scratch directory"); `global.rst` `STARTER_NESTED_SCRATCH` (".job.ad and other metadata" go to `user/`) — the two disagree | P | X[A,B,C,F] ls |
| X-03 | An x509 proxy lands in scratch under its source basename and `X509_USER_PROXY` names it | lpc `x509userproxy`; reserved `x509up_u` prefix | `env-of-job.rst` `X509_USER_PROXY` (location U) | P | X[*/proxy] |
| X-04 | `SendCredential`: Kerberos cache written into scratch, `KRB5CCNAME` set; needs a credd/credmon | lxplus profile; watch-mode node keeps it | `admin-manual/file-and-cred-transfer.rst` "Credential Propagation by Job Universe" (vanilla: "written in the job's scratch directory") | D | X[A,C/cred]; `probe_surface_scratch_logs.txt`; lxplus `m67-driverless.txt` |
| X-05 | `MOUNT_UNDER_SCRATCH` creates `tmp/`, `var/tmp/` (+ any listed dir, e.g. `dev/shm`) in scratch and bind-mounts them; nothing when the starter cannot mount or the list is empty | reserved `tmp`/`var`; what the child's cwd could expose | `admin-manual/configuration/startd.rst` `MOUNT_UNDER_SCRATCH` | D (unmountable case U) | X[A,C,D,E] |
| X-06 | An input dir named `tmp` merges into the job's `/tmp` under MOUNT_UNDER_SCRATCH | reserved `tmp` | — | U | X[C,D,G/tmpin,singall] |
| X-07 | `TMPDIR`/`TMP`/`TEMP` point into scratch | temp files a service makes land beside (not in) `service/` | — | U | S4d, X TMPDIR lines |
| X-08 | Under Singularity/Apptainer: scratch path inside the container (`SINGULARITY_TARGET_DIR`), `_CONDOR_*_AD` paths valid inside, `MOUNT_UNDER_SCRATCH` as `-S`; `MY.SingularityImage` has effect only where the EP config uses it | lxplus/lpc images; `announce.py` in the Triton image | `admin-manual/configuration/starter.rst` `SINGULARITY_TARGET_DIR`; `admin-manual/ep-policy-configuration.rst` (Singularity example) | P | X[B2,F2,G,H/sing*]; `probe_surface_scratch_logs.txt` |

## L — job lifecycle
| ID | Behaviour relied on | Why (plan) | Docs | St | Probe |
|---|---|---|---|---|---|
| L-01 | JobStatus 1→2→4, an unspooled job leaves the queue at completion and is in history at once | `RunHandle._poll`, `host_service` "gone" branch reads history | `users-manual/managing-a-job.rst` "The Job Lifecycle"; `codes-other-values/job-status-codes.rst` | D (hand-off timing U) | L1 |
| L-02 | `condor_rm` of a running job: SIGTERM to the whole process family at once; SIGKILL after the max vacate time; X state until then | `ServiceJob.stop()`; `announce.py` SIGTERM handler reaps the child | `admin-manual/configuration/schedd.rst` `GRACEFULLY_REMOVE_JOBS`; `startd.rst` `MachineMaxVacateTime`; JDL `kill_sig`, `job_max_vacate_time` (family-wide delivery U) | P | L2 |
| L-03 | A child left running when the job's top process exits is killed | "a service outliving its run" | — (procd) | U | L2 exit-normally, exit-on-term |
| L-04 | `condor_hold` kills a running job; release restarts it from scratch (`NumJobStarts`+1) | held status paths | `man-pages/condor_hold.rst` | D | L3a, L3b |
| L-05 | `periodic_remove`/`periodic_hold` are evaluated only every `PERIODIC_EXPR_INTERVAL` (60 s default) | `svc<i>.sub` `periodic_remove = JobStatus == 5` | JDL `periodic_remove`; `configuration/schedd.rst` `PERIODIC_EXPR_INTERVAL` | D | L3c, L3d |
| L-06 | `max_retries`+`retry_until=3`: generated `OnExitRemove`; exit 1 retried, 3 not; a signal death retried; idle between tries | m67 plain driver job (D6) | JDL `max_retries`, `retry_until` | D (signal case U) | L4 |
| L-07 | Spooled jobs: held (16) until `spool()`; stay at JobStatus 4 until retrieved/removed; `retrieve` lands outputs in `initialdir`; removal without retrieve loses them | lpc/lxplus `spool=True`; `CondorPilots.stop`, spooled `ServiceJob.stop` | JDL `leave_in_queue`; `htcondor2.Schedd.submit/spool/retrieve` docstrings | D | L5a–L5f |
| L-08 | `act(Remove)` on a job not in the queue does not raise | `release_service`, cleanup paths | `htcondor2.Schedd.act` docstring ("currently undocumented" result ad) | U | L6 |
| L-09 | `act(..., reason=)` reaches `RemoveReason`/`HoldReason` | `host_service` RuntimeError names `HoldReason`; RunHandle/stop reasons | `htcondor2.Schedd.act` docstring (`reason` "a free-form justification") | D | L7 |

## Q — schedd queries
| ID | Behaviour relied on | Why (plan) | Docs | St | Probe |
|---|---|---|---|---|---|
| Q-01 | A projection returns only the projected attributes that are defined (plus `ServerTime`) | `RunHandle` projects `DAG_JobsHeld`; `STATUS_ATTRS` | `htcondor2.Schedd.query` ("These attributes will be returned… (Others may be as well.)") | D | Q1, Q2 |
| Q-02 | An undefined attribute in a constraint matches nothing and does not raise | `DAG_JobsHeld > 0` on a non-DAG ad | `classads/` UNDEFINED semantics | D | Q3 |
| Q-03 | `history(constraint, projection, match=1)` returns the most recently *recorded* match; `since` | `schedd.history(..., match=1)` for a gone job | `htcondor2.Schedd.history` docstring | D | Q4–Q6 |

## D — DAGMan (B2)
| ID | Behaviour relied on | Why (plan) | Docs | St | Probe |
|---|---|---|---|---|---|
| D-01 | `from_dag` option names (case, aliases, unknown keys) and that it writes `<dag>.condor.sub` into the DAG dir at call time, refusing an existing one without `force` | `from_dag(<abs run.dag>, {"usedagdir": True, "force": True})` | `htcondor2.Submit.from_dag`/`from_dag_options`; `man-pages/condor_submit_dag.rst` `-f/-force` | P | D1 |
| D-02 | In a fresh directory `force` changes nothing but the `-force` flag | redesign 1: no reuse, so `force` may go | `condor_submit_dag.rst` `-force` | D | D1 (fresh with/without) |
| D-03 | `UseDagDir`: node `.sub` files and a relative node `executable` resolve against the DAG dir, whatever the submitter's cwd | `run.dag` names node files relative | `condor_submit_dag.rst` `-UseDagDir` ("execute each DAG from their respective directories") | P | D[ok] (relative `driver.sh`); r8 D1–D2 |
| D-04 | First-run DAG dir contents over time (`.condor.sub`, `.dagman.log`, `.lib.out/err`, `.dagman.out`, `.nodes.log`, `.metrics`, `.lock` while running, `.rescueNNN` on failure) | per-run dir contents; nothing else writes there | `automated-workflows/dagman-reference.rst` "Produced Files" | D | D[*] files lines |
| D-05 | A SERVICE node is submitted with the DAG and removed when the DAG ends; the DAG result ignores its exit (0 or nonzero), an idle one, a user-removed one | SERVICE svc<i>; "DAGMan removes its SERVICE nodes" | `dagman-advance-functionality.rst` "SERVICE Node" (removed at end; "best-effort basis") | P | D[ok, svc-exit0, svc-exit3, svc-idle, svc-removed] |
| D-06 | What a SERVICE node that is *idle or held* when the driver finishes does to the DAG's exit, per `DAGMAN_USE_STRICT`, and whether `periodic_remove` or a per-DAG strictness override prevents it | `periodic_remove = JobStatus == 5` in `svc<i>.sub` | `admin-manual/configuration/dagman.rst` `DAGMAN_USE_STRICT` (warnings→errors; this warning U); SERVICE "best-effort" | U | D[svc-idle, svc-held, svc-held-strict0, svc-held-prm-race, svc-held-prm-long, svc-userhold-end]; D-S (strict via ConfigFile/AddToEnv) |
| D-07 | `DAG_Jobs*`/`DAG_Nodes*` counters: which nodes they count (SERVICE?) and how soon they reflect a node's state | `RunHandle(dag=True)` `held` iff `DAG_JobsHeld > 0` | `classad-attributes/job-classad-attributes.rst` `DAG_JobsHeld` ("job processes currently held within the DAG") | P | D[*] timelines; D-S driver-held-counter |
| D-08 | `RETRY driver 2 UNLESS-EXIT 3`: 1→retry, 3→no retry, exhausted→DAG fails; rescue file written; DAGMan `ExitCode` 0/1 | D6 retry owner; `RunHandle` done/failed | `dagman-completion.rst` "Retrying Failed Nodes"; `man-pages/condor_dagman.rst` "Exit Status" | D | D[retry-1-0, retry-3, retry-exhausted] |
| D-09 | A held driver node leaves DAGMan running (JobStatus 2) with `DAG_JobsHeld = 1` for ever; release resumes | `RunHandle` `held` | `DAG_JobsHeld` def; hold not a node failure (U) | P | D[driver-held, driver-kill9-noresult] |
| D-10 | `condor_rm` of DAGMan removes the node jobs; DAGMan ad JobStatus 3 | `RunHandle.remove()`, `removed` | `configuration/dagman.rst` `DAGMAN_REMOVE_NODE_JOBS`; `job-classad-attributes.rst` `OtherJobRemoveRequirements` | D | D[dag-removed] |
| D-11 | Node ads carry `DAGManJobId`, `DAGNodeName`, `DAGManNodeRetry`; `RemoveReason` of a SERVICE node removed at DAG end | B2 live leg ("RemoveReason names DAGManJobId") | `dagman-reference.rst` "Job ClassAd Attributes" (RemoveReason text U) | P | D[*] node lines |
| D-12 | DAGMan (scheduler universe) gets an AFS token but no Kerberos cache | the DAG dir on AFS (lxplus) | `file-and-cred-transfer.rst` "Scheduler universe jobs" | D | site check |

## N — networking and identity from jobs
| ID | Behaviour relied on | Why (plan) | Docs | St | Probe |
|---|---|---|---|---|---|
| N-01 | `.machine.ad` `Machine` is the EP's FQDN, resolvable in the job; a container's own hostname may differ | `host_identity()`, announce identity, driver task server host | `classad-attributes/machine-classad-attributes.rst` `Machine`; `env-of-job.rst` `_CONDOR_MACHINE_AD` | D (resolvability U) | N1; lxplus `m67-driverless.txt` |
| N-02 | Jobs on one EP share the network namespace: a port bound by one is taken for the others; another job dials it by `Machine` | `announce.py` bind-scan over `worker_ports`; SERVICE node dials the driver | — (site/EP dependent) | U | N2; `probe_service_job.txt` A; `probe_r9_timewait.txt` |
| N-03 | `condor_ssh_to_job` into a running job | site check (2) gets the SERVICE node's shell | `man-pages/condor_ssh_to_job.rst` | D | N3 |
| N-04 | A job submits to its pool's schedd found by name through the collector | m67 `pilots="condor"`, `schedd_locate` | — (P5 at lxplus) | U | N4 |
