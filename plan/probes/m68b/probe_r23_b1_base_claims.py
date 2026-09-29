"""m68b r23-B1 probe: B1's premises about code m68a changed, driven against executors 0e48380 (m68a merged).

One line per premise, each printing what the code does (a fake schedd logs every bindings call):
  K  `CondorPilots._submit(htc, schedd, desc, n, stack)` puts the cluster's removal on `stack` when
     `schedd.submit` returns; closing that stack is `_remove`: a spooled completed job is retrieved, then what
     is queued removed, with no drain; a raising spool closes it too
  D  `CondorPilots.stop` = drain (`CLOSE_WAIT_S`) + that stack's close + secret unlink
  H  `recipes.http_server` inputs by `root`
  A  `counts_as_alive`: held with code 16 (spooling) alive, code 13 not
  C  a generic copy with `service_ports=None` has `service_hosts == ("cluster",)`; lxplus keeps `MY.SendCredential`
  E  the engine's managed leg refuses a GPU recipe on a backend without `host_service`, naming it
  R  `RunHandle._poll` reads history with `match=1` once the job left the queue
Run (macOS arm64, uv venv python 3.12.10 with graphed d0ad16b):
  PYTHONPATH=<executors 0e48380>/src python probe_r23_b1_base_claims.py
Probe T/P of probe_code_premises.py (task server unpickles every signed body; CLOSE_WAIT_S) re-run on the same tree
is appended to the .txt.
"""
import contextlib
import dataclasses
import inspect
import tempfile
import time
from pathlib import Path

from graphed.services import Launch, ServiceSpec

from graphed_executors.htcondor_backend import driverless, launch
from graphed_executors.htcondor_backend.launch import CondorPilots
from graphed_executors.htcondor_backend.sites import SITES, counts_as_alive
from graphed_executors.submit import recipes, services

print("# executors from", launch.__file__)


class Result:
    def cluster(self):
        return 7


class Schedd:
    def __init__(self, ads, spool_raises=False):
        self.log, self.ads, self.spool_raises = [], ads, spool_raises

    def submit(self, sub, count, spool):
        self.log.append(("submit", count, spool))
        return Result()

    def spool(self, result):
        self.log.append(("spool",))
        if self.spool_raises:
            raise OSError("spool failed")

    def query(self, constraint, projection):
        self.log.append(("query", constraint))
        return self.ads

    def retrieve(self, constraint):
        self.log.append(("retrieve", constraint))

    def act(self, action, constraint, reason=None):
        self.log.append(("act", action, constraint))

    def history(self, constraint, projection, match=None):
        self.log.append(("history", constraint, match))
        return [{"JobStatus": 4, "ExitCode": 0}]


class Htc:
    class JobAction:
        Remove = "Remove"

    @staticmethod
    def Submit(d):
        return d


spooled = CondorPilots(dataclasses.replace(SITES["generic"], spool=True), log_dir=tempfile.mkdtemp())
s = Schedd([{"JobStatus": 4}])
stack = contextlib.ExitStack()
spooled._submit(Htc, s, {}, 1, stack)
before = list(s.log)
t0 = time.monotonic()
stack.close()
print(f"K after _submit: {before}; stack.close() adds {s.log[len(before):]} in {time.monotonic() - t0:.2f}s")
s = Schedd([{"JobStatus": 1}], spool_raises=True)
try:
    with contextlib.ExitStack() as stack:
        spooled._submit(Htc, s, {}, 1, stack)
except OSError as exc:
    print(f"K a raising spool ({exc}): {s.log}")
src = inspect.getsource(CondorPilots.stop)
print("D CondorPilots.stop calls:", [n for n in ("_drain", "_stack.close()", "_secret.unlink", "retrieve", "act(")
                                     if n in src], "| CLOSE_WAIT_S =", launch.CLOSE_WAIT_S)

for kw in ({}, {"root": "site"}, {"root": "data/site"}):
    spec = recipes.http_server("h", **kw)
    print(f"H http_server(**{kw}): argv {spec.launch.argv} inputs {spec.launch.inputs}")

print("A counts_as_alive held 16:", counts_as_alive({"JobStatus": 5, "HoldReasonCode": 16}),
      "| held 13:", counts_as_alive({"JobStatus": 5, "HoldReasonCode": 13}))
print("C generic service_ports=None service_hosts:",
      dataclasses.replace(SITES["generic"], service_ports=None).service_hosts,
      "| lxplus MY.SendCredential:", SITES["lxplus"].submit.get("MY.SendCredential"))


class NoHost:
    service_hosts = ("cluster",)


gpu = ServiceSpec("g", "http", check="http:/", launch=Launch(argv=("x",), resources={"gpus": 1}))
try:
    services.ServiceSet([gpu], NoHost(), scope="probe")._managed(gpu, {}, contextlib.ExitStack())
except services.ServiceUnavailable as exc:
    print("E backend without host_service:", str(exc)[-150:])

h = driverless.RunHandle(site="generic", schedd="s", cluster=7, log_dir=Path(tempfile.mkdtemp()), submitted_at=0.0)
s = Schedd([])
h._poll(s)
print("R RunHandle._poll on a job gone from the queue:", s.log)
