"""m69b-r1: what graphed d0ad16b does with the server specs of two contexts built with equal arguments (default
name "histserv"): session.declare_service accepts the second, and collate unions both plans' "histserv-0" into
ONE spec, i.e. one server process for both contexts' slots.

Run: ~/vibe-coding/cloud/graphed-histogram/.venv/bin/python probe_same_name_contexts_rv1.py > probe_same_name_contexts_rv1.txt
"""
from __future__ import annotations

from graphed import Session
from graphed.awkward import AwkwardBackend
from graphed.core import Partition
from graphed.core.execution import Plan, Task
from graphed.aggregate import collate
from graphed.services import Launch, ServiceSpec


def server(ctx_memory_mb: int) -> ServiceSpec:  # §5.1 "Server specs", server 0 of a context named "histserv"
    return ServiceSpec("histserv-0", kind="histserv", check="tcp", ports=(10000, 10100),
                       launch=Launch(("{python}", "-m", "histserv", "--port", "{port}", "--prune-after-seconds",
                                      "315360000", "--log-level", "WARNING"), resources={"memory_mb": ctx_memory_mb}),
                       timeout_s=600.0)


s = Session(AwkwardBackend())
s.declare_service(server(2000))
s.declare_service(server(2000))  # a second context, same arguments
print("declare_service twice (equal specs): accepted; declared", sorted(s.services()))
plans = {name: Plan(process=lambda p, r: 1, combine=lambda a, b: a + b, empty=int,
                    tasks=(Task(0, Partition(f"{name}.root", "Events", 0, 1)),), services=(server(2000),))
         for name in ("data", "mc")}
c = collate(plans)
print("collate of two plans each on its own context's histserv-0:", [x.name for x in c.services])
