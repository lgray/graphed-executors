"""m69a: what coffea's graphed NanoEvents exposes for the conversion's witnesses (type, behaviors, source node, metadata)."""
import os
from coffea.nanoevents import NanoEventsFactory, NanoAODSchema
f = os.path.join(os.path.dirname(__file__), "fixtures/nano_hgg_v15.root")
ev = NanoEventsFactory.from_root({f: "Events"}, schemaclass=NanoAODSchema, mode="graphed",
                                 metadata={"dataset": "MC", "filename": "nano_hgg_v15.root"}).events()
print("EVENTS", type(ev).__module__ + "." + type(ev).__qualname__, "| graphed.Array subclass", __import__("graphed").Array in type(ev).__mro__)
pho = ev.Photon
print("PHOTON", type(pho).__qualname__, "| has metric_table", hasattr(pho, "metric_table"), "| has delta_r", hasattr(pho, "delta_r"))
try:
    print("METADATA", ev.metadata)
except Exception as e:
    print("METADATA raises", type(e).__name__, str(e)[:120])
srcs = ev.session.sources()
for nid, d in srcs.items():
    print("SOURCE", nid, type(d).__module__ + "." + type(d).__qualname__)
print("CONTROL hasattr(Photon, 'no_such_method_xyz')", hasattr(pho, "no_such_method_xyz"))
print("PHOTON typestr tail", pho.typestr[-60:])
import uproot
raw = uproot.graphed({f: "Events"})
print("RAW uproot.graphed type", type(raw).__qualname__, "| raw sources", [type(d).__module__ + "." + type(d).__qualname__ for d in raw.session.sources().values()])
try:
    raw.Photon
    print("RAW .Photon OK")
except Exception as e:
    print("RAW .Photon raises", type(e).__name__)
