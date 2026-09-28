"""r12-B1 pool leg (htcondor/mini): a ServiceJob-shaped job (inputs announce_proto.py, service.json,
graphed-secret, as B1 L433-438) running http.server by the recipe's argv; a GET from outside the job fetches
/graphed-secret from the service, and it equals the task-server stand-in's secret.

Run: docker run -d --name r12b1-pool -v <plan>/probes/m68b:/probes:ro -v <dir of this file>:/r12:ro htcondor/mini
     docker exec -u submituser r12b1-pool python3 /r12/probe_r12_b1_pool.py > probe_r12_b1_pool.txt"""
import json, os, subprocess, time, urllib.request, urllib.error
import htcondor2 as htc
WORK = os.path.expanduser("~/r12b1"); os.makedirs(WORK, exist_ok=True); os.chdir(WORK)
schedd = htc.Schedd()
secret = os.urandom(32).hex()
open("graphed-secret", "w").write(secret); os.chmod("graphed-secret", 0o600)
open("rec.jsonl", "w").close()
recv = subprocess.Popen(["python3", "/probes/receiver_proto.py", "graphed-secret", "10000", "10100", WORK + "/rec.jsonl"],
                        stdout=subprocess.PIPE, text=True)
url = recv.stdout.readline().strip()
json.dump({"argv": ["{python}", "-m", "http.server", "{port}"], "env": {}, "check": "http:/", "ports": [10000, 10100],
           "key": "r12-k", "url": url, "watch": None, "secret": "graphed-secret", "python": "/usr/bin/python3",
           "timeout_s": 60, "lease_s": 30, "beat_s": 10}, open("service.json", "w"))
sub = htc.Submit({"universe": "vanilla", "executable": "/usr/bin/python3", "arguments": "announce_proto.py service.json",
    "transfer_input_files": "/probes/announce_proto.py,service.json,graphed-secret", "should_transfer_files": "YES",
    "when_to_transfer_output": "ON_EXIT_OR_EVICT", "transfer_output_files": '""', "output": "s.out", "error": "s.err",
    "log": "s.log", "request_cpus": "1", "request_memory": "256", "initialdir": WORK})
cl = schedd.submit(sub).cluster()
ep = None
for _ in range(120):
    rows = [json.loads(l) for l in open("rec.jsonl") if l.strip()]
    if rows: ep = rows[0]["fields"][1]; break
    time.sleep(1)
print("condor", htc.version().split()[1], "announced", ep)
for p in ("/", "/graphed-secret"):
    try:
        body = urllib.request.urlopen("http://%s%s" % (ep, p), timeout=5).read().decode()
        print("GET", p, "-> 200", ("equals the task server's secret: %s" % (body.strip() == secret)) if p != "/" else
              "listing names graphed-secret: %s" % ("graphed-secret" in body))
    except urllib.error.HTTPError as e:
        print("GET", p, "->", e.code)
schedd.act(htc.JobAction.Remove, "ClusterId == %d" % cl)
recv.terminate()
time.sleep(3)
print("queue empty after remove:", not schedd.query("ClusterId == %d" % cl, ["JobStatus"]))
