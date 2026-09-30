"""m69b-r2: can two fills the optimizer merges (weight=[w] vs weight=[w * 1.0]) stay separate leaves in a plan
composed with another output, on graphed d0ad16b without a graphed change?

A: the merge happens in compile_ir whatever else is marked and in whatever order (no per-output opt-out;
   aggregate_plan does not expose optimize=).
B: reading each marked fill at its compiled position (compiled.correspondence.node_map into the IR outputs'
   order, recorded by the on_compiled hook) gives the histogram of both fills, with the counter listed first or
   last, equal to a direct boost fill done twice.
C: control: gh.plan of the same fills still refuses (frozen m48/m49 behaviour).

Run: ~/vibe-coding/cloud/graphed-histogram/.venv/bin/python probe_merged_leaves.py > probe_merged_leaves.txt
"""
from __future__ import annotations

import os
import tempfile

import awkward as ak
import boost_histogram as bh
import numpy as np
from graphed import Session, aggregate_plan, compile_ir
from graphed.awkward import AwkwardBackend, from_parquet
from graphed.core import GraphStore
from graphed.core.execution import SequentialRunner

import graphed_histogram as gh

X = np.array([1.0, 2.0, 3.0, 4.0])
W = np.array([0.5, 1.0, 1.5, 2.0])
d = tempfile.mkdtemp()
path = os.path.join(d, "e.parquet")
ak.to_parquet(ak.Array({"x": X, "w": W}), path)


def build():
    s = Session(AwkwardBackend())
    ev = from_parquet(s, "events", path)
    h = gh.boost.Histogram(bh.axis.Regular(4, 0, 5), storage=bh.storage.Weight())
    h.fill(ev.x, weight=[ev.w])
    h.fill(ev.x, weight=[ev.w * 1.0])
    return s, ev, h


s, ev, h = build()
fills = h.fill_nodes()
counter = ev.x * 0 + 1
for label, marked in (("fills only", fills), ("counter first", [counter, *fills]), ("counter last", [*fills, counter])):
    c = compile_ir(s, *marked)
    print(f"A {label}: {len({f.node_id for f in fills})} distinct fill nodes marked, "
          f"{len(GraphStore.deserialize(bytes(c.ir)).outputs())} compiled outputs for {len(marked)} marked")

expected = bh.Histogram(bh.axis.Regular(4, 0, 5), storage=bh.storage.Weight())
expected.fill(X, weight=W)
expected.fill(X, weight=W)

for counter_first in (True, False):
    s, ev, h = build()
    fills = h.fill_nodes()
    counter = ev.x * 0 + 1
    held: dict[str, list[int]] = {}

    def hook(compiled, fills=fills, held=held, counter=counter):
        order = {cid: i for i, cid in enumerate(GraphStore.deserialize(bytes(compiled.ir)).outputs())}
        pos = lambda a: order[compiled.correspondence.node_map[a.node_id][0]]  # noqa: E731
        held["fills"] = [pos(f) for f in fills]
        held["counter"] = [pos(counter)]
        return None

    def reduce(values, held=held):
        hist = sum((values[p] for p in held["fills"][1:]), values[held["fills"][0]].copy())
        return {"h": hist, "n": int(ak.sum(values[held["counter"][0]]))}

    def combine(a, b):
        return {"h": a["h"] + b["h"], "n": a["n"] + b["n"]} if a and b else (a or b)

    marked = [counter, *fills] if counter_first else [*fills, counter]
    plan = aggregate_plan(*marked, reduce=reduce, combine=combine, empty=dict, externals=h.evaluators(),
                          on_compiled=hook)
    value = SequentialRunner().run(plan).value
    got = value["h"]
    print(f"B counter {'first' if counter_first else 'last'}: fill positions {held['fills']} counter {held['counter']}; "
          f"n={value['n']}; values equal={np.array_equal(got.values(flow=True), expected.view(flow=True).value)} "
          f"variances equal={np.array_equal(got.variances(flow=True), expected.view(flow=True).variance)}")

s, ev, h = build()
try:
    gh.plan({"h": h})
    print("C gh.plan: accepted")
except Exception as e:  # noqa: BLE001
    print(f"C gh.plan: {type(e).__name__}: {str(e)[:80]}")
