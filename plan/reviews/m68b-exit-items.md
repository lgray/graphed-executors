# m68b exit items

## decisions
Planner decisions on ambiguities in §3.3 (and the D3/D10/§6–§9 lines m68b binds), one line of reason each.

- `SiteProfile.job_root: str | None = None` (lpc `None`, lxplus `"/afs"`, generic `"/"`) is the one source; `_SELF_SUBMIT_ROOT` and `DagmanProfile` go. Reason: owner's choice (notes-m68b.md); both questions are "which tree do the schedd and every job read directly".
- "Under the root" is `root == "/" or Path(abspath(p)).is_relative_to(root)`. Reason: `PureWindowsPath("C:/x").is_relative_to("/")` is False and m67's all-OS generic self-submit case must stay green (probe_code_premises W).
- `job_root=None` refuses `pilots="condor"` (fail closed), checked after `jobs_can_submit` and `worker_ports`. Reason: today a profile outside the dict self-submits with no check (probe_code_premises S); the order keeps m67's refusal messages.
- No per-site DAGMan keys: stock `Submit.from_dag`, never spooled. Reason: the DAG dir lies under `job_root`, which the schedd reads; the LPC values that motivated `DagmanProfile` belong to a site that is refused, and their transcript is absent from this checkout; lxplus acceptance is site check (2).
- The service port is chosen in the job by `announce.py` from the row's `worker_ports`. Reason: a port picked on the driver can be taken on a shared node (r7 M12); probe_service_job A.
- `announce.py` owns the child (bind-scan, Popen, self-check, announce, reap), not `service.sh`. Reason: it must see a child that dies on a port taken after the scan and move on, as m68a's managed rule does.
- The self-check dials `identity:port`. Reason: that is the endpoint announced, so an unresolvable name fails in the job (exit 3, seen by `host_service`) instead of at the first task.
- `service.json` carries argv/env/check/ports/key/url/watch/python/timeout_s/lease_s; `arguments="service.json"`. Reason: arbitrary argv does not survive condor argument quoting, and neither secret nor url belongs in the ad.
- Recipe `inputs` are made absolute with `os.path.abspath` (drops a trailing `/`). Reason: condor transfers a directory's contents for a trailing separator (probe_service_job C), so every input lands under its basename.
- `env.tgz` for a ServiceJob is the pilots' existing tarball, named by path. Reason: tarring the venv twice per run is waste.
- `{python}`/interpreter = `CondorPilots._stage`'s for image-less recipes, `python3` for imaged. Reason: the old text said "the image's python3 otherwise", which contradicts `_stage` on non-`ship_env` sites (`sys.executable`).
- `announce.py` must parse as python 3.9. Reason: it runs under the job's `python3` (minicondor 3.9 measured; Triton image version is site check (1)).
- `/announce` routes before `pickle.loads`; three fields, integer port, else 400. Reason: today every signed body is unpickled first (probe_code_premises T); r7 X2.
- `wait_announce(key, timeout) -> (host:port, identity) | None`, popping. Reason: the identity must reach the probe (r7 M11); `None` lets `host_service` poll in slices.
- `host_service` polls `job.alive()` between `POLL_S` slices and fails fast on a completed/held job; timeout → `TimeoutError`, dead/held → `RuntimeError`, each after removing the job. Reason: r7 M13; a job that exited or is held never announces, so waiting `timeout_s` (600 s default) is pure loss.
- `ServiceJob.stop()` removes at once. Reason: a service never exits by itself, so `CondorPilots.stop`'s 20 s drain (probe_code_premises P) is dead time.
- Attached `announce.py` re-POSTs its announce every `POLL_S` and self-terminates on 403 or no answer for `lease_s`. Reason: without it a crashed driver leaves a GPU service running to its walltime; pilots already follow this rule.
- DAG mode re-announces whenever the (`driver.url`, `graphed-secret`) pair changes, secret written before url, each by `os.replace`. Reason: the retried driver rebound the same url in the probe (probe_dag_service R), so url-only change detection (r7 M14's wording) would miss it.
- `announce_only` = specs with a `launch`, no `services=` endpoint, and `image` or `gpus > 0`. Reason: a driver job's `service_hosts` is `("driver",)` (§3.1), so exactly those cannot be hosted in the job.
- The in-job backend gets `host_service`/`release_service` (announce wait, no submit) iff `announce_only` is non-empty. Reason: DAG names then resolve by §3.1's leg 3 with the announced identity (m68a exit item) without touching §3.1.
- In a DAG, the driver's task server binds the slot's `Machine` on `worker_ports` even with `pilots="local"`. Reason: the SERVICE node dials it from another node; `127.0.0.1` would not reach.
- `RunHandle(..., dag: bool = False)`: DAGMan exit 0/1 → done/failed; `result()` never retrieves. Reason: probe_dag_service R/X exit codes; the DAG is unspooled, `result.pkl` lands in the DAG dir.
- Live tests: (a)/(b) on a generic copy with `service_ports=None`; the DAG leg with a GPU `http_server` on a pool with one simulated GPU; the timeout leg asks for 2 GPUs. Reason: r7 M15 for (a); in a driver job only a GPU/imaged recipe is DAG-hosted, and minicondor needs `sim_gpu.config` to match one (probe_sim_gpu).
- lxplus run: `model_repository="models"`. Reason: r7 M17 (probe_service_job C).
- LPC/lxplus premises that need a live site are two owner-run site checks after CI is green, not freeze blockers. Reason: owner instruction (sites unreachable from the planning session).

## r8 exit items
Wording, notes and small implementer constraints from review r8 (`plan-services-m68b-r8.md`). None of them makes a round unclean.

- `ServiceJob.stop()` also unlinks its `service-<key>/graphed-secret`, as `CondorPilots.stop` unlinks the pilots' secret (`launch.py`, the last line of `stop`). The file is 0600 and belongs to a dead server's secret, so this is hygiene only.
- "Its removal registered when `schedd.submit` returns" (L479, D10) sits inside `launcher._submit`, which submits and then spools in one call (`launch.py:226-230`). The `ServiceJob` reuses whatever pre-spool registration hook m68a gives `CondorPilots` and adds none of its own.
- On a non-spooled pool a completed `ServiceJob` leaves the queue at once. `host_service`'s "gone" branch therefore reads `JobStatus`/`ExitCode` from `schedd.history(..., match=1)`, as `RunHandle._poll` does.
- `announce.py` is stdlib-only and cannot import `server.POLL_S`. Carry the beat interval in `service.json` (for example `beat_s`) or copy the constant with a comment. The plan should say which.
- §6: `sim_gpu.config`'s two lines must be in the pool config before `condor` starts in `test-htcondor`'s pool step, or be followed by `condor_restart -daemon startd`, as `probe_sim_gpu.py` does.
- Docs (`htcondor.rst` "Cluster-hosted services"): a recipe `inputs` directory lands under its basename, so `recipes.triton`'s `model_repository` must be a bare name relative to the driver's cwd (for example `"models"`, not `"a/models"`).
- Docs: a SERVICE node that dies before announcing costs the DAG up to 3 × `timeout_s` (the driver times out, exits 1, and `RETRY` runs it twice more) before it fails. The in-job backend does not query the schedd.
- Note: `announce_only` ignores leg 2. A site row with both a `services` entry for a kind and a `job_root` would submit a SERVICE node that goes unused whenever the site endpoint passes. No row has both today (lxplus and generic `services={}`, lpc `job_root=None`).
- Evidence added by r8: `probes/m68b/probe_r8_paths.{py,txt}` (relative `executable`; `from_dag` cwd), `probe_r8_fromdag_force.txt` and `probe_r8_announce_loop.txt`. `probe_service_job` and `probe_dag_service` were re-run on `htcondor/mini` 25.13.2 and reproduce.

## decisions (round 2)
- `ServiceJob` `executable` is `<initialdir>/service.sh`, absolute. Reason: a relative executable resolves against the submitter's cwd (probe_r8_paths E), as `CondorPilots.start` already handles.
- DAG submitted with `from_dag(<abs run.dag>, {"usedagdir": True, "force": True})`, node files relative in `run.dag`. Reason: usedagdir frees the submit from the process cwd (no `os.chdir`, which is process-global); force is needed anyway for a reused `log_dir` and renames a stale rescue DAG so the new DAG runs from the start (probe_dag_service U, probe_r8_fromdag_force).
- A reused DAG `log_dir` is accepted, not refused, with a previous `driver.url`/`graphed-secret` removed before submit. Reason: m67 allows reuse; stale rendezvous files would only draw announces to a dead server.
- DAG mode refuses `user_modules` and `announce_only` recipe inputs outside `job_root`; nothing is copied. Reason: unspooled nodes read them from the schedd side, an unreadable one holds its node for ever; a model repository can be large to copy.
- `announce.py` start: `timeout_s` is the whole start's budget; a child exit moves on only if its port is taken, else exit 3 at once naming the returncode. Reason: bounded start (probe_announce_rules L1–L3); a bad model must not be retried per port on a GPU.
- Attached orphan clock starts when the child is ready; 403 on any POST or no 200 for `lease_s` (first announce included) → terminate child, exit 0. Reason: a driver that died while the job was idle otherwise leaves a GPU service to its walltime (probe_announce_rules L4–L6); pilots' clock also starts at construction.
- `lease_s`/`beat_s` travel in `service.json` (the server's `LEASE_S`/`POLL_S` at `host_service` time). Reason: `announce.py` is stdlib-only and cannot import `server`.
- `test_cluster_service_job`'s subprocess legs are POSIX-only. Reason: Windows has no catchable SIGTERM and can refuse `os.replace` on an open file; `announce.py` only runs in Linux jobs.

## r9 exit items
Wording and small constraints from review r9 (`plan-services-m68b-r9.md`). None of them makes a round unclean.

- §3.3 L539, site check (2): "the stock `from_dag` submit accepted unspooled" should read `from_dag(<abs run.dag>, {"usedagdir": True, "force": True})` accepted unspooled. The DAG is no longer submitted with stock options. §9 L821's "stock `from_dag` description" (`getenv`) still holds under those options, as `probe_dag_service.txt` shows.
- `data/from_dag-generic.txt` (from `probe_dag_service.txt`) embeds the DAG dir's absolute path and the pool's `CsdVersion` string in `arguments`, `environment`, `error`, `log` and `output`. The test compares after substituting both, or regenerates them, rather than byte-for-byte.
- Evidence added by r9: `probes/m68b/probe_r9_timewait.{py,txt}` (POSIX, no pool): a plain-bind "is the port free" test sees a server-side `TIME_WAIT` from the service's own `http:` self-check as taken. `probe_announce_rules.py` re-run locally reproduces L1–L6 (port numbers differ).

## decisions (round 3)
- "Free" (the scan and the after-exit check) is a bind with `SO_REUSEADDR` succeeding. Reason: a listener still refuses it, while the server-side `TIME_WAIT` left by the service's own self-check does not, so a child that answered once and died is not restarted per port (probe_r9_timewait; probe_announce_rules L7: one start in 10/10 runs).
- `data/from_dag-generic.txt` is compared after substituting the DAG dir and `CsdVersion`. Reason: both are embedded in the description and differ per run and pool.

## r10 exit items
Wording and small constraints from review r10 (`plan-services-m68b-r10.md`). None of them makes a round unclean.

- §3.3 L420 (the premise table) and L525 still say "stock" `from_dag`. The DAG is submitted with `usedagdir`/`force`, so the word should go or become "`from_dag` with `usedagdir`/`force`". The `OtherJobRemoveRequirements` line L525 cites still holds under those options (`probe_dag_service.txt`, header).
- `data/from_dag-generic.txt` substitution: `arguments` carries `CsdVersion` in its shell-escaped form (`$CondorVersion:' '25.13.2' '2026-08-19' …$`), not the raw string, and the DAG dir also appears in `-Lockfile`/`-Dag`. The test substitutes both forms, or rebuilds the expected text from the pool's `htcondor2.version()` and the tmp dir.
- Docs (`htcondor.rst` "Cluster-hosted services"): with "free" decided by a `SO_REUSEADDR` bind, a recipe's server that binds *without* `SO_REUSEADDR` can fail on a port that holds only a `TIME_WAIT` (for example one left by another job's task server on the same node). `announce.py` then exits 3 naming the returncode instead of moving on. The shipped recipes bind with it: `http.server` sets `allow_reuse_address`, and gRPC/Triton set it by default. The m66 `TaskServer` sets it on POSIX (`server.py:81`). Say that a custom recipe's server must do the same.
- Evidence r10: `probe_announce_rules.py` re-run locally reproduces L1–L7. L7 gives `[1]*10` child starts and exit 3 naming 7. `announce_proto.py` `free()` now sets `SO_REUSEADDR` (L62-71).

## r11 exit items
Wording, notes and small constraints from review r11 (`plan-services-m68b-r11.md`, a whole-unit read). None of them makes a round unclean.

- `driver._runner` reads `announce_only` and `dag_dir` with defaults (`run.get("announce_only") or []`, `run.get("dag_dir")`). m68a's frozen `test_services_sites.py` builds `driver._runner({"site": s, "pilots": "local", …})` by hand, and m67 `run.json` files predate both keys.
- `data/from_dag-generic.txt` comparison:
  - It needs real bindings *and* `condor_dagman` on PATH. The htcondor 25.14.1 wheel without it raises "Failed to locate condor_dagman executable in PATH" (`probes/m68b/probe_r11_fromdag_versions.txt`).
  - So that part of the all-OS `test_driverless_dag` runs only where the pool is (test-htcondor) and skips elsewhere. The recorder legs stay all-OS.
  - Its `CsdVersion` is the bindings' own `htcondor2.version()`, not the pool's. For the PyPI wheel it is `25.14.1 … BuildID: UW_Python_Wheel_Build`.
  - The `condor_dagman` path (`executable`, `-dagman`) is local. Substitute it too.
  - Measured: 25.13.2 and 25.14.1 are otherwise identical.
- `RunHandle(dag=True).result()` "makes no `retrieve` call" discriminates from m67 only on a `spool=True` site (lxplus) with the DAGMan ad still in the queue at `JobStatus` 4. m67 retrieves only when `in_queue and spool` (`driverless.py:99-100`).
- §3.3 L475-477, DAG mode: "announces again whenever that pair changes" should read "announces each new pair until it takes a 200", as `announce_proto.py:141-145` does (`last` is set only on 200). Then a torn read (new url, old secret → 403) or a refused POST is retried.
- `probe_dag_service.py`'s driver stand-in (`dag_driver_node.py`) matches an announce record by port only.
  - In the r11 re-run of R, both driver starts bound 10000. `announces.jsonl` held a single record, and the second start took the first start's record.
  - The committed transcript's `[10001, 10001]` still witnesses the same-url re-announce. The discriminating check is the frozen leg "the secret alone replaced (same url) → announced again".
  - If the probe is re-run, match per attempt (by record count or by secret).
- `announce.py` must *run* under python 3.9/3.10, not only parse. Ruff's `UP` rules at `target-version = "py311"` would push 3.11 forms: UP041 rewrites `socket.timeout` to `TimeoutError`, which is a different class on 3.9, and UP017 gives `datetime.UTC`. So:
  - use `from __future__ import annotations`;
  - catch `OSError`, not `socket.timeout`;
  - use no 3.10+ stdlib names.
  The frozen `feature_version=(3, 9)` parse check covers syntax only.
- `test_cluster_service_job`'s subprocess legs also run on macOS. There, the identity falls back to `socket.getfqdn()`, which the self-check dials, and that name is unmeasured on the macOS runners. The legs set `$_CONDOR_MACHINE_AD` in the subprocess env to a file with a resolvable `Machine` (for example `localhost`), and compare against `host_identity()` read under the same env.
- The "under `job_root`" test applies to the directory actually used. With `log_dir=None`, generic (`"/"`) accepts the temporary dir and any other root refuses, as m67 refuses `None` for lxplus today.
- r10's items still stand: "stock" `from_dag` at L420 and L526.
- Evidence r11: `probes/m68b/probe_r11_coverage.txt`, `probe_r11_dag_names.txt`, `probe_r11_fromdag_versions.txt`, `probe_r11_reruns.txt` (re-runs of `probe_service_job`, `probe_dag_service` and `probe_announce_rules`).

## decisions (round 5)
- Frozen subprocess legs run `python -m graphed_executors.htcondor_backend.announce`; the job keeps running the transferred file by path. Reason: coverage records only the module form (probe_r11_coverage); an imaged job has no package to `-m`, and a `__main__` guard with stdlib-only imports makes both the same code.
- SERVICE nodes use derived ids `svc<i>` (name order) for node name, `.sub` stem and announce key; `run.json.announce_only` maps name → id. Reason: a spec name is free text; `driver` collides (probe_r11_dag_names) and whitespace breaks the three-field announce; deriving keeps every legal name usable instead of refusing some.
- A spec whose `kind` the site row's `services` serves never becomes a SERVICE node. Reason: D2's order puts leg 2 before leg 3, and LPC's EAF Triton must keep serving driverless runs as in m68a; a leg-2 failure in the job then exits 1 and is retried.
- `announce.py` runtime floor 3.9 (`__future__` annotations, `OSError` not `socket.timeout`, no 3.10+ names). Reason: ruff's py311 UP rules would otherwise introduce forms that differ on 3.9.
- Subprocess legs set `$_CONDOR_MACHINE_AD` with `Machine = localhost`. Reason: a CI runner's `getfqdn` (macOS) is not known to resolve.
- The `from_dag` fixture comparison runs only in `test-htcondor` and substitutes DAG dir, bindings' `CsdVersion` and `condor_dagman` path. Reason: the wheel lacks `condor_dagman` (probe_r11_fromdag_versions); the rest is identical across 25.13.2/25.14.1.
- m68b split into B1 (attached hosting, commit 1 + its freeze) and B2 (DAG, job_root, lxplus, commits 2–3 + its freeze), CI/docs/§7 with B2. Reason: non-convergence rule; each part reviewable on its own.

## r12-B1 exit items
Wording, notes and small implementer constraints from review r12-B1 (`plan-services-m68b-r12-b1.md`). None of them makes a round unclean.

- **`TaskServer` wake-ups.**
  - Today `add()` wakes one waiter with `self._cond.notify()` (`server.py:139`, also `:246`), and the waiters are the pilots' `lease` calls.
  - If `wait_announce` waits on the same `Condition`, it can take a notify meant for a pilot. That pilot then idles until its `POLL_S` (10 s) long-poll ends, and no frozen test sees the delay.
  - So give announces their own `Condition`, or wake with `notify_all` on both sides.
- **`ServiceJob` `initialdir`.**
  - If the implementer reuses `CondorPilots.submit_description(url, 1, base)`, it resets `initialdir` to the launcher's `log_dir` *after* `base` (`launch.py:167-169`).
  - It would also put `arguments=f"{url} …"` in the ad unless `base` overrides it.
  - So `test_cluster_service_job`'s keys leg should also pin `initialdir == …/service-<key>`. Today only the live leg would catch the error, as a held job.
- **`MY.SingularityImage` from a recipe's `image`** is written quoted, `f'"{image}"'`, as the profile templates it (`sites.py` lpc/lxplus). The keys leg compares it in that form.
- **`request_cpus`/`request_memory`/`request_gpus`** come from `Launch.resources`, which is `Mapping[str, float]` and is not coerced (graphed `services.py:46`). Render them as integers (`str(int(v))`), and pin that with an integer in the keys leg.
- **The subprocess legs' env** is `{**os.environ, "_CONDOR_MACHINE_AD": …}`, not a fresh dict. Otherwise `COVERAGE_PROCESS_START` is dropped and `announce.py` records nothing (`ci.yml:297`, `probe_r11_coverage.txt`).
- **Live (a), "run 2's task GET is answered by run 2's child".** A witness that discriminates is `GET /service.json` from the task: its `key` carries run 2's `run_nonce`. Both runs can take the same port once run 1's job is removed, so the endpoint alone does not tell the children apart. This still holds under M28-B1 (a), which unlinks only the secret.
- **Spooled sites (lpc, lxplus).**
  - `stop()`'s immediate `act(Remove)` discards the `service.out`/`.err` of a job that exited 3, because they come back only via `retrieve`.
  - So `host_service`'s dead-job `RuntimeError` (L492–494) carries no reason from `announce.py`, such as a bad model or a timeout.
  - Either retrieve before removing when the job sits at `JobStatus` 4 on a spooled profile, as `CondorPilots.stop` does (`launch.py:272-273`), or name `service-<key>/` in the error. Say which in the docs.
- **The coverage witness** "≥ 90% from `tests/frozen/m68b`" cannot be read off `test-htcondor`'s combined report, which also runs m66/m67/m68a and the extras. Read it as "`announce.py` ≥ 90% in the per-file gate, with the frozen m68b legs executing it".
  - Also note that no listed subprocess leg uses a `tcp` or `grpc:` check. The connect branch of the self-check is covered only by extras, which the per-file gate allows.
- **Order of work.** `tests/frozen/m68b` joins `test-htcondor` only in B2's commit 3 (L420, L596). Until then, B1's live legs and its coverage do not run in CI, so B1 cannot be gated on its own.
- **Evidence r12-B1:**
  - `probes/m68b/probe_r12_b1_pool.{py,txt}` (htcondor/mini 25.13.2): a `ServiceJob`-shaped `http.server` job serves `/graphed-secret`, and the body equals the task server's secret.
  - `probes/m68b/probe_r12_b1_secret_served.{py,txt}` (local): the same exposure, a signature accepted with the stolen secret, and a control giving 404.
  - `probe_announce_rules.py`, run locally, reproduces L1–L7.

## r12-B2 exit items
Wording, fixture notes and small constraints from review r12-B2 (`plan-services-m68b-r12-b2.md`, a whole-part read of B2). None of them makes the round unclean.

- `test_driverless_dag` lpc legs (L580): on `SITES["lpc"]` itself neither leg can run. `launcher._refuse()` (`launch.py:179-192`, called at `driverless.py:167`) refuses a tmp `log_dir` outside `sandbox_root` naming `3DayLifetime` before any `job_root` check, and a `log_dir` under `/uscmst1b_scratch/...` cannot be created on a runner. The row should say that both legs, "submits one plain job" and the `services={}` control "refused naming `job_root`", run on `dataclasses.replace(SITES["lpc"], sandbox_root=<tmp>)`, with `image=` and a fake venv as m67's lpc test does. Otherwise the control's message depends on an ordering the plan does not state.
- B2's file list and commit 2 (L499, L595) leave out `htcondor_backend/services.py`. Writing `svc<i>.sub` from "`ServiceJob`'s keys with `watch` = the DAG dir, `url` null, no secret" needs B1's `ServiceJob` to build its files and keys without submitting, with a `watch` argument and no secret. B1's `service.json` pins `watch: null`. Also, `lease_s`/`beat_s` are "the server's at `host_service` time", but no server exists when `submit_driverless` runs. Use `server.LEASE_S`/`POLL_S` (watch mode has no orphan rule, so neither is read). Name the file in commit 2.
- `svc<i>`, "`i` its index in name order" (L515): say whether `i` counts only the specs that become SERVICE nodes or all of `plan.services`. Both readings pass every frozen leg, and "only the SERVICE specs" is the natural one.
- A reused DAG `log_dir` keeps the previous DAG's `service-svc0/`, so B1's "a fresh `<log_dir>/service-<key>/`" is not fresh in DAG mode, where the key is always `svc0`, `svc1` and so on. Clear or overwrite it with the other stale files before submit (L532).
- Site check (2) (L564) and the lxplus walk-through: with `inputs=("models",)` made absolute against the submitter's cwd, the DAG refuses unless that cwd's `models/` is under `/afs`. Say "from an `/afs` cwd and `log_dir`".
- §8 names `api.rst` (`SiteProfile.job_root`) and README rows for m68b, but commit 3 (L596-599) lists only `htcondor.rst` and the changelog. Add `api.rst` there, or drop it from §8 if autodoc picks the field up.
- r11's item "`run.get("announce_only") or []`" is superseded by the plan's `or {}` (L534). `announce_only` is a mapping.
- Evidence r12-B2: `probes/m68b/probe_r12_dag_held_node.{py,txt}`. On a DAG whose driver node never writes `result.pkl`, the node is held, by input transfer (a missing executable) or by output transfer (a `kill -9`ed driver with `transfer_output_files=result.pkl`). DAGMan stays at `JobStatus 2` with `DAG_JobsHeld = 1` and does not fail the DAG within 400 s. See M40-B2.

## decisions (round 6)
- A per-call announce secret (valid only on `/announce`, only for its keys) replaces the pilots' secret in every `ServiceJob` and in the DAG dir; `announce.py` also reads it into memory and unlinks it before starting the child. Reason: the pilots' secret signs pickles, and a service serving its cwd exposed it (probe_r12_b1_secret_served, probe_r12_b1_pool); the scoped secret removes the code-execution path, and the unlink stops even a forged announce (probe_announce_rules L8). Both, as defence in depth.
- `/announce` is verified by looking up the key's announce secret from the plain-text body before any pickle parse. Reason: parsing text is safe, and the key selects the secret.
- Announces wait on their own `Condition`. Reason: `add()` wakes one waiter with `notify()`; a `wait_announce` could otherwise swallow a pilot's wake-up.
- `ServiceJob.files(dir)` builds files and keys without submitting; B2's SERVICE nodes use it with `watch`, each in `service-svc<i>/`. Reason: several SERVICE nodes cannot share one `service.json`; B2 needs B1's keys without a submit.
- `RunHandle(dag=True)` reports `held` for a running DAGMan job with `DAG_JobsHeld > 0`. Reason: a held node leaves DAGMan at `JobStatus 2` indefinitely (probe_r12_dag_held_node); m67's contract has `held`.
- Spooled `ServiceJob.stop()` retrieves a completed job before removal. Reason: keeps `announce.py`'s exit reason for `host_service`'s error.
- `test-htcondor` running `tests/frozen/m68b` moves to commit 1 (B1). Reason: B1 must be gated on its own.

## r13-B1 exit items
Wording and small constraints from review r13-B1 (`plan-services-m68b-r13-b1.md`, a delta round). None of them makes the round unclean.

- **L506, the stale clause.** "A record under a released key stays unread" no longer holds: after `forget_announce`, that key's announces get 403 and nothing is recorded.
  - **L516–517, the release order.** `release_service` pops the record, then forgets the key. A beat that arrives between the two leaves a record behind. Forget first, then pop, and drop the stale clause.
- **L510–515, the failure paths.** When `host_service` fails (timeout, dead or held job, or `schedd.submit` raising), it removes the job but does not `forget_announce` the key. D10's "releases what it started" covers the registered announce secret too. Say that these paths also call `forget_announce([key])`.
- **L499–501, a body with no key.** Say that a body that is not UTF-8, or is empty, gets 403 with nothing recorded, because no key means no secret to verify against. It is not a 400.
- **L604, the order of the unlink.** "After the announce … the file is gone" also passes when `announce.py` unlinks the file only after the child is ready. To pin "before starting the child" (L436), have the leg's child record `test -e graphed-secret` at start.
- **Evidence r13-B1:** `probe_announce_rules.py`, re-run locally, reproduces L1–L8. M29-B1 cites the existing `probes/site-lxplus/m67-driverless.txt`, which shows `KRB5CCNAME=FILE:/srv/lgray.cc` in the scratch dir.

## r13-B2 exit items
Wording and small constraints from review r13-B2 (`plan-services-m68b-r13-b2.md`, a delta round). The design findings are M41-B2 and M42-B2 in that review; the items below do not make the round unclean.

- **L420–422 and L600, the simulated-GPU pool line.** B1's commit 1 now makes `test-htcondor` run `tests/frozen/m68b`, but the pool line arrives only in B2's commit 3. B2's live file (`http_server` with `resources={"gpus": 1}`) needs the GPU, so commit 2 is red in CI.
  - Move the pool line to B2's commit 0 or 2.
  - Change L600's "The live files need" to "`test_driverless_dag_live.py` needs". B1's live file requests no GPU that must match.
- **L559–560, L614 and L880, the pilots' secret on the shared tree.** With `pilots="condor"`, m67's in-job `CondorPilots` writes the pilots' secret to `<dag_dir>/pilots/graphed-secret` (`run["log_dir"] = out/pilots`, `launch.py:200-202`), under the same ACL.
  - Reword the rationale to say the SERVICE node gets only an announce secret.
  - Change "Fails on: a pilots' secret in the DAG dir" to "…in `dag_dir/graphed-secret`, which the SERVICE node reads".
  - §9: the DAG dir also holds the pilots' secret in `pilots/`, as m67's lxplus self-submit already does. Site check (2)'s `fs listacl` covers it.
- **L606, the lpc copy.** `submit_driverless` takes a site name, so the copy is registered with `monkeypatch.setitem(SITES, "lpc", dataclasses.replace(...))`, the pattern of m67's `test_driverless_payload.py:199`. m67's lpc test (L209) is a refusal, not a submit.
  - The control's "`services={}`" means the row's `services` field on that copy, not the `services=` kwarg.
- **L606, the ids leg.** To discriminate "name order" from declaration order and "among those specs" from an index over all specs, declare `driver` before `a b` and add an image-less CPU spec whose name sorts first. That spec gets no node and does not shift the ids.
- **Evidence r13-B2:** `probes/m68b/probe_r13_dag_held_service.{py,txt}` and `probe_r13_dag_held_service_prm.py` (htcondor/mini 25.13.2; `DAGMAN_USE_STRICT = 1` default).

## decisions (round 7)
- (Superseded in part by round 8: the credential drop applies to the attached path only.) The service child runs in `service/`, into which `announce.py` moves the recipe's inputs, and a `ServiceJob` drops `MY.SendCredential`. Reason: both — the subdir keeps anything condor puts in scratch (lxplus's ticket cache, `m67-driverless.txt`; job/machine ads) out of the served cwd, including files we cannot foresee (probe_announce_rules L9); dropping the credential means there is no ticket to leak at all. Acceptance of a credential-less job at lxplus is site check (1)'s.
- `RunHandle(dag=True)` projects `DAG_JobsHeld`; `wait()` keeps m67's terminal set, so a held driver node times out naming `held`. Reason: a real schedd returns only projected attributes (probe_r13_dag_held_service); `held` stays releasable, as in m67's contract.
- Every `svc<i>.sub` carries `periodic_remove = JobStatus == 5` (after the profile keys, before `extra_submit`). Reason: a held SERVICE node at DAG end makes DAGMan exit 1 under `DAGMAN_USE_STRICT`, removed it does not (probe_r13_dag_held_service; `_prm` variant).
- `release_service` forgets the announce key before popping, and every `host_service` failure path forgets it. Reason: no record can reappear after release; D10's "releases what it started" covers the registered secret.
- The simulated-GPU pool line moves to commit 1 with `test-htcondor` running `tests/frozen/m68b`. Reason: B2's live file must find the GPU whenever it lands; B1's timeout leg is unaffected (it asks for two).

