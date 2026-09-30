"""Driven trace of the shape m69b builds on: gh.plan({...}) -> SequentialRunner, graphed d0ad16b +
graphed-histogram 4c4b79f. Shows (1) the plan's process and what its reduce receives (values only,
no partition), (2) the value's slot shape, (3) require_bound's placeholder bind on an unbound
Bindable part, (4) resolve_services reaching a reduce through _PartitionReduce."""
from dataclasses import dataclass, replace
import awkward as ak, boost_histogram as bh, graphed_histogram as gh
from graphed import Session, vary
from graphed.awkward import AwkwardBackend, from_parquet
from graphed.core.execution import SequentialRunner
from graphed.services import UnboundService, require_bound, resolve_services, ServiceSpec, bind_services
import tempfile, os

d = tempfile.mkdtemp(); path = os.path.join(d, "e.parquet")
ak.to_parquet(ak.Array({"x": [1.0, 2.0, 3.0, 4.0], "w": [0.5, 1.0, 1.5, 2.0]}), path)
s = Session(AwkwardBackend()); ev = from_parquet(s, "events", path, steps_per_file=2)
h = gh.boost.Histogram(bh.axis.Regular(4, 0, 5), storage=bh.storage.Weight())
w = vary(ev.w, "sf", up=ev.w * 1.2, down=ev.w * 0.8)
h.fill(ev.x, weight=[w], variation_axis=True)
g = gh.boost.Histogram(bh.axis.Regular(4, 0, 5))
g.fill(ev.x)
plan = gh.plan({"m": h, "n": g}, steps_per_file=2)
print("PROCESS", type(plan.process).__name__, "REDUCE", type(plan.process.reduce).__name__, "TASKS", len(plan.tasks))
seen = []
@dataclass(frozen=True)
class Spy:
    inner: object
    def __call__(self, values):
        seen.append([type(v).__name__ for v in values]); return self.inner(values)
spied = replace(plan, process=replace(plan.process, reduce=Spy(plan.process.reduce)))
value = SequentialRunner().run(spied).value
print("REDUCE_ARGS", seen[0], "calls", len(seen))
print("VALUE_KEYS", sorted(map(str, value)), "TYPES", sorted({type(v).__name__ for v in value.values()}))
print("AXIS_MODE_SLOT_AXES", [type(a).__name__ for a in value[("m", None)].axes], list(value[("m", None)].axes[1]))

calls = []
@dataclass(frozen=True)
class NeedsHists:
    ep: str | None = None
    def __call__(self, values): return values
    def bind_services(self, endpoints):
        calls.append(dict(endpoints))
        if "hists" not in endpoints and self.ep is None: raise UnboundService("hists")
        return replace(self, ep=endpoints.get("hists", self.ep))
    def resolve_services(self, value):
        calls.append(("resolve", type(value).__name__)); return value
s.declare_service(ServiceSpec("hists", "histserv"))
p2 = replace(plan, process=replace(plan.process, reduce=NeedsHists()), services=(s.service_for("hists"),))
try:
    require_bound(p2)
except UnboundService as e:
    print("REQUIRE_BOUND_UNBOUND raises", type(e).__name__, "bind calls", calls)
calls.clear()
b = bind_services(p2, {"hists": "tcp://127.0.0.1:1"}); require_bound(b)
print("REQUIRE_BOUND_BOUND bind calls", calls)
calls.clear(); resolve_services(b, {"k": 1}); print("RESOLVE_REACHES_REDUCE", calls)
