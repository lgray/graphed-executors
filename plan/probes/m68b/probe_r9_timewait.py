"""r9 review probe (POSIX, no pool): does announce.py's "port no longer free" test see a port as taken merely
because its own http: self-check left a server-side TIME_WAIT on it?

Child: answers the http: self-check once with 503 (a server still loading), then exits 7 (a bad model). Nothing
else ever binds the range. The plan's rule says: exit 3 at once naming the returncode, one child start.
A: the prototype as written (plain bind in free()); B: the same with SO_REUSEADDR in free(). Each leg N runs over a
fresh 10-port range (whether the server or the client sends FIN first is a race, so one run proves nothing).
Control C: a live listener still refuses a SO_REUSEADDR bind, so B still sees a real taker.

Run: python3 probe_r9_timewait.py > probe_r9_timewait.txt
"""
import json, os, socket, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
CHILD = '''import sys, http.server
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(503); self.end_headers(); self.wfile.write(b"loading"); self.server.done = True
    def log_message(self, *a): pass
s = http.server.HTTPServer(("", int(sys.argv[1])), H)
s.done = False
while not s.done:
    s.handle_request()
s.server_close()
sys.exit(7)
'''
N = 10
d = tempfile.mkdtemp()
open(os.path.join(d, "child.py"), "w").write(CHILD)
open(os.path.join(d, "sec"), "w").write("00")
src = open(os.path.join(HERE, "announce_proto.py")).read()
patched = src.replace("    s = socket.socket()\n    try:\n        s.bind",
                      "    s = socket.socket()\n    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)\n    try:\n        s.bind")
assert patched != src
open(os.path.join(d, "proto_reuse.py"), "w").write(patched)


def run(proto, lo):
    cfg = {"argv": [sys.executable, os.path.join(d, "child.py"), "{port}"], "env": {}, "check": "http:/",
           "ports": [lo, lo + 9], "key": "k", "url": "http://localhost:1", "watch": None,
           "secret": os.path.join(d, "sec"), "python": sys.executable, "timeout_s": 20, "lease_s": 3, "beat_s": 1}
    p = os.path.join(d, "svc.json")
    json.dump(cfg, open(p, "w"))
    t = time.monotonic()
    r = subprocess.run([sys.executable, proto, p], capture_output=True, text=True, timeout=60)
    lines = [l.split("] ", 1)[1] for l in r.stdout.splitlines()]
    return r.returncode, time.monotonic() - t, sum("child exited" in l for l in lines), lines


for leg, proto, base in (("A plain bind", os.path.join(HERE, "announce_proto.py"), 24000),
                         ("B SO_REUSEADDR", os.path.join(d, "proto_reuse.py"), 25000)):
    starts, shown = [], False
    for i in range(N):
        rc, dt, n, lines = run(proto, base + 20 * i)
        starts.append(n)
        if n > 1 and not shown:
            shown = True
            print("%s run %d -> exit %d after %.1fs, child starts %d" % (leg, i, rc, dt, n))
            for l in lines:
                print("   " + l)
    print("%s: child starts per run (%d runs): %s" % (leg, N, starts))

l = socket.socket(); l.bind(("", 24900)); l.listen()
s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
    s.bind(("", 24900)); print("C listener port, SO_REUSEADDR bind: accepted (would miss a taker)")
except OSError as e:
    print("C listener port, SO_REUSEADDR bind: refused errno %d (a real taker is still seen)" % e.errno)
