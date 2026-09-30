"""m68b r24-B1 review probe: the CURRENT announce_proto.py (round-18: service/ cwd, secret unlink, SIGTERM blocked
around Popen + unblocked in preexec_fn, pid-based post-SIGTERM reap, sys.platform guards) run as a real
ServiceJob-shaped condor job (the B1 keys: absolute executable service.sh, arguments service.json,
transfer_input_files announce.py,service.json,graphed-secret relative to initialdir, job_max_vacate_time 30).
The last pool run of the prototype was probe_service_job.txt at r8, before all of those changes.

Run: docker run -d --name r24r-mini -v <scratch>:/work -v <plan>/probes:/probes:ro htcondor/mini:25.13.2-el9
     docker exec -u submituser r24r-mini /usr/bin/python3 /work/probe_r24r_b1_job_prototype.py
Legs:
 J1 announce + serve from service/: GET / 200, GET /service.json and /graphed-secret 404; then the receiver dies,
    the orphan rule (lease_s 5) ends the job with exit 0 and service.out comes back: the child's blocked mask
    (SigBlk) excludes SIGTERM (15), and the job-side graphed-secret was gone when the child started
 J2 condor removal (family-wide SIGTERM) of a serving job: seconds until it leaves the queue, child pid gone,
    history JobStatus 3 with EnteredCurrentStatus
 J3 the same with a child that ignores SIGTERM: announce.py's pid reap SIGKILLs it after 5 s, so the job leaves
    well inside job_max_vacate_time (30 s); child pid gone
 J4 a receiver holding another secret (403): child reaped, job exits 0 at once
"""

import json
import os
import signal
import subprocess
import time
import urllib.error
import urllib.request

import htcondor2 as htc

WORK = os.path.expanduser("~/r24r-job")
PROBES = "/probes/m68b"
os.makedirs(WORK, exist_ok=True)
os.chdir(WORK)
schedd = htc.Schedd()
print("condor", htc.version().split("$")[1].strip() if "$" in htc.version() else htc.version())

# the child: prints its blocked-signal mask and whether ../graphed-secret exists, optionally ignores SIGTERM,
# then serves its cwd (service/) like `python -m http.server <port>`
CHILD = (
    "import os, signal, sys, http.server\n"
    "blk = [l.split()[1] for l in open('/proc/self/status') if l.startswith('SigBlk')][0]\n"
    "print('child mask SigBlk=%s sigterm_blocked=%s secret_beside=%s cwd=%s' % (blk, bool(int(blk, 16) >> 14 & 1),"
    " os.path.exists('../graphed-secret'), os.path.basename(os.getcwd())), flush=True)\n"
    "if sys.argv[2] == 'ign':\n"
    "    signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
    "http.server.test(HandlerClass=http.server.SimpleHTTPRequestHandler, port=int(sys.argv[1]))\n"
)
open(os.path.join(WORK, "child.py"), "w").write(CHILD)


def receiver(tag, secret_hex):
    sf = os.path.join(WORK, "recv-%s.secret" % tag)
    open(sf, "w").write(secret_hex)
    rec = os.path.join(WORK, "recv-%s.jsonl" % tag)
    open(rec, "w").close()
    p = subprocess.Popen(["/usr/bin/python3", PROBES + "/receiver_proto.py", sf, "12000", "12100", rec],
                         stdout=subprocess.PIPE, text=True)
    return p, p.stdout.readline().strip(), rec


