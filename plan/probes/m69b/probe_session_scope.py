"""m69b-r3: can the context's packing state be scoped to the Session that declares its servers?

m69a's `dataset_plan` builds each dataset's events through coffea -> `uproot.graphed`, which makes a new Session per
call (uproot5-graphed-mvp `src/uproot/_graphed.py` `graphed`: `session = Session(AwkwardBackend(...))`), and `plan()`
collates the datasets. Two sessions each declaring an equal `histserv-0` and collated: how many servers run?

Run: ~/vibe-coding/cloud/graphed-histogram/.venv/bin/python -B probe_session_scope.py > probe_session_scope.txt
"""
from __future__ import annotations

import os
import tempfile

import awkward as ak
from graphed import Session, aggregate_plan
from graphed.aggregate import collate
from graphed.awkward import AwkwardBackend, from_parquet
from graphed.services import Launch, ServiceSpec

d = tempfile.mkdtemp()
paths = {ds: os.path.join(d, f"{ds}.parquet") for ds in ("MC", "Data")}  # one file per dataset, as m69a
for p in paths.values():
    ak.to_parquet(ak.Array({"x": [1.0, 2.0]}), p)
spec = ServiceSpec("histserv-0", kind="histserv", check="tcp",
                   launch=Launch(("{python}", "-m", "histserv", "--port", "{port}"), resources={"memory_mb": 1000}))
plans, sessions = {}, []
for ds in ("MC", "Data"):
    s = Session(AwkwardBackend())
    sessions.append(s)
    s.declare_service(spec)
    ev = from_parquet(s, "events", paths[ds])
    plans[ds] = aggregate_plan(ev.x * 0 + 1, reduce=lambda v: 0, combine=lambda a, b: 0,
                               empty=int, services=["histserv-0"])
print("distinct sessions:", sessions[0] is not sessions[1])
print("per-plan services:", {ds: [x.name for x in p.services] for ds, p in plans.items()})
print("collated services:", [x.name for x in collate(plans).services])
