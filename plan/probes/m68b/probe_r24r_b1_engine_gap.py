"""m68b r24-B1 review probe: how long after a plan task's GET of a managed service does the run release that service?
B1's live row (a) compares run 2's task GET time t with its service's history EnteredCurrentStatus (whole seconds),
so the gap decides whether the two share a second. Measured on m68a's engine (executors 0e48380 + graphed d0ad16b's
macOS arm64 wheel, Python 3.12, ThreadBackend(2), a driver-hosted recipes.http_server): time from the last task's GET
to `_stop_child` (the release), 1-task and 4-task plans, 5 runs each. A condor run adds the pilot's /result POST and
`_remove`'s query + act (milliseconds each).

Run (scratch venv, no container): python probe_r24r_b1_engine_gap.py > probe_r24r_b1_engine_gap.txt
"""
import time
import urllib.request
from dataclasses import dataclass, replace

from graphed.core.execution import Partition, Plan, Task
from graphed_executors.submit import SubmitRunner, ThreadBackend
from graphed_executors.submit import services as svc
from graphed_executors.submit.recipes import http_server

GETS: list[float] = []
RELEASES: list[float] = []


@dataclass(frozen=True)
class Get:
    endpoint: str | None = None

    def bind_services(self, endpoints):
        return replace(self, endpoint=endpoints["web"])

    def __call__(self, partition, resources):
        with urllib.request.urlopen(self.endpoint + "/", timeout=5) as r:
            r.read()
        GETS.append(time.time())
        return (partition.uri,)


def concat(a, b):
    return a + b


def empty():
    return ()


_stop = svc._stop_child


def stop(proc, name):
    RELEASES.append(time.time())
    return _stop(proc, name)


svc._stop_child = stop
for n in (1, 4):
    gaps = []
    for _ in range(5):
        tasks = tuple(Task(j, Partition(f"mem://gap/{j}", "", j, j + 1)) for j in range(n))
        plan = Plan(process=Get(), combine=concat, empty=empty, tasks=tasks, services=(http_server("web"),))
        GETS.clear()
        RELEASES.clear()
        with SubmitRunner(ThreadBackend(2)) as runner:
            runner.run(plan)
        gaps.append(RELEASES[0] - max(GETS))
    print(f"{n}-task plan: last task GET -> release:", ["%.1f ms" % (g * 1e3) for g in gaps])
