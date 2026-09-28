"""Driver-node stand-in for probe_dag_service.py (python3.9, stdlib): each start is a fresh 'task server'
(receiver_proto.py, new port + new secret written into the DAG dir, secret then driver.url), waits for
the SERVICE node's announce, GETs the announced endpoint, then exits per plan: argv[2] is a comma list of
exit codes by attempt (e.g. "1,0": first start exits 1, the retry exits 0)."""

import json
import os
import subprocess
import sys
import time
import urllib.request

dag = sys.argv[1]
codes = [int(c) for c in sys.argv[2].split(",")]
counter = os.path.join(dag, "attempts")
n = int(open(counter).read()) if os.path.exists(counter) else 0
open(counter, "w").write(str(n + 1))
record = os.path.join(dag, "announces.jsonl")
secret = os.path.join(dag, "secret.%d" % n)
open(secret, "w").write(os.urandom(32).hex())
here = os.path.dirname(os.path.abspath(__file__))
recv = subprocess.Popen(["python3", os.path.join(here, "receiver_proto.py"), secret, "10000", "10100", record,
                         os.path.join(dag, "driver.url")], stdout=subprocess.PIPE, text=True)
url = recv.stdout.readline().strip()
seen = None
end = time.monotonic() + 90
while time.monotonic() < end and seen is None:
    for line in open(record).read().splitlines() if os.path.exists(record) else []:
        rec = json.loads(line)
        if rec["ok"] and rec["port"] == int(url.rpartition(":")[2]):
            seen = rec
    time.sleep(0.5)
out = {"attempt": n, "url": url, "announce": seen}
if seen:
    with urllib.request.urlopen("http://%s/" % seen["fields"][1], timeout=5) as r:
        out["get"] = r.status
open(os.path.join(dag, "driver.%d.json" % n), "w").write(json.dumps(out))
recv.terminate()
sys.exit(codes[min(n, len(codes) - 1)])
