"""m69b-r2: does frozen m69a `test_each_dataset_run_on_its_own_collects_into_the_same_product` hold unchanged once
each dataset's value also carries local diagnostic histograms?

The test compares `collate` + `SequentialRunner` against per-dataset plans on `SubmitRunner(ThreadBackend(2))`
with `==`, two partitions per dataset (RANGES), combine = coffea's `processor.accumulate([a, b])`, empty = dict.
Here: two parquet "datasets", two partitions each, value = counters + {"diagnostics": {name: bh.Histogram}} filled
with Weight storage and lognormal x random-sign float32 weights (the m69a carried constraint's fixture shape).
The control flips one bin of one side and must print False.

Run: ~/vibe-coding/cloud/graphed-histogram/.venv/bin/python probe_m69a_each_rv2.py > probe_m69a_each_rv2.txt
"""
from __future__ import annotations

import importlib.util
import os
import tempfile

import awkward as ak
import boost_histogram as bh
import numpy as np
from graphed import Session, aggregate_plan, collate
from graphed.awkward import AwkwardBackend, from_parquet
from graphed.core import GraphStore
from graphed.core.execution import SequentialRunner
from graphed_executors.submit import SubmitRunner, ThreadBackend

import graphed_histogram as gh

spec = importlib.util.spec_from_file_location(
    "coffea_accumulator",
    os.path.expanduser("~/vibe-coding/cloud/docs-executors/.venv/lib/python3.12/site-packages/coffea/processor/accumulator.py"),
)
acc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acc)


def accumulate(a, b):
    return acc.accumulate([a, b])


d = tempfile.mkdtemp()
rng = np.random.default_rng(7)
paths = {}
for ds in ("MC", "Data"):
    n = 200
    w = (rng.lognormal(0, 1, n) * rng.choice([-1.0, 1.0], n)).astype(np.float32)
    paths[ds] = os.path.join(d, f"{ds}.parquet")
    ak.to_parquet(ak.Array({"m": rng.uniform(100, 180, n), "pt": rng.exponential(60, n), "w": w}), paths[ds],
                  row_group_size=100)


class Reduce:
    def __init__(self, n_counters, fills, counter):
        self.names, self.fills, self.counter, self.pos = n_counters, fills, counter, None

    def hook(self, compiled):
        order = {cid: i for i, cid in enumerate(GraphStore.deserialize(bytes(compiled.ir)).outputs())}
        self.pos = {k: order[compiled.correspondence.node_map[f.node_id][0]] for k, f in self.fills.items()}
        self.cpos = order[compiled.correspondence.node_map[self.counter.node_id][0]]

    def __call__(self, values):
        return {"nTot": int(ak.sum(values[self.cpos])), "diagnostics": {k: values[p].copy() for k, p in self.pos.items()}}

    def __getstate__(self):
        return {"names": self.names, "pos": self.pos, "cpos": self.cpos, "fills": {}, "counter": None}


def dataset_plan(ds):
    s = Session(AwkwardBackend())
    ev = from_parquet(s, "events", paths[ds], steps_per_file=2)
    hm = gh.boost.Histogram(bh.axis.Regular(80, 100, 180), storage=bh.storage.Weight())
    hp = gh.boost.Histogram(bh.axis.Regular(50, 0, 250), storage=bh.storage.Weight())
    hm.fill(ev.m, weight=[ev.w])
    hp.fill(ev.pt, weight=[ev.w])
    counter = ev.m * 0 + 1
    r = Reduce(("nTot",), {"m_gg": hm.fill_nodes()[0], "pt_gg": hp.fill_nodes()[0]}, counter)
    return aggregate_plan(counter, hm.fill_nodes()[0], hp.fill_nodes()[0], reduce=r, combine=accumulate, empty=dict,
                          externals={**hm.evaluators(), **hp.evaluators()}, on_compiled=r.hook, steps_per_file=2)


one = SequentialRunner().run(collate({ds: dataset_plan(ds) for ds in paths})).value
submit = SubmitRunner(ThreadBackend(2))
try:
    collected = {}
    for fut in [submit.submit(collate({ds: dataset_plan(ds)})) for ds in paths]:
        collected |= fut.result().value
finally:
    submit.close()
print(f"tasks per dataset: {len(dataset_plan('MC').tasks)}; leaf types {sorted({type(v).__name__ for v in one['MC']['diagnostics'].values()})}")
print(f"collected == one: {collected == one}")
bad = {ds: {**v, "diagnostics": {k: h.copy() for k, h in v["diagnostics"].items()}} for ds, v in collected.items()}
bad["MC"]["diagnostics"]["m_gg"].view()[3] = (1.0, 1.0)
print(f"control (one bin changed) == one: {bad == one}")
