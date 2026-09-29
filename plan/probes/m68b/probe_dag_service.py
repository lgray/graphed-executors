"""m68b pool probe: driverless DAG = JOB driver + SERVICE node + RETRY driver 2 UNLESS-EXIT 3 (minicondor).

Run: docker exec -u submituser m68b-probe-pool python3 /probes/probe_dag_service.py > probe_dag_service.txt

Each DAG, in its own fresh directory, is submitted through the bindings (htcondor2.Submit.from_dag(run.dag, {"UseDagDir": True, "AddToEnv": "_CONDOR_DAGMAN_USE_STRICT=0"}),
schedd.submit, no spool) from the home dir (not the DAG dir), the DAG dir being one both nodes read directly. The SERVICE node runs announce_proto.py in watch mode (key = the node name);
each driver start (dag_driver_node.py) is a new receiver on a new port with a new secret, written into
the DAG dir secret-first then driver.url, each by atomic rename.
 R  driver exits 1, then 0: one SERVICE cluster serves both driver starts (it re-announces to the second
    url with the second secret), DAGMan exits 0, the SERVICE job is removed at DAG end.
 X  driver exits 3: no retry, DAGMan exits nonzero, the SERVICE job is removed (a rescue DAG is left).
Also printed: the from_dag description (the generic DAG submit fixture) and the removed SERVICE ad.
"""

import json
import os
import shutil
import time

import htcondor2 as htc

schedd = htc.Schedd()
P = "/probes"


def wait_for(pred, timeout, step=2.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = pred()
        if v:
            return v
        time.sleep(step)
    return None


def run(tag, codes, reuse=None):
    d = os.path.expanduser("~/m68b-dag-%s" % (reuse or tag))
    if reuse:
        print("[%s] reusing %s, which holds: %s" % (tag, d, sorted(f for f in os.listdir(d) if f.startswith("run.dag"))))
        for f in ("attempts", "announces.jsonl"):
            if os.path.exists(os.path.join(d, f)):
                os.remove(os.path.join(d, f))
    else:
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)
    for f in ("announce_proto.py", "receiver_proto.py", "dag_driver_node.py"):
        shutil.copy(os.path.join(P, f), d)
    json.dump({"argv": ["{python}", "-m", "http.server", "{port}"], "env": {}, "check": "http:/",
               "ports": [10000, 10100], "key": "web", "url": None, "watch": d, "secret": None,
               "python": "/usr/bin/python3", "timeout_s": 60, "lease_s": 30, "beat_s": 10},
              open(os.path.join(d, "service.json"), "w"))
    common = ("universe = vanilla\nshould_transfer_files = YES\nwhen_to_transfer_output = ON_EXIT_OR_EVICT\n"
              "transfer_output_files = \"\"\nrequest_memory = 128\n")
    open(os.path.join(d, "driver.sub"), "w").write(
        common + "executable = /usr/bin/python3\narguments = %s/dag_driver_node.py %s %s\n"
        "output = driver.$(Cluster).out\nerror = driver.$(Cluster).err\nlog = nodes.log\nqueue\n"
        % (d, d, ",".join(map(str, codes))))
    open(os.path.join(d, "web.sub"), "w").write(
        common + "executable = /usr/bin/python3\narguments = announce_proto.py service.json\n"
        "transfer_input_files = announce_proto.py,service.json\n"
        "output = web.out\nerror = web.err\nlog = nodes.log\nqueue\n")
    dagfile = os.path.join(d, "run.dag")
    open(dagfile, "w").write("JOB driver driver.sub\nSERVICE web web.sub\nRETRY driver 2 UNLESS-EXIT 3\n")
    os.chdir(os.path.expanduser("~"))  # the submitter's cwd is not the DAG dir
    desc = htc.Submit.from_dag(dagfile, {"UseDagDir": True, "AddToEnv": "_CONDOR_DAGMAN_USE_STRICT=0"})
    if tag == "R":
        print("from_dag description:")
        for k in sorted(desc.keys()):
            print("   %s = %s" % (k, desc[k]))
    dagman = schedd.submit(desc).cluster()
    print("[%s] DAGMan cluster %d, JobUniverse %s" % (tag, dagman, schedd.query("ClusterId == %d" % dagman, ["JobUniverse"])[0]["JobUniverse"]))
    wait_for(lambda: not schedd.query("ClusterId == %d || DAGManJobId == %d" % (dagman, dagman), ["ClusterId"]), 400)
    nodes = list(schedd.history("DAGManJobId == %d" % dagman,
                                ["ClusterId", "DAGNodeName", "JobStatus", "ExitCode", "RemoveReason", "DAGManJobId"], match=20))
    for n in sorted(nodes, key=lambda a: a["ClusterId"]):
        print("[%s]   node %s cluster %s JobStatus %s ExitCode %s RemoveReason %r" % (
            tag, n.get("DAGNodeName"), n["ClusterId"], n.get("JobStatus"), n.get("ExitCode"), n.get("RemoveReason")))
    dm = list(schedd.history("ClusterId == %d" % dagman, ["JobStatus", "ExitCode", "JobUniverse"], match=1))[0]
    print("[%s] DAGMan history: JobStatus %s ExitCode %s JobUniverse %s" % (tag, dm.get("JobStatus"), dm.get("ExitCode"), dm.get("JobUniverse")))
    print("[%s] SERVICE clusters: %d; driver clusters: %d" % (
        tag, sum(n.get("DAGNodeName") == "web" for n in nodes), sum(n.get("DAGNodeName") == "driver" for n in nodes)))
    for i in range(3):
        p = os.path.join(d, "driver.%d.json" % i)
        if os.path.exists(p):
            r = json.load(open(p))
            print("[%s] driver start %d: url %s, announce %s, GET %s" % (tag, i, r["url"], r["announce"] and r["announce"]["fields"], r.get("get")))
    print("[%s] announces received:" % tag, [json.loads(l)["port"] for l in open(os.path.join(d, "announces.jsonl"))])


print("condor", htc.version())
run("R", [1, 0])
run("X", [3])

