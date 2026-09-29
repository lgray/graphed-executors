"""m68b probe (local, stdlib, no condor): the start and orphan rules of announce_proto.py.

Run: python3 probe_announce_rules.py > probe_announce_rules.txt   (POSIX)

 L1 a child that exits at once, 20-port range, timeout_s 600 -> exit 3 at once naming the returncode (no restarts)
 L2 a child alive but never ready, 3-port range, timeout_s 2 -> exit 3 after ~2 s total (the budget is the whole start)
 L3 a child whose port another process takes after the scan (the stranger accepts TCP, so the check is http:)
    -> the next port is announced
 L4 attached, url on a closed port, lease_s 3 -> the ready child is reaped and exit 0 after ~lease_s (no 200 ever)
 L5 attached, a server with another secret (403) -> child reaped, exit 0 at once
 L6 attached, beats every beat_s; the server stops -> child reaped, exit 0 within ~lease_s
 L7 a child that answers the http: check once with 503 (leaving a server-side TIME_WAIT), then exits 7, 5-port range,
    x10 -> exit 3 naming 7 after exactly one child start each run (free() binds with SO_REUSEADDR)
 L8 attached, http.server child in the cwd that held graphed-secret: after the announce GET /graphed-secret -> 404,
    the file is gone from the cwd, and the beats still take 200
 L10 {python} = ./env/bin/python (a symlink in the job dir to this interpreter): the child starts from service/ and
    announces, argv[0] absolute; control: Popen of the relative path with cwd=service/ raises FileNotFoundError
 L11 an executable input service/serve.sh (execs python3 -m http.server "$1"), argv ("./serve.sh", "{port}"):
    announces (a literal argv[0] resolves against service/)
 L12 argv[0] "./missing": exit 3 at once naming ./missing, no traceback
 L13 a SIGTERM-ignoring child, url on a closed port, lease_s 3: the orphan path's one bounded reap kills it; exit 0
    within lease_s + 5 s, child pid gone
 L14 the same, SIGTERM to announce.py ~1 s after its "orphaned" line (inside the reap): exits within 5 s
 L16 in-process: the SIGTERM handler, called with Popen.wait/poll spied, raises the private exception, leaves
    SIGTERM ignored, and never calls wait or poll
 L15 the child's environment is the recipe's env over the job's (a job variable and a recipe variable both seen)
 L9 the job dir holds a stand-in ticket cache (user.cc) beside the transferred `service/models/`: the child runs in
    service/, GET /user.cc -> 404, GET /models/m.txt -> 200 (the argv names inputs relatively)
"""

import json
import signal
import os
import socket
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROTO = os.path.join(HERE, "announce_proto.py")
RECV = os.path.join(HERE, "receiver_proto.py")
PY = sys.executable
work = tempfile.mkdtemp(prefix="m68b-rules-")
os.chdir(work)
SECRET = os.urandom(32).hex()
open("secret", "w").write(SECRET)
open("other", "w").write(os.urandom(32).hex())
RACER = os.path.join(work, "racer.py")
open(RACER, "w").write(
    "import subprocess, sys, time\n"
    "port, lo = int(sys.argv[1]), int(sys.argv[2])\n"
    "if port == lo:\n"
    "    subprocess.Popen([sys.executable, '-c', 'import socket,time;s=socket.socket();s.bind((\"\",%d));s.listen();time.sleep(30)' % port], stdout=subprocess.DEVNULL)\n"
    "    time.sleep(1); sys.exit(1)\n"
    "import runpy; sys.argv = ['http.server', str(port)]; runpy.run_module('http.server', run_name='__main__')\n")


def free_base(n):
    for base in range(23000, 60000, 200):
        socks = []
        try:
            for p in range(base, base + n):
                s = socket.socket(); s.bind(("", p)); socks.append(s)
            return base
        except OSError:
            continue
        finally:
            for s in socks:
                s.close()


