"""Record the Hgg processor's op shapes on coffea NanoEvents mode='graphed'; one line per op."""
import functools, operator, os, traceback
import awkward as ak, numpy
import graphed
from graphed.awkward import gak
from graphed.core.execution import SequentialRunner
from coffea.nanoevents import NanoEventsFactory, NanoAODSchema

PATH = os.path.expanduser("~/vibe-coding/coffea-graphed-mvp/tests/samples/nano_dy.root")
ev = NanoEventsFactory.from_root({PATH: "Events"}, schemaclass=NanoAODSchema, mode="graphed",
                                metadata={"dataset": "DY"}).events()
outs = {}

def t(name, fn, keep=True):
    try:
        r = fn()
        if keep and isinstance(r, graphed.Array):
            outs[name] = r
        print(f"OK   {name}: {type(r).__name__}")
    except Exception as exc:
        print(f"FAIL {name}: {type(exc).__name__}: {str(exc).splitlines()[0][:160]}")

P = lambda: ev.Photon
t("events.metadata['dataset']", lambda: ev.metadata["dataset"], keep=False)
t("hasattr(events,'GenPart')", lambda: hasattr(ev, "GenPart"), keep=False)
t("'superclusterEta' in Photon.fields", lambda: "superclusterEta" in ev.Photon.fields, keep=False)
t("Photon.fields", lambda: list(ev.Photon.fields)[:3], keep=False)
t("events.Flag[name] reduce and_", lambda: functools.reduce(operator.and_, (ev.Flag[n] for n in ("goodVertices", "globalSuperTightHalo2016Filter"))))
t("HLT.fields startswith loop", lambda: [f for f in ev.HLT.fields if f.startswith("Ele")][:2], keep=False)
t("gak.num(genWeight, axis=0) -> int()", lambda: int(gak.num(ev.genWeight, axis=0)), keep=False)
t("gak.sum(genWeight>0) -> int()", lambda: int(gak.sum(ev.genWeight > 0)), keep=False)
t("genWeight.to_numpy()", lambda: ev.genWeight.to_numpy(), keep=False)
t("len(events)", lambda: len(ev), keep=False)
t("gak.sum(genWeight>0) deferred", lambda: gak.sum(ev.genWeight > 0))
t("events[mask] (run range & MET)", lambda: ev[(ev.run >= 1) & (ev.MET.pt > 10)])
t("numpy.abs(a - b) % (2*pi)", lambda: numpy.abs(ev.MET.phi - ev.Jet.phi) % (2 * numpy.pi))
t("gak.where", lambda: gak.where(ev.Jet.pt > 30, ev.Jet.pt, 0.0))
t("gak.any(axis=1)", lambda: gak.any(ev.Jet.pt > 50, axis=1))
t("gak.zeros_like / ones_like", lambda: gak.zeros_like(ev.Photon.pt) + gak.ones_like(ev.Photon.pt))
t("setitem Photon['mass']", lambda: (P().__setitem__("mass", gak.zeros_like(ev.Photon.pt)), P())[1])
t("events['Photon'] = photons", lambda: (ev.__setitem__("Photon", ev.Photon), ev.Photon)[1])
t("Rho * ones_like(photons.pt)", lambda: ev.fixedGridRhoFastjetAll * gak.ones_like(ev.Photon.pt))
t("numpy.exp/sqrt/cosh/sinh/log/arctan/tan/sin/cos/arcsin", lambda: numpy.log(numpy.exp(ev.Photon.eta)) + numpy.sqrt(ev.Photon.pt) + numpy.cosh(ev.Photon.eta) + numpy.sinh(ev.Photon.eta) + numpy.arctan(ev.Photon.phi) + numpy.tan(ev.Photon.phi / 4) + numpy.sin(ev.Photon.phi) + numpy.cos(ev.Photon.phi) + numpy.arcsin(ev.Photon.phi / 4))
t("numpy.where(graphed, ...)", lambda: numpy.where(ev.Photon.eta > 0, 310.0, -310.0))
t("numpy.isnan", lambda: numpy.isnan(ev.Photon.pt))
t("numpy.copy(graphed)", lambda: numpy.copy(ev.Photon.pt))
t("PV.x.to_numpy + numpy.zeros_like + boolean setitem (pre-v13 ScEta path)", lambda: numpy.zeros_like(ev.PV.x.to_numpy()), keep=False)
t("photons[mask]", lambda: ev.Photon[(ev.Photon.pt > 25) & (numpy.abs(ev.Photon.eta) < 2.5)])
t("gak.argsort + index", lambda: ev.Photon[gak.argsort(ev.Photon.pt, ascending=False)])
t("gak.combinations(fields=)", lambda: gak.combinations(ev.Photon, 2, fields=["pho_lead", "pho_sublead"]))
t("candidate + candidate (.pt/.mass/.energy/.z/.charge)", lambda: (lambda d: (d.pho_lead + d.pho_sublead).mass + (d.pho_lead + d.pho_sublead).energy + (d.pho_lead + d.pho_sublead).z + (d.pho_lead + d.pho_sublead).charge)(gak.combinations(ev.Photon, 2, fields=["pho_lead", "pho_sublead"])))
t("setitem on combinations record", lambda: (lambda d: (d.__setitem__("pt", (d.pho_lead + d.pho_sublead).pt), d.pt)[1])(gak.combinations(ev.Photon, 2, fields=["pho_lead", "pho_sublead"])))
t("gak.with_name(..., 'PtEtaPhiMCandidate')", lambda: gak.with_name(gak.combinations(ev.Photon, 2, fields=["pho_lead", "pho_sublead"]), "PtEtaPhiMCandidate"))
t("gak.zip + with_name PtEtaPhiMCandidate", lambda: gak.with_name(gak.zip({k: ev.Jet[k] for k in ("pt", "eta", "phi", "mass")}), "PtEtaPhiMCandidate"))
t("metric_table (delta_r_mask) + gak.all(axis=-1)", lambda: gak.all(ev.Jet.metric_table(ev.Muon) > 0.4, axis=-1))
t("metric_table on zipped PtEtaPhiMCandidate", lambda: gak.all(gak.with_name(gak.zip({k: ev.Jet[k] for k in ("pt", "eta", "phi", "mass")}), "PtEtaPhiMCandidate").metric_table(ev.Muon) > 0.4, axis=-1))
t("bool(gak.num(x, axis=0) > 0) in if", lambda: bool(gak.num(ev.Muon.pt, axis=0) > 0), keep=False)
t("gak.local_index==n, pad_none, fill_none, flatten (choose_jet)", lambda: gak.flatten(gak.fill_none(gak.pad_none(ev.Jet.pt[gak.local_index(ev.Jet.pt) == 0], 1), -999.0)))
t("gak.firsts + ~gak.is_none + mask", lambda: (lambda f: f[~gak.is_none(f)])(gak.firsts(ev.Photon)))
t("gak.flatten/unflatten with counts", lambda: gak.unflatten(gak.flatten(ev.Jet.pt, axis=1), gak.num(ev.Jet)))
t("gak.fields + record dict -> ak.Array({...}) rebuild", lambda: ak.Array({f: ev.Photon[f] for f in gak.fields(ev.Photon)[:3]}), keep=False)
t("gak.zip dict rebuild", lambda: gak.zip({f: ev.Photon[f] for f in gak.fields(ev.Photon)[:3]}))
t("with numpy.errstate(...)", lambda: (numpy.errstate(over="ignore").__enter__(), numpy.log(ev.Jet.pt))[1])
t("events.attrs['@events_factory']._partition_key", lambda: ev.attrs["@events_factory"]._partition_key, keep=False)
t("gak.to_arrow_table", lambda: gak.to_arrow_table(ev.Photon.pt), keep=False)