def submit(tag, url, secret_hex, mode, lease_s=30.0, beat_s=10.0):
    d = os.path.join(WORK, "service-%s" % tag)
    os.makedirs(d, exist_ok=False)
    subprocess.run(["cp", PROBES + "/announce_proto.py", os.path.join(d, "announce.py")], check=True)
    with open(os.path.join(d, "graphed-secret"), "w") as f:
        f.write(secret_hex)
    os.chmod(os.path.join(d, "graphed-secret"), 0o600)
    json.dump({"argv": ["{python}", os.path.join(WORK, "child.py"), "{port}", mode], "env": {}, "check": "http:/",
               "ports": [10000, 10100], "key": "k-" + tag, "url": url, "watch": None, "python": "/usr/bin/python3",
               "timeout_s": 60, "lease_s": lease_s, "beat_s": beat_s}, open(os.path.join(d, "service.json"), "w"))
    sh = os.path.join(d, "service.sh")
    open(sh, "w").write('#!/bin/sh\n[ -f env.tgz ] && tar xzf env.tgz\n'
                        'command -v /usr/bin/python3 >/dev/null 2>&1 || { echo "no /usr/bin/python3" >&2; exit 3; }\n'
                        'exec /usr/bin/python3 announce.py "$@"\n')
    os.chmod(sh, 0o755)
    desc = {"universe": "vanilla", "executable": sh, "arguments": "service.json", "initialdir": d,
            "output": "service.out", "error": "service.err", "log": "service.log",
            "should_transfer_files": "YES", "when_to_transfer_output": "ON_EXIT_OR_EVICT",
            "transfer_input_files": "announce.py,service.json,graphed-secret", "transfer_output_files": '""',
            "request_cpus": "1", "request_memory": "256", "JobBatchName": "graphed-service-k-" + tag,
            "job_max_vacate_time": "30"}
    return int(schedd.submit(htc.Submit(desc)).cluster()), d


def wait_for(pred, timeout, step=0.25):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = pred()
        if v:
            return v
        time.sleep(step)
    return None


def in_queue(c):
    return bool(schedd.query("ClusterId == %d" % c, ["JobStatus"]))


def hist(c, attrs):
    rows = list(schedd.history("ClusterId == %d" % c, attrs, match=1))
    return {a: rows[0].get(a) for a in attrs} if rows else {}


def get(hostport, path):
    try:
        with urllib.request.urlopen("http://%s%s" % (hostport, path), timeout=5) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def pids(port):
    return subprocess.run(["pgrep", "-f", "child.py %s" % port], capture_output=True, text=True).stdout.split()


def announced(rec):
    txt = wait_for(lambda: open(rec).read().strip(), 120)
    return json.loads(txt.splitlines()[0])["fields"] if txt else None


S = os.urandom(32).hex()

# J1
recv, url, rec = receiver("j1", S)
c, d = submit("j1", url, S, "serve", lease_s=5.0, beat_s=1.0)
f = announced(rec)
hp = f[1]
print("J1 announced", f, "| GET / %s, /service.json %s, /graphed-secret %s, /announce.py %s" % (
    get(hp, "/"), get(hp, "/service.json"), get(hp, "/graphed-secret"), get(hp, "/announce.py")))
recv.terminate()
recv.wait()
t0 = time.monotonic()
wait_for(lambda: not in_queue(c), 60)
print("J1 receiver stopped: job left the queue after %.1fs; history %s" % (
    time.monotonic() - t0, hist(c, ["JobStatus", "ExitCode"])))
out = open(os.path.join(d, "service.out")).read()
print("J1 service.out:", [l for l in out.splitlines() if "child mask" in l or "ready pid" in l or "orphaned" in l])
print("J1 child pid after:", pids(hp.rpartition(":")[2]))

# J2, J3
for tag, mode in (("j2", "serve"), ("j3", "ign")):
    recv, url, rec = receiver(tag, S)
    c, d = submit(tag, url, S, mode)
    f = announced(rec)
    port = f[1].rpartition(":")[2]
    before = pids(port)
    t0 = time.monotonic()
    schedd.act(htc.JobAction.Remove, "ClusterId == %d" % c)
    wait_for(lambda: not in_queue(c), 60)
    left = time.monotonic() - t0
    time.sleep(1)
    print("%s (%s child) removed: left the queue after %.1fs (job_max_vacate_time 30); child pids before %s after %s;"
          " history %s" % (tag.upper(), mode, left, before, pids(port),
                          hist(c, ["JobStatus", "EnteredCurrentStatus", "JobCurrentStartDate", "JobBatchName"])))
    recv.terminate()
    recv.wait()

# J4
recv, url, rec = receiver("j4", os.urandom(32).hex())
c, d = submit("j4", url, S, "serve")
t0 = wait_for(lambda: schedd.query("ClusterId == %d" % c, ["JobStatus"])[0].get("JobStatus") == 2
              if in_queue(c) else True, 120) and time.monotonic()
wait_for(lambda: not in_queue(c), 90)
print("J4 403 receiver: job left the queue %.1fs after it ran; history %s; service.out orphan line: %s" % (
    time.monotonic() - t0, hist(c, ["JobStatus", "ExitCode"]),
    [l for l in open(os.path.join(d, "service.out")).read().splitlines() if "orphaned" in l]))
recv.terminate()
