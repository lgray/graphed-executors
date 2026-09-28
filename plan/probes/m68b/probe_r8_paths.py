"""r8 review probe (minicondor): path resolution the m68b plan leaves implicit.
 E  a relative `executable` with `initialdir` set, submitted from another cwd: resolved against cwd or initialdir?
 D  Submit.from_dag(<abs run.dag>) submitted from a cwd != the DAG dir, run.dag naming `driver.sub` relatively:
    (D1) as is; (D2) with options {"usedagdir": True}; (D3) run.dag naming the node .sub by absolute path.
"""
import os, shutil, time
import htcondor2 as htc

schedd = htc.Schedd()
H = os.path.expanduser("~")
print("condor", htc.version())

def wait_gone(q, t=120):
    end = time.monotonic() + t
    while time.monotonic() < end and schedd.query(q, ["ClusterId"]):
        time.sleep(2)

def hist(c, attrs):
    r = list(schedd.history("ClusterId == %d" % c, attrs, match=1))
    return {a: r[0].get(a) for a in attrs} if r else None

# ---- E ----
d = os.path.join(H, "r8-exe"); shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
open(os.path.join(d, "svc.sh"), "w").write("#!/bin/sh\necho ran-from-initialdir-script\n")
os.chmod(os.path.join(d, "svc.sh"), 0o755)
os.chdir(H)
try:
    c = schedd.submit(htc.Submit({"universe": "vanilla", "executable": "svc.sh", "initialdir": d,
                                  "output": "o.txt", "error": "e.txt", "log": "l.log",
                                  "should_transfer_files": "YES", "request_memory": "64"})).cluster()
    wait_gone("ClusterId == %d" % c, 90)
    print("E relative executable, initialdir=%s, cwd=%s -> cluster %d" % (d, H, c), hist(c, ["JobStatus", "ExitCode", "Cmd", "HoldReason"]))
    q = schedd.query("ClusterId == %d" % c, ["JobStatus", "HoldReason", "Cmd"])
    if q:
        print("E still queued:", dict(q[0])); schedd.act(htc.JobAction.Remove, "ClusterId == %d" % c)
    print("E output:", open(os.path.join(d, "o.txt")).read().strip() if os.path.exists(os.path.join(d, "o.txt")) else None)
except Exception as exc:
    print("E submit raised:", repr(exc)[:300])

# ---- D ----
def dag(tag, opts, absolute):
    d = os.path.join(H, "r8-dag-" + tag); shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
    open(os.path.join(d, "driver.sub"), "w").write(
        "universe = vanilla\nexecutable = /bin/echo\narguments = hi\ninitialdir = %s\noutput = drv.out\n"
        "log = nodes.log\nshould_transfer_files = YES\nrequest_memory = 64\nqueue\n" % d)
    sub = os.path.join(d, "driver.sub") if absolute else "driver.sub"
    open(os.path.join(d, "run.dag"), "w").write("JOB driver %s\n" % sub)
    os.chdir(H)
    try:
        desc = htc.Submit.from_dag(os.path.join(d, "run.dag"), opts)
        c = schedd.submit(desc).cluster()
    except Exception as exc:
        print("D%s raised: %r" % (tag, exc)); return
    wait_gone("ClusterId == %d || DAGManJobId == %d" % (c, c), 120)
    h = hist(c, ["JobStatus", "ExitCode", "Iwd"])
    nodes = list(schedd.history("DAGManJobId == %d" % c, ["ClusterId", "ExitCode"], match=5))
    out = os.path.join(d, "drv.out")
    tail = open(os.path.join(d, "run.dag.dagman.out")).read().splitlines() if os.path.exists(os.path.join(d, "run.dag.dagman.out")) else []
    err = [l for l in tail if "ERROR" in l or "rror" in l][:3]
    print("D%s opts=%s abs_sub=%s cwd=%s -> DAGMan %s nodes=%d drv.out=%r errors=%s" % (
        tag, opts, absolute, H, h, len(nodes), open(out).read().strip() if os.path.exists(out) else None, err))

dag("1", {}, False)
dag("2", {"usedagdir": True}, False)
dag("3", {}, True)
