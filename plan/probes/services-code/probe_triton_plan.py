import json, pickle, subprocess, sys, tempfile, os
import awkward as ak, numpy as np
import fake_triton_probe as ft, probe_funcs as pf
from graphed import Session
from graphed.awkward import AwkwardBackend
from graphed.awkward.io import from_parquet
from graphed.aggregate import aggregate_plan
from graphed.execute import external_key, compile_ir
from graphed.core import GraphStore, DurablePlan, OpSpec
from graphed.preserve import TRITON_PLUGIN, record_external

d = tempfile.mkdtemp()
for i in range(2):
    ak.to_parquet(ak.Array({"x": np.arange(100.0) + 100 * i}), f"{d}/f{i}.parquet")
DESC = b'{"model": "scorer", "version": "1"}'

def build(url_a, url_b):
    s = Session(AwkwardBackend())
    ev = from_parquet(s, "events", d)
    p = lambda u: {"url": u, "model": "scorer", "transport": "fake_triton_probe:transport", "input_name": "x", "output_name": "y"}
    wa = record_external(s, TRITON_PLUGIN, DESC, [ev.x], params=p(url_a))
    wb = record_external(s, TRITON_PLUGIN, DESC, [ev.x + 1], params=p(url_b))
    return s, wa, wb

s, wa, wb = build("http://gpu-a:8000", "http://gpu-b:8000")
ir = compile_ir(s, wa, wb).ir
ext = [n for n in GraphStore.deserialize(bytes(ir)).nodes() if n["kind"] == "external"]
print("EXT_NODE_PARAMS", json.dumps(ext[0]["params"], sort_keys=True))
print("EXT_DESCRIPTOR_KEYS", sorted(ext[0]["descriptor"]))
print("EXTERNAL_KEYS_DIFFER_BY_URL", external_key(ext[0]) != external_key(ext[1]))
s2, wa2, wb2 = build("http://gpu-c:8000", "http://gpu-b:8000")
ir2 = compile_ir(s2, wa2, wb2).ir
print("IR_BYTES_DIFFER_WHEN_ONLY_URL_CHANGES", bytes(ir) != bytes(ir2))

plan = aggregate_plan(wa, wb, reduce=pf.reduce_sum, combine=pf.combine, empty=pf.empty)
print("N_TASKS", len(plan.tasks), "PROCESS_TYPE", type(plan.process).__module__ + "." + type(plan.process).__qualname__)
blob = pickle.dumps(plan.process)
print("STDLIB_PICKLE_PROCESS_BYTES", len(blob))
from graphed.core.execution import LocalResources
for t in plan.tasks:
    print("TASK", t.key, plan.process(t.partition, LocalResources()))
print("CONNECTS", ft.CONNECTS)
print("INFERS", ft.INFERS)

spec = OpSpec.from_callable(plan.process)
print("OPSPEC_KIND_OF_AGGREGATE_PROCESS", spec.kind, "opaque", spec.opaque)
dp = DurablePlan(ir=bytes(ir), process=spec, combine=OpSpec.from_callable(pf.combine), empty=OpSpec.from_callable(pf.empty), partitions=tuple(t.partition for t in plan.tasks))
out = os.path.join(d, "plan.json"); open(out, "wb").write(dp.to_bytes())
print("DURABLE_PLAN_BYTES", len(dp.to_bytes()), "combine_ref", dp.combine.ref)
code = ("import sys;from graphed.core import DurablePlan;from graphed.checkpoint.runner import run_resumable;"
        "from graphed.checkpoint.store import Store as S;import tempfile;"
        "p=DurablePlan.from_bytes(open(sys.argv[1],'rb').read());print(run_resumable(p,S(tempfile.mkdtemp())).value)")
for label, env in (("NO_USER_MODULES", {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}), ("WITH_PYTHONPATH", dict(os.environ, PYTHONPATH=os.getcwd()))):
    r = subprocess.run([sys.executable, "-c", code, out], cwd=d, env=env, capture_output=True, text=True)
    print("FRESH_PROCESS", label, "rc", r.returncode, (r.stdout.strip() or r.stderr.strip().splitlines()[-1]))
