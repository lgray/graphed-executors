"""m69a: (a) the real infer_nano_version on coffea graphed NanoEvents of the fixture; (b) numpy.sum vs ak.sum on float32 genWeight-like data."""
import sys, os
import numpy as np, awkward as ak
sys.path.insert(0, os.path.expanduser("~/vibe-coding/graphed-workdir/lanes/htcondor/refs/HiggsDNA"))
from higgs_dna.utils.misc_utils import infer_nano_version
from coffea.nanoevents import NanoEventsFactory, NanoAODSchema
f = os.path.join(os.path.dirname(__file__), "fixtures/nano_hgg_v15.root")
ev = NanoEventsFactory.from_root({f: "Events"}, schemaclass=NanoAODSchema, mode="graphed").events()
print("GRAPHED_TYPE", type(ev).__module__, type(ev).__name__, "| hasattr GenPart", hasattr(ev, "GenPart"))
print("INFER_NANO_VERSION graphed", infer_nano_version(ev))
eager = NanoEventsFactory.from_root({f: "Events"}, schemaclass=NanoAODSchema, mode="eager").events()
print("INFER_NANO_VERSION eager", infer_nano_version(eager))
rng = np.random.default_rng(1)
diff = 0
for n in (200, 4180, 100000):
    w = ak.Array((rng.choice([-1.0, 1.0], n) * rng.uniform(50, 250, n)).astype(np.float32))
    a, b = np.sum(w.to_numpy()), ak.sum(w)
    diff += a != b
    print("SUMS", n, repr(a), repr(b), "str_equal", str(a) == str(b), type(a).__name__, type(b).__name__)
print("SUM_MISMATCHES", diff)
