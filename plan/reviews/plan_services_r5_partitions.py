"""r5 probe: explicit Partition ranges through aggregate_plan on coffea mode='graphed' NanoEvents."""
import os
import graphed
from graphed.awkward import gak
from graphed.core import Partition
from coffea.nanoevents import NanoEventsFactory, NanoAODSchema
fx = os.path.expanduser("~/vibe-coding/graphed-workdir/lanes/htcondor/probes/services-code/fixtures/nano_hgg_v15.root")
ev = NanoEventsFactory.from_root({fx: "Events"}, schemaclass=NanoAODSchema, mode="graphed", metadata={"dataset": "MC"}).events()
n = gak.num(ev, axis=0); gw = gak.sum(ev.genWeight); npho = gak.sum(gak.num(ev.Photon.pt, axis=1))
parts = [Partition(fx, "Events", 0, 100), Partition(fx, "Events", 100, 200)]
plan = graphed.aggregate_plan(n, gw, npho, reduce=lambda v: [(float(v[0]), float(v[1]), float(v[2]))], combine=lambda a, b: a + b, empty=list, partitions=parts)
print("PLAN_TASKS", [repr(t)[:120] for t in plan.tasks])
print("PER_PARTITION", __import__("graphed.core.execution", fromlist=["x"]).SequentialRunner().run(plan).value)
import uproot; t = uproot.open(fx)["Events"]
for s, e in [(0, 100), (100, 200)]:
    a = t.arrays(["genWeight", "nPhoton"], entry_start=s, entry_stop=e)
    print("EAGER", (s, e), (float(e - s), float(__import__("awkward").sum(a.genWeight)), float(__import__("awkward").sum(a.nPhoton))))
