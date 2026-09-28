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