print("RECORDED_OK_OUTPUTS", len(outs))
from coffea_plan_helpers import reduce_lens, combine_lens, empty_lens  # noqa: E402
try:
    plan = graphed.aggregate_plan(*outs.values(), reduce=reduce_lens, combine=combine_lens, empty=empty_lens)
    res = SequentialRunner().run(plan).value
    print("PLAN_RUN_OK n_outputs", len(res))
except Exception as exc:
    print("PLAN_RUN_FAIL", type(exc).__name__, str(exc).splitlines()[0][:300])
print("BOOL_NUM_AXIS0_VALUE", bool(gak.num(ev.Muon.pt, axis=0) > 0), "and for an empty-selection", bool(gak.num(ev.Muon.pt[ev.Muon.pt > 1e9], axis=0) > 0))
for label, fn in (("with_name", lambda: gak.with_name(gak.zip({k: ev.Jet[k] for k in ("pt", "eta", "phi", "mass")}), "PtEtaPhiMCandidate")),
                  ("setitem", lambda: ev.Photon.__setitem__("mass", gak.zeros_like(ev.Photon.pt)))):
    try:
        fn()
    except Exception as exc:
        print("FULL_ERROR", label, type(exc).__name__, " ".join(str(exc).split())[:500])
print("NUMPY_WHERE_TYPE", type(numpy.where(ev.Photon.eta > 0, 310.0, -310.0)), numpy.shape(numpy.where(ev.Photon.eta > 0, 310.0, -310.0)))
