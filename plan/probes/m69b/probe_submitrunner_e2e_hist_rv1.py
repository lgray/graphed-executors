"""End to end on graphed-executors db8fb0a (git archive): SubmitRunner(ThreadBackend(2)) over a served plan
on two histserv servers, nothing bound by hand. Checks the docs claim that the executor starts, binds and
resolves; value vs the unbacked twin; no histserv process left."""
import os, subprocess, tempfile
import awkward as ak, boost_histogram as bh, numpy as np
import graphed_histogram as gh
from graphed import Session
from graphed.awkward import AwkwardBackend, from_parquet
from graphed.core.execution import SequentialRunner
from graphed_executors.submit.engine import SubmitRunner
from graphed_executors.submit.threadpool import ThreadBackend
from graphed_histogram import histserv

d = tempfile.mkdtemp(); path = os.path.join(d, "e.parquet")
rng = np.random.default_rng(1); x = rng.normal(2, 1, 4000); w = rng.choice([0.25, 0.5, 1.0], 4000)
ak.to_parquet(ak.Array({"x": x, "w": w}), path)
def hists(back):
    s = Session(AwkwardBackend()); ev = from_parquet(s, "events", path, steps_per_file=4)
    out = {"a": gh.boost.Histogram(bh.axis.Regular(50, -2, 6), storage=bh.storage.Weight()),
           "b": gh.boost.Histogram(bh.axis.Regular(30, -2, 6), storage=bh.storage.Double())}
    out["a"].fill(ev.x, weight=[ev.w]); out["b"].fill(ev.x)
    if back:
        for k, h in out.items():
            histserv.backed(h, histserv.Context(memory_mb=512, workers=2, name=f"rv1-e2e-{k}"))
    return out
plan = gh.plan(hists(True), steps_per_file=4)
print("services:", [(s.name, s.kind, dict(s.launch.resources)) for s in plan.services])
res = SubmitRunner(ThreadBackend(2)).run(plan)
twin = SequentialRunner().run(gh.plan(hists(False), steps_per_file=4)).value
print("value types:", {k: type(v).__name__ for k, v in res.value.items()})
print("equal twin:", all(np.array_equal(np.asarray(res.value[k].view(flow=True)), np.asarray(twin[k].view(flow=True))) for k in twin))
left = subprocess.run(["pgrep", "-f", "-m", "histserv --port"], capture_output=True, text=True).stdout.strip()
print("histserv left after run:", left or "none")
