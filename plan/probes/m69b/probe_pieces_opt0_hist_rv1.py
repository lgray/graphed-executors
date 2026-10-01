"""A composing plan passing aggregate_plan(opt_level=0) through gh.boost.pieces (§5.0: "a composing plan
passes it to aggregate_plan"): merged fills (w, w*1.0) read once per marked fill at both levels."""
import os, tempfile
import awkward as ak, boost_histogram as bh, numpy as np
import graphed_histogram as gh
from graphed import Session, aggregate_plan
from graphed.awkward import AwkwardBackend, from_parquet
from graphed.core.execution import SequentialRunner

d = tempfile.mkdtemp(); path = os.path.join(d, "e.parquet")
x = np.linspace(0.05, 3.95, 400); ak.to_parquet(ak.Array({"x": x}), path)
for level in (1, 0):
    s = Session(AwkwardBackend()); ev = from_parquet(s, "events", path, steps_per_file=3)
    h = gh.boost.Histogram(bh.axis.Regular(4, 0.0, 4.0), storage=bh.storage.Weight())
    h.fill(ev.x, weight=[ev.x * 0.5]); h.fill(ev.x, weight=[ev.x * 0.5 * 1.0])
    p = gh.boost.pieces({"h": h})
    plan = p.serve(aggregate_plan(*p.fill_nodes, reduce=p.reduce, combine=p.combine, empty=p.empty,
                                  externals=p.externals, on_compiled=p.on_compiled, steps_per_file=3, opt_level=level))
    got = gh.unpack(SequentialRunner().run(plan).value)["h"]
    want = bh.Histogram(bh.axis.Regular(4, 0.0, 4.0), storage=bh.storage.Weight()); want.fill(x, weight=x); 
    print(f"opt_level={level}: positions={sorted(set(p.reduce.positions.values()))} values equal 2x-fill: {np.allclose(got.values(), want.values(), rtol=1e-12)}")