## r14-B2 exit items
Wording from review r14-B2 (`plan-services-m68b-r14-b2.md`, a delta round). The design finding is M43-B2 in that review.

- **L547, where `periodic_remove` goes.** `ServiceJob`'s keys run profile keys → `MY.SingularityImage` →
  `extra_submit` (L463-464), so "after the profile keys and before the launcher's `extra_submit`" leaves open whether it
  sits before or after `MY.SingularityImage`. Harmless (distinct keys), but say "just before the launcher's
  `extra_submit`", so a user's `periodic_remove` in `extra_submit` still overrides it and the implementer inserts at
  one place.

## r14-B1 exit items
Wording and small constraints from review r14-B1 (`plan-services-m68b-r14-b1.md`, a delta round). The design findings are M30-B1 and M31-B1 in that review.

- **L622, stale wording.** "`service.json` and `graphed-secret` in the child's cwd as in the job" should now read "in the job dir (the child runs in `service/`), as in the job".
- **L627–630, a claim no row witnesses.** "Fails on: an announce secret left registered after a failed or released call" is not tested. Add a spy on `TaskServer.forget_announce` to the live row (b): the key is forgotten on the timeout path and on the dead-child path, and `release_service` calls `forget_announce` before `ServiceJob.stop`. Or say that the line is carried by review.
- **L440–442, the rationale names only lxplus.** LPC's `x509userproxy` (`sites.py:51-53`) is also transferred into scratch, and LPC has `"cluster"`. The `service/` subdir keeps it out of the child's cwd too, so say so. The proxy stays readable by the child through `X509_USER_PROXY`, but the child does not serve it.
- **L443, a missing input.** The prototype skips an input that is not in scratch (`os.path.exists`). Say so, or say that it exits 3 naming the input. Condor holds a job with a missing input anyway, so neither choice matters in a job.
- **Evidence r14-B1:** `probe_announce_rules.py`, re-run locally, reproduces L1–L9. The duplicate-basename check (htcondor/mini) shows that the later file silently wins: the user's `service.json` replaced the job's own, with exit code 0.

