**CLEAN**

# Review r15-B2: plan-services.md §3.3 part B2, delta round

Snapshot: `plan/reviews/plan-services-m68b-r15-b2-snapshot.md`. Delta against `plan-services-m68b-r14-b2-snapshot.md`
(four hunks, +22/−12). Scope: B2's delta plus the context it needs. That is B1's changed `service/`, reserved-name and
`MY.SendCredential` lines where B2's `svc<i>.sub` inherits them, the DAG files paragraph, site check (2), the B2 row
and "Fails on (B2)". B1 and m68a's §3.1 are taken as written. Code: graphed-executors `c2298d7`. No probe was needed
and no container was started.

## Checked and holding

**M43-B2 is closed at its cause.**
- B1 (L450-452, L469) now scopes the drop: "An attached `ServiceJob` drops `MY.SendCredential` … a watch-mode one
  (B2) keeps it". B2 (L560-562) says `svc<i>.sub` keeps the profile's `MY.SendCredential` and why: the node reads
  `dag_dir` every second, `dag_dir` is AFS on lxplus, and `service/` keeps the ticket cache out of the served cwd. The
  round-8 decision records it.
- On lxplus the profile value is `"True"` (`sites.py:74`), so `svc0.sub` carries `MY.SendCredential = True`.
  `driver.sub` keeps it through `submit_description` (`launch.py:170`), which the driver job needs to write `dag_dir`.
- The credential assertions agree:
  - B1's row: no key on an attached `ServiceJob` on `SITES["lxplus"]` ("a watch-mode one keeps it").
  - B2's row: `svc0.sub` carries it on `replace(SITES["lxplus"], job_root=<tmp>)`.
  - "Fails on (B2)": "a SERVICE node without the credential its `dag_dir` needs".
- These assertions discriminate. An implementation that drops the key in both modes fails B2's row. One that keeps it
  in both fails B1's.
- Site check (2) records the SERVICE node's `klist` and `ls -a` of `service/`, as the closure asked. How the owner
  gets that shell in the Triton image is an exit item.

**`periodic_remove` placement.** "Just before the launcher's `extra_submit`, which may override it" sets the
precedence, as the r14 exit item asked. B1's `files()` already applies `extra_submit` last (L469-470), so B2 re-applies
it after its own key: `{**keys, "periodic_remove": …, **extra_submit}`. That is idempotent and the key order does not
matter in a submit file. Neither the profiles (`sites.py`) nor `CondorPilots`' base keys (`launch.py:150-166`) set
`periodic_remove`, so nothing but `extra_submit` can override it. No row pins the override. That is acceptable for a
user opt-out and not needed for any "Fails on" line.

**The reserved-name refusal against B2's files.**
- The reserved basenames (`service`, `service.sh`, `service.json`, `announce.py`, `graphed-secret`, `env.tgz`, `env`,
  `_condor_*`, `.*`) name files in the node's scratch dir. B2's own names live in the DAG dir or its
  `service-svc<i>/` initialdir, and none is transferred under a colliding basename:
  - `svc<i>.sub`, `service-svc<i>/`, `run.dag`, `driver.url` and `driver.sub`.
  - The DAG dir's `graphed-secret`, read in place through `watch`.
- The node's `env.tgz` is `<launcher.log_dir>/env.tgz`, the DAG dir's own copy written by `_stage(out, …)`
  (`driverless.py:205`). It is not a user input.
- B2's input refusals (outside `job_root`) and the reserved-name refusal are independent checks on the same recipe
  inputs. Neither contradicts the other.
- Where the refusal fires on the DAG path (constructor or `files()`, never `submit()` alone) is not stated. That is an
  exit item.

**"Fails on" and commits.** The new B2 clause has a witness (the lxplus leg). No figure, commit or §6/§7/§8/§9 line
changed in the delta. §7's totals are unaffected.

## Design findings

None.

## Not raised (exit items)
These are under "## r15-B2 exit items" in `plan/reviews/m68b-exit-items.md`:
- The lxplus leg's setup: `image=`, a fake venv and a GPU spec.
- `submit` without spool asserted on the `spool=True` lxplus copy, since generic cannot discriminate.
- Site check (2)'s `klist` in the Triton image: how the owner gets the shell, and what to record if the image has no
  krb5 tools.
- Where the reserved-name refusal fires on the DAG path.
- Round-7 decision 1 superseded by round 8.

## Cleanup
No container or background process was started, and no `r15b2-` containers exist. The scratch dir
`/tmp/claude-0/review-r15-b2/` was not used. Nothing was committed and the plan was not edited.
