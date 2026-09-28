"""m66/m67 acquisition sites: is each acquired resource registered for release at the point of acquisition?"""
import dataclasses, os, signal, socket, subprocess, sys, tempfile
from pathlib import Path
from graphed_executors.htcondor_backend import launch
from graphed_executors.htcondor_backend.backend import HTCondorBackend
from graphed_executors.htcondor_backend.sites import SITES

def alive(pid):
    try: os.kill(pid, 0); return True
    except OSError: return False

# (a) LocalPilots.start: second Popen fails -> first child unreachable from launcher.stop()
real = subprocess.Popen; spawned = []
def popen(cmd, **kw):
    if spawned: raise OSError("EAGAIN (injected on pilot 2)")
    p = real([sys.executable, "-c", "import time; time.sleep(30)"]); spawned.append(p); return p
launch.subprocess.Popen = popen
lp = launch.LocalPilots()
try: lp.start("http://127.0.0.1:1", b"s", 2)
except OSError as e: print("a LocalPilots.start raised:", e)
lp.stop()
print("a after stop: launcher._procs =", lp._procs, "| first child alive:", alive(spawned[0].pid))
spawned[0].kill(); spawned[0].wait()
launch.subprocess.Popen = real

# (b) HTCondorBackend.__init__: launcher.start raises after acquiring -> ExitStack frees the port, launcher.stop not called
class Half:
    stops = 0
    def start(self, url, secret, n): raise RuntimeError("pilot 2 refused")
    def stop(self): Half.stops += 1
    def alive(self): return 0
s = socket.socket(); s.bind(("", 0)); port = s.getsockname()[1]; s.close()
try: HTCondorBackend(Half(), 2, host="127.0.0.1", port_range=(port, port))
except RuntimeError as e: print("b backend raised:", e)
t = socket.socket(); t.bind(("", port)); t.close()
print("b port free after refused start: True | launcher.stop calls:", Half.stops)

# (c) CondorPilots.start on a spool site: submit succeeds, spool raises -> cluster queued, never recorded
calls = []
class Res:
    def cluster(self): return 4242
class Schedd:
    def submit(self, sub, count, spool): calls.append(("submit", count)); return Res()
    def spool(self, r): calls.append(("spool",)); raise RuntimeError("spool: connection reset")
    def act(self, *a, **k): calls.append(("act",) + a[:1])
    def query(self, **k): return [{"JobStatus": 5}]
class Htc:
    Submit = dict
    param = {"SCHEDD_HOST": "s"}
launch._htcondor = lambda: Htc
prof = dataclasses.replace(SITES["generic"], spool=True)
cp = launch.CondorPilots(prof, log_dir=tempfile.mkdtemp())
cp._choose = lambda htc: ("s", Schedd())
try: cp.start("http://h:1", b"s", 2)
except RuntimeError as e: print("c CondorPilots.start raised:", e)
print("c schedd calls:", calls, "| launcher.cluster:", cp.cluster, "| constraint:", repr(cp._constraint))
try: cp.stop()
except Exception as e: print("c stop():", type(e).__name__, e)
print("c Remove acts reaching cluster 4242:", [c for c in calls if c[0] == "act"])
