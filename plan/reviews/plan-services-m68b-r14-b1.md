**NOT CLEAN**

# Review r14-B1: `plan-services.md` §3.3 part B1 (attached cluster hosting), delta round

Scope: the B1 delta between `reviews/plan-services-m68b-r13-b1-snapshot.md` and the plan, plus the minimum context around it. The delta covers:
- the §3.3 preamble, where the pool line moves to commit 1 (L420–422);
- the new "child's cwd holds only its inputs" bullet (L440–446);
- the profile keys less `MY.SendCredential`, and `service.json.inputs` (L463–465);
- `/announce`'s 403 for a body that is not UTF-8 or is empty (L507–508);
- the forget-on-failure and the release order (L524–526);
- the site check (1) additions (L604–605);
- the B1 rows (L621–622), "Fails on (B1)" (L627–630) and commit 1 (L636–637).

B2 is not reviewed. m68a §3.1 is taken as given.

Snapshot: `reviews/plan-services-m68b-r14-b1-snapshot.md`, identical to the plan at review time. Line numbers below refer to it.
Code: graphed-executors main `c2298d7`.

## M29-B1: closed at its cause

The plan fixes the cause in two independent ways:
- **The child's cwd holds only its inputs (L440–446).** `announce.py` creates `service/`, moves each input (by its basename from `service.json.inputs`) into it, and starts the child there. The prototype does this (`announce_proto.py` `main`: `makedirs`, `os.rename`, `Popen(..., cwd=RUN_DIR)`).
  - I re-ran `probe_announce_rules.py` locally. It reproduces L1–L9 as recorded, including L9: `GET /user.cc` → 404 and `GET /models/m.txt` → 200.
  - This also covers LPC. LPC's profile carries `x509userproxy` (`sites.py:51-53`) and LPC has `"cluster"`, so condor puts the grid proxy in scratch. The plan does not name this case (exit item).
- **`ServiceJob` drops `MY.SendCredential` (L445–446, L463).** That is the only credential key lxplus has (`sites.py:74`).
  - Site check (1) (L604–605) records that the job is accepted and starts without the key, and runs `ls -a` on scratch and on `service/`. This is the owner-site measurement r13 asked for.
- **The unlink order still holds under the new layout.** `announce.py` unlinks `graphed-secret` before it moves anything or starts the child. The row's `../graphed-secret` check now points at the right place, the job dir above `service/`.

## The other delta items

- **The absolute `{python}` is needed and correct.** On POSIX, `Popen` with `cwd=` resolves a relative `args[0]` against the new cwd. So `./env/bin/python` (`launch.py:215`, the `ship_env` case) would miss inside `service/`. `abspath` taken from scratch is right, and `python3` (no separator) is left for PATH. It is unwitnessed, though (M31-B1).
- **403 on a body that is not UTF-8 or is empty is consistent.** Without a key there is no secret to verify against. It matches the rest of the route: key → secret → 403 before any 400. Today's `do_POST` (`server.py:273-285`) reads `Content-Length` bytes, so an empty body is reachable.
- **The release/forget order closes the r13 window.** `release_service` forgets the key first, then calls `stop()`, then pops the record. A beat after the forget gets 403, which is also the orphan rule, so `announce.py` exits 0.
  - Every failure path now forgets the key, including `schedd.submit` raising.
  - "Fails on" names it, but no row witnesses it (exit item).
- **The basename refusals are incomplete (M30-B1).**
- **The pool line moving to commit 1 creates no contradiction.** B1's timeout leg asks for 2 GPUs, which the pool never matches.

## Design findings

**M30-B1 · L444 (the refusal set) with L449–451 (`transfer_input_files`) · the refusal covers `service` and duplicate basenames among the inputs, but not an input that collides with the job's own transferred names. Condor lets the later file silently replace the earlier one.**

- **Measurement:** on htcondor/mini (container `r14b1-mini`, removed after), a job with `transfer_input_files = service.json,/work/u/service.json` started, exited 0, and `cat service.json` in scratch printed the user's file. There was no hold and no error.
- **Why this changes code:**
  - `ServiceJob` puts `announce.py`, `service.json`, `graphed-secret` and, on `ship_env`, `env.tgz` in the same list as the inputs.
  - A recipe input with one of those basenames replaces the job's own file:
    - the job then runs the user's `announce.py`;
    - or it reads the user's JSON as its config;
    - or it announces with the wrong secret, gets 403 and exits 0 as an orphan;
    - or it unpacks a foreign `env.tgz`.
  - The new move-by-basename step adds one more collision. `service.sh` untars `env.tgz` into `./env` in scratch. If an input is named `env`, `tar` merges into it, `announce.py` then moves `env/` into `service/`, and the absolute `{python}` (`<scratch>/env/bin/python`) no longer exists. `Popen` then raises `FileNotFoundError`, which is a traceback exit and not the plan's exit 3.
  - The implementer has to decide the reserved set. As written, they will refuse only `service`.
- **Closed when:** L444 says `ServiceJob` refuses, naming it, any input whose basename is one of the job's own names: `service`, `service.sh`, `announce.py`, `service.json`, `graphed-secret`, `env.tgz` and `env`. Refuse these on every profile, or `env.tgz`/`env` only on `ship_env`; the plan picks one. "Fails on (B1)" gains "an input that replaces a job file".
- **Test** (`test_cluster_service_job.py`, the refusal leg): add an input named `service.json`, and one named `env` on a `ship_env` copy. Each is refused naming the basename. Control: `models/` is accepted.

**M31-B1 · L443 ("a relative `{python}` made absolute") with row L622 · no test runs a relative `{python}`, so an `announce.py` that leaves `./env/bin/python` relative passes the whole frozen suite, yet it fails every image-less service on LPC and lxplus.**

- **Measurement:**
  - Every subprocess leg uses the spec `{python} -m http.server {port}`. The probe's `python` is `sys.executable`, which is absolute (`probe_announce_rules.py` `cfg`).
  - The live file runs on `generic`, where `ship_env=False` (`sites.py:84-86`), so its `python` is also absolute.
  - The only relative case is `ship_env` (`launch.py:215`), which runs only at LPC and lxplus. Site check (1) runs Triton, which is imaged and uses `python3`, so it does not exercise that case either.
  - Popen resolves a relative `args[0]` against `cwd=` on POSIX. Without the `abspath`, the child fails to start.
- **Why this changes code:** the test author writes a leg that is not in the row today.
- **Closed when:** row L622 gains a subprocess leg. In it, `service.json.python` is `./env/bin/python`, a symlink in the job dir pointing at `sys.executable`, and the spec is `{python} -m http.server {port}`. The leg announces, and the child's `argv[0]` is absolute. Control: the same leg with a prototype that drops the `abspath` exits without announcing.

## Exit items

These are appended under "## r14-B1 exit items" in `m68b-exit-items.md`.

## Evidence

- **Snapshot:** `reviews/plan-services-m68b-r14-b1-snapshot.md`.
- **`probe_announce_rules.py`, re-run** in `/tmp/claude-0/review-r14-b1/rules.txt`. L1–L9 match the committed `.txt`, apart from pids, timings and ports.
- **Duplicate-basename check:** htcondor/mini, container `r14b1-mini`. The job was `transfer_input_files = service.json,/work/u/service.json`. Scratch listing: `.job.ad .machine.ad _condor_stderr _condor_stdout service.json x.sh`; `service.json` contents: `user`; exit code 0. The container was removed.
- **Code:** `sites.py:51-53,74,84-86`, `launch.py:215-218`, `server.py:273-285`.