## decisions (round 8)
- `ServiceJob` refuses, on every profile, an input whose basename is a job file (`service`, `service.sh`, `service.json`, `announce.py`, `graphed-secret`, `env.tgz`, `env`), begins with `_condor_` or `.`, or repeats another input's. Reason: condor lets a later name silently replace an earlier one (r14-B1's mini check); one set on every profile is simpler to pin than a `ship_env`-dependent one, and `env` is harmless to reserve elsewhere.
- An input absent from scratch is skipped by `announce.py`. Reason: condor holds a job with a missing input before it runs, so the case does not arise in a job.
- A watch-mode (SERVICE node) `ServiceJob` keeps `MY.SendCredential`; only the attached path drops it. Reason: the node reads `dag_dir` (AFS on lxplus) in the job; `service/` keeps the ticket cache out of the served cwd (probe_announce_rules L9); acceptance and `klist` are site check (2)'s.
- A relative `{python}` is made absolute before `Popen(cwd=service/)`. Reason: POSIX resolves a relative `argv[0]` against the new cwd (probe_announce_rules L10 control: `FileNotFoundError`).

## r15-B2 exit items
Wording and test tightening from review r15-B2 (`plan-services-m68b-r15-b2.md`, a delta round). No design finding.

- **L633, the new lxplus leg's setup.** `SITES["lxplus"]` templates `MY.SingularityImage` over `{image}` and has
  `ship_env=True` (`sites.py:72-80`), so `CondorPilots._refuse` needs `image=` and a shippable venv
  (`launch.py:180-194`). Its only SERVICE-capable host is `("cluster",)`, so the spec must be GPU or imaged. Say "with
  `image=` and a fake venv, a GPU spec" as the lpc leg does.
