"""m68b r22-B1 probe (POSIX, stdlib, no condor): the B1 row's held-port leg ("with the range's first port held by a
listener it announces the next") on Linux and macOS, for a listener bound to the wildcard ("", p) and to
("127.0.0.1", p).

Per listener address it prints:
  free   = announce_proto.free(p) while the listener holds p (a SO_REUSEADDR bind of ("", p); False = seen as taken)
  proto  = the port announce_proto.py announces over [p, p + 2] ({python} -m http.server {port}, check http:/ and tcp,
           $_CONDOR_MACHINE_AD Machine = localhost as in the harness); the leg passes iff it is p + 1
  noscan = the same with a mutant whose free() is always True (no scan): its announced port, or its exit line
Run: <python> probe_r22_b1_held_port.py
  Linux: htcondor/mini:25.13.2-el9 (container r22p-mini, removed), /usr/bin/python3 3.9.25 and /opt/venv/bin/python 3.12.
  macOS 26 arm64 (the planner's host): /usr/bin/python3 3.9.6 and uv python 3.12.
"""
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
FREE = '''def free(port):
    """A bind with SO_REUSEADDR: refused by a listener, not by a TIME_WAIT the self-check itself left behind."""'''
src = open(os.path.join(HERE, "announce_proto.py")).read()
assert FREE in src
d = tempfile.mkdtemp(prefix="r22b1-port-")
os.chdir(d)
open("proto.py", "w").write(src)
open("noscan.py", "w").write(src.replace(FREE, FREE + "\n    return True"))
open("machine.ad", "w").write('Machine = "localhost"\n')
env = {**os.environ, "_CONDOR_MACHINE_AD": os.path.join(d, "machine.ad")}
sys.path.insert(0, d)
import proto  # noqa: E402


def base():
    for b in range(24000, 60000, 10):
        try:
            for p in range(b, b + 3):
                s = socket.socket(); s.bind(("", p)); s.close()
            return b
        except OSError:
            s.close()


def announce(script, lo, check):
    open("graphed-secret", "w").write("00" * 32)
    json.dump({"argv": ["{python}", "-m", "http.server", "{port}"], "env": {}, "check": check, "ports": [lo, lo + 2],
               "key": "k", "url": "http://127.0.0.1:1", "watch": None, "python": sys.executable, "timeout_s": 15,
               "lease_s": 2, "beat_s": 1}, open("svc.json", "w"))
    out = subprocess.run([sys.executable, script, "svc.json"], env=env, capture_output=True, text=True, timeout=60).stdout
    m = re.search(r"body='k localhost:(\d+)", out)
    if m:
        return int(m.group(1))
    return [l.split("] ", 1)[1] for l in out.splitlines() if "not ready" in l]


print("%s | python %s" % (sys.platform, sys.version.split()[0]))
for addr in ("", "127.0.0.1"):
    for check in ("http:/", "tcp"):
        lo = base()
        lst = socket.socket()
        lst.bind((addr, lo))
        lst.listen()
        a, b = announce("proto.py", lo, check), announce("noscan.py", lo, check)
        print("  listener %-11r check %-6s free(p) %-5s | proto announces %s (leg %s) | noscan %s (leg %s)"
              % ((addr or "wildcard"), check, proto.free(lo), a, "PASS" if a == lo + 1 else "FAIL", b,
                 "PASS" if b == lo + 1 else "FAIL"))
        lst.close()
os.chdir("/")
shutil.rmtree(d)
