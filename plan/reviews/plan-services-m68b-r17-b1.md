**NOT CLEAN**

# Review r17-B1: `plan-services.md` §3.3 part B1 (attached cluster hosting), whole-part read after the redesign

## Scope
- **Read in full:** the §3.3 preamble and the ladder rows tagged B1 (L415–431), and the shared subsection "HTCondor behaviour relied on", as it binds B1 (L432–451). Also B1 (L453–567), the frozen harness and the three B1 rows (L684–696), "Fails on (B1)" (L700–709), the B1 commits (L716–720), and D2/D3/D10 (L36–53, L54–59, L107–123).
- **Read where B1 touches it:** B2 (the `ServiceJob(..., watch=).files` use) and m68a §3.1 (recipes, `ServiceSet`, `htcondor_backend/` lines).
- **Snapshot:** `reviews/plan-services-m68b-r17-b1-snapshot.md`, identical to the plan at review time.
- **Code:** graphed-executors main `c2298d7` (`htcondor_backend/launch.py`, `server.py`).
- **Matrix:** `probes/m68b/condor_surface/{NEEDS,RESULTS}.md`, `probe_surface_submit.txt`, `probe_input_dir.{py,txt}`, `announce_proto.py` and `probe_announce_rules.txt`.
- **New evidence:** `probes/m68b/probe_r17_b1_{input_exec,comma}.{py,txt}`, from htcondor/mini 25.13.2 in container `r17b1-mini`, which has been removed.

Three design findings: M34-B1, M35-B1 and M36-B1. The exit items are appended under "## r17-B1 exit items" in `m68b-exit-items.md`.

## What holds
- **The input-only `service/` rule is sound on the pool.** The submit-side mirror (file inputs as symlinks, directory inputs as real trees of file symlinks, one transferred `dir/service`) lands intact, unspooled and spooled (`probe_input_dir.txt` mirror-plain/-spool).
  - A top-level or nested file symlink arrives as a regular file (S-07, `probe_surface_submit.txt` S5).
  - An empty directory in the tree lands.
  - An executable input keeps its mode through the symlink and runs from `service/` (`probe_r17_b1_input_exec.txt`).
  - A directory symlink is what holds a job (S-08, S5a/S5b; `probe_input_dir.txt` linkdir). The mirror plus the refusal covers it.
  - `.machine.ad`, `service.json` and similar inputs land in `service/` and replace nothing (S-12 via `probe_input_dir.txt`).
- **Every not-assumable knob in the shared table is met per job as stated.** This covers `MachineMaxVacateTime` (job_max_vacate_time 30), the scratch layout (cwd-derived paths), a job PATH (no `sys.executable`), and credd (dropped on attached).
- **The B1 rows' HTCondor citations match RESULTS.** S-03 (initialdir before submit, `exist_ok=False` dir), S-04 (no assumed `service.out`), S-05, L-02, L-09 (`HoldReason` only when condor set it), S-18 (a 2-GPU request idles, no hold), S-16 (the quoted `SingularityImage`) and S-01 (absolute executable) all agree with what RESULTS observed.
- **The `/announce` route is consistent with `server.py`.** It is routed before `pickle.loads` (`server.py:274-283` today unpickles every signed body), uses its own `Condition`, and keeps `lease` unchanged.
- **`lease_s`/`beat_s` are defined.** They are `LEASE_S=30`/`POLL_S=10` (`server.py:38-39`).
- **The spooled `stop()` retrieve matches `CondorPilots.stop`** (`launch.py:263-276`).
- **D2/D3/D10 agree with B1.** This covers the scheme minted by the check, the per-call key `f"{scope}-{token}"`, `host_service` returning only after the in-job self-check, and each release registered as its acquisition returns. The "before spool" registration inside `launcher._submit` is already a standing exit item (m68b-exit-items L36).
- **Commit sizes are within the 2k limit.** B1-0 is ~750 and B1-1 is ~790, which is plausible for `services.py` ~230, `announce.py` ~130, server +60, backend +30, `service.sh` and CI.

## M34-B1: argv[0] "made absolute" uses the wrong base for an input, and a `Popen` that raises has no outcome
- **Where.** L472–477: "resolves the child's `argv[0]` and `{python}` without its own `sys.executable` … a name with a separator is made absolute". L495: "the argv names each input by its basename, relative to `service/`". Also "Fails on" L707–708.
- **Why it changes code.** The two rules refer to two directories.
  - `{python}` (`./env/bin/python`) lives in the job dir. That is where `service.sh` unpacks `env.tgz` and where `announce.py`'s cwd, and so `os.path.abspath`, points.
  - A recipe's own executable input (argv `("./serve.sh", "{port}")`, `inputs=("serve.sh",)`) lives in `service/`, which L495 says argv names are relative to.
  - Applying L474–475's rule to such an argv[0] gives `<job>/serve.sh`, which does not exist, and `Popen` raises `FileNotFoundError`. Left alone, POSIX `Popen(cwd="service")` resolves it correctly.
  - The implementer must invent the split: resolve `{python}` against the job dir before rendering, and leave a literal argv[0] with a separator relative to `service/` or make it absolute against `service/`.
  - The plan also gives `announce.py` no outcome for `Popen` raising (missing or non-executable argv[0], a bare name `which` did not find). The prototype (`announce_proto.py` `start`) lets the exception escape, so the job exits 1 with a traceback, not the plan's "exit 3 naming" convention.