- **L633, "`submit` without spool" discriminates only on a `spool=True` profile.** The ids/DAG-text leg runs on a
  generic copy (`spool=False`), where `launcher._submit` (`launch.py:226-230`, spool = `profile.spool`) also passes.
  The new lxplus copy is `spool=True`. Assert there that the recorder logs `("submit", …, spool=False)` and no
  `("spool",)` (`tests/frozen/m67/driverless_harness.py:254-259`). This pins "never spooled" (L568; round-1 decision)
  at the one site it is for. The same precedent as r13's `result()`-no-`retrieve` item.
- **L617, site check (2)'s `klist`.** The SERVICE node runs in `tritonserver:24.11-py3`. Its `klist` is unmeasured.
  m67's `klist` ran in the coffea image (`m67-driverless.txt` L22), and the Triton image may not ship krb5 tools. Name
  how the owner gets the SERVICE node's shell (`condor_ssh_to_job <svc cluster>`). Record `$KRB5CCNAME` and whether its
  file exists, plus `klist`/`tokens` where present. The deciding evidence stays "the SERVICE node reading
  `driver.url`/`graphed-secret` on AFS".
- **L447-450 vs L552-561, the reserved-name refusal on the DAG path.** B2 builds nodes with `ServiceJob(...,
  watch=…).files`, never `submit()`. Say that the refusal is raised by the constructor or `files()`, so the SERVICE
  nodes get it, before `run.dag` is written and before `from_dag`. Optionally add one DAG case (an `announce_only`
  recipe input named `service.json` refused naming it, recorder without `from_dag`). The names do not collide with
  B2's own files: `svc<i>.sub`, `service-svc<i>/`, `run.dag` and `driver.url` live in the DAG dir, not in the node's
  scratch.
