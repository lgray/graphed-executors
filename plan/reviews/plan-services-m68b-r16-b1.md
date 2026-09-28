**CLEAN**

# Review r16-B1: `plan-services.md` §3.3 part B1 (attached cluster hosting), delta round

## Scope
This round covers the B1 delta between `reviews/plan-services-m68b-r15-b1-snapshot.md` and the plan, with only the context needed to read it. The delta has three parts:
- **L445–452:** the reserved-name refusal moves to `ServiceJob`'s constructor. It adds `tmp`, `var` and the `x509up_u` prefix.
- **L634:** the refusal leg adds `tmp` and `x509up_u1000`, both refused at construction. The relative-`{python}` leg now reads argv[0] with `ps -o args= -p <pid>`.
- **L623:** a B2-owned lxplus probe line, which this review does not cover.

B2 is not reviewed. m68a §3.1 is taken as given.

Snapshot: `reviews/plan-services-m68b-r16-b1-snapshot.md`, identical to the plan at review time.

Code: graphed-executors main `c2298d7`.

## M32-B1: closed at its cause
- **The refusal set now covers condor's scratch roots.** It names `tmp` and `var` as condor's scratch entries and gives the right reason: under `MOUNT_UNDER_SCRATCH`, condor bind-mounts them over `/tmp` and `/var/tmp`. This matches r15's measurement on htcondor/mini 25.13.2.
  - An input `var` would merge into `scratch/var`, which holds `var/tmp`, so refusing the top-level name is the right unit.
- **The parenthesis no longer claims the prefixes are the whole set.** `_condor_` and `.` are now one entry among several.
- **The refusal happens before anything is written.** It sits in the constructor, so it runs before `submit()` creates `service-<key>/` and before B2's `files()` writes. The constructor has what it needs: `spec` carries the inputs, and the check runs on every profile, so it needs no profile field. The basename is taken after `abspath`, which drops a trailing separator (L467), so `models/` checks as `models`. This is consistent with the control.
- **The test is updated.** The row's refusal leg now includes `tmp` and says "refused at construction". Its control, `models/`, stands.

## `x509up_u` prefix: correct
- lpc's profile sets `x509userproxy = {home}/x509up_u{uid}` (`sites.py:53`), so the transferred basename always has this prefix. The rule and the leg's `x509up_u1000` match the code.

## The `ps`-based argv[0] read works
- **It works on both CI platforms.** `ps -o args=` is supported by both procps and BSD `ps`, so it works on the Linux and macOS rows of the matrix.
- **Measured here.** A child started as `<job>/service/../env/bin/python -m http.server` shows that absolute argv[0] in `ps` output. The job path is a symlink to `sys.executable`, and Python does not rewrite argv[0].
- **The leg still discriminates through the announce.** A relative path makes `Popen` raise, as the parenthesis now says.
- **The pid source is not named.** This is an exit item: the prototype's `ready pid=` log line or `pgrep -P` both work, so the test author faces no real design choice.

## Nothing new contradicts the code or leaves a decision open
- **The constructor refusal is a new failure path of `host_service`.** It comes after the announce secret is minted, because the constructor takes `secret=`. "Every failure path … calls `forget_announce([key])`" (L530–532) covers it as written, so this is only an exit item for the witness.
- **Observation for the B2 reviewer (not a B1 finding).** A watch-mode `ServiceJob` keeps `MY.SendCredential`. On lxplus, the ticket cache in scratch is `<user>.cc` (L440–441), and the reserved set does not name that basename. Attached jobs drop `SendCredential`, so B1 is not affected.

## Design findings
None.

## Exit items
Three items are appended under "## r16-B1 exit items" in `m68b-exit-items.md`:
1. The pid source for the argv[0] leg.
2. The constructor refusal's `forget_announce`, which no leg witnesses.
3. `tmp`/`var` assume the default `MOUNT_UNDER_SCRATCH`.

The section also records this round's `ps` evidence.

## Evidence
- The word diff between the r15-B1 snapshot and the plan.
- `sites.py:51-53`, `announce_proto.py:139`, `probe_announce_rules.py` L10 reader, and `probe_announce_rules.txt` L10.
- A local `ps -o args= -p` check in `/tmp/claude-0/review-r16-b1/`. The child process was killed and is confirmed gone.
- No container was started, and none with the `r16b1-` prefix exists.
