"""Surface area D: DAGMan as m68b B2 uses it — from_dag options, first-run DAG dir contents, SERVICE node semantics
(running/exited/idle/held/removed at DAG end, strictness, periodic_remove timing), RETRY/UNLESS-EXIT, DAG exit codes,
held and removed DAGs, DAG_* counters, node attributes and logs. Every DAG gets its own fresh directory (the
per-run-directory redesign) and is submitted as B2 does: schedd.submit(Submit.from_dag(<abs run.dag>, opts)), unspooled,
from a cwd that is not the DAG dir.

Pool: `echo 'NUM_CPUS = 40' > /etc/condor/config.d/98-cpus` + `condor_restart -daemon startd` in surf-dag first (4 real CPUs would
starve concurrent jobs/SERVICE nodes).
Run: docker exec -u submituser -w /home/submituser surf-dag python3 /probes/condor_surface/probe_surface_dagman.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from surface_lib import HOME, fresh, header, htc, listdir, read, say, schedd, script, short, write

header("probe_surface_dagman")
os.chdir(HOME)

# ---------------------------------------------------------------- D1 from_dag option spelling and side effects
d = fresh("d1")
write(os.path.join(d, "a.sub"), "executable = /bin/true\nqueue\n")
write(os.path.join(d, "run.dag"), "JOB a a.sub\n")
say("D1 dir before from_dag:", listdir(d))
for opts in ({}, {"usedagdir": True, "force": True}, {"UseDagDir": True, "Force": True}, {"usedagdir": 1},
             {"UseDagDir": False}, {"usedagdri": True}, {"force": True, "AutoRescue": 0}):
    try:
        s = htc.Submit.from_dag(os.path.join(d, "run.dag"), opts)
        args = str(s.get("arguments"))
        flags = [f for f in ("-UseDagDir", "-force", "-AutoRescue 1", "-AutoRescue 0") if f in args]
        say("D1 from_dag(%r): flags %s; dir now %s" % (opts, flags, listdir(d)))
    except Exception as e:
        say("D1 from_dag(%r): raised %s %s" % (opts, type(e).__name__, short(str(e), 200)))
try:
    htc.Submit.from_dag(os.path.join(d, "missing.dag"), {})
except Exception as e:
    say("D1 from_dag(missing file): raised", type(e).__name__, short(str(e), 120))
# a first DAG in a fresh dir without force vs with force: same description apart from -force?
d_nf, d_f = fresh("d1-noforce"), fresh("d1-force")
for dd in (d_nf, d_f):
    write(os.path.join(dd, "a.sub"), "executable = /bin/true\nqueue\n")
    write(os.path.join(dd, "run.dag"), "JOB a a.sub\n")
s_nf = htc.Submit.from_dag(os.path.join(d_nf, "run.dag"), {"UseDagDir": True})
s_f = htc.Submit.from_dag(os.path.join(d_f, "run.dag"), {"UseDagDir": True, "Force": True})
diff = sorted(k for k in set(s_nf.keys()) | set(s_f.keys())
              if str(s_nf.get(k)).replace(d_nf, "D") != str(s_f.get(k)).replace(d_f, "D"))
say("D1 fresh dir, with vs without force: keys differing (dir substituted):", diff,
    "| arguments tail without:", str(s_nf.get("arguments")).split("-dagman")[-1], "with:", str(s_f.get("arguments")).split("-dagman")[-1])

# ---------------------------------------------------------------- DAG builder
DRIVER = """#!/bin/sh
# argv: <retry> <codes...>; exit code = codes[retry]; sleeps $SLEEP first; writes result.pkl unless NORESULT
retry=$1; shift; i=0; code=0
for c in "$@"; do [ $i -eq $retry ] && code=$c; i=$((i+1)); done
sleep ${SLEEP:-25}
[ "$code" = k ] && kill -9 $$
[ -n "$NORESULT" ] || echo "attempt $retry exit $code" > result.pkl
echo "driver attempt=$retry exit=$code pwd=$(pwd)"
exit $code
"""
SERVICE = {
    "run": "sleep 3600\n",
    "exit0": "sleep 5; exit 0\n",
    "exit3": "sleep 5; exit 3\n",
}


def make_dag(name, codes=(0,), svc="run", svc_kw=None, driver_env="", dag_extra="", driver_kw=None):
    d = fresh(name)
    write(os.path.join(d, "driver.sh"), DRIVER, 0o755)
    drv = {"universe": "vanilla", "executable": "driver.sh",  # relative: resolved against the DAG dir under UseDagDir
           "arguments": "$(RETRY) " + " ".join(map(str, codes)), "should_transfer_files": "YES",
           "when_to_transfer_output": "ON_EXIT", "transfer_output_files": "result.pkl", "output": "driver.out",
           "error": "driver.err", "log": "driver.condor.log", "request_memory": "64", "request_disk": "10240",
           "environment": '"%s"' % driver_env}
    drv.update(driver_kw or {})
    write(os.path.join(d, "driver.sub"), "".join("%s = %s\n" % kv for kv in drv.items()) + "queue\n")
    lines = "JOB driver driver.sub\nRETRY driver 2 UNLESS-EXIT 3\n"
    if svc is not None:
        sd = os.path.join(d, "service-svc0")
        os.makedirs(sd)
        write(os.path.join(sd, "service.sh"), "#!/bin/sh\n" + SERVICE.get(svc, "sleep 3600\n"), 0o755)
        sv = {"universe": "vanilla", "executable": os.path.join(sd, "service.sh"), "initialdir": sd,
              "should_transfer_files": "YES", "when_to_transfer_output": "ON_EXIT", "transfer_output_files": '""',
              "output": "service.out", "error": "service.err", "log": "service.log", "request_memory": "64",
              "request_disk": "10240"}
        sv.update(svc_kw or {})
        write(os.path.join(d, "svc0.sub"), "".join("%s = %s\n" % kv for kv in sv.items()) + "queue\n")
        lines += "SERVICE svc0 svc0.sub\n"
    write(os.path.join(d, "run.dag"), lines + dag_extra)
    return d


DAGMAN_ATTRS = ["JobStatus", "ExitCode", "DAG_Status", "DAG_NodesTotal", "DAG_NodesDone", "DAG_NodesFailed",
                "DAG_NodesQueued", "DAG_JobsSubmitted", "DAG_JobsIdle", "DAG_JobsRunning", "DAG_JobsHeld",
                "DAG_JobsCompleted", "HoldReasonCode", "RemoveReason"]
NODE_ATTRS = ["ClusterId", "DAGNodeName", "DAGManJobId", "DAGManNodeRetry", "JobStatus", "ExitCode", "ExitBySignal",
              "HoldReasonCode", "NumJobStarts", "RemoveReason"]

specs = {
    # name: (make_dag kwargs, submit options, actions [(t, what)])
    "ok": (dict(codes=(0,), svc="run"), {"usedagdir": True}, []),
    "ok-force": (dict(codes=(0,), svc="run"), {"usedagdir": True, "force": True}, []),
    "svc-exit0": (dict(codes=(0,), svc="exit0"), {"usedagdir": True}, []),
    "svc-exit3": (dict(codes=(0,), svc="exit3"), {"usedagdir": True}, []),
    "svc-idle": (dict(codes=(0,), svc="run", svc_kw={"requirements": "False"}), {"usedagdir": True}, []),
    "svc-held": (dict(codes=(0,), svc="run", svc_kw={"transfer_input_files": "/nonexistent/models"}), {"usedagdir": True}, []),
    "svc-held-prm-race": (dict(codes=(0,), svc="run", driver_env="SLEEP=15",
                               svc_kw={"transfer_input_files": "/nonexistent/models", "periodic_remove": "JobStatus == 5"}),
                          {"usedagdir": True}, []),
    "svc-held-prm-long": (dict(codes=(0,), svc="run", driver_env="SLEEP=150",
                               svc_kw={"transfer_input_files": "/nonexistent/models", "periodic_remove": "JobStatus == 5"}),
                          {"usedagdir": True}, []),
    "svc-held-strict0": (dict(codes=(0,), svc="run", svc_kw={"transfer_input_files": "/nonexistent/models"}),
                         {"usedagdir": True, "ConfigFile": "@strict0"}, []),
    "svc-userhold-end": (dict(codes=(0,), svc="run", driver_env="SLEEP=40"), {"usedagdir": True}, [(15, "hold svc0")]),
    "svc-removed": (dict(codes=(0,), svc="run", driver_env="SLEEP=40"), {"usedagdir": True}, [(15, "rm svc0")]),
    "retry-1-0": (dict(codes=(1, 0), svc="run", driver_env="SLEEP=5"), {"usedagdir": True}, []),
    "retry-3": (dict(codes=(3,), svc="run", driver_env="SLEEP=5"), {"usedagdir": True}, []),
    "retry-exhausted": (dict(codes=(1, 1, 1), svc="run", driver_env="SLEEP=5"), {"usedagdir": True}, []),
    "driver-kill9-noresult": (dict(codes=("k",), svc="run", driver_env="SLEEP=5 NORESULT=1"), {"usedagdir": True}, []),
    "driver-held": (dict(codes=(0,), svc="run", driver_env="SLEEP=60"), {"usedagdir": True}, [(20, "hold driver"), (50, "release driver")]),
    "dag-removed": (dict(codes=(0,), svc="run", driver_env="SLEEP=120"), {"usedagdir": True}, [(30, "rm dagman")]),
    "no-service": (dict(codes=(0,), svc=None, driver_env="SLEEP=5"), {"usedagdir": True}, []),
}
strict0 = write(os.path.join(fresh("d-conf"), "strict0.conf"), "DAGMAN_USE_STRICT = 0\n")

runs = {}
for name, (mk, opts, actions) in specs.items():
    d = make_dag(name, **mk)
    opts = {k: (strict0 if v == "@strict0" else v) for k, v in opts.items()}
    before = listdir(d)
    sub = htc.Submit.from_dag(os.path.join(d, "run.dag"), opts)
    after_fromdag = listdir(d)
    c = int(schedd.submit(sub).cluster())
    runs[name] = dict(dir=d, cluster=c, t0=time.monotonic(), actions=list(actions), seen=set(), last=None, done=False,
                      timeline=[], files=[("t=0 before from_dag", before), ("after from_dag", after_fromdag),
                                          ("after submit", listdir(d))])
say("D2 submitted", {n: r["cluster"] for n, r in runs.items()})


def node_ad(dag_cluster, node, attrs=("ClusterId", "JobStatus")):
    ads = list(schedd.query("DAGManJobId == %d && DAGNodeName == \"%s\"" % (dag_cluster, node), list(attrs)))
    return ads[-1] if ads else None


deadline = time.monotonic() + 1500
while time.monotonic() < deadline and not all(r["done"] for r in runs.values()):
    for name, r in runs.items():
        if r["done"]:
            continue
        t = time.monotonic() - r["t0"]
        c = r["cluster"]
        for (at, what) in list(r["actions"]):
            if t >= at:
                verb, node = what.split()
                if node == "dagman":
                    schedd.act(htc.JobAction.Remove, "ClusterId == %d" % c, reason="probe removes the DAG")
                else:
                    na = node_ad(c, node)
                    if na:
                        act = {"hold": htc.JobAction.Hold, "rm": htc.JobAction.Remove, "release": htc.JobAction.Release}[verb]
                        schedd.act(act, "ClusterId == %d" % na["ClusterId"], reason="probe %s %s" % (verb, node))
                r["timeline"].append("t=%3.0f ACTION %s" % (t, what))
                r["actions"].remove((at, what))
        ads = list(schedd.query("ClusterId == %d" % c, DAGMAN_ATTRS))
        if not ads:
            r["done"] = True
            r["timeline"].append("t=%3.0f DAGMan left the queue" % t)
            r["files"].append(("after end", listdir(r["dir"])))
            continue
        a = ads[0]
        nodes = {n: node_ad(c, n, ("JobStatus", "HoldReasonCode")) for n in ("driver", "svc0")}
        row = (a.get("JobStatus"), a.get("DAG_JobsIdle"), a.get("DAG_JobsRunning"), a.get("DAG_JobsHeld"),
               a.get("DAG_NodesQueued"), a.get("DAG_NodesDone"), a.get("DAG_NodesTotal"),
               tuple((n, v.get("JobStatus") if v else None) for n, v in nodes.items()))
        if row != r["last"]:
            r["timeline"].append("t=%3.0f DAGMan JobStatus=%s JobsIdle=%s JobsRunning=%s JobsHeld=%s NodesQueued=%s "
                                 "NodesDone=%s NodesTotal=%s nodes(JobStatus)=%s" % ((t,) + row))
            r["last"] = row
        fl = listdir(r["dir"])
        key = tuple(fl)
        if key not in r["seen"] and len(r["seen"]) < 6:
            r["seen"].add(key)
            r["files"].append(("t=%.0f running" % t, fl))
    time.sleep(2)

for name, r in runs.items():
    c = r["cluster"]
    say("=" * 20, name, "DAGMan cluster", c, "dir", r["dir"])
    for line in r["timeline"]:
        say("D[%s] %s" % (name, line))
    h = list(schedd.history("ClusterId == %d" % c, DAGMAN_ATTRS + ["JobUniverse"], match=1))
    if h:
        say("D[%s] DAGMan history: %s" % (name, {k: h[0].get(k) for k in DAGMAN_ATTRS + ["JobUniverse"] if h[0].get(k) is not None}))
    else:
        say("D[%s] DAGMan still queued: %s" % (name, list(schedd.query("ClusterId == %d" % c, DAGMAN_ATTRS))))
        schedd.act(htc.JobAction.Remove, "ClusterId == %d" % c, reason="probe cleanup")
    for na in sorted(schedd.history("DAGManJobId == %d" % c, NODE_ATTRS, match=20), key=lambda x: x.get("ClusterId")):
        say("D[%s]   node %s" % (name, {k: (short(na.get(k), 150) if k == "RemoveReason" else na.get(k)) for k in NODE_ATTRS if na.get(k) is not None}))
    for label, fl in r["files"]:
        say("D[%s]   files %-22s %s" % (name, label, fl))
    out = read(os.path.join(r["dir"], "run.dag.dagman.out"), 10 ** 7)
    keep = [l for l in out.splitlines() if any(s in l for s in ("EXITING WITH STATUS", "ERROR", "Warning", "fatal", "Rescue", "rescue",
                                                                  "Removing", "remove", "SERVICE", "service", "Node svc0", "held"))]
    for l in keep[-14:]:
        say("D[%s]   dagman.out: %s" % (name, l[18:].strip()[:220]))
    m = read(os.path.join(r["dir"], "run.dag.metrics"))
    if not m.startswith("<"):
        import json
        try:
            j = json.loads(m)
            say("D[%s]   metrics: %s" % (name, {k: j.get(k) for k in ("exitcode", "DagStatus", "jobs", "jobs_failed", "jobs_succeeded",
                                                                       "service_nodes", "service_nodes_failed", "service_nodes_succeeded",
                                                                       "total_jobs", "total_jobs_run", "retries")}))
        except Exception as e:
            say("D[%s]   metrics unreadable" % name, e)
say("D-done")