- **Round-7 decision 1** still reads "a `ServiceJob` drops `MY.SendCredential`" without scope. Round 8 narrows it to
  the attached path. Mark it superseded there, or leave it as is if the log is read in order.

## r15-B1 exit items
Wording and small constraints from review r15-B1 (`plan-services-m68b-r15-b1.md`, a delta round). The design finding is M32-B1 in that review.

- **L631, the relative-`{python}` leg's witness.** The POSIX legs also run on macOS (the `ci.yml` matrix). "The child's `argv[0]` is absolute" therefore needs a reader that works there too, such as `ps -o args= -p <pid>`. `/proc/<pid>/cmdline` and `pgrep -a` (which the probe uses) are Linux-only. Alternatively, let the announce alone carry the leg. It already discriminates, because a relative path makes `Popen` raise `FileNotFoundError`.
- **L449–451, the proxy's basename.** On lpc, condor also transfers `x509up_u<uid>` into scratch. An input with that basename would replace the proxy, or be replaced by it. This is contrived. Refuse it only if the reserved set is extended anyway (M32-B1), or leave it to review.
- **Evidence r15-B1:** `probe_announce_rules.py`, re-run locally, reproduces L1–L10. On htcondor/mini 25.13.2 the executable lands in scratch under its own name (`service.sh`, not `condor_exec.exe`). Under `MOUNT_UNDER_SCRATCH` (the default, active when the starter can mount), scratch also holds `tmp/` and `var/tmp/`, bind-mounted over `/tmp` and `/var/tmp` (M32-B1).

## decisions (round 9)
- The reserved input names add `tmp`, `var` and the `x509up_u` prefix, checked in `ServiceJob`'s constructor. Reason: under `MOUNT_UNDER_SCRATCH` condor's `tmp/`/`var/tmp/` in scratch are bind-mounted over `/tmp`/`/var/tmp`, so an input `tmp` would merge into and serve the job's `/tmp` (r15-B1); the proxy's basename is condor's too; the constructor covers B2's `files()` before `run.dag` is written.

## r16-B1 exit items
These are wording items and small constraints from review r16-B1 (`plan-services-m68b-r16-b1.md`, a delta round). That review has no design finding.

- **L634, where the relative-`{python}` leg gets `<pid>`.** The plan's `announce.py` text does not say that the child's pid is ever emitted. The prototype logs `ready pid=<n>` (`announce_proto.py:139`), and the probe instead finds the process with `pgrep -af`. The plan should name the pid source: either keep the prototype's `ready pid=` log line in `announce.py`, or use `pgrep -P <announce.py pid>`, which works on Linux and macOS.
- **L445–451 with L529–532, the constructor refusal as a `host_service` failure path.** `host_service` mints the key's announce secret before it constructs the `ServiceJob`, because the constructor takes `secret=`. A reserved-name refusal therefore raises after `announce_secret([key])`. "Every failure path … calls `forget_announce([key])`" already covers this, but no leg witnesses it. Either name the refusal among those paths, or add it to the live row's `forget_announce` spy, where it needs no pool.
- **L449–450, `tmp`/`var` assume the default `MOUNT_UNDER_SCRATCH` (`/tmp,/var/tmp`).** A site that adds a directory, for example `/dev/shm`, adds a scratch root such as `dev` that the fixed set does not refuse. The plan should state the assumption beside the reason. The execute side's configuration cannot be read from the submit host.
- **Evidence r16-B1:** on Linux, `ps -o args= -p <pid>` prints the absolute `…/env/bin/python` argv[0] of a child that was started through a symlink to `sys.executable` with `cwd=service/`. The argv[0] is not rewritten.

