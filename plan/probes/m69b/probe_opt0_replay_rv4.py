"""m69b-r4 reviewer: consumers of an opt-0 cone plan's shipped IR beyond the run itself.

The cone is emulated as in probe_opt0_cone_store.py (patched into `aggregate_plan`'s one `compile_ir` call).
  replay   `graphed.debug.replay` of a `store=` plan: opt 1 (control), opt 0 as §5.0 leaves replay, opt 0 with replay's
           recompile check made at the plan's level
  frame    a marked op failing on the data, after 20 unmarked nodes (so shipped ids != record ids): the StageError frame
  partial  an unmarked consumed reduction (`x - sum(x)`): whole store vs cone at build
  writes   a `PartWrite` with a metadata reduction, 20 unmarked nodes: the part at opt 1 vs opt 0

Run: ~/vibe-coding/cloud/graphed-histogram/.venv/bin/python -B probe_opt0_replay_rv4.py > probe_opt0_replay_rv4.txt
"""
from __future__ import annotations

import dataclasses
import os
import tempfile

import awkward as ak
import numpy as np
import graphed.aggregate as agg
import graphed.debug.replaying as rp
from graphed.awkward import functions as gak
from graphed import Session, aggregate_plan
from graphed.awkward import AwkwardBackend, from_parquet
from graphed.core import GraphStore
from graphed.core.execution import SequentialRunner
from graphed.debug import replay
from graphed.execute import Correspondence, _frames_by_key

REAL = agg.compile_ir
d = tempfile.mkdtemp(prefix="m69b_rv4_")
path = os.path.join(d, "e.parquet")
ak.to_parquet(ak.Array({"x": np.array([1.0, 2.0, 3.0]), "w": np.array([0.5, 1.0, 1.5])}), path)


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


def build(level, fn, *, store=None, noise=0, bad=False):
    s = Session(AwkwardBackend())
    ev = from_parquet(s, "events", path)
    _unmarked = [ev.w + float(i) for i in range(noise)]
    out = ev.x[ev.x > 100][0] if bad else ev.x * 2.0  # LINE-OF-OUT
    agg.compile_ir = cone if level == 0 else REAL
    try:
        plan = fn(out, store)
    finally:
        agg.compile_ir = REAL
    return plan, out


def mk(out, store):
    return aggregate_plan(out, reduce=lambda v: float(ak.sum(v[0])), combine=lambda a, b: a + b, empty=float,
                          store=store)


line = next(i for i, t in enumerate(open(__file__), 1) if "# LINE-OF-OUT" in t and "ev.x" in t)

print("replay:")
for level, fix in ((1, False), (0, False), (0, True)):
    plan, out = build(level, mk, store=os.path.join(d, f"cap{level}{fix}"), noise=5)
    SequentialRunner().run(plan)
    rp.compile_ir = (lambda s, *o, **kw: cone(s, *o, **kw)) if fix else REAL
    try:
        diff = replay(plan, 0, out).diff()
        res = f"diff.equal={diff.equal} ({diff.reference}); replayed {diff.replayed}"
    except Exception as e:  # noqa: BLE001
        res = f"{type(e).__name__}: {e}"
    finally:
        rp.compile_ir = REAL
    tag = f"opt {level}" + (", replay checks at the plan's level" if fix else "")
    print(f"  {tag}: {res}")

print(f"frame (the failing op is recorded at line {line}):")
for level in (1, 0):
    plan, out = build(level, mk, noise=20, bad=True)
    shipped = len(GraphStore.deserialize(bytes(plan.process.ir)).nodes())
    try:
        SequentialRunner().run(plan)
        res = "no error"
    except Exception as e:  # noqa: BLE001
        err = e if hasattr(e, "user_frame") else getattr(e, "__cause__", e)
        f = getattr(err, "user_frame", None)
        res = f"{type(err).__name__} at line {getattr(f, 'lineno', None)} op={getattr(err, 'op', None)!r}"
    print(f"  opt {level}: out record id {out.node_id}, shipped nodes {shipped}; {res}")

print("partial (unmarked `x - sum(x)`):")
for label, fn in (("whole store", lambda s, *o, **kw: REAL(s, *o, optimize=False)), ("cone", cone)):
    s = Session(AwkwardBackend())
    ev = from_parquet(s, "events", path)
    _unmarked = ev.x - gak.sum(ev.x, axis=None)
    out = ev.x * 2.0
    agg.compile_ir = fn
    try:
        plan = mk(out, None)
        res = f"builds; value {SequentialRunner().run(plan).value}"
    except Exception as e:  # noqa: BLE001
        res = f"{type(e).__name__}: {str(e)[:90]}"
    finally:
        agg.compile_ir = REAL
    print(f"  {label}: {res}")

print("writes (a metadata reduction; 20 unmarked nodes):")
from graphed.write import PartWrite  # noqa: E402

parts = {}
for level in (1, 0):
    s = Session(AwkwardBackend())
    ev = from_parquet(s, "events", path)
    _unmarked = [ev.x + float(i) for i in range(20)]
    dest = os.path.join(d, f"w{level}")

    def codec(v, p, kv):
        with open(p, "w") as fh:
            fh.write(f"{ak.to_list(v)} {sorted(kv.items())}")

    pw = PartWrite(array=ev.w + 1.0, destination=dest, name=lambda p: "part0.txt", codec=codec,
                   metadata={"sumw": gak.sum(ev.w, axis=None), "tag": "t"})
    agg.compile_ir = cone if level == 0 else REAL
    try:
        plan = aggregate_plan(ev.x * 2.0, reduce=lambda v: (float(ak.sum(v[0])), v[1:]), combine=lambda a, b: b if a is None else a,
                              empty=lambda: None, writes=[pw])
    finally:
        agg.compile_ir = REAL
    val = SequentialRunner().run(plan).value
    parts[level] = open(os.path.join(dest, "part0.txt")).read()
    shipped = len(GraphStore.deserialize(bytes(plan.process.ir)).nodes())
    print(f"  opt {level}: shipped nodes {shipped}; value {val[0]}; part {parts[level]}")
print(f"  parts equal: {parts[0] == parts[1]}")
