import sys, concurrent.futures as cf
sys.path.insert(0, "/Users/lgray/vibe-coding/lanes/htcondor/graphed-executors/tests/frozen/m42")
from submit_backends import concat_plan, concat, empty_text, mem_partitions
from graphed_executors.submit import SubmitCapabilities, SubmitRunner
from graphed_executors.parsl_backend._shim import _parsl_task_shim
from graphed_executors.parsl_backend.backend import _ParslFuture
from graphed.core.execution import Plan, Task

class WorkerLost(Exception):
    def __init__(self, key, pilot): super().__init__(key, pilot); self.key, self.pilot = key, pilot

POISON = sys.argv[2]
class B:
    capabilities = SubmitCapabilities(*([False]*7))
    def __init__(self): self.h = {}
    def n_workers(self): return 1
    def submit(self, fn, *args, key, **kw):
        resolved = tuple(a.result() if isinstance(a, _ParslFuture) else a for a in args)  # parsl verbatim
        raw = cf.Future()
        task = [a for a in resolved if isinstance(a, Task)]
        if task and task[0].partition.uri == POISON:
            raw.set_exception(WorkerLost(key, "host:1"))
        else:
            raw.set_result(_parsl_task_shim(fn, *resolved))
        return _ParslFuture(raw, self.h)
    def broadcast(self, p, *, token): return p
    def subscribe_events(self, t, h): return lambda: None
    def cancel(self, f): pass
    def close(self): pass
    def describe_failure(self, exc):
        return (exc.key, exc.pilot) if isinstance(exc, WorkerLost) else None

n = int(sys.argv[1])
plan = concat_plan(n, "p")
POISON = sorted(plan.tasks, key=lambda t: t.key)[0].partition.uri
try:
    SubmitRunner(B()).run(plan)
except BaseException as e:
    print(f"n={n}: {type(e).__name__}: {str(e)[:90]}")
