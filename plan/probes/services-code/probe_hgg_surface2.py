import os, numpy
import graphed
from graphed.awkward import gak
from coffea.nanoevents import NanoEventsFactory, NanoAODSchema
ev = NanoEventsFactory.from_root({os.path.expanduser("~/vibe-coding/coffea-graphed-mvp/tests/samples/nano_dy.root"): "Events"}, schemaclass=NanoAODSchema, mode="graphed").events()
print("HAS_with_field", hasattr(gak, "with_field"))
for name, fn in (
    ("gak.with_field(photons, zeros, 'mass')", lambda: gak.with_field(ev.Photon, gak.zeros_like(ev.Photon.pt), "mass")),
    ("zip w/ charge + with_name PtEtaPhiMCandidate + metric_table", lambda: gak.all(gak.with_name(gak.zip({k: ev.Jet[k] for k in ("pt", "eta", "phi", "mass")} | {"charge": gak.zeros_like(ev.Jet.pt)}), "PtEtaPhiMCandidate").metric_table(ev.Muon) > 0.4, axis=-1)),
    ("with_name on combinations after with_field pt/eta/phi/mass/charge", lambda: (lambda d: gak.with_name(gak.with_field(gak.with_field(gak.with_field(gak.with_field(gak.with_field(d, (d.pho_lead + d.pho_sublead).pt, "pt"), (d.pho_lead + d.pho_sublead).eta, "eta"), (d.pho_lead + d.pho_sublead).phi, "phi"), (d.pho_lead + d.pho_sublead).mass, "mass"), (d.pho_lead + d.pho_sublead).charge, "charge"), "PtEtaPhiMCandidate"))(gak.combinations(ev.Photon, 2, fields=["pho_lead", "pho_sublead"]))),
    ("gak.where replacing numpy.where", lambda: gak.where(ev.Photon.eta > 0, 310.0, -310.0)),
):
    try:
        r = fn(); print("OK  ", name, type(r).__name__)
    except Exception as exc:
        print("FAIL", name, type(exc).__name__, " ".join(str(exc).split())[:200])
