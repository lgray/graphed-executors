import json, pickle, tempfile
import awkward as ak, numpy as np, boost_histogram as bh
import graphed_histogram as gh
from graphed import Session
from graphed.awkward import AwkwardBackend
from graphed.awkward.io import from_parquet
from graphed.execute import compile_ir
from graphed.core import GraphStore, OpSpec
from graphed.core.execution import LocalResources

d = tempfile.mkdtemp()
for i in range(2):
    ak.to_parquet(ak.Array({"x": np.linspace(0, 99, 10_000) + i}), f"{d}/f{i}.parquet")
s = Session(AwkwardBackend())
ev = from_parquet(s, "events", d)
h = gh.Histogram(bh.axis.Regular(50, 0, 100), storage=bh.storage.Weight())
h.fill(ev.x)
node = h.fill_nodes()[0]
ir = compile_ir(s, node).ir
ext = [n for n in GraphStore.deserialize(bytes(ir)).nodes() if n["kind"] == "external"][0]
print("FILL_NODE_DESCRIPTOR", json.dumps(ext["descriptor"], sort_keys=True)[:300])
print("FILL_NODE_PARAMS", json.dumps(ext["params"], sort_keys=True)[:300])
plan = h.plan()
print("PLAN_TYPES process", type(plan.process).__name__, "reduce", type(plan.process.reduce).__name__, "combine", plan.combine.__module__ + ":" + plan.combine.__qualname__, "empty", type(plan.empty).__name__)
print("EXTERNALS_IN_PROCESS", [(k[:20], type(v).__name__) for k, v in plan.process.externals])
partials = [plan.process(t.partition, LocalResources()) for t in plan.tasks]
print("PARTIAL_TYPE", type(partials[0]).__module__ + "." + type(partials[0]).__name__, "PICKLED_PARTIAL_BYTES", [len(pickle.dumps(p)) for p in partials])
total = plan.combine(partials[0], partials[1])
print("COMBINED_SUM", total.sum(flow=True), "N_TASKS", len(plan.tasks))
print("OPSPEC_KINDS process", OpSpec.from_callable(plan.process).kind, "combine", OpSpec.from_callable(plan.combine).kind, "empty", OpSpec.from_callable(plan.empty).kind)
print("PROCESS_STDLIB_PICKLE_BYTES", len(pickle.dumps(plan.process)))

import os, subprocess, sys
blob = pickle.dumps(plan)
path = os.path.join(d, "plan.pkl"); open(path, "wb").write(blob)
print("WHOLE_RUNTIME_PLAN_STDLIB_PICKLE_BYTES", len(blob), "tasks", len(plan.tasks), "partition0", plan.tasks[0].partition)
code = ("import pickle,sys;from graphed.core.execution import SequentialRunner;"
        "p=pickle.load(open(sys.argv[1],'rb'));print(SequentialRunner().run(p).value.sum(flow=True))")
env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
r = subprocess.run([sys.executable, "-c", code, path], cwd=tempfile.mkdtemp(), env=env, capture_output=True, text=True)
print("FRESH_PROCESS_NO_USER_CODE rc", r.returncode, r.stdout.strip() or r.stderr.strip().splitlines()[-1])
