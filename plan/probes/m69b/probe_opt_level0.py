"""m69b-r3: `aggregate_plan` compiled at opt_level=0 (graphed d0ad16b's `compile_ir(optimize=False)`, the 1:1
lowering M6 names opt_level=0), stood in by patching the one `compile_ir` call inside `aggregate_plan`.

A: two fills the optimizer merges (weight=[w], weight=[w * 1.0]) plus a counter: compiled outputs at opt_level 1 and 0.
B: the opt_level=0 plan, fills read at their compiled positions: equal to a direct boost fill done twice.
C: gh.plan (0.0.4) under opt_level=0 plans and runs (no merge, so no refusal).
D: determinism: sha256 of the compiled IR and of the pickled plan, per opt_level, in this interpreter; run it
   twice with different PYTHONHASHSEED and compare the D lines.

Run: for s in 1 2; do PYTHONHASHSEED=$s ~/vibe-coding/cloud/graphed-histogram/.venv/bin/python -B probe_opt_level0.py; done > probe_opt_level0.txt
"""
from __future__ import annotations

import functools
import hashlib
import os
import tempfile

import awkward as ak
import boost_histogram as bh
import numpy as np
import graphed.aggregate as agg
from graphed import Session, aggregate_plan
from graphed.awkward import AwkwardBackend, from_parquet
from graphed.core import GraphStore
from graphed.core.execution import SequentialRunner

import graphed_histogram as gh

REAL = agg.compile_ir
X = np.array([1.0, 2.0, 3.0, 4.0])
W = np.array([0.5, 1.0, 1.5, 2.0])
d = os.path.join(tempfile.gettempdir(), "m69b_opt_level0")  # a fixed path: the IR names its source
os.makedirs(d, exist_ok=True)
path = os.path.join(d, "e.parquet")
ak.to_parquet(ak.Array({"x": X, "w": W}), path)
expected = bh.Histogram(bh.axis.Regular(4, 0, 5), storage=bh.storage.Weight())
expected.fill(X, weight=W)
expected.fill(X, weight=W)


def build():
    s = Session(AwkwardBackend())
    ev = from_parquet(s, "events", path)
    h = gh.boost.Histogram(bh.axis.Regular(4, 0, 5), storage=bh.storage.Weight())
    h.fill(ev.x, weight=[ev.w])
    h.fill(ev.x, weight=[ev.w * 1.0])
    return ev, h


def composed(opt_level: int):
    agg.compile_ir = functools.partial(REAL, optimize=opt_level >= 1)
    try:
        ev, h = build()
        fills, counter = h.fill_nodes(), ev.x * 0 + 1
        held: dict[str, list[int]] = {}

        def hook(compiled):
            order = {cid: i for i, cid in enumerate(GraphStore.deserialize(bytes(compiled.ir)).outputs())}
            held["n"] = [len(order)]
            held["fills"] = [order[compiled.correspondence.node_map[f.node_id][0]] for f in fills]

        def reduce(values):
            return sum((values[p] for p in held["fills"][1:]), values[held["fills"][0]].copy())

        plan = aggregate_plan(counter, *fills, reduce=reduce, combine=lambda a, b: a + b,
                              empty=lambda: expected * 0, externals=h.evaluators(), on_compiled=hook)
        return plan, held
    finally:
        agg.compile_ir = REAL


for level in (1, 0):
    plan, held = composed(level)
    got = SequentialRunner().run(plan).value
    print(f"A/B opt_level={level}: {held['n'][0]} compiled outputs for 3 marked, fill positions {held['fills']}, "
          f"equal to two direct fills: {np.array_equal(got.view(flow=True), expected.view(flow=True))}")

for level in (1, 0):
    agg.compile_ir = functools.partial(REAL, optimize=level >= 1)
    try:
        _ev, h = build()
        try:
            got = SequentialRunner().run(gh.plan({"h": h})).value
            print(f"C gh.plan at opt_level={level}: equal to two direct fills: "
                  f"{np.array_equal(gh.unpack(got)['h'].view(flow=True), expected.view(flow=True))}")
        except Exception as e:  # noqa: BLE001
            print(f"C gh.plan at opt_level={level}: {type(e).__name__}: {str(e)[:60]}")
    finally:
        agg.compile_ir = REAL

for level in (1, 0):
    irs = [hashlib.sha256(bytes(composed(level)[0].process.ir)).hexdigest()[:16] for _ in range(2)]
    print(f"D opt_level={level}: ir sha256 {irs[0]} (a second build in this interpreter equal: {irs[0] == irs[1]})")