def run(label, cfg, until=None):
    print(label)
    if not os.path.exists("secret"):
        open("secret", "w").write(SECRET)
    json.dump(cfg, open("svc.json", "w"))
    t = time.monotonic()
    p = subprocess.Popen([PY, PROTO, "svc.json"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if until:
        until(p)
    out, _ = p.communicate(timeout=120)
    lines = [l for l in out.splitlines() if "announce" in l]
    print("   -> exit %s after %.1fs" % (p.returncode, time.monotonic() - t))
    for l in lines[-4:]:
        print("   " + l.split("] ", 1)[1])
    return out


def cfg(**kw):
    base = {"argv": ["{python}", "-m", "http.server", "{port}"], "env": {}, "check": "tcp", "key": "k",
            "url": None, "watch": None, "secret": "secret", "python": PY, "timeout_s": 600, "lease_s": 30,
            "beat_s": 10}
    base.update(kw)
    return base


lo = free_base(20)
run("L1 exits at once, %d ports" % 20, cfg(argv=["{python}", "-c", "import sys; sys.exit(7)"], ports=[lo, lo + 19]))
lo = free_base(3)
run("L2 never ready, 3 ports, timeout_s 2", cfg(argv=["{python}", "-c", "import time; time.sleep(60)"],
                                                ports=[lo, lo + 2], timeout_s=2))


def receiver(secret_file):
    rlo = free_base(5)
    rec = os.path.join(work, "rec-%d.jsonl" % rlo)
    open(rec, "w").close()
    r = subprocess.Popen([PY, RECV, secret_file, str(rlo), str(rlo + 4), rec], stdout=subprocess.PIPE, text=True)
    return r, r.stdout.readline().strip(), rec


open("recv-secret", "w").write(SECRET)
r, url, rec = receiver("recv-secret")
lo = free_base(4)
run("L3 port taken after the scan (http:/ check)", cfg(argv=["{python}", RACER, "{port}", str(lo)], ports=[lo, lo + 3],
                                                       url=url, check="http:/", lease_s=2),
    until=lambda p: (time.sleep(10), r.terminate()))
print("   announced ports:", [json.loads(l)["fields"][1].rpartition(":")[2] for l in open(rec)], "(range starts %d)" % lo)

lo = free_base(3)
_s = socket.socket(); _s.bind(("", 0)); closed = _s.getsockname()[1]; _s.close()  # an unbound port


def child_gone_after(p):
    time.sleep(1.5)
    pid = subprocess.run(["pgrep", "-f", "http.server %d" % lo], capture_output=True, text=True).stdout.split()
    print("   child pid while waiting:", pid)
    p.wait(60)
    time.sleep(0.5)
    print("   child pid after exit:", subprocess.run(["pgrep", "-f", "http.server %d" % lo], capture_output=True, text=True).stdout.split())


run("L4 no 200 ever (closed url), lease_s 3", cfg(ports=[lo, lo + 2], url="http://127.0.0.1:%d" % closed, lease_s=3),
    until=child_gone_after)
r, url, rec = receiver("other")
run("L5 403 (another server's secret)", cfg(ports=[lo, lo + 2], url=url, lease_s=30))
r.terminate()
open("recv-secret", "w").write(SECRET)
r, url, rec = receiver("recv-secret")
run("L6 beats, then the server stops, lease_s 3, beat_s 1", cfg(ports=[lo, lo + 2], url=url, lease_s=3, beat_s=1),
    until=lambda p: (time.sleep(5), r.terminate()))
print("   announces received before the stop:", len(open(rec).read().splitlines()))

ONCE = os.path.join(work, "once.py")
open(ONCE, "w").write(
    "import http.server, sys\n"
    "port, count = int(sys.argv[1]), sys.argv[2]\n"
    "open(count, 'a').write('start\\n')\n"
    "class H(http.server.BaseHTTPRequestHandler):\n"
    "    def do_GET(self):\n"
    "        self.send_response(503); self.end_headers()\n"
    "    def log_message(self, *a): pass\n"
    "srv = http.server.HTTPServer(('', port), H)\n"
    "srv.handle_request(); srv.server_close(); sys.exit(7)\n")
starts, codes = [], []
for i in range(10):
    lo = free_base(5)
    count = os.path.join(work, "count-%d" % i)
    json.dump(cfg(argv=["{python}", ONCE, "{port}", count], ports=[lo, lo + 4], check="http:/", timeout_s=60),
              open("svc.json", "w"))
    open("secret", "w").write(SECRET)
    p = subprocess.run([PY, PROTO, "svc.json"], capture_output=True, text=True)
    starts.append(len(open(count).read().splitlines()))
    codes.append((p.returncode, "exited 7" in p.stdout))
print("L7 503 once then exit 7, 5 ports, 10 runs: child starts per run", starts, "; (exit, names 7):", sorted(set(codes)))

import urllib.request, urllib.error
open("graphed-secret", "w").write(SECRET)
r, url, rec = receiver("recv-secret")
lo = free_base(3)


def l8(p):
    time.sleep(4)
    port = json.loads(open(rec).read().splitlines()[0])["fields"][1].rpartition(":")[2]
    try:
        urllib.request.urlopen("http://127.0.0.1:%s/graphed-secret" % port, timeout=5)
        print("   GET /graphed-secret -> 200 (exposed)")
    except urllib.error.HTTPError as exc:
        print("   GET /graphed-secret ->", exc.code)
    print("   graphed-secret still in the cwd:", os.path.exists("graphed-secret"))
    time.sleep(3)
    print("   announces taking 200 so far:", len(open(rec).read().splitlines()))
    r.terminate()


run("L8 secret not served by the child", cfg(ports=[lo, lo + 2], url=url, secret="graphed-secret", lease_s=3, beat_s=1),
    until=l8)

os.makedirs("service/models", exist_ok=True)  # as transferred: one `service/` dir holding exactly the inputs
open("service/models/m.txt", "w").write("model")
open("user.cc", "w").write("TGT")
open("graphed-secret", "w").write(SECRET)
r, url, rec = receiver("recv-secret")
lo = free_base(3)


def l9(p):
    time.sleep(4)
    port = json.loads(open(rec).read().splitlines()[0])["fields"][1].rpartition(":")[2]
    for path in ("/user.cc", "/models/m.txt"):
        try:
            with urllib.request.urlopen("http://127.0.0.1:%s%s" % (port, path), timeout=5) as resp:
                print("   GET %s -> %s %r" % (path, resp.status, resp.read()))
        except urllib.error.HTTPError as exc:
            print("   GET %s -> %s" % (path, exc.code))
    r.terminate()


run("L9 child cwd holds only the inputs", cfg(ports=[lo, lo + 2], url=url, secret="graphed-secret", lease_s=3, beat_s=1),
    until=l9)

os.makedirs("env/bin", exist_ok=True)
if not os.path.lexists("env/bin/python"):
    os.symlink(PY, "env/bin/python")
open("graphed-secret", "w").write(SECRET)
r, url, rec = receiver("recv-secret")
lo = free_base(3)


def l10(p):
    time.sleep(4)
    port = json.loads(open(rec).read().splitlines()[0])["fields"][1].rpartition(":")[2]
    ps = subprocess.run(["pgrep", "-af", "http.server %s" % port], capture_output=True, text=True).stdout.split()
    print("   child argv[0]:", ps[1] if len(ps) > 1 else None)
    r.terminate()


run("L10 relative {python}", cfg(ports=[lo, lo + 2], url=url, secret="graphed-secret", lease_s=3, beat_s=1,
                                 python="./env/bin/python"), until=l10)
try:
    subprocess.Popen(["./env/bin/python", "-c", "pass"], cwd="service").wait()
    print("   control: relative ./env/bin/python with cwd=service/ started")
except FileNotFoundError as exc:
    print("   control: relative ./env/bin/python with cwd=service/ ->", type(exc).__name__)

open("service/serve.sh", "w").write("#!/bin/sh\nexec %s -m http.server \"$1\"\n" % PY)
os.chmod("service/serve.sh", 0o755)
open("graphed-secret", "w").write(SECRET)
r, url, rec = receiver("recv-secret")
lo = free_base(3)
run("L11 executable input as argv[0]", cfg(argv=["./serve.sh", "{port}"], ports=[lo, lo + 2], url=url,
                                         secret="graphed-secret", lease_s=3, beat_s=1),
    until=lambda p: (time.sleep(5), r.terminate()))
print("   announces:", len(open(rec).read().splitlines()))
open("graphed-secret", "w").write(SECRET)
out = run("L12 missing argv[0]", cfg(argv=["./missing", "{port}"], ports=[lo, lo + 2], url=url, secret="graphed-secret"))
print("   traceback in output:", "Traceback" in out)

IGN = os.path.join(work, "ignorer.py")
open(IGN, "w").write(
    "import signal, sys, runpy\n"
    "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
    "sys.argv = ['http.server', sys.argv[1]]\n"
    "runpy.run_module('http.server', run_name='__main__')\n")
_s = socket.socket(); _s.bind(("", 0)); closed = _s.getsockname()[1]; _s.close()


def alive(pid):
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    st = open("/proc/%d/stat" % pid).read().split()[2] if os.path.exists("/proc/%d/stat" % pid) else "?"
    return st != "Z"


for tag in ("L13", "L14"):
    lo = free_base(3)
    open("graphed-secret", "w").write(SECRET)
    json.dump(cfg(argv=["{python}", IGN, "{port}"], ports=[lo, lo + 2], url="http://127.0.0.1:%d" % closed,
                  secret="graphed-secret", lease_s=3, beat_s=1), open("svc.json", "w"))
    t0 = time.monotonic()
    p = subprocess.Popen([PY, PROTO, "svc.json"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    child = None
    for line in p.stdout:
        if "ready pid=" in line:
            child = int(line.split("ready pid=")[1].split()[0])
        if "orphaned" in line:
            t_orph = time.monotonic()
            if tag == "L14":
                time.sleep(1)
                t_sig = time.monotonic()
                p.send_signal(signal.SIGTERM)
            break
    rest = p.stdout.read()
    p.wait(60)
    t1 = time.monotonic()
    if tag == "L13":
        print("L13 orphan reap of a SIGTERM-ignoring child: exit %s, %.1fs after start (orphaned at %.1fs), child alive %s"
              % (p.returncode, t1 - t0, t_orph - t0, alive(child)))
    else:
        print("L14 SIGTERM during the orphan reap: exit %s %.1fs after the SIGTERM, child alive %s; %s"
              % (p.returncode, t1 - t_sig, alive(child), [l.split('] ', 1)[1] for l in rest.splitlines() if 'announce' in l]))

import signal as _signal
open("graphed-secret", "w").write(SECRET)
r, url, rec = receiver("recv-secret")
lo = free_base(3)
ENVDUMP = os.path.join(work, "envdump.py")
open(ENVDUMP, "w").write(
    "import os, sys, runpy\n"
    "open(os.path.join(%r, 'env.txt'), 'w').write('%%s %%s' %% (os.environ.get('JOBVAR'), os.environ.get('RECVAR')))\n"
    "sys.argv = ['http.server', sys.argv[1]]\n"
    "runpy.run_module('http.server', run_name='__main__')\n" % work)
os.environ["JOBVAR"] = "from-job"
run("L15 env merge", cfg(argv=["{python}", ENVDUMP, "{port}"], ports=[lo, lo + 2], url=url, secret="graphed-secret",
                         lease_s=3, beat_s=1, env={"RECVAR": "from-recipe"}),
    until=lambda p: (time.sleep(4), r.terminate()))
print("   child saw JOBVAR RECVAR:", open(os.path.join(work, "env.txt")).read())

import importlib.util
spec = importlib.util.spec_from_file_location("announce_proto", PROTO)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
calls = []
orig_wait, orig_poll = subprocess.Popen.wait, subprocess.Popen.poll
subprocess.Popen.wait = lambda self, *a, **k: calls.append("wait")
subprocess.Popen.poll = lambda self, *a, **k: calls.append("poll")
prev = signal.getsignal(signal.SIGTERM)
try:
    mod.on_sigterm(signal.SIGTERM, None)
    raised = None
except BaseException as exc:
    raised = type(exc).__name__
finally:
    subprocess.Popen.wait, subprocess.Popen.poll = orig_wait, orig_poll
print("L16 handler raised %s, SIGTERM afterwards SIG_IGN %s, Popen calls %s"
      % (raised, signal.getsignal(signal.SIGTERM) is signal.SIG_IGN, calls))
signal.signal(signal.SIGTERM, prev)
