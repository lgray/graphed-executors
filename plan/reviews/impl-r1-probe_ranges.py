import sys, importlib, tempfile, numpy as np, awkward as ak
from pathlib import Path
F = Path.home()/"vibe-coding/lanes/hgg/graphed-executors/tests/frozen/m69a"
sys.path.insert(0, str(F)); sys.path.insert(0, str(F/"data"))
import hgg_harness as h
import pyarrow.parquet as pq
from graphed.core import SequentialRunner
from graphed_executors.submit import SubmitRunner, ThreadBackend
import make_hgg_fixture as mk
h.place_higgs_dna_data()
an = importlib.import_module("analysis")
tmp = Path(tempfile.mkdtemp(dir=sys.argv[1]))
# varied-weight MC variant: lognormal magnitudes, random signs
out, names = mk.read_collections(str(h.MC_FIXTURE))
rng = np.random.default_rng(7)
n = len(out["genWeight"])
out["genWeight"] = ak.values_astype((rng.lognormal(0, 2, n) * rng.choice([-1, 1], n)), np.float32)
vw = tmp/"nano_hgg_v15_varw.root"; mk.write(str(vw), out)
cases = [
  ("mc", h.MC_FIXTURE, "MC", [(0, 37), (37, 59), (59, 200)]),
  ("data", h.DATA_FIXTURE, "DataC_2024", [(0, 17), (17, 45), (45, 200)]),
  ("mc-varw", vw, "MC", [(0, 13), (13, 60), (60, 200)]),
]
for kind, uri, ds, ranges in cases:
    orc = h.oracle_parts(str(uri), ds, h.YEAR, ranges, tmp/("o-"+kind))
    for rname, runner in [("seq", SequentialRunner()), ("thr", SubmitRunner(ThreadBackend(3)))]:
        o = tmp/f"g-{kind}-{rname}"
        val = runner.run(an.plan(str(uri), ranges=ranges, dataset=ds, year=h.YEAR, out=str(o))).value
        for (s, e) in ranges:
            name = f"{Path(uri).stem}_Events_{s}-{e}.parquet"
            (p,) = o.rglob(name)
            t = pq.read_table(p)
            print(kind, rname, (s, e), "rows", t.num_rows, "diffs", h.compare_part(orc[(s, e)], (val[name], t)),
                  orc[(s,e)][0], t.schema.metadata.get(b"sum_genw_presel"))
        print(kind, rname, "totals-eq", an.totals(val) == __import__("coffea.processor",fromlist=["x"]).accumulate([c for c,_ in orc.values()]))
        if hasattr(runner, "close"): runner.close()
