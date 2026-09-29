# r19-B1: announce_proto.py's orphan path (url answering nothing, lease_s short) with a child that ignores SIGTERM,
# then SIGTERM to announce.py while it sits in that orphan reap. No pool needed. Run: python3 probe_r19_b1_orphan_reap.py
# (announce_proto.py beside it). Every process it starts is SIGKILLed at the end.
import json, os, secrets, shutil, signal, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
IGN = """import signal, sys, http.server
signal.signal(signal.SIGTERM, signal.SIG_IGN)
http.server.ThreadingHTTPServer(("", int(sys.argv[1])), http.server.SimpleHTTPRequestHandler).serve_forever()
"""


def alive(pid):
    try:
        with open("/proc/%d/stat" % pid) as f:
            return f.read().split()[2]  # state letter (Z = zombie)
    except OSError:
        return "gone"


d = tempfile.mkdtemp(prefix="r19b1-orphan-")
shutil.copy(os.path.join(HERE, "announce_proto.py"), d)
os.makedirs(os.path.join(d, "service"))
open(os.path.join(d, "service", "ign.py"), "w").write(IGN)
open(os.path.join(d, "sec"), "w").write(secrets.token_hex(32))
open(os.path.join(d, "mad"), "w").write('Machine = "localhost"\n')
json.dump({"argv": ["{python}", "ign.py", "{port}"], "env": {}, "check": "http:/", "ports": [18750, 18760],
           "key": "k-1", "url": "http://127.0.0.1:1", "watch": None, "secret": "sec", "python": sys.executable,
           "timeout_s": 20, "lease_s": 3, "beat_s": 1}, open(os.path.join(d, "service.json"), "w"))
env = {**os.environ, "_CONDOR_MACHINE_AD": os.path.join(d, "mad")}
p = subprocess.Popen([sys.executable, "announce_proto.py", "service.json"], cwd=d, env=env,
                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
t0 = time.monotonic()
child = None
for line in p.stdout:
    print("  out:", line.rstrip())
    if "ready pid=" in line:
        child = int(line.split("ready pid=")[1].split()[0])
    if "orphaned" in line:
        break
t_orphan = time.monotonic() - t0
time.sleep(12)
print("A orphaned at %.1fs; 12s later announce.py returncode=%s, child state=%s"
      % (t_orphan, p.poll(), alive(child)))
p.send_signal(signal.SIGTERM)
time.sleep(10)
print("B 10s after SIGTERM to announce.py: returncode=%s, child state=%s" % (p.poll(), alive(child)))
for pid in (p.pid, child):
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass
p.wait()
shutil.rmtree(d, ignore_errors=True)
print("cleanup: announce.py returncode after SIGKILL=%s" % p.returncode)
