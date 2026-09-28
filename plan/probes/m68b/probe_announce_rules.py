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
"""

import json
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
    p = subprocess.Popen([PY, PROTO, "svc.json"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
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
