"""m69b-r5-A reviewer: the r4-repair's new frozen clauses, driven.

  badnodeid  what Python sees when a GraphStore binding refuses an out-of-range id (serialize(outputs=), the precedent
             §5.0 names for GraphStore.cone), and whether any `BadNodeId` name is importable
  replay     the frozen row's fixture (marked `w`, `w * 1.0`; unmarked: a node over column `z`, a node raising on the
             data) as a `store=` plan: opt 0 with d0ad16b's replay, opt 0 with replay's check at the plan's level, and
             opt 1; then the same with the outputs `(w, w)` (one record id passed twice) at 0 (check fixed) and 1;
             then the cut: `Replay.value` feeds `reduce` one value per IR output of the plan-level compile, mapped
             through its `correspondence.node_map` as `aggregate_plan`'s `slot` does

The cone is emulated as in probe_opt0_replay_rv4.py (patched into `aggregate_plan`'s / `replay`'s `compile_ir`).
Run: ~/vibe-coding/cloud/graphed-histogram/.venv/bin/python -B probe_opt0_rv5a.py > probe_opt0_rv5a.txt
"""
from __future__ import annotations

import dataclasses
import os
import shutil
import tempfile

import awkward as ak
import numpy as np

import graphed
import graphed.aggregate as agg
import graphed.core
import graphed.core.graphed_core as ext
import graphed.debug.replaying as rp
from graphed import Session, aggregate_plan
from graphed.awkward import AwkwardBackend, from_parquet
from graphed.core import GraphStore
from graphed.core.execution import SequentialRunner
from graphed.debug import replay
from graphed.execute import Correspondence, _frames_by_key

REAL = agg.compile_ir


def cone(session, *outputs, **kw):
    if kw.get("optimize") is False:
        return REAL(session, *outputs, **kw)
    whole = REAL(session, *outputs, optimize=False)
    nodes = GraphStore.deserialize(bytes(whole.ir)).nodes()
    ids = [a.node_id for a in outputs]
    keep, stack = set(), list(ids)
    while stack:
        i = stack.pop()
        if i not in keep:
            keep.add(i)
            stack.extend(nodes[i]["inputs"])
    store, remap = GraphStore(), {}
    for n in nodes:
        if n["id"] in keep:
            ins = [remap[j] for j in n["inputs"]]
            add = {"source": lambda: store.add_source(n["name"], n["params"]),
                   "op": lambda: store.add_op(n["name"], ins, n["params"]),
                   "reduction": lambda: store.add_reduction(n["name"], ins, n["params"])}[n["kind"]]
            remap[n["id"]] = add()
    node_map = {i: (remap[i], None) for i in sorted(keep)}
    return dataclasses.replace(
        whole,
        ir=bytes(store.serialize(outputs=[remap[i] for i in ids])),
        correspondence=Correspondence(node_map=node_map, frames=_frames_by_key(session, node_map)),
    )


print("badnodeid:")
try:
    GraphStore().serialize(outputs=[5])
    print("  serialize(outputs=[5]) on an empty store: no error")
except BaseException as e:  # noqa: BLE001
    print(f"  serialize(outputs=[5]) on an empty store: {type(e).__module__}.{type(e).__name__}: {e}")
names = sorted({n for m in (graphed, graphed.core, ext) for n in dir(m) if "Bad" in n})
print(f"  names containing 'Bad' in graphed, graphed.core, graphed.core.graphed_core: {names}")
print(f"  control, names containing 'Graph' in graphed.core.graphed_core: {sorted(n for n in dir(ext) if 'Graph' in n)}")

d = tempfile.mkdtemp(prefix="m69b_rv5a_")
try:
    path = os.path.join(d, "e.parquet")
    ak.to_parquet(ak.Array({"x": np.array([1.0, 2.0, 3.0]), "w": np.array([0.5, 1.0, 1.5]),
                            "z": np.array([7.0, 8.0, 9.0])}), path)

    def build(level, store, dup=False):
        s = Session(AwkwardBackend())
        ev = from_parquet(s, "events", path)
        _unmarked = (ev.z * 3.0, ev.x[ev.x > 100][0])
        outs = (ev.w, ev.w) if dup else (ev.w, ev.w * 1.0)
        agg.compile_ir = cone if level == 0 else REAL
        try:
            plan = aggregate_plan(*outs, reduce=lambda v: (len(v), sum(float(ak.sum(a)) for a in v)),
                                  combine=lambda a, b: (max(a[0], b[0]), a[1] + b[1]), empty=lambda: (0, 0.0), store=store)
        finally:
            agg.compile_ir = REAL
        return plan, outs

    print("replay (fixture: marked w, w * 1.0; unmarked z * 3.0 and x[x > 100][0]; store=):")
    for level, fix, dup in ((0, False, False), (0, True, False), (1, False, False), (0, True, True), (1, False, True)):
        plan, outs = build(level, os.path.join(d, f"cap{level}{fix}{dup}"), dup)
        run = SequentialRunner().run(plan).value
        rp.compile_ir = cone if fix else REAL
        try:
            diff = replay(plan, 0, *outs).diff()
            res = f"diff.equal={diff.equal} ({diff.reference}); recorded {diff.recorded}; replayed {diff.replayed}"
        except Exception as e:  # noqa: BLE001
            res = f"{type(e).__name__}: {e}"
        finally:
            rp.compile_ir = REAL
        tag = f"opt {level}" + (", replay checks at the plan's level" if fix else "") + (", outputs (w, w)" if dup else "")
        n_ir = len(GraphStore.deserialize(bytes(plan.process.ir)).outputs())
        print(f"  {tag}: IR outputs {n_ir}; run (reduce arity, total) {run}; {res}")

    ORIG_VALUE = rp.Replay.__dict__["value"]

    def per_ir_output(level):
        def value(self):
            compiled = (cone if level == 0 else REAL)(self._session, *[graphed.Array(self._session, i) for i in self._output_ids])
            out = {s.node.node_id: s.value for s in self.steps() if s.node.node_id in self._output_ids}
            landed = {compiled.correspondence.node_map[i][0]: out[i] for i in self._output_ids}
            return self._process.reduce([landed[c] for c in GraphStore.deserialize(self._process.ir).outputs()])
        prop = rp.cached_property(value)
        prop.__set_name__(rp.Replay, "value")
        return prop

    print("the cut (Replay.value per IR output of the plan-level compile):")
    for level, dup in ((0, True), (1, True), (1, False), (0, False)):
        plan, outs = build(level, os.path.join(d, f"cut{level}{dup}"), dup)
        SequentialRunner().run(plan)
        rp.compile_ir = cone if level == 0 else REAL
        rp.Replay.value = per_ir_output(level)
        try:
            diff = replay(plan, 0, *outs).diff()
            res = f"diff.equal={diff.equal} ({diff.reference}); recorded {diff.recorded}; replayed {diff.replayed}"
        except Exception as e:  # noqa: BLE001
            res = f"{type(e).__name__}: {e}"
        finally:
            rp.compile_ir = REAL
            rp.Replay.value = ORIG_VALUE
        print(f"  opt {level}, outputs {'(w, w)' if dup else '(w, w * 1.0)'}: {res}")
finally:
    shutil.rmtree(d)
