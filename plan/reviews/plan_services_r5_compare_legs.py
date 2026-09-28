"""r5 probe: a compare_part built from plan §4's text; delete each leg, run control + 7 mutations."""
import glob, json, os, sys, tempfile
from importlib import resources
sys.path.insert(0, os.path.expanduser("~/vibe-coding/graphed-workdir/lanes/htcondor/refs/hgg"))
import inclusive_processor as tpl
import numpy as np, pyarrow as pa, pyarrow.compute as pc, pyarrow.parquet as pq
from coffea.nanoevents import NanoEventsFactory
fx = os.path.expanduser("~/vibe-coding/graphed-workdir/lanes/htcondor/probes/services-code/fixtures/nano_hgg_v15.root")
meta = json.load(resources.files("higgs_dna.metaconditions").joinpath("Era2022_v1.json").open())
out = tempfile.mkdtemp()
proc = tpl.HggInclusiveProcessor(metaconditions=meta, output_location=out, year={"MC": ["2024"]})
C = proc.process(NanoEventsFactory.from_root({fx: "Events"}, entry_start=0, entry_stop=100, metadata={"dataset": "MC", "filename": "f.root"}).events())
path = glob.glob(f"{out}/**/*.parquet", recursive=True)[0]
T = pq.read_table(path)

def uview(a):
    a = np.asarray(a)
    return a.view(f"u{a.dtype.itemsize}") if a.dtype.kind == "f" else a

def compare(e, a, legs):
    (ce, te), (ca, ta) = e, a
    out = []
    if "counters" in legs and ce != ca: out.append("counters")
    if "schema" in legs and ta.schema.remove_metadata() != te.schema.remove_metadata(): out.append("schema")
    if "names" in legs and te.column_names != ta.column_names: out.append("names")
    for n in te.column_names:
        if n not in ta.column_names: out.append(f"missing {n}"); continue
        x, y = te.column(n).combine_chunks(), ta.column(n).combine_chunks()
        if "validity" in legs and not pc.is_valid(x).equals(pc.is_valid(y)): out.append(f"validity {n}")
        if "values" in legs:
            xv, yv = uview(x.drop_null().to_numpy(zero_copy_only=False)), uview(y.drop_null().to_numpy(zero_copy_only=False))
            if xv.shape != yv.shape or not np.array_equal(xv, yv): out.append(f"values {n}")
    if "kv" in legs and (te.schema.metadata or {}) != (ta.schema.metadata or {}): out.append("kv")
    return out

fcol = next(n for n in T.column_names if pa.types.is_float64(T.schema.field(n).type))
icol = next(n for n in T.column_names if pa.types.is_int64(T.schema.field(n).type))
def setcol(t, n, arr): return t.set_column(t.column_names.index(n), pa.field(n, arr.type), arr)
def ulp(t):
    v = t.column(fcol).to_numpy().copy(); v[0] = np.nextafter(v[0], np.inf); return setcol(t, fcol, pa.array(v))
def narrow(t): return setcol(t, icol, pc.cast(t.column(icol), pa.int32()))
def nullify(t):
    v = t.column(icol).to_numpy(); m = np.zeros(len(v), bool); m[3] = True
    return setcol(t, icol, pa.array(v, mask=m))
def swap(t):
    n = t.column_names; i, j = 0, 1; order = n[:]; order[i], order[j] = order[j], order[i]; return t.select(order)
def kv(t):
    md = dict(t.schema.metadata); k = next(iter(md)); md[k] = md[k] + b"0"; return t.replace_schema_metadata(md)
Cc = {k: dict(v) for k, v in C.items()}; Cc["MC"]["nTot"] += 1
MUT = {"control(reread)": (C, pq.read_table(path)), "ulp": (C, ulp(T)), "drop_row": (C, T.slice(1)), "swap": (C, swap(T)),
       "int64->int32": (C, narrow(T)), "null": (C, nullify(T)), "kv": (C, kv(T)), "counter": (Cc, T)}
ALL = {"counters", "schema", "names", "validity", "values", "kv"}
print("COLS float", fcol, "int", icol, "rows", T.num_rows)
for leg in ["(none)"] + sorted(ALL):
    legs = ALL - {leg}
    r = {m: bool(compare((C, T), a, legs)) for m, a in MUT.items()}
    ctl_ok = not r["control(reread)"]; missed = [m for m, v in r.items() if m != "control(reread)" and not v]
    print(f"DELETE {leg:9s} control_clean {ctl_ok} missed {missed}")
# leg-named assertion: each mutation must produce its own leg's entry
EXP = {"ulp": f"values {fcol}", "drop_row": None, "swap": "schema", "int64->int32": "schema", "null": f"validity {icol}", "kv": "kv", "counter": "counters"}
for leg in ["(none)"] + sorted(ALL):
    legs = ALL - {leg}
    missed = [m for m, e in EXP.items() if not (compare((C, T), MUT[m], legs) if e is None else e in compare((C, T), MUT[m], legs))]
    print(f"NAMED DELETE {leg:9s} missed {missed}")
