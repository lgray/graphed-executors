"""P4: which PayloadDescriptor/param fields of a histogram fill node enter IR identity; where the evaluator travels."""
import dataclasses, tempfile
import awkward as ak, numpy as np, boost_histogram as bh
import graphed_histogram as gh
from graphed import Session
from graphed.awkward import AwkwardBackend
from graphed.awkward.io import from_parquet
from graphed.execute import compile_ir
from graphed.core import GraphStore, OpSpec, PayloadDescriptor

d = tempfile.mkdtemp()
ak.to_parquet(ak.Array({"x": np.linspace(0, 99, 1000)}), f"{d}/f0.parquet")

def record(storage=bh.storage.Weight(), swap_evaluator=None, extra_param=None):
    s = Session(AwkwardBackend())
    ev = from_parquet(s, "events", d)
    h = gh.Histogram(bh.axis.Regular(50, 0, 100), storage=storage)
    h.fill(ev.x)
    node = h.fill_nodes()[0]
    if swap_evaluator or extra_param:  # re-record the same fill by hand with a different evaluator / params
        ext = [n for n in s._store.nodes() if n["kind"] == "external"][0]
        (fn, ids), = s._externals.values()
        desc = PayloadDescriptor(**ext["descriptor"])
        params = dict(ext["params"], **(extra_param or {}))
        s2 = Session(AwkwardBackend()); ev2 = from_parquet(s2, "events", d)
        node = s2.record_external("histogram.fill", swap_evaluator or fn, [ev2.x], params,
                                  descriptor=desc, form=gh.boost.HistogramForm(desc.content_hash))
        s, h = s2, None
    return s, node, h

base_s, base_node, base_h = record()
base_ir = bytes(compile_ir(base_s, base_node).ir)
ext = [n for n in GraphStore.deserialize(base_ir).nodes() if n["kind"] == "external"][0]
print("DESCRIPTOR", ext["descriptor"]); print("PARAMS_KEYS", sorted(ext["params"]))

# 1) every descriptor field and a new param, varied one at a time on a bare store
def ext_id(desc_kw, params):
    st = GraphStore(); src = st.add_source("events")
    return st.add_external(PayloadDescriptor(**desc_kw), [src], params), st
d0 = dict(ext["descriptor"]); p0 = dict(ext["params"])
id0, st = ext_id(d0, p0)
for field, alt in [("kind", "histserv"), ("content_hash", "0" * 64), ("framework", "histserv"),
                   ("version", "9.9.9"), ("io_schema", "grpc"), ("preprocessing_ref", "backing=histserv")]:
    st2 = GraphStore(); src = st2.add_source("events")
    a = st2.add_external(PayloadDescriptor(**d0), [src], p0)
    b = st2.add_external(PayloadDescriptor(**dict(d0, **{field: alt})), [src], p0)
    print(f"DESCRIPTOR_FIELD {field:18s} distinct_node={a != b}")
st3 = GraphStore(); src = st3.add_source("events")
a = st3.add_external(PayloadDescriptor(**d0), [src], p0)
b = st3.add_external(PayloadDescriptor(**d0), [src], dict(p0, backing="histserv"))
c = st3.add_external(PayloadDescriptor(**d0), [src], dict(p0))
print(f"NEW_PARAM backing          distinct_node={a != b}  same_params_interned={a == c}")

# 2) storage choice is spec-borne
s_d, n_d, _ = record(storage=bh.storage.Double())
print("STORAGE_WEIGHT_vs_DOUBLE_IR_DIFFER", bytes(compile_ir(s_d, n_d).ir) != base_ir)

# 3) the evaluator object is NOT in the IR, but rides in the runtime plan's process
@dataclasses.dataclass(frozen=True)
class BackedFill(gh.FillEvaluator):
    backing: str = "histserv://host:50051"
fe = base_s._externals[base_node.node_id][0]
s_b, n_b, _ = record(swap_evaluator=BackedFill(**{f.name: getattr(fe, f.name) for f in dataclasses.fields(fe)}))
ir_b = bytes(compile_ir(s_b, n_b).ir)
print("EVALUATOR_SWAP_IR_IDENTICAL", ir_b == base_ir)
s_p, n_p, _ = record(extra_param={"backing": "histserv://host:50051"})
print("PARAM_BACKING_IR_DIFFER", bytes(compile_ir(s_p, n_p).ir) != base_ir)

import graphed
plan_a = base_h.plan()
plan_b = graphed.aggregate_plan(n_b, reduce=plan_a.process.reduce, combine=plan_a.combine, empty=plan_a.empty)
print("PLAN_EXTERNALS_KEYS", [k[:16] + "…|" + k.split("|", 1)[1][:40] for k, _ in plan_b.process.externals])
print("PLAN_EXTERNALS_TYPES", [type(v).__name__ for _, v in plan_b.process.externals],
      "backing_on_worker_object", [getattr(v, "backing", None) for _, v in plan_b.process.externals])
print("CAPTURE_ID_EQUAL (aggregate.py:121, ir+partition)",
      plan_a.process._capture_id(plan_a.tasks[0].partition) == plan_b.process._capture_id(plan_b.tasks[0].partition)
      if hasattr(plan_a.process, "_capture_id") else "n/a")
print("OPSPEC_IDENTITY_DIFFER (DurablePlan.task_id input)",
      OpSpec.from_callable(plan_a.process).identity() != OpSpec.from_callable(plan_b.process).identity())
