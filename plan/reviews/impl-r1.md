# m66 implementation review, round 1: PR graphed-executors#34 at 89a2eac (`freeze-m66..origin/lane/htcondor`)

**Verdict: 3 design findings: 1 High, 1 Medium, 1 Low.** Not APPROVE-READY.

Checked and clean, each by a probe or a read, no finding:
- **Intent.** Frozen m66 passes on macOS with LocalPilots: 49 passed; the live pool did not run here (no bindings).
  - A cancelled dependency fails its combine with `CancelledError`, whether the combine was submitted before
    or after the cancel.
  - 300 dependents submitted from leaf done-callbacks on 4 pilots all settle correctly (0.3 s), with no deadlock.
- **Security.** `do_POST` is the only handler, and it compares the HMAC before `pickle.loads` on every path.
  `compare_digest` is used. The secret travels only as a 0600 file, and `log_message` is silenced.
- **State machine.** `started` guards the one-time RUNNING transition, and `requeued` allows one requeue.
  `WorkerLost(key, pilot)`. When closed, `beat` returns False, so `/next` and `/beat` answer 410. Every
  `settle` runs after the lock is released.
- **Launcher.** All five `WEIGHT_ATTRS` are present in the recorded LPC ads. Failover, `Collector.locate`,
  spool, retrieve and remove are all present, and CI 8(b) is green. The executable path is absolute, and the
  refusals run before `_htcondor()`. The tar also runs before it, which frozen `test_start_ships_a_non_editable_env_and_a_private_secret`
  pins.
- **Proportion.** I searched every module and found nothing oversized and no guard for an unreachable
  state. Each guard found has a reachable trigger: cancel/close for `settle`, a driver-unimportable result
  for `result`, and a direct-backend lambda for `add`.

## Findings

**H1: since 89a2eac, a pilot whose driver is gone holds its slot until its current task ends. That breaks
plan §2 ("Lost driver … exits 1"), and one docs claim is false.** The probe runs an 8.0 s task with
`LEASE_S=1` and shuts the server down: the pilot exits 1 **after 8.0 s**. Two statements are wrong for the
whole length of the task:
- `htcondor.rst` "When something goes wrong": "…so a crashed driver does not hold batch slots";
- the `pilot.py` docstring: "1 when the driver has been unreachable for a lease".

A hung task (for example, a stalled xrootd read) now holds its slot until the site's walltime. That is the
case the removed `os._exit` comment named. The change was made for the per-file gate.

Premise for the repair, measured: the pre-89a2eac `pilot.py` with today's tests puts `pilot.py` at **88%**
(frozen+extra, macOS; missing 46–51). A plain revert therefore fails the 90% gate. The retry branch in
`_Driver.post` needs a hit from a pilot that exits normally.

Decision (issuer): restore the plan's prompt exit mid-task. The other option would change the plan contract
and the docs to "after its current task".

Closing test: in an extra test, the server goes away while the pilot runs a task of at least 5×`LEASE_S`.
The pilot's return code is 1 before the task would have ended, and `pilot.py` stays at 90% or more per file.

**M1: the pilot id `hostname:pid` is not unique under PID namespaces, and a lost task then hangs silently.**
The LPC site check shows **pid 14 on both pilots** (apptainer `--pid`). Their ids were distinct only because
FERMIHTC rewrites the hostname per job. When two pilots share an id, the survivor's beats keep the dead
pilot's lease alive. The requeue never happens, and the no-pilots-left rule never fires.

Probe (`LEASE_S=1`, a DieOnce task, two pilots):
- distinct ids: the task is requeued and runs;
- the same id (patched `getpid`/`gethostname`): `live_pilots()==1`, and the task is still `RUNNING` after 10 s.

Closing test: two pilots with identical `hostname`/`pid` register as 2 live pilots, and a DieOnce task is
requeued to the survivor.

**L1: a non-ASCII `X-Graphed-Sig` raises `TypeError` in `compare_digest` outside `do_POST`'s try.** No
response is sent, and each such request prints a traceback on the driver's stderr. Nothing is unpickled, so
this is noise, not a bypass. Probe: `"00"` gets 403, and `"\xe9"` gets `RemoteDisconnected` plus the
traceback. Closing test: a POST with header byte `\xe9` gets 403 and prints nothing to stderr.

## Exit-round constraints (not findings)
- `backend.py`'s `N_WORKERS_WAIT_S` comment carries a measurement ("took 45 s"). The site check measured
  33.3 s and 116.3 s. State the reason and drop the figure.
- `retries` on `HTCondorRunner` and `htcondor_runner` has no effect, because `submit` ignores the hint at the
  floor. Say so in the `htcondor.rst` parameter table: the only retry is requeue-once.
- Once H1 is repaired, the `pilot.py` docstring and the htcondor.rst bullet must match the behaviour you
  choose.
- The journal/attempts figure "frozen-only ≈95–96%" should read 94.9% (see the table).

## Frozen-only coverage: an owner decision, not a finding

Commands: `pytest tests/frozen/m66 --cov --cov-config=.coveragerc-htcondor` with `COVERAGE_PROCESS_START`
(LocalPilots self-measure), then `coverage combine`, then `diff-cover --compare-branch=origin/main --include
'src/graphed_executors/htcondor_backend/**/*.py'`. Run on macOS at 89a2eac. The CI column is job 108005628950.

| file | frozen-only, macOS, line+branch (measured) | frozen-only diff lines, CI (inferred) | frozen+extra, CI (measured) |
|---|---|---|---|
| `__init__.py` | 100% | 6/6 = 100% | 100% |
| `sites.py` | 100% | 22/22 = 100% | 100% |
| `backend.py` | 92% | 85/87 = 97.7% | 96% |
| `launch.py` | 69% | 154/160 = 96.3% | 99% |
| `pilot.py` | **83%** | **65/75 = 86.7%** | 98% |
| `server.py` | 94% | 210/221 = 95.0% | 99% |
| **diff total** | 88% (503/571) | **542/571 = 94.9%** | 99% (566/571) |

- **CI-only live-pool lines** (frozen `test_htcondor_live_pool`, not runnable on macOS):
  - `launch.py` 41–42, 48, 207–215, 220–227, 231–234, 239–240 and 244–255;
  - `backend.py` 193 and 203–204 (the `htcondor_runner` facade).

  The inferred column credits these from the arguments of 8(a) (generic, `log_dir` given) and 8(b)
  (`COLLECTOR_HOST` query, spool). They are inferred, not measured.
- **Extra-only lines**: 24 lines in total.
  - `pilot.py` 47–49, 52–53, 69–70 and 97–99: the lost-driver path and the unpicklable exception;
  - `server.py` 90, 167, 197–198, 202, 211 and 215–216: bind exhausted, close with held tasks, cancelled
    queued task, idle poll timeout, stale result, unpicklable result;
  - `launch.py` 193 (the default `log_dir`), 228–230 and 235–236 (collector failover and no match).
- **Never covered**: `backend.py` 77 and 116; `server.py` 132–134.
- `pilot.py` is below the 90% per-file gate on frozen hits alone, whichever column you read.