- **Measurement.** `probe_r17_b1_input_exec.txt`:
  - On the pool, `service/serve.sh` (a mirrored symlink to an 0755 file) lands executable and `cd service && ./serve.sh` runs, unspooled and spooled.
  - Locally, the plan's rule turns `./serve.sh` into `<job>/serve.sh` (absent), and `Popen` raises `FileNotFoundError`.
  - Control: the same argv[0] left relative with `cwd=service/` runs.
  - Probe L10 (`probe_announce_rules.txt`) covers only `{python}`.
- **Closed when.** B1 says:
  - `{python}` is resolved against the job dir (a separator → absolute there; bare → `shutil.which` on `$PATH`/`os.defpath`, else bare) before rendering.
  - A literal argv[0] with a separator is resolved against `service/`, the child's cwd, where the argv's inputs are.
  - A `Popen` that raises exits 3 naming argv[0] and the error.
- **Test.** In `test_cluster_service_job.py` subprocess legs:
  - A spec with `inputs=("serve.sh",)` (an executable script that `exec`s `python3 -m http.server "$1"`) and argv `("./serve.sh", "{port}")` announces.
  - A spec whose argv[0] is `./missing` exits 3 naming `./missing` within a few seconds, with no traceback exit 1.

## M35-B1: the live witness "run 2's task `GET /service.json` returns a `key` carrying run 2's `run_nonce`" cannot pass
- **Where.** L696, `test_cluster_services_live.py` (a): "two sequential runs on one runner each get their own service cluster, and run 2's task `GET /service.json` returns a `key` carrying run 2's `run_nonce`".
- **Why it changes code.** This witness predates the redesign (exit item r12-B1, m68b-exit-items L123), when the child served scratch.
  - Now the child's cwd is `service/`, which holds exactly the recipe's inputs (L461–480).
  - `service.json` is the job's own file in scratch, never in `service/`. An input of that name lands in `service/` and replaces nothing, but it is the user's file and carries no key.
  - The key is minted per `host_service` call, so no spec can carry it as an input.
  - `GET /service.json` against `recipes.http_server` therefore answers 404, and the leg fails whatever the implementation does.
  - The test author must invent another way to show that run 2's task reached run 2's child.
- **Measurement.** `probe_input_dir.txt` mirror-plain: `service/` lists only the inputs, and the job's `service.json` stays outside it. `probe_announce_rules.txt` L9: `GET` of a job-dir file → 404, an input → 200. B1 L472–477: `cwd=service/`.
- **Closed when.** L696 replaces the witness with one that discriminates under `service/`. For example, the task records its `GET` time, and history then shows:
  - run 1's service cluster (`JobBatchName` `graphed-service-<run 1 key>`) left the queue before that time;
  - run 2's (`JobBatchName` carrying run 2's `run_nonce`) was running at that time (`JobCurrentStartDate` ≤ t ≤ its `CompletionDate`/`EnteredCurrentStatus`).
  - Or any other witness that does not read a scratch file through the service.
- **Test.** The amended L696 leg. As a control, the old `GET /service.json` now returns 404, so the replacement is not vacuous.

## M36-B1: the `,` refusal guards the inputs, which the mirror makes safe, not the paths the list actually names
- **Where.** L479–480 (refusal: "a path containing `,` (the list separator, S-09)"), L493 (`transfer_input_files=…[,<launcher.log_dir>/env.tgz][,<dir>/service]`, absolute), row L695 (the refusal leg), and "Fails on" L709.
- **Why it changes code.**
  - Under the mirror, no input path is ever an entry of `transfer_input_files`. The list names `dir/service` only, and condor walks the directory, so an input or a nested file with a `,` in its name transfers intact.
  - The entries that can split are the absolute `<launcher.log_dir>/env.tgz` and `<dir>/service`, with `<dir>` = `<launcher.log_dir>/service-<key>`. A `launcher.log_dir` containing `,` holds the `ServiceJob` 13 at input transfer, which surfaces only as `host_service`'s `RuntimeError` after a submit.
  - m66's pilots are unaffected here because they list the secret and `env.tgz` by relative name (`launch.py:149`). Their absolute `user_modules` are what B2's `,` refusal covers.
  - The implementer must change which path is checked, or how the list names it. Entries relative to `initialdir` (`service`, `../env.tgz`) or a refusal of a `,` in `launcher.log_dir` both close it.
- **Measurement.** `probe_r17_b1_comma.txt` (htcondor/mini 25.13.2):
  - (A) inputs `d,ir/f,1` and `w,t` inside the mirrored `service/`, list `<dir>/service`: the job ran and all of them landed.
  - (B) the job dir under `~/log,dir/`, list the absolute `<dir>/service`: held, "2 total failures".
  - (C) the same dir, list the relative `service` (resolved against `initialdir`): the job ran.
  - S-09 (`probe_surface_submit.txt` S5c) remains the right row, but for the listed paths.
- **Closed when.** B1 names every `transfer_input_files` entry of a `ServiceJob` relative to its `initialdir`, or refuses at construction a `launcher.log_dir` containing `,`, naming it. The input-path refusal is either dropped or kept with its reason restated. It is no longer an S-09 hold, and a refusal kept without a hazard should say so. "Fails on" L709 follows.
- **Test.** L695's refusal leg:
  - The `,` case moves to the listed paths: either every entry of `transfer_input_files` is relative (no `os.sep`-rooted entry), or a launcher whose `log_dir` contains `,` is refused naming it.
  - If the input refusal is dropped: an input named `a,b` is accepted and lands as `service/a,b`.

## Evidence
- `probes/m68b/probe_r17_b1_input_exec.{py,txt}` (M34-B1)
- `probes/m68b/probe_r17_b1_comma.{py,txt}` (M36-B1)
- Container `r17b1-mini`, started and removed. Scratch was `/tmp/claude-0/review-r17-b1/`.
