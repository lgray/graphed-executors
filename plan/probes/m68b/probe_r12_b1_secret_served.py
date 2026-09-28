"""r12-B1: does a cluster-hosted http_server serve the job's scratch dir, graphed-secret included?

Emulates the ServiceJob scratch dir (announce.py, service.json, graphed-secret as B1 L433-438 transfers them),
runs the prototype announce.py there against receiver_proto (the /announce stand-in), then, as a stranger on the
network, GETs /graphed-secret and /service.json from the service and signs a POST to the task server with what
it read. Control: the same with the child's cwd a fresh subdirectory (no secret there)."""
import hashlib, hmac, json, os, shutil, subprocess, sys, tempfile, time, urllib.request, urllib.error

P = "/home/user/repo/plan/probes/m68b"

def run(child_cwd_sub):
    scratch = tempfile.mkdtemp(prefix="r12b1-scratch-")
    secret = os.urandom(32).hex()
    open(os.path.join(scratch, "graphed-secret"), "w").write(secret)
    rec = os.path.join(scratch, "rec.jsonl"); open(rec, "w").close()
    recv = subprocess.Popen([sys.executable, P + "/receiver_proto.py", os.path.join(scratch, "graphed-secret"),
                             "18000", "18050", rec], stdout=subprocess.PIPE, text=True)
    url = recv.stdout.readline().strip()
    argv = ["{python}", "-m", "http.server", "{port}"]
    if child_cwd_sub:
        os.mkdir(os.path.join(scratch, "svc"))
        argv = ["{python}", "-m", "http.server", "--directory", "svc", "{port}"]
    json.dump({"argv": argv, "env": {}, "check": "http:/", "ports": [18060, 18100], "key": "k1", "url": url,
               "watch": None, "secret": "graphed-secret", "python": sys.executable, "timeout_s": 30,
               "lease_s": 30, "beat_s": 10}, open(os.path.join(scratch, "service.json"), "w"))
    shutil.copy(P + "/announce_proto.py", scratch)
    env = dict(os.environ, _CONDOR_MACHINE_AD="")
    ann = subprocess.Popen([sys.executable, "announce_proto.py", "service.json"], cwd=scratch, env=env,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    endpoint = None
    for _ in range(60):
        time.sleep(0.5)
        lines = [json.loads(l) for l in open(rec) if l.strip()]
        if lines:
            endpoint = lines[0]["fields"][1]; break
    print("mode:", "child cwd = subdir" if child_cwd_sub else "child cwd = scratch (B1 as written)")
    print("  announced endpoint:", endpoint)
    for path in ("/", "/graphed-secret", "/service.json"):
        try:
            with urllib.request.urlopen("http://%s%s" % (endpoint, path), timeout=5) as r:
                body = r.read().decode()
                print("  GET %s -> %s %r" % (path, r.status, body[:80]))
                if path == "/graphed-secret":
                    stolen = body.strip()
                    print("  stolen == task-server secret:", stolen == secret)
                    b = b"forged"
                    sig = hmac.new(bytes.fromhex(stolen), b, hashlib.sha256).hexdigest()
                    req = urllib.request.Request(url + "/result", data=b, method="POST", headers={"X-Graphed-Sig": sig})
                    try:
                        st = urllib.request.urlopen(req, timeout=5).status
                    except urllib.error.HTTPError as e:
                        st = e.code
                    print("  forged signed POST to task server /result -> %s (403 = signature refused; 400 = accepted signature, body parsed)" % st)
        except urllib.error.HTTPError as e:
            print("  GET %s -> %s" % (path, e.code))
    ann.terminate(); ann.wait(10); recv.terminate(); recv.wait(10)
    pass
    shutil.rmtree(scratch, ignore_errors=True)

print("python", sys.version.split()[0])
run(False)
run(True)
