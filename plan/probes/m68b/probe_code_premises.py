"""m68b code premises, driven against graphed-executors main (c2298d7).

Run: <venv with `-e /home/user/code[htcondor]`>/bin/python probe_code_premises.py > probe_code_premises.txt

 S  site root today: m67 reads `_SELF_SUBMIT_ROOT` (driverless.py), not the profile; a profile outside
    that dict self-submits with no root check; lpc refuses on `jobs_can_submit` first; the refusal order
    for a six-kwarg profile names `worker_ports`. `SiteProfile` field names; a six-kwarg profile builds.
 W  `"/"` as "every path": `PureWindowsPath("C:/x").is_relative_to("/")` is False, so an explicit
    `root == "/"` rule is what keeps the all-OS m67 generic self-submit case green on Windows.
 T  the task server unpickles every signed body before it routes (a signed plain-text /announce is 400
    with an UnpicklingError); unsigned is 403 before any parse; an unknown path falls to /result.
 P  pilots read the secret file as hex (`bytes.fromhex`); `CLOSE_WAIT_S` (CondorPilots.stop's drain wait).
"""

import dataclasses
import inspect
import os
import pickle
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path, PurePosixPath, PureWindowsPath

from graphed.core.execution import Plan

from graphed_executors.htcondor_backend import driverless, launch, pilot, server, sites
from graphed_executors.htcondor_backend.sites import SITES, SiteProfile

print("S SiteProfile fields:", [f.name for f in dataclasses.fields(SiteProfile)])
print("S _SELF_SUBMIT_ROOT =", driverless._SELF_SUBMIT_ROOT)
print("S jobs_can_submit:", {k: p.jobs_can_submit for k, p in SITES.items()})


class Reached(Exception):
    pass


def stop(*_a, **_k):
    raise Reached("bindings reached: every refusal passed")


launch._htcondor = stop
driverless.launch._htcondor = stop


def top(partition, resources):
    return None


plan = Plan(process=pilot._run, combine=pilot._run, empty=None)  # importable module-level callables
env = Path(tempfile.mkdtemp()) / "env"
env.mkdir()
(env / "pyvenv.cfg").write_text("home = /usr/bin\n")


def attempt(label, **kw):
    try:
        driverless.submit_driverless(plan, request_memory_mb=64, **kw)
    except Reached as exc:
        print(f"S {label}: {exc}")
    except ValueError as exc:
        print(f"S {label}: refused: {exc}")


tmp = tempfile.mkdtemp()
attempt("generic pilots=condor log_dir=/tmp/..", site="generic", pilots="condor", log_dir=tmp)
attempt("lxplus pilots=condor log_dir=/tmp/..", site="lxplus", pilots="condor", log_dir=tmp, image="img", env=env)
attempt("lpc pilots=condor", site="lpc", pilots="condor", log_dir=tmp, image="img", env=env)
SITES["custom"] = dataclasses.replace(SITES["generic"], name="custom")  # a site outside the dict
attempt("custom (generic copy) pilots=condor log_dir=/tmp/..", site="custom", pilots="condor", log_dir=tmp)
bare = SiteProfile(name="bare", submit={}, spool=False, ship_env=False, sandbox_root=None, schedd_query=None)
SITES["bare"] = bare
attempt("six-kwarg profile pilots=condor", site="bare", pilots="condor", log_dir=tmp)
src = inspect.getsource(driverless.submit_driverless)
print("S order in submit_driverless: jobs_can_submit @", src.index("jobs_can_submit"),
      "worker_ports @", src.index("worker_ports is None"), "_SELF_SUBMIT_ROOT @", src.index("_SELF_SUBMIT_ROOT"))

print("W PureWindowsPath('C:/Users/x').is_relative_to('/') =", PureWindowsPath("C:/Users/x").is_relative_to("/"))
print("W PurePosixPath('/tmp/x').is_relative_to('/') =", PurePosixPath("/tmp/x").is_relative_to("/"))
print("W PurePosixPath('/afs/cern.ch/u').is_relative_to('/afs') =", PurePosixPath("/afs/cern.ch/u").is_relative_to("/afs"))


class _NoPilots:
    log_dir = None

    def alive(self):
        return 0


ts = server.TaskServer("127.0.0.1", (10000, 10100), _NoPilots())
secret = ts.secret


def post(path, body, signed=True):
    headers = {server.SIG_HEADER: server.sign(secret, body)} if signed else {}
    req = urllib.request.Request(ts.url + path, data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read()[:0]
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode().strip().splitlines()[-1:]


text = b"k1 host.example:10002 host.example"
print("T unsigned plain-text /announce ->", post("/announce", text, signed=False))
print("T signed plain-text /announce ->", post("/announce", text))
print("T signed pickle to /announce ->", post("/announce", pickle.dumps(("p", 0, True, b""))))
print("T signed pickle ('p', 0, True, b'') to /whatever (falls to /result) ->", post("/whatever", pickle.dumps(("p", 0, True, b""))))
ts.close()
ts.shutdown()

print("P pilot reads the secret as:", [l.strip() for l in inspect.getsource(pilot).splitlines() if "fromhex" in l])
print("P launch.write_secret writes:", [l.strip() for l in inspect.getsource(launch.write_secret).splitlines() if "write_text" in l])
print("P CLOSE_WAIT_S =", launch.CLOSE_WAIT_S, "(CondorPilots.stop waits up to this for alive() == 0 before Remove)")
print("P python", sys.version.split()[0], "os", os.name)
