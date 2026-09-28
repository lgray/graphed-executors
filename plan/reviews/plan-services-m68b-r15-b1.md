**NOT CLEAN**

# Review r15-B1: `plan-services.md` §3.3 part B1 (attached cluster hosting), delta round

Scope: the B1 delta between `reviews/plan-services-m68b-r14-b1-snapshot.md` and the plan, plus the minimum context around it. The delta covers:
- the "child's cwd holds only its inputs" bullet: the lpc `x509userproxy`, the skip of a missing input, the relative `{python}` rationale with L10, and the reserved-name/prefix refusal set (L439–452);
- the profile keys line, "attached: less `MY.SendCredential`" (L469);
- the B1 rows (L630–632): the refusal leg, the relative-`{python}` leg, and the `forget_announce`/stop spies;
- "Fails on (B1)" (L641–642).

B2 is not reviewed. m68a §3.1 is taken as given.

Snapshot: `reviews/plan-services-m68b-r15-b1-snapshot.md`, identical to the plan at review time. Line numbers below refer to it.
Code: graphed-executors main `c2298d7`.

## M30-B1 (job-file collisions): closed for the job's own names, but the prefix rule misses two of condor's entries

- **Closed for the job's own names.** The reserved set names every file `ServiceJob` transfers or creates in scratch:
  - `announce.py`, `service.json`, `graphed-secret` and `env.tgz` are transferred;
  - `service.sh` is the executable. On htcondor/mini 25.13.2 it lands in scratch under its own name, not as `condor_exec.exe`;
  - `env` is created by `service.sh`'s untar;
  - `service` is created by `announce.py`.
- **Most of condor's own files are covered.** The set applies on every profile. The prefixes `_condor_` and `.` cover `_condor_stdout`, `_condor_stderr`, `.job.ad` and `.machine.ad` (scratch listings below). The row's leg samples the set and has a control.
- **Incomplete: `tmp` and `var` (M32-B1).** "Begins with `_condor_` or `.` (condor's own scratch files)" claims to cover everything condor puts in scratch. Under `MOUNT_UNDER_SCRATCH` it also creates `tmp/` and `var/tmp/`.

## M31-B1 (relative `{python}`): closed

- **The leg discriminates.** The row gains a leg: `service.json.python = ./env/bin/python`, a symlink in the job dir to `sys.executable`. The leg passes only if the service announces.
  - If `announce.py` leaves the path relative, `Popen(cwd="service")` raises `FileNotFoundError`. The job then exits without announcing.
  - The rerun of `probe_announce_rules.py` shows this. L10: the child's argv[0] is `/tmp/m68b-rules-…/env/bin/python`, and the control raises `FileNotFoundError`.
- **One gap in the witness.** "The child's `argv[0]` is absolute" needs a way to read it that works on macOS, where the POSIX legs also run (`ci.yml` matrix). This is an exit item.

## The other delta items

- **The `x509userproxy` rationale is correct.** LPC's profile transfers `x509up_u{uid}` (`sites.py:51-53`). It stays in scratch, outside `service/`, so the child cannot serve it. It stays readable through `X509_USER_PROXY`. No code changes.
- **The missing-input skip matches the prototype** (`announce_proto.py:132`, `os.path.exists`). It is recorded as a round-8 decision.
- **The `forget_announce` spy closes the r14 exit item.** It sees the key forgotten on the timeout path and on the dead-child path, and before `ServiceJob.stop` on release. The only unwitnessed failure path left is `schedd.submit` raising. That is a code line the implementer already has, so it gets no finding.
- **Attached "less `MY.SendCredential`" is consistent with the row.** An attached job has no key, a watch-mode job keeps it, and a control checks the pilots' description.
- **Nothing in the delta contradicts the code or leaves a decision open, apart from M32-B1.**

## Design findings

**M32-B1 · L449–451 (the prefix rule and "condor's own scratch files") with L441–443 · the refusal set misses `tmp` and `var`. Under `MOUNT_UNDER_SCRATCH`, condor creates them in scratch and bind-mounts them over the job's `/tmp` and `/var/tmp`. An input with either name merges into condor's directory, and `announce.py` then moves it into `service/`. From then on the child's served cwd holds the job's whole `/tmp` (or `/var/tmp`).**

- **Measurement:** on htcondor/mini 25.13.2, `MOUNT_UNDER_SCRATCH = "/tmp,/var/tmp"` (the default).
  - **Container `r15b1-priv` (`--privileged`, so the starter can mount):**
    - Scratch holds `.job.ad .machine.ad _condor_stderr _condor_stdout <exe> tmp/ var/tmp/`.
    - `/proc/self/mountinfo` shows `…/scratch/tmp` mounted on `/tmp` and `…/scratch/var/tmp` on `/var/tmp`.
    - With `transfer_input_files = …/in/tmp`, the user's `tmp/f` landed inside condor's `tmp/`. The job then ran `mkdir service && mv tmp service/tmp` (what `announce.py` does for input `tmp`), which succeeded. It then wrote `/tmp/job-temp-file`, and `ls service/tmp` listed both `f` and `job-temp-file`.
  - **Container `r15b1-mini` (unprivileged, no mount namespace):** the same inputs only create plain `tmp/` and `var/` directories.
  - **Real sites:** the starter at LPC and lxplus runs as root, so the mounts are active there.
- **Why this changes code:**
  - The implementer writes the reserved set from L449–451. As written, it lets `tmp` and `var` through.
  - With either name as an input, whatever the job, the child or its libraries write to `/tmp` is served on the worker port. That breaks the bullet's own invariant ("the child's cwd holds only its inputs") and "Fails on (B1): … any file but the recipe's inputs in the service's cwd".
  - The fix is one more line of `ServiceJob` refusal: add `tmp` and `var` to the reserved names. They are condor's `MOUNT_UNDER_SCRATCH` roots. Refuse them on every profile, like the rest of the set.
- **Closed when:** L449–451 lists `tmp` and `var` among the refused basenames, with the reason (condor's `MOUNT_UNDER_SCRATCH` directories, bind-mounted over `/tmp` and `/var/tmp`). The parenthesis "condor's own scratch files" no longer implies the two prefixes are the whole set.
- **Test** (`test_cluster_service_job.py`, the refusal leg): an input named `tmp` is refused, naming the basename. Control: `models/` is still accepted.

## Exit items

These are appended under "## r15-B1 exit items" in `m68b-exit-items.md`.

## Evidence

- **Snapshot:** `reviews/plan-services-m68b-r15-b1-snapshot.md`.
- **`probe_announce_rules.py`, re-run** in `/tmp/claude-0/review-r15-b1/rules.txt`. L1–L10 match the committed `.txt`, apart from pids, timings and paths. L10: argv[0] is absolute, and the control raises `FileNotFoundError`.
- **htcondor/mini 25.13.2:**
  - `r15b1-mini`: the scratch listing, with the executable keeping its name, and `TMPDIR`=scratch.
  - `r15b1-priv`: the `tmp`/`var/tmp` bind mounts and the `tmp` input moved into `service/` exposing `/tmp`.
  - Both containers were removed, and no processes are left.
- **Code:** `sites.py:51-53,74`, `announce_proto.py:100,130-133`, `.github/workflows/ci.yml:41,61`.
