"""D-06/D-07 follow-up. (a) Can the DAG itself (not periodic_remove) make an idle or held SERVICE node at DAG end
harmless? Strictness is lowered per DAG through from_dag's ConfigFile or AddToEnv. (b) How fast does a held driver
node show up in the DAGMan ad's DAG_JobsHeld vs in a direct node query?
Same DAG shape as probe_surface_dagman.py (driver writes result.pkl and exits 0 after SLEEP s; svc0 sleeps).

Pool: `echo 'NUM_CPUS = 40' > /etc/condor/config.d/98-cpus` + `condor_restart -daemon startd` in surf-dag first (4 real CPUs would
starve concurrent jobs/SERVICE nodes).
Run: docker exec -u submituser -w /home/submituser surf-dag python3 /probes/condor_surface/probe_surface_dagman_strict.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from surface_lib import HOME, fresh, header, htc, read, say, schedd, write

header("probe_surface_dagman_strict")
say("#", "DAGMAN_QUEUE_UPDATE_INTERVAL =", htc.param.get("DAGMAN_QUEUE_UPDATE_INTERVAL"))
os.chdir(HOME)


def make(name, sleep, svc_extra):
    d = fresh("ds-" + name)
    write(os.path.join(d, "driver.sh"), "#!/bin/sh\nsleep %d\necho ok > result.pkl\n" % sleep, 0o755)
    write(os.path.join(d, "driver.sub"), "executable = driver.sh\nshould_transfer_files = YES\ntransfer_output_files = result.pkl\n"
          "log = driver.condor.log\nrequest_memory = 64\nrequest_disk = 10240\nqueue\n")
    write(os.path.join(d, "svc0.sub"), "executable = /bin/sleep\narguments = 3600\nshould_transfer_files = YES\n"
          "transfer_output_files = \"\"\nlog = svc0.log\nrequest_memory = 64\nrequest_disk = 10240\n%squeue\n" % svc_extra)
    write(os.path.join(d, "run.dag"), "JOB driver driver.sub\nSERVICE svc0 svc0.sub\nRETRY driver 2 UNLESS-EXIT 3\n")
    return d


conf = write(os.path.join(fresh("ds-conf"), "dag.conf"), "DAGMAN_USE_STRICT = 0\n")
IDLE, HELD = "requirements = False\n", "transfer_input_files = /nonexistent/models\n"
cases = {
    "idle-strict-default": (20, IDLE, {"UseDagDir": True}),
    "idle-ConfigFile-strict0": (20, IDLE, {"UseDagDir": True, "ConfigFile": conf}),
    "idle-AddToEnv-strict0": (20, IDLE, {"UseDagDir": True, "AddToEnv": "_CONDOR_DAGMAN_USE_STRICT=0"}),
    "held-AddToEnv-strict0": (20, HELD, {"UseDagDir": True, "AddToEnv": "_CONDOR_DAGMAN_USE_STRICT=0"}),
    "driver-held-counter": (400, "", {"UseDagDir": True}),
}
runs = {}
for name, (sleep, extra, opts) in cases.items():
    d = make(name, sleep, extra)
    sub = htc.Submit.from_dag(os.path.join(d, "run.dag"), opts)
    env = str(sub.get("environment"))
    runs[name] = dict(d=d, c=int(schedd.submit(sub).cluster()), t0=time.monotonic(), env=env, held_at=None, seen=None)
    say("D-S %s submitted DAGMan %d; description environment = %s" % (name, runs[name]["c"], env))

end = time.monotonic() + 600
while time.monotonic() < end and any(schedd.query("ClusterId == %d" % r["c"], ["JobStatus"]) for r in runs.values()):
    r = runs["driver-held-counter"]
    t = time.monotonic() - r["t0"]
    nodes = list(schedd.query('DAGManJobId == %d && DAGNodeName == "driver"' % r["c"], ["ClusterId", "JobStatus"]))
    if nodes and nodes[0].get("JobStatus") == 2 and r["held_at"] is None and t > 15:
        schedd.act(htc.JobAction.Hold, "ClusterId == %d" % nodes[0]["ClusterId"])
        r["held_at"] = t
        say("D-S driver-held-counter t=%.0f held the driver node" % t)
    if r["held_at"] is not None:
        dag = list(schedd.query("ClusterId == %d" % r["c"], ["JobStatus", "DAG_JobsHeld", "DAG_AdUpdateTime"]))
        row = (dag[0].get("DAG_JobsHeld") if dag else None, nodes[0].get("JobStatus") if nodes else None)
        if row != r["seen"]:
            say("D-S driver-held-counter t=%.0f DAGMan DAG_JobsHeld=%s | direct node query JobStatus=%s" % ((t,) + row))
            r["seen"] = row
        if row[0] == 1 or t - r["held_at"] > 400:
            schedd.act(htc.JobAction.Remove, "ClusterId == %d" % r["c"])
    time.sleep(2)
for name, r in runs.items():
    h = list(schedd.history("ClusterId == %d" % r["c"], ["JobStatus", "ExitCode", "DAG_Status"], match=1))
    say("D-S %-24s DAGMan history %s; result.pkl %s; rescue %s" % (name, h and {k: h[0].get(k) for k in ("JobStatus", "ExitCode", "DAG_Status")},
        os.path.exists(os.path.join(r["d"], "result.pkl")), [f for f in os.listdir(r["d"]) if "rescue" in f]))
    for l in read(os.path.join(r["d"], "run.dag.dagman.out"), 10 ** 7).splitlines():
        if "STRICT" in l or "EXITING" in l or "thinks there are" in l:
            say("D-S %-24s   dagman.out: %s" % (name, l[18:].strip()[:200]))
say("D-S-done")
