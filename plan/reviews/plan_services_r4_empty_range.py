"""r4 probe: the original on fixture ranges (0,100) and (100,200); schema equality, nulls, NaNs."""
import glob, json, os, sys, tempfile
from importlib import resources
sys.path.insert(0, os.path.expanduser("~/vibe-coding/graphed-workdir/lanes/htcondor/refs/hgg"))
import inclusive_processor as tpl
import numpy as np, pyarrow as pa, pyarrow.parquet as pq
from coffea.nanoevents import NanoEventsFactory
fx = os.path.expanduser("~/vibe-coding/graphed-workdir/lanes/htcondor/probes/services-code/fixtures/nano_hgg_v15.root")
meta = json.load(resources.files("higgs_dna.metaconditions").joinpath("Era2022_v1.json").open())
tabs = {}
for s, e in [(0, 100), (100, 200)]:
    out = tempfile.mkdtemp()
    proc = tpl.HggInclusiveProcessor(metaconditions=meta, output_location=out, year={"MC": ["2024"]})
    try:
        ev = NanoEventsFactory.from_root({fx: "Events"}, entry_start=s, entry_stop=e, metadata={"dataset": "MC", "filename": "f.root"}).events()
        c = proc.process(ev)
    except Exception as x:
        print("RANGE", (s, e), "RAISED", type(x).__name__, str(x)[:200]); continue
    parts = glob.glob(f"{out}/**/*.parquet", recursive=True)
    t = pq.read_table(parts[0]) if parts else None
    tabs[(s, e)] = t
    print("RANGE", (s, e), "COUNTERS", c, "PARTS", [os.path.basename(p) for p in parts], "ROWS", None if t is None else t.num_rows)
a, b = tabs.get((0, 100)), tabs.get((100, 200))
if a is not None and b is not None:
    diff = [(f.name, str(f.type), str(g.type), f.nullable, g.nullable) for f, g in zip(a.schema, b.schema) if f.type != g.type or f.nullable != g.nullable]
    print("SCHEMA_EQUAL_IGNORING_META", a.schema.remove_metadata() == b.schema.remove_metadata(), "names_equal", a.column_names == b.column_names, "NDIFF", len(diff), diff[:8])
    nulls = [n for n in a.column_names if a.column(n).null_count]
    nans = [n for n in a.column_names if pa.types.is_floating(a.schema.field(n).type) and np.isnan(a.column(n).to_numpy(zero_copy_only=False)).any()]
    types = sorted({str(f.type) for f in a.schema})
    print("NONEMPTY_PART nulls_in", len(nulls), nulls[:5], "nans_in", len(nans), nans[:5], "types", types)
