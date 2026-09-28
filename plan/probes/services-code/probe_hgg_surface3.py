import json, os, tempfile
from graphed.awkward import gak
from coffea.lumi_tools import LumiMask
from coffea.nanoevents import NanoEventsFactory, NanoAODSchema
ev = NanoEventsFactory.from_root({os.path.expanduser("~/vibe-coding/coffea-graphed-mvp/tests/samples/nano_dy.root"): "Events"}, schemaclass=NanoAODSchema, mode="graphed").events()
p = os.path.join(tempfile.mkdtemp(), "golden.json"); json.dump({"1": [[1, 100000]]}, open(p, "w"))
try:
    m = LumiMask(p)(ev.run, ev.luminosityBlock); print("LUMIMASK_GRAPHED OK", type(m).__name__)
except Exception as exc:
    print("LUMIMASK_GRAPHED FAIL", type(exc).__name__, " ".join(str(exc).split())[:250])
import correctionlib.schemav2 as cs, correctionlib
c = cs.Correction(name="id", version=1, inputs=[cs.Variable(name="eta", type="real")], output=cs.Variable(name="w", type="real"), data=1.0)
cj = os.path.join(tempfile.mkdtemp(), "c.json"); open(cj, "w").write(cs.CorrectionSet(schema_version=2, corrections=[c]).model_dump_json())
cset = correctionlib.CorrectionSet.from_file(cj)
try:
    r = cset["id"].evaluate(gak.flatten(ev.Jet.eta, axis=1)); print("CORRECTIONLIB_DIRECT_EVALUATE OK", type(r).__name__)
except Exception as exc:
    print("CORRECTIONLIB_DIRECT_EVALUATE FAIL", type(exc).__name__, " ".join(str(exc).split())[:200])
try:
    r = gak.apply_correction(cj, "id", [gak.flatten(ev.Jet.eta, axis=1)], None, args=["$0"]); print("GAK_APPLY_CORRECTION OK", type(r).__name__)
except Exception as exc:
    print("GAK_APPLY_CORRECTION FAIL", type(exc).__name__, " ".join(str(exc).split())[:200])
