"""Derive a small NanoAOD v15 fixture with diphotons: nano_tt_v15.root (200 ev, every branch the Hγγ
template reads) with two loose photons + the diphoton HLT path injected into the first N events."""
import sys, numpy as np, awkward as ak, uproot
src, dst, N = sys.argv[1], sys.argv[2], int(sys.argv[3])
tree = uproot.open(src)["Events"]
arr = tree.arrays()
names = tree.keys()
colls = sorted({n[1:] for n in names if n.startswith("n") and any(k.startswith(n[1:] + "_") for k in names)})
out = {}
for c in colls:
    out[c] = ak.zip({k[len(c) + 1:]: arr[k] for k in names if k.startswith(c + "_")})
flat = [n for n in names if not n.startswith("n") and not any(n.startswith(c + "_") for c in colls)]
flat += [n for n in names if n.startswith("n") and n[1:] not in colls and n[1:] not in names]  # n* that count nothing; jagged counters are derived
for n in flat:
    out[n] = arr[n]
# --- inject two photons per event into the first N events (a template photon, fields overridden)
ph = ak.flatten(out["Photon"])
tmpl = ph[ak.argmax(ph.mvaID, axis=0, keepdims=False)]
rng = np.random.default_rng(20260925)
def photon(pt, eta, phi):
    p = tmpl
    for f, v in dict(pt=pt, eta=eta, phi=phi, mvaID=0.95, r9=0.96, hoe=0.01, sieie=0.009, electronVeto=True,
                     pixelSeed=False, isScEtaEB=abs(eta) < 1.4442, isScEtaEE=abs(eta) > 1.566,
                     pfChargedIsoPFPV=0.1, trkSumPtHollowConeDR03=0.1, pfPhoIso03=0.5,
                     superclusterEta=eta, mass=0.0, charge=0).items():
        if f in p.fields:
            p = ak.with_field(p, ak.values_astype(ak.Array([v]), ak.type(ph[f]).content.primitive)[0] if ak.type(ph[f]).content.primitive not in ("bool",) else bool(v), f)
    return p
pairs = []
for i in range(N):
    pt1, pt2 = 80 + 40 * rng.random(), 45 + 15 * rng.random()
    e1, e2 = rng.uniform(-1.3, 1.3), rng.uniform(-1.3, 1.3)
    f1 = rng.uniform(-np.pi, np.pi); f2 = f1 + rng.uniform(2.6, 3.1)
    f2 = (f2 + np.pi) % (2 * np.pi) - np.pi
    pairs.append([photon(pt1, e1, f1), photon(pt2, e2, f2)])
injected = ak.Array(pairs)
out["Photon"] = ak.concatenate([injected, out["Photon"][N:]], axis=0)
hlt = "HLT_Diphoton30_18_R9IdL_AND_HE_AND_IsoCaloId"
for path in [hlt, *[k for k in names if k.startswith("HLT_Diphoton30_22_R9Id_OR_IsoCaloId_AND_HE_R9Id_Mass9")]]:
    out[path] = ak.concatenate([ak.Array([True] * N), out[path][N:]])
with uproot.recreate(dst) as f:
    f.mktree("Events", {k: ak.type(v).content for k, v in out.items()}, counter_name=lambda c: "n" + c)
    f["Events"].extend(out)
    runs = uproot.open(src)["Runs"].arrays() if "Runs" in uproot.open(src) else ak.Array({"run": np.array([1])})
    f.mktree("Runs", {k: ak.type(runs[k]).content for k in runs.fields})
    f["Runs"].extend({k: runs[k] for k in runs.fields})
t2 = uproot.open(dst)["Events"]
print("written", dst, "entries", t2.num_entries, "branches", len(t2.keys()), "(src", len(names), ")")
print("nPhoton first", t2["nPhoton"].array()[:3].tolist(), "HLT first", t2[hlt].array()[:2].tolist(), "Photon_pt[0]", t2["Photon_pt"].array()[0].tolist())
print("missing vs src:", sorted(set(names) - set(t2.keys()))[:10])