## r16-B2 exit items
These are wording items and small constraints from review r16-B2 (`plan-services-m68b-r16-b2.md`, a whole-part read). The design finding is M44-B2 in that review.

- **L168 (m67's `run.json` schema) vs L555–556.** m67's line still reads `announce_only: [] (m68)`, a list. B2
  makes it `{name: id}`, a dict, which `driver._runner` reads as `run.get("announce_only") or {}`. Mark the m67 line
  "(m68b: a `{name: node id}` map)" so nobody writes a list.
- **L636, the ids leg's first clause.** "specs named `driver` and `a b` get `svc0`/`svc1`" reads as `driver → svc0`.
  The same row's `announce_only == {"a b": "svc0", "driver": "svc1"}` is the truth. Reorder the clause to "`a b` and
  `driver` get `svc0`/`svc1`".
- **L634 vs L656–658, the watch-mode `ServiceJob` partition.** B1's frozen row (commit B1-0, gated at B1-1) asserts
  "(a watch-mode one keeps it)", that is, `MY.SendCredential` on `ServiceJob(watch=…)`. That assertion needs the
  `watch=` path, but B2's commit 2 claims "`ServiceJob` watch mode in `services.py`". Fix it one of two ways:
  - move those ~15 lines into B1's commit 1, since `announce.py`'s watch loop is already there;
  - or drop the parenthetical from B1's row, because B2's row already asserts that `svc0.sub` carries
    `MY.SendCredential = True`.
- **L658, the commit label.** `ci+docs(m68b)` carries no CI change: the CI lines are in B1's commit 1 (L655, L421).
  Name it `docs(m68b)`.
- **Evidence r16-B2:** `probes/m68b/probe_r16_dag_stale_result.{py,sh,txt}` (M44-B2). An evicted driver node with
  `ON_EXIT_OR_EVICT` is held at output transfer. That reproduces `probe_r12_dag_held_node.txt`. Removing each held
  node gives DAGMan `ExitCode 1` after two retries, while a stale `result.pkl` remains in the DAG dir.

## decisions (round 10, owner-directed)
- Each DAG run gets its own new directory `<log_dir>/graphed-<nonce>/` (`exist_ok=False`, the nonce m67 already mints); `from_dag` takes `{"usedagdir": True}` only. Reason: owner directive; with no reuse there is no `force`, no rescue handling and no pre-submit cleanup, and a stale `result.pkl` (r16 M44) cannot exist. Supersedes round 2's "reused DAG log_dir accepted with cleanup" and `force` (probe_dag_service R, X re-run in fresh dirs).
- m67's plain driverless job keeps `log_dir` as its run directory. Reason: m67's frozen live test pins `driver.log` in `log_dir` (test_driverless_live.py:90), and a plain job reaches done/failed only through a completed output transfer, so reuse there cannot surface a previous result; m67's frozen tests stay unmodified.
- The service child's cwd holds exactly its declared inputs by construction: `ServiceJob.files()` builds `service/` submit-side (file inputs as symlinks, directory inputs as real trees of file symlinks) and transfers that one directory. Reason: owner directive (one allowlist rule instead of an enumerated reserved list); condor follows file symlinks, refuses directory symlinks, and an input named like a job file lands inside `service/` and replaces nothing, spooled or not (probe_input_dir). Supersedes the reserved-name decisions of rounds 8 and 9 and the move-by-basename step of round 7; only a missing input and a duplicate basename are refused.
- Attached `service-<key>/` dirs are created with `exist_ok=False`. Reason: the key is per call, so the same no-reuse rule holds by construction.
- A `failed` DAG handle without `result.pkl` raises `RuntimeError` naming `run.dag.dagman.out`. Reason: in a fresh run dir the file is absent when no driver start transferred one; a bare `FileNotFoundError` names nothing.
- The watch-mode `ServiceJob` path (and its kept `MY.SendCredential`) lands in commit 1; commit 3 is `docs(m68b)`. Reason: B1's frozen row asserts it, so B1's gate needs it; commit 3 carries no CI.

## decisions (round 11, HTCondor surface)
- graphed's HTCondor needs are stated once: §3.3 "HTCondor behaviour relied on" points at `condor_surface/NEEDS.md`/`RESULTS.md` and names how each not-assumable knob is met per job or per DAG. Reason: owner direction; one matrix instead of per-finding premises.
- DAG submitted with `AddToEnv: _CONDOR_DAGMAN_USE_STRICT=0`; `RunHandle(dag=True)` takes done/failed from the latest driver try's ExitCode and held from a driver-node query; no `DAG_*` counter, `DAG_Status` or DAGMan ExitCode read. Reason: D-05/D-06 (an idle/held SERVICE node fails DAGMan under default strictness), D-07 (counters lag 300 s). Supersedes rounds 6–7's `DAG_JobsHeld` projection; `periodic_remove` stays as slot hygiene only (L-05). probe_dag_service re-run with the options (description shows `-insert_env _CONDOR_DAGMAN_USE_STRICT=0`).
- `driver.sh` (plain and DAG) writes a placeholder `result.pkl` `(False, RuntimeError)` and touches `driver.log` before exec. Reason: S-15 (a missing output holds the job for every exit) — a killed driver becomes a retried, then failed, try (L-06, D-08); probe_placeholder. m67's frozen tests read `driver.sh` only by name and run the driver via `-m`, so they stay unmodified.
- `ServiceJob` sets `job_max_vacate_time=30`; `announce.py` bounds its SIGTERM reap at 5 s. Reason: L-02 (family-wide SIGTERM; removal lingers to `MachineMaxVacateTime`, 600 s default).
- `announce.py` never uses its own `sys.executable`; a separator-bearing name is made absolute, a bare one resolved by `shutil.which` on `$PATH` or `os.defpath`. Reason: S-05 (no PATH, `sys.executable == ''` in a job).
- Inputs that are or contain a directory symlink, and paths (and `user_modules`) containing `,`, are refused; the service/ mirror walks without following links. Reason: S-08, S-09 (holds at input transfer); replaces round 10's `followlinks=True`, which could also loop.
- No reserved scratch names are added (the study's consequence 10 is superseded by the service/ design, which its own consequence 11 requires); `.machine.ad` spoofing is impossible by construction and pinned by a test (S-12; probe_input_dir: an input `.machine.ad` stays inside `service/`, `$_CONDOR_MACHINE_AD` still names the EP). A `service` mount point makes `announce.py` exit 3.
- Error paths name `HoldReasonCode` (and condor-set `HoldReason`), never graphed's own `act(reason=)`; they do not assume `service.out` exists; "queue empty" legs poll. Reason: L-09, S-04, L-02.
- Site checks gain the study's owner items (lxplus image env/`sys.executable`/vacate time/N-02; DAG strictness and update interval; lpc proxy landing and scratch mounts as site check (3)).

## r17-B1 exit items
These are wording, citation and test-precision items from review r17-B1 (`plan-services-m68b-r17-b1.md`, a whole-part read after the redesign). The design findings are M34-B1, M35-B1 and M36-B1 in that review.

- **L457–458, stale reason in the Secrets bullet.** The bullet says the child's "cwd is the job's scratch dir and … may serve it". The child now runs in `service/`, so `http.server` cannot reach `graphed-secret`. The unlink still guards a child that reads `../graphed-secret`. Restate it that way, and keep the probe citations as history.
  - Row L695's `GET /graphed-secret` → 404 sub-leg now passes whether or not the file is unlinked. The discriminating witness is the "`../graphed-secret` exists at start → False" sub-leg. Say so, or drop the `GET` sub-leg.
- **L695, the `.machine.ad` identity sub-leg does not discriminate.** In the subprocess legs the harness sets `$_CONDOR_MACHINE_AD` to its own file and lays out `service/` itself. An input named `.machine.ad` therefore cannot change the announced identity, whatever `ServiceJob` does. The real witnesses are the unit assertion that `transfer_input_files` names `dir/service` once and never an input, plus `probe_input_dir.txt`'s pool legs. Say that the sub-leg is a consistency check, or drop it.
- **Shared subsection L432–437 vs RESULTS.md.** Several RESULTS consequence lines describe the superseded in-job design, where `announce.py` moves inputs and reserved names are extended: S-14's "keep `announce.py` moving them", X-05's reserved set and guard "before moving it", X-06, and plan consequences 10 and 11.
  - The plan follows the round-10/11 decisions instead. Mark those lines superseded in RESULTS, or say so in the shared subsection, so that "relies on nothing the matrix contradicts" reads true.
  - The spooled mirror is pinned only by `probes/m68b/probe_input_dir.txt` (mirror-spool), not by a matrix row. S-07/S5 is unspooled. Add it as a row (for example S-19, "a submit-side tree of file symlinks transferred as one directory, spooled and not") or cite the probe in the shared subsection.
- **L495 vs §3.1 `recipes.triton`.** B1 says "the argv names each input by its basename, relative to `service/`". `triton(model_repository=…)` puts the argument verbatim into both `inputs` and argv. A non-bare `model_repository` (`data/models`, `/abs/models`) therefore always fails in the job, and it surfaces only as `host_service`'s `RuntimeError`. Only the docs commit (L724) states the constraint. Name it in B1 beside L495. A construction refusal of an argv that names an input by a non-basename path is optional.
- **Evidence r17-B1:** `probes/m68b/probe_r17_b1_input_exec.{py,txt}` (M34-B1): an executable mirrored input lands 0755 and runs from `service/`, spooled or not. `probe_r17_b1_comma.{py,txt}` (M36-B1): a `,` inside `service/` transfers, and a `,` in the listed absolute dir holds the job.

## r17-B2 exit items
These are wording, citation and test-precision items from review r17-B2 (`plan-services-m68b-r17-b2.md`, a whole-part read after the redesign). The design finding is M45-B2 in that review.

- **L655, the citation for a retried signal death.** "retried by … `RETRY` (DAG, D-08)": D-08's probes are exit codes 1/3 only, and the matrix does not pin a signal-killed node. Cite `probes/m68b/probe_r17_b2_sigretry.txt`, where SIGKILL with a placeholder present and exec failure (rc 127) are each retried three times, never held, and end DAGMan `ExitCode 1` with the placeholder in the run dir. Also add the case to NEEDS/RESULTS D-08, for example as `D[retry-kill9-placeholder]`.
- **L697, the fixture's version citation.** `probe_r11_fromdag_versions.txt` compared the wheel and the system bindings under `{usedagdir, force}`, not B2's options. Also cite `probes/m68b/probe_r17_b2_fromdag_wheel.txt`: the 25.14.1 wheel under `{UseDagDir, AddToEnv}` matches `probe_dag_service.txt`'s description after the three substitutions.
- **L571, the definition of `job_root`.** It says "the tree the site's schedd and every job read directly". Jobs also write there: the driver job writes `driver.url` and `graphed-secret` into `dag_dir`, and m67's `pilots="condor"` writes `<log_dir>/pilots/`. Say "read and write directly".
- **L640, the history read for driver tries.** Name the bound, for example `schedd.history(<driver-node constraint>, [...], match=3)`, since `RETRY driver 2` allows at most three tries. m67's comment at `driverless.py:65` notes that an unbounded history read scans the whole history, and `wait()` repeats it every poll.
- **L697, the highest-`ClusterId` leg.** Have the recorder return the driver ads with the highest `ClusterId` not first (for example `[try 2 ExitCode 0 (cluster 10), try 1 ExitCode 1 (cluster 9)]` reversed), so a first-ad reading fails. Q-03 says history returns ads in recorded order.
- **L697, the placeholder `sh` sub-leg on Windows.** The file is all-OS, and the main matrix runs `tests/frozen` on `windows-latest`. State the leg's scope, either `skipif(shutil.which("sh") is None)` or POSIX-only as B1's subprocess legs are.
- **L722–724 docs commit: m67's changed behaviour.** Add these to `htcondor.rst`'s driverless section:
  - a driver killed before writing a result (OOM, SIGKILL, missing interpreter) is now retried like exit 1, not held;
  - after the last try, `result()` raises "the driver exited before writing a result; see driver.log";
  - the exit table (docs/htcondor.rst:279-296) gains a "killed" row.
- **§2 L168 vs L616, the `announce_only` default.** §2 lists `announce_only: []` as an m68 key of `run.json`, while L616 says m68a's run dicts predate the key. `run.get("announce_only") or {}` accepts either form. Make the two texts agree: either m68a writes no `announce_only`, or L616 says an empty list is read as `{}`.
- **Evidence r17-B2:** `probes/m68b/probe_r17_b2_sigretry.{py,txt}` and `probes/m68b/probe_r17_b2_fromdag_wheel.txt`.

## decisions (round 12)
- `{python}` is resolved against the job dir before rendering; a literal argv[0] is left as written (so relative to `service/`); a raising `Popen` exits 3 naming argv[0]. Reason: the interpreter lives beside `announce.py`, a recipe's executable input inside `service/` (probe_r17_b1_input_exec; probe_announce_rules L11, L12).
- Every `ServiceJob` `transfer_input_files` entry is relative to `initialdir` (`env.tgz` a file symlink there); the input `,` refusal is dropped. Reason: a `,` splits only listed paths; names inside the one listed `service` dir transfer intact (probe_r17_b1_comma A–C).
- The attached live identity witness uses history times (`EnteredCurrentStatus`, `JobCurrentStartDate`, `JobBatchName`) around the task's GET time. Reason: the job's own files are outside `service/`, so `GET /service.json` is 404.
- `RunHandle(dag=True)` maps every DAGMan JobStatus: 3 removed, 5 held, 1/2 via the driver-node query, 4 (queued or history) via the latest driver try from `history(..., match=3)`. Reason: M45; a queued-4 ad must exercise the no-retrieve path.
- RESULTS.md gets an appended section (superseded consequence lines; rows S-19, D-08a). Reason: the plan must rely on nothing the matrix contradicts; the surface agent is done.

## r18-B2 exit items
These are test-precision and wording items from review r18-B2 (`plan-services-m68b-r18-b2.md`, a delta round). There is no design finding.

- **L644–650 and L708, the rest of the DAGMan state map.** The plan now maps every JobStatus that DAGMan can take here, but the frozen row pins only some of them.
  - Pinned: gone at 4, queued at 4, 1 with no driver ad, and 2 with a held driver.
  - Not pinned: DAGMan's own 3 → `removed` and 5 → `held` (an implementation that sent 5 through the driver-node query would read `queued`), and 2 with a running driver ad → `running`.
  - Add these three recorder cases.
  - Say what any other JobStatus (6/7, not expected for a scheduler-universe job) gives, e.g. "any other → `running`, as m67's `_poll`".
- **L722–726, "Fails on (B2)".** Add the failure the M45 leg catches: "a finished DAG read as running, or retrieved on a spooled profile".

## r18-B1 exit items
These are wording and test-precision items from review r18-B1 (`plan-services-m68b-r18-b1.md`, a delta round). There is no design finding.

- **L706, the leftover absolute wording.** The `ServiceJob` keys clause still says "`transfer_input_files` names `dir/service` once", but the same row later says every entry is relative and names `service`. Say "names `service` (relative to `initialdir`, the `dir/service/` tree) once", so the test does not assert `"<dir>/service"`.
- **L706, the detached argv[0] clause.** The clause "the service announces (a relative path would make `Popen` raise) and the child's `argv[0]`, read with `ps -o args=` …, is absolute" belongs to the `service.json.python = ./env/bin/python` case. With the `serve.sh` and `./missing` legs now inserted between them, that is no longer clear.
  - Move the clause next to its case.
  - Say that the `./serve.sh` leg's argv[0] stays relative (no `ps` absoluteness check there).
- **L505, citing the evidence for the `env.tgz` symlink.** The plan says "`env.tgz` a file symlink in `initialdir` … followed by condor", but it cites nothing for a relative top-level symlink entry, which matters when spooled (lpc and lxplus both spool). Cite `probes/m68b/probe_r18_b1_envlink.txt` there, and add it to S-19's probe column in RESULTS' appended section.
- **L707, what "left the queue" means.** In "left the queue (`EnteredCurrentStatus`)", that attribute is the time the job entered `JobStatus` 3 (its removal), not the time it left the queue. Also note that `t` and the history times come from one clock, the one-host pool.
  - Say "was removed (history `EnteredCurrentStatus`, JobStatus 3) before `t`".
  - Note that the task's `t` is `time.time()` on the pool host.
- **Evidence r18-B1:** `probes/m68b/probe_r18_b1_envlink.{py,txt}`.

## r19-B2 exit items
These are wording, file-list and test-precision items from review r19-B2 (`plan-services-m68b-r19-b2.md`, a whole-part read). There is no design finding.

- **L580 header vs L659–664, where the placeholder is written.** `driver.sh` is written by `CondorPilots._stage` in `launch.py` (`launch.py:213-224`), which `pilot.sh` shares. The B2 header lists `sites.py`, `driverless.py`, `driver.py` and `backend.py` only. Name where the placeholder goes: `launch.py` (for example a `_stage` argument used only for the driver), or `driverless.py` writing its own `driver.sh`. Either way, `pilot.sh` is unchanged; m66's `test_htcondor_sites.py:149` reads it by name only.
- **L632–635, the announce secret's file mode.** "Each through a temporary file and `os.replace`" does not give a mode.
  - §9 (L996–998) says the DAG dir's `graphed-secret` is guarded by the directory's ACL, not the file mode. That holds on AFS only.
  - On `generic` (`job_root="/"`, a local filesystem) the run dir is created with the default umask (0755), so a 0644 temporary file would let another local user sign `/announce`.
  - Say the temporary file is written as `write_secret` writes the pilots' secret (0600) before the `os.replace`. Scope §9's sentence to AFS.
- **L603–606, the `job_root` check is lexical.** "Under" is `Path(os.path.abspath(p))`, so an input (or a file inside a directory input) under `job_root` that is a symlink to a path outside it passes the refusal. Such inputs are common in model repositories (RESULTS S-08). Positive control: `/tmp/claude-0/review-r19-b2/jr_lexical.txt` shows abspath under root True and realpath False.
  - A node whose input the schedd cannot read is held at transfer (S-13). A held SERVICE node is then removed by `periodic_remove`, and the driver fails after three × `timeout_s`, so it is not "waits on for ever". "For ever" is true of a held *driver* node (D-09), for an unreadable `user_modules` path.
  - Either state that the check is lexical, with that consequence, in the text and in the docs commit's `job_root` paragraph, or check `os.path.realpath` of each file `ServiceJob.files()` links.
  - Correct "which DAGMan waits on for ever" accordingly.
- **L607 / B1 L505, when the SERVICE node's `env.tgz` link is made.** In attached mode the pilots' `env.tgz` already exists when `files()` runs. In the DAG it is built by `_stage` for `driver.sh`, in the same run dir. Say that `files()` runs after `_stage`: a dangling link holds the node (S-13), which leads to three driver timeouts. The frozen lxplus leg can use an image-less GPU spec and assert `os.path.isfile(<svc dir>/env.tgz)`, which follows the link.
- **L710, the second live run's path.** "A second run whose plan process SIGKILLs … the driver (`pilots="local"`)" does not say whether it is a DAG (a GPU SERVICE spec, `RunHandle(dag=True)`, three driver clusters in history) or m67's plain job (no service, `NumJobStarts == 3`). Name the path, since the file is the DAG live file. The DAG case is probed (`probe_r17_b2_sigretry.txt`). The plain case rests on L-06 plus S-15 and has no probe with the placeholder present, so it is the one worth a live leg if only one is kept.
- **Evidence r19-B2:** `/tmp/claude-0/review-r19-b2/jr_lexical.txt` (scratch; reproduced by three lines of Python: a symlink under root, then `abspath` vs `realpath` `is_relative_to`).

## r19-B1 exit items
These are wording, citation and test-precision items from review r19-B1 (`plan-services-m68b-r19-b1.md`, a whole-part read). The design finding is M37-B1 in that review.

- **L707, the r18 item that was not applied.** The row's `ServiceJob` keys clause still says "`transfer_input_files` names `dir/service` once, never an input itself". The same row later says every entry is relative and names `service`. Replace the first wording with "names `service` (relative to `initialdir`, the `dir/service/` tree) once", so no test asserts `"<dir>/service"`.
- **L708, the live witness's history attributes.** The witness relies on three attributes in the history ad of a removed running job: `JobBatchName`, `JobCurrentStartDate` and `EnteredCurrentStatus` (= the removal second, `JobStatus` 3). No committed probe or matrix row pinned them; r18 checked them only in scratch.
  - They are now measured in `probes/m68b/probe_r19_b1_history_times.txt`: all three are present, and a `t` taken in the job lies between them.
  - Cite that file in the row, and add it to RESULTS' appended section (for example as Q-04).
- **L541 / §3.1 L268, the child's environment.** The plan says what `announce.py` passes to `Popen` but not how the recipe's `env` combines with the job's own environment. The prototype merges them (`announce_proto.py:110`, `{**os.environ, **env}`).
  - A replace would drop condor's `CUDA_VISIBLE_DEVICES` (S-18), and it would drop the image's `PATH`, which Popen uses to resolve a bare `tritonserver` (X-08). The B1 legs would all still pass.
  - Say "the recipe's `env` over the job's environment".
  - Optionally add a leg where the child records one variable from each.
- **L708, which `http_server` spec the live test uses.** §3.1 L239 gives `http_server(name, *, root=".")`, but `root` appears neither in the argv nor in any stated `inputs`.
  - If an implementation made `root` an input, `files()` would mirror pytest's whole cwd into `service/`, and a directory symlink anywhere in it would make construction refuse.
  - The row should name the spec's `inputs` (for example `()`, the child serving the empty `service/`), and B1 should say that `root` is not an input.
- **Evidence r19-B1:**
  - `probes/m68b/probe_r19_b1_orphan_reap.{py,txt}` (M37-B1): the prototype's orphan reap never returns for a SIGTERM-ignoring child, and a SIGTERM during that reap never lets it exit.
  - `probes/m68b/probe_r19_b1_history_times.{py,txt}` (htcondor/mini 25.13.2, container `r19b1-mini`, removed).

## decisions (round 14)
- `announce.py` has one bounded reap (terminate, ≤ 5 s, kill) for every exit path; the SIGTERM handler sets SIGTERM to ignored and raises a private `BaseException` into the main thread, whose top level does the reap. Reason: M37 — the orphan path had no bound and nothing outside the job ends it; a handler that waits can deadlock on `Popen`'s waitpid lock held by the interrupted wait (probe_r19_b1_orphan_reap; probe_announce_rules L13, L14).
- The child's env is the recipe's `env` over the job's. Reason: condor's `CUDA_VISIBLE_DEVICES` and an image's `PATH` must reach it (L15).
- B2 wording only: the placeholder lives in `launch._stage` (driver-only argument); the DAG-dir announce secret is written 0600; the `job_root` check is stated as lexical with its consequence; `files()` runs after `_stage`; the killed-driver live leg is the DAG path.
