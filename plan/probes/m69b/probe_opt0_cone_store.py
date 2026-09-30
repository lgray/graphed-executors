"""m69b-r4: an opt_level=0 plan that ships only its outputs' cone, 1:1, renumbered, emulated in Python.

The emulated `_compile_cone(session, *arrays)`: the whole arena (`compile_ir(optimize=False)`, whose frozen m22
whole-store contract stays), reachability from the marked arrays over `inputs` (what Rust
`optimizer::dead_code_elimination` computes), each kept node re-added in ascending record id to a fresh `GraphStore`
with remapped inputs, serialized with the marked ids remapped; `correspondence.node_map` = record id -> (shipped id,
None), frames re-keyed by graphed's `_frames_by_key`. Patched into `aggregate_plan`'s one `compile_ir` call.

Cases (the reviewer's probe_opt0_cone_rv3 sessions, plus merged histogram fills):
  none / cols / raise   `ev.x * 2.0` marked; unmarked: nothing / 50 nodes over `w` / `ev.x[ev.x > 100][0]`
  fills                 two fills gh merges at opt 1 (weight=[w], [w * 1.0]) + a counter, cols-style noise unmarked
Printed per case: shipped node count, the replay-style cone (`lower(opt_level=0)`) size, Rust DCE's
`reachable_nodes` for the same outputs, the whole-store (`compile_ir(optimize=False)`) node count, and the value.
Then the cone IR's sha256 (fixed source path) for a cross-seed comparison.

Run: for s in 1 2; do PYTHONHASHSEED=$s ~/vibe-coding/cloud/graphed-histogram/.venv/bin/python -B probe_opt0_cone_store.py; done > probe_opt0_cone_store.txt
"""
from __future__ import annotations

import dataclasses
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
from graphed.debug.lowering import lower
from graphed.execute import Correspondence, _frames_by_key

import graphed_histogram as gh

REAL = agg.compile_ir
d = os.path.join(tempfile.gettempdir(), "m69b_opt0_cone")  # a fixed path: the IR names its source
os.makedirs(d, exist_ok=True)
path = os.path.join(d, "e.parquet")
X, W = np.array([1.0, 2.0, 3.0]), np.array([0.5, 1.0, 1.5])
ak.to_parquet(ak.Array({"x": X, "w": W}), path)
SEEN: dict[str, int] = {}


def compile_cone(session, *outputs, **_kw):
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
        i = n["id"]
        if i not in keep:
            continue
        ins = [remap[j] for j in n["inputs"]]
        kind = n["kind"]
        if kind == "source":
            remap[i] = store.add_source(n["name"], n["params"])
        elif kind == "op":
            remap[i] = store.add_op(n["name"], ins, n["params"])
        elif kind == "reduction":
            remap[i] = store.add_reduction(n["name"], ins, n["params"])
        elif kind == "external":
            remap[i] = store.add_external(n["descriptor"], ins, n["params"])
        elif kind == "exchange":
            remap[i] = store.add_exchange(ins, n["params"])
        else:
            remap[i] = store.add_join(ins, n["params"])
    node_map = {i: (remap[i], None) for i in sorted(keep)}
    SEEN.update(whole=len(nodes), shipped=len(keep))
    return dataclasses.replace(
        whole,
        ir=bytes(store.serialize(outputs=[remap[i] for i in ids])),
        correspondence=Correspondence(node_map=node_map, frames=_frames_by_key(session, node_map)),
    )


def case(name: str):
    s = Session(AwkwardBackend())
    ev = from_parquet(s, "events", path)
    if name == "fills":
        h = gh.boost.Histogram(bh.axis.Regular(4, 0, 5), storage=bh.storage.Weight())
        h.fill(ev.x, weight=[ev.w])
        h.fill(ev.x, weight=[ev.w * 1.0])
        _unrelated = [ev.w + float(i) for i in range(50)]
        _bad = ev.x[ev.x > 100][0]
        fills, counter = h.fill_nodes(), ev.x * 0 + 1
        held: dict[str, list[int]] = {}

        def hook(compiled):
            order = {c: k for k, c in enumerate(GraphStore.deserialize(bytes(compiled.ir)).outputs())}
            held["p"] = [order[compiled.correspondence.node_map[f.node_id][0]] for f in fills]

        want = bh.Histogram(bh.axis.Regular(4, 0, 5), storage=bh.storage.Weight())
        want.fill(X, weight=W)
        want.fill(X, weight=W)
        plan = aggregate_plan(counter, *fills, reduce=lambda v: sum((v[p] for p in held["p"][1:]), v[held["p"][0]].copy()),
                              combine=lambda a, b: a + b, empty=lambda: want * 0, externals=h.evaluators(),
                              on_compiled=hook)
        marked = [counter, *fills]
        check = lambda v: f"equal to two direct fills: {np.array_equal(v.view(flow=True), want.view(flow=True))}"  # noqa: E731
    else:
        keep = ev.x * 2.0
        if name == "cols":
            _unrelated = [ev.w + float(i) for i in range(50)]
        if name == "raise":
            _bad = ev.x[ev.x > 100][0]
        plan = aggregate_plan(keep, reduce=lambda v: float(ak.sum(v[0])), combine=lambda a, b: a + b, empty=float)
        marked = [keep]
        check = lambda v: f"value {v}"  # noqa: E731
    replay_cone = {op.node_id for a in marked for op in lower(s, a, opt_level=0).ops}
    dce = s._store.reduce(outputs=[a.node_id for a in marked])[1]["reachable_nodes"]
    try:
        res = check(SequentialRunner().run(plan).value)
    except Exception as e:  # noqa: BLE001
        res = f"{type(e).__name__}: {getattr(e, 'cause_message', str(e))[:70]}"
    shipped = len(GraphStore.deserialize(bytes(plan.process.ir)).nodes())
    print(f"{name:5}: shipped {shipped} nodes (cone {SEEN['shipped']}, replay cone {len(replay_cone)}, "
          f"Rust DCE {dce}; whole store {SEEN['whole']}); {res}")
    return plan


agg.compile_ir = compile_cone
try:
    for name in ("none", "cols", "raise", "fills"):
        plan = case(name)
    print(f"sha256 of the fills case's cone IR: {hashlib.sha256(bytes(plan.process.ir)).hexdigest()[:16]}")
finally:
    agg.compile_ir = REAL
