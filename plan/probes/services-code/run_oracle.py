"""Run the eager HiggsDNA-distilled template on the derived fixture: the m69a oracle."""
import json, os, sys, glob, time
from importlib import resources
sys.path.insert(0, os.path.expanduser("~/vibe-coding/graphed-workdir/lanes/htcondor/refs/hgg"))
import inclusive_processor as tpl
from coffea.nanoevents import NanoEventsFactory
import pyarrow.parquet as pq
out_dir = sys.argv[2]
with resources.files("higgs_dna.metaconditions").joinpath("Era2022_v1.json").open("r") as f:
    meta = json.load(f)
proc = tpl.HggInclusiveProcessor(metaconditions=meta, output_location=out_dir, year={"MC": ["2024"]})
ev = NanoEventsFactory.from_root({sys.argv[1]: "Events"}, metadata={"dataset": "MC", "filename": os.path.basename(sys.argv[1])}, entry_stop=None).events()
t0 = time.time(); out = proc.process(ev); dt = time.time() - t0
print("COUNTERS", out, f"({dt:.1f}s)")
parts = sorted(glob.glob(f"{out_dir}/**/*.parquet", recursive=True))
print("PARTS", [p.replace(out_dir, "") for p in parts])
for p in parts:
    t = pq.read_table(p); md = {k.decode(): v.decode() for k, v in (t.schema.metadata or {}).items()}
    print("ROWS", t.num_rows, "COLS", t.num_columns, "first cols", t.column_names[:6], "META", md)
    import numpy as np
    m = t.column("mass").to_numpy() if "mass" in t.column_names else None
    print("mass[:5]", None if m is None else np.round(m[:5], 2).tolist(), "| n_jets[:5]", t.column("n_jets").to_numpy()[:5].tolist() if "n_jets" in t.column_names else None)
