"""r21-B1: a ServiceJob's env.tgz link under a RELATIVE launcher.log_dir (CondorPilots keeps log_dir as given).
A: link target spelled as launcher.log_dir / "env.tgz" (relative) -> dangling -> the job at input transfer.
B: target os.path.abspath(...) -> the job runs (the positive control). m66 keeps a relative log_dir as given
(launch.py:127) and its own pilot path copes with it (launch.py:203-205: executable relative to the submitter's cwd,
initialdir relative likewise); only a symlink target spelled from it breaks. Pool: htcondor/mini 25.13.2."""
import os, time, tarfile, htcondor2 as htc
from pathlib import Path
base = Path(os.path.expanduser("~/r21b1-relink")); base.mkdir(exist_ok=True); os.chdir(base)
log_dir = Path("logs")                       # as CondorPilots(log_dir="logs") keeps it
log_dir.mkdir(exist_ok=True)
with tarfile.open(log_dir / "env.tgz", "w:gz") as t: t.add(__file__, arcname="env/marker")
schedd = htc.Schedd()
for case, target in (("A relative target", log_dir / "env.tgz"), ("B absolute target", Path(os.path.abspath(log_dir / "env.tgz")))):
    svc = log_dir / ("service-" + case[0]); svc.mkdir(exist_ok=True)
    link = svc / "env.tgz"
    if link.is_symlink(): link.unlink()
    os.symlink(target, link)
    (svc / "service.sh").write_text("#!/bin/sh\ntar xzf env.tgz && ls env\n"); (svc / "service.sh").chmod(0o755)
    r = schedd.submit(htc.Submit({"executable": os.path.abspath(svc / "service.sh"), "initialdir": str(svc),
        "transfer_input_files": "env.tgz", "should_transfer_files": "YES", "output": "service.out",
        "error": "service.err", "log": "service.log", "request_memory": "16"}))
    cl = r.cluster(); ad = None
    for _ in range(60):
        q = schedd.query(f"ClusterId == {cl}", ["JobStatus", "HoldReasonCode", "HoldReason"])
        if q and q[0].get("JobStatus") == 5: ad = q[0]; break
        if not q: ad = next(iter(schedd.history(f"ClusterId == {cl}", ["JobStatus", "ExitCode"], match=1)), None); break
        time.sleep(1)
    print("%s: link -> %s, resolves on the submit side: %s; job: %s" % (case, os.readlink(link), link.exists(),
          {k: ad.get(k) for k in ("JobStatus", "ExitCode", "HoldReasonCode", "HoldReason")} if ad else None))
    schedd.act(htc.JobAction.Remove, f"ClusterId == {cl}")
