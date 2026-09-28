"""m68b pool probe: a cluster-hosted service job on minicondor (htcondor/mini, one node).

Run: docker run -d --name m68b-probe-pool -v <plan>/probes/m68b:/probes htcondor/mini
     docker exec -u submituser m68b-probe-pool python3 /probes/probe_service_job.py > probe_service_job.txt

Legs:
 A  in-job port choice: the driver-side receiver holds the range's first port and a listener the second;
    the job (announce_proto.py) takes the next free one and announces it; the announced identity is the
    slot's Machine and equals FULL_HOSTNAME (what backend.host_identity() reads).
 B  the endpoint answers from another process; condor_rm of the job ends the service's child (pid gone).
 C  transfer_input_files: "<abs>/models" lands the directory, "<abs>/models/" only its contents.
 D  a request_gpus=2 job on a pool with at most one (simulated) GPU stays idle (never matches); removing it empties the queue.
"""

import json
import os
import socket
import subprocess
import time

import htcondor2 as htc

WORK = os.path.expanduser("~/m68b-svc")
PROBES = "/probes"
os.makedirs(WORK, exist_ok=True)
os.chdir(WORK)
schedd = htc.Schedd()


def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout.strip()


def ad(cluster, attrs):
    rows = schedd.query("ClusterId == %d" % cluster, attrs)
    if not rows:
        rows = list(schedd.history("ClusterId == %d" % cluster, attrs, match=1))
    return {a: rows[0].get(a) for a in attrs} if rows else {}


def wait_for(pred, timeout, step=1.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = pred()
        if v:
            return v
        time.sleep(step)
    return None


print("condor", htc.version())
print("FULL_HOSTNAME", htc.param["FULL_HOSTNAME"])
print("slot Machine", [a["Machine"] for a in htc.Collector().query(htc.AdType.Startd, projection=["Machine"])])

# ---- A: port choice in the job, announce ----
with open("graphed-secret", "w") as f:
    f.write(os.urandom(32).hex())
os.chmod("graphed-secret", 0o600)
record = os.path.join(WORK, "announces.jsonl")
open(record, "w").close()
recv = subprocess.Popen(["python3", PROBES + "/receiver_proto.py", "graphed-secret", "10000", "10100", record],
                        stdout=subprocess.PIPE, text=True)
url = recv.stdout.readline().strip()
print("A receiver (task-server stand-in) at", url)
holder = socket.socket()
holder.bind(("", 10001))
holder.listen()
print("A a listener holds 10001")
with open("service.json", "w") as f:
    json.dump({"argv": ["{python}", "-m", "http.server", "{port}"], "env": {}, "check": "http:/",
               "ports": [10000, 10100], "key": "nonce1-0123456789abcdef", "url": url, "watch": None,
               "secret": "graphed-secret", "python": "/usr/bin/python3", "timeout_s": 60}, f)
sub = htc.Submit({
    "universe": "vanilla", "executable": "/usr/bin/python3",
    "arguments": "announce_proto.py service.json",
    "transfer_input_files": PROBES + "/announce_proto.py,service.json,graphed-secret",
    "should_transfer_files": "YES", "when_to_transfer_output": "ON_EXIT_OR_EVICT",
    "transfer_output_files": '""', "output": "service.out", "error": "service.err", "log": "service.log",
    "request_cpus": "1", "request_memory": "256", "JobBatchName": "graphed-service-nonce1-0123456789abcdef",
})
cluster = schedd.submit(sub).cluster()
print("A submitted service cluster", cluster)
got = wait_for(lambda: open(record).read().strip(), 90)
print("A announce record:", got)
rec = json.loads(got.splitlines()[0])
key, hostport, ident = rec["fields"]
print("A announced port", hostport.rpartition(":")[2], "(10000 receiver, 10001 listener)")
print("A identity == FULL_HOSTNAME:", ident == htc.param["FULL_HOSTNAME"])
print("A job ad", ad(cluster, ["JobStatus", "RemoteHost", "Args"]))
print("A arguments carry no secret:", "graphed-secret" not in str(ad(cluster, ["Args"])) or "file name only")

# ---- B: reach it, then remove the job ----
import urllib.request
with urllib.request.urlopen("http://%s/" % hostport, timeout=5) as r:
    print("B GET http://%s/ -> %s %s" % (hostport, r.status, r.headers.get("Content-Type")))
pids = sh("pgrep -f 'http.server %s'" % hostport.rpartition(":")[2])
print("B service child pid(s) while running:", pids)
schedd.act(htc.JobAction.Remove, "ClusterId == %d" % cluster, reason="graphed: service released")
gone = wait_for(lambda: not schedd.query("ClusterId == %d" % cluster, ["JobStatus"]), 60)
time.sleep(2)
print("B queue empty after remove:", bool(gone))
print("B child pid(s) after remove:", repr(sh("pgrep -f 'http.server %s'" % hostport.rpartition(":")[2])))
print("B history", ad(cluster, ["JobStatus", "RemoveReason", "VacateReason"]))
recv.terminate()
holder.close()

# ---- C: trailing separator on a transferred directory ----
os.makedirs("models/graphed_identity/1", exist_ok=True)
open("models/graphed_identity/config.pbtxt", "w").write('name: "graphed_identity"\n')
open("models/graphed_identity/1/model.onnx", "wb").write(b"\0")
for spec in (os.path.abspath("models"), os.path.abspath("models") + "/"):
    sub = htc.Submit({
        "universe": "vanilla", "executable": "/usr/bin/find", "arguments": ". -mindepth 1 -not -name _condor* -not -name .*.ad -not -name .*.tmp -not -name tmp -not -name var -not -path ./tmp/* -not -path ./var/*",
        "transfer_input_files": spec, "should_transfer_files": "YES", "transfer_output_files": '""',
        "output": "ls.out", "error": "ls.err", "log": "ls.log", "request_memory": "64",
    })
    c = schedd.submit(sub).cluster()
    wait_for(lambda: ad(c, ["JobStatus"]).get("JobStatus") == 4 and not schedd.query("ClusterId == %d" % c, ["JobStatus"]), 60)
    print("C transfer_input_files=%r -> scratch has: %s" % (spec[len(WORK) + 1:] if spec.startswith(WORK) else spec,
                                                           open("ls.out").read().split()))
print("C os.path.abspath('models/') =", repr(os.path.abspath("models/")[len(WORK):]))

# ---- D: a GPU request the pool cannot match ----
sub = htc.Submit({"universe": "vanilla", "executable": "/bin/sleep", "arguments": "300", "request_gpus": "2",
                  "request_memory": "64", "should_transfer_files": "YES", "transfer_output_files": '""',
                  "log": "gpu.log"})
c = schedd.submit(sub).cluster()
time.sleep(20)
print("D request_gpus=2 after 20s:", ad(c, ["JobStatus", "NumJobStarts", "RequestGPUs"]),
      "TotalGPUs in slot ads:", [a.get("TotalGPUs") for a in htc.Collector().query(htc.AdType.Startd, projection=["TotalGPUs"])])
schedd.act(htc.JobAction.Remove, "ClusterId == %d" % c, reason="graphed: service timed out")
print("D queue empty after remove:", bool(wait_for(lambda: not schedd.query("ClusterId == %d" % c, ["JobStatus"]), 30)))
