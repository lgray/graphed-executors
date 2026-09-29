"""m68b r23-B1 review probe: the round-17 reuse of m68a's `_submit`/`_remove` for a `ServiceJob`, and the new
`CondorPilots.start` line on the in-job driver's `log_dir`, on executors 0e48380 plus that one line.

  S        a spooled profile; `CondorPilots.start` from A with log_dir="logs"; from B, a ServiceJob-shaped job
           (`service-k/` under `launcher.log_dir`, absolute `initialdir`/`executable`, CondorPilots' base keys) whose
           script prints and exits 3, submitted through `launcher._submit` on its own ExitStack (`with` + `pop_all`);
           once it completed (JobStatus 4, still queued: spooled), `stack.close()`: does `service.out` reach
           `service-k/`, and does the job leave the queue?
  control  the same job ended by a bare `act(Remove)` (no retrieve): `service.out` does not come back (L-07).
  N        `log_dir` shaped as driverless writes `run["log_dir"]` (`str(Path(os.path.abspath(x)) / "pilots")`),
           `start()`ed from another cwd: does the new line change it?
Run: htcondor/mini:25.13.2-el9 (container r23r-mini, removed), as submituser, /opt/venv/bin/python 3.12 with
htcondor 25.13.2 and graphed 0.0.6 overlaid with d0ad16b python/graphed, PYTHONPATH=/code/src (a scratch worktree of executors 0e48380 with the round-17
line in `CondorPilots.start`):  python probe_r23r_b1_remove_reuse.py
"""
import contextlib
import dataclasses
import os
import shutil
import time
from pathlib import Path

import htcondor2 as htc
import graphed_executors.htcondor_backend.launch as launch
from graphed_executors.htcondor_backend.launch import CondorPilots
from graphed_executors.htcondor_backend.sites import SITES, counts_as_alive

print("# launch.py from", launch.__file__)
root = Path(os.path.expanduser("~")) / "r23r"
shutil.rmtree(root, ignore_errors=True)
A, B, C = (root / n for n in "ABC")
for d in (A, B, C):
    d.mkdir(parents=True)
schedd = htc.Schedd()
SPOOLED = dataclasses.replace(SITES["generic"], spool=True, ship_env=False)


def started(profile, log_dir, cwd):
    os.chdir(cwd)
    p = CondorPilots(profile, log_dir=log_dir)
    p.start("http://127.0.0.1:1", b"\0" * 32, 1)
    schedd.act(htc.JobAction.Remove, f"ClusterId == {p.cluster[1]}")
    return p


def service_job(p, key):
    d = Path(p.log_dir) / f"service-{key}"
    d.mkdir(exist_ok=False)
    (d / "service.sh").write_text("#!/bin/sh\necho announce-exited-3\necho why >&2\nexit 3\n")
    (d / "service.sh").chmod(0o755)
    base = p.submit_description("", 1)
    desc = {k: base[k] for k in ("universe", "should_transfer_files", "when_to_transfer_output",
                                 "transfer_output_files")}
    desc.update({"executable": str(d / "service.sh"), "initialdir": str(d), "arguments": "service.json",
                 "output": "service.out", "error": "service.err", "log": "service.log", "request_memory": "16",
                 "JobBatchName": f"graphed-service-{key}"})
    with contextlib.ExitStack() as st:
        result = p._submit(htc, p._schedd, desc, 1, st)
        stack = st.pop_all()
    return d, f"ClusterId == {int(result.cluster())}", stack


def wait_status(constraint, want):
    for _ in range(120):
        q = schedd.query(constraint, ["JobStatus", "HoldReasonCode", "Iwd", "SUBMIT_Iwd"])
        if q and q[0].get("JobStatus") == want:
            return dict(q[0])
        time.sleep(1)
    return {"timeout": q and dict(q[0])}


def gone(constraint):
    for _ in range(30):
        if not schedd.query(constraint, ["JobStatus"]):
            return True
        time.sleep(1)
    return False


p = started(SPOOLED, "logs", A)
print(f"S log_dir {str(p.log_dir)!r} (profile spool={p.profile.spool})")
os.chdir(B)
for case in ("S", "control"):
    d, constraint, stack = service_job(p, case)
    ad = wait_status(constraint, 4)
    alive = counts_as_alive(ad) if "JobStatus" in ad else None
    if case == "S":
        stack.close()
    else:
        schedd.act(htc.JobAction.Remove, constraint)
    out = (d / "service.out").read_text().strip() if (d / "service.out").exists() else None
    err = (d / "service.err").read_text().strip() if (d / "service.err").exists() else None
    print(f"{case:7s} completed ad {ad} counts_as_alive {alive} | after close: left queue {gone(constraint)}"
          f" | service-{case}/service.out {out!r} service.err {err!r}")
    stack.close()  # a second close is a no-op (the control's removal ran already)
p.stop()

UNSPOOLED = dataclasses.replace(SITES["generic"], spool=False, ship_env=False)
for x in ("logs", "a/../logs2", "./logs3/"):
    os.chdir(A)
    run_log_dir = str(Path(os.path.abspath(x)) / "pilots")  # driverless: out = Path(abspath(log_dir)); run.json
    q = started(UNSPOOLED, run_log_dir, C)
    print(f"N x={x!r}: run['log_dir'] {run_log_dir!r} | after start from C {str(q.log_dir)!r}"
          f" | unchanged {str(q.log_dir) == run_log_dir}")
    q.stop()
