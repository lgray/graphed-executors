"""What ServiceJob.match_refusal does with an empty slot list (the call _host_service guards with `if machines`):
a queued job ad stand-in, no bindings; classad2 is never imported when no slot is given."""
import sys
import types
from types import SimpleNamespace

from graphed.services import Launch, ServiceSpec

from graphed_executors.htcondor_backend import CondorPilots
from graphed_executors.htcondor_backend.services import ServiceJob


class Ad(dict):
    def eval(self, key):
        return self[key]


sys.modules.setdefault("classad2", types.ModuleType("classad2"))  # stand-in: no slot ad is built from it
pilots = CondorPilots("generic", log_dir="/tmp/rv-no-ads")
pilots._schedd = SimpleNamespace(query=lambda constraint: [Ad(RequestMemory=512, RequestCpus=1)])
spec = ServiceSpec("s", kind="rv", check="tcp", launch=Launch(("{python}", "-c", "pass")))
job = ServiceJob(spec, pilots, key="scope-k", url="http://127.0.0.1:1", secret=b"s")
job.cluster = 7
try:
    print("match_refusal([]) ->", job.match_refusal([]))
except Exception as exc:
    print("match_refusal([]) raises", type(exc).__name__, exc)
