"""m69a premise probe: the ORIGINAL inclusive_processor.py (imported as a module) on one entry range, default and eager NanoEvents modes."""
import glob, hashlib, inspect, json, os, sys, time
from importlib import metadata, resources

import pyarrow.parquet as pq

PIN = "791229c2a091e7f0708f885c5fe245a702567ead37c9ab6d850d7d41ce52d1dd"
src = open("inclusive_processor.py", "rb").read()
print("SHA256", hashlib.sha256(src).hexdigest(), "PINNED_MATCH", hashlib.sha256(src).hexdigest() == PIN)
sys.path.insert(0, os.getcwd())
import inclusive_processor as tpl  # noqa: E402
from coffea.nanoevents import NanoEventsFactory  # noqa: E402

url, dataset, start, stop, out = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
for d in ("coffea", "awkward", "uproot", "higgs-dna", "correctionlib", "vector", "numba", "pyarrow", "fsspec-xrootd", "xrootd"):
    try:
        print("VERSION", d, metadata.version(d))
    except metadata.PackageNotFoundError:
        print("VERSION", d, "MISSING")
print("INFER_NANO_VERSION_FROM", inspect.getsourcefile(tpl.infer_nano_version))
print("FROM_ROOT_DEFAULT_MODE", inspect.signature(NanoEventsFactory.from_root).parameters["mode"].default)
for rel in ("metaconditions/Era2022_v1.json",
            "metaconditions/" + tpl.HggInclusiveProcessor.GOLDEN_JSON["2024"],
            "systematics/JSONs/POG/JME/2024_Summer24/jetid.json.gz"):
    p = resources.files("higgs_dna").joinpath(rel)
    print("DATAFILE", rel, "is_file", p.is_file(), hashlib.sha256(p.read_bytes()).hexdigest()[:16] if p.is_file() else "")

with resources.files("higgs_dna.metaconditions").joinpath("Era2022_v1.json").open("r") as f:
    meta = json.load(f)

tables = {}
for mode in (None, "eager"):
    o = f"{out}/{mode or 'default'}"
    proc = tpl.HggInclusiveProcessor(metaconditions=meta, output_location=o, year={dataset: ["2024"]})
    kw = {} if mode is None else {"mode": mode}
    t0 = time.time()
    ev = NanoEventsFactory.from_root({url: "Events"}, entry_start=start, entry_stop=stop,
                                     metadata={"dataset": dataset, "filename": url.split("/")[-1]}, **kw).events()
    counters = proc.process(ev)
    print(f"MODE {mode or 'default'} COUNTERS", counters, f"nano_version {proc.nano_version} data_kind {proc.data_kind} ({time.time() - t0:.1f}s)")
    parts = sorted(glob.glob(f"{o}/**/*.parquet", recursive=True))
    print(f"MODE {mode or 'default'} PARTS", [p[len(o):] for p in parts])
    for p in parts:
        t = pq.read_table(p)
        md = {k.decode(): v.decode()[:80] for k, v in (t.schema.metadata or {}).items()}
        print(f"MODE {mode or 'default'} ROWS", t.num_rows, "COLS", t.num_columns, "META", md)
        print(f"MODE {mode or 'default'} FIRST_COLS", t.column_names[:8], "LAST_COLS", t.column_names[-4:])
        tables[mode] = t
if len(tables) == 2:
    a, b = tables[None], tables["eager"]
    print("DEFAULT_VS_EAGER equals(check_metadata=True)", a.equals(b, check_metadata=True))
