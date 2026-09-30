"""m69b-r2: §5.1 "`pieces.on_compiled` records on `pieces.reduce` each marked fill's compiled position".

A: one recording reduce/hook pair (what one `pieces` object holds) handed to two `aggregate_plan` calls that mark
   the counter first and then last; the first plan, run after the second is built, reads at the second's positions.
B: `_variation_labels` (the payload 0.0.4's hook returns and `pieces.on_compiled` must keep returning) on a varied
   histogram whose fills the optimizer merged, i.e. on the path `pieces` now accepts.

Run: ~/vibe-coding/cloud/graphed-histogram/.venv/bin/python probe_positions_reuse_rv2.py > probe_positions_reuse_rv2.txt
"""
from __future__ import annotations

import os
import tempfile

import awkward as ak
import boost_histogram as bh
import numpy as np
from graphed import Session, aggregate_plan, vary
from graphed.awkward import AwkwardBackend, from_parquet
from graphed.core import GraphStore
from graphed.core.execution import SequentialRunner

import graphed_histogram as gh
from graphed_histogram.boost import _variation_labels

X = np.array([1.0, 2.0, 3.0, 4.0])
W = np.array([0.5, 1.0, 1.5, 2.0])
d = tempfile.mkdtemp()
path = os.path.join(d, "e.parquet")
ak.to_parquet(ak.Array({"x": X, "w": W}), path)

s = Session(AwkwardBackend())
ev = from_parquet(s, "events", path)
h = gh.boost.Histogram(bh.axis.Regular(4, 0, 5), storage=bh.storage.Weight())
h.fill(ev.x, weight=[ev.w])
h.fill(ev.x, weight=[ev.w * 1.0])
fills = h.fill_nodes()
counter = ev.x * 0 + 1


class Recording:
    """The plan's pieces.reduce: positions recorded by the hook, read by the reduce."""

    fills: list[int] | None = None
    counter: int | None = None

    def hook(self, compiled):
        order = {cid: i for i, cid in enumerate(GraphStore.deserialize(bytes(compiled.ir)).outputs())}
        pos = lambda a: order[compiled.correspondence.node_map[a.node_id][0]]  # noqa: E731
        self.fills, self.counter = [pos(f) for f in fills], pos(counter)

    def __call__(self, values):
        hist = sum((values[p] for p in self.fills[1:]), values[self.fills[0]].copy())
        return {"h": hist, "n": int(ak.sum(values[self.counter]))}


def combine(a, b):
    return {"h": a["h"] + b["h"], "n": a["n"] + b["n"]} if a and b else (a or b)


rec = Recording()
first = aggregate_plan(counter, *fills, reduce=rec, combine=combine, empty=dict, externals=h.evaluators(),
                       on_compiled=rec.hook)
at_first = (list(rec.fills), rec.counter)
aggregate_plan(*fills, counter, reduce=rec, combine=combine, empty=dict, externals=h.evaluators(), on_compiled=rec.hook)
print(f"A positions after building the counter-first plan: fills {at_first[0]} counter {at_first[1]}; "
      f"after building a counter-last plan with the same pieces: fills {rec.fills} counter {rec.counter}")
try:
    v = SequentialRunner().run(first).value
    print(f"A the counter-first plan run afterwards: n={v['n']} h={type(v['h']).__name__}")
except Exception as e:  # noqa: BLE001
    print(f"A the counter-first plan run afterwards: {type(e).__name__}: {str(e)[:100]}")

s2 = Session(AwkwardBackend())
ev2 = from_parquet(s2, "events", path)
hv = gh.boost.Histogram(bh.axis.Regular(4, 0, 5), storage=bh.storage.Weight())
w = vary(ev2.w, "sf", up=ev2.w * 1.0, down=ev2.w * 0.5)
hv.fill(ev2.x, weight=[w])
from graphed import compile_ir  # noqa: E402

c = compile_ir(s2, *hv.fill_nodes())
n_out = len(GraphStore.deserialize(bytes(c.ir)).outputs())
try:
    labels = _variation_labels((("hv", hv),), c)
    print(f"B varied fills: {len(hv.fill_nodes())} marked, {n_out} compiled; _variation_labels returned "
          f"{type(labels).__name__} of {len(labels or ())} keys")
except Exception as e:  # noqa: BLE001
    print(f"B varied fills: {len(hv.fill_nodes())} marked, {n_out} compiled; _variation_labels raised {type(e).__name__}: {e}")
