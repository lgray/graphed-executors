"""Server RSS after the probe's raw-client warm-up vs the frozen harness's graphed-histogram warm-up (ps RSS)."""

import sys
import tempfile
import time

sys.path.insert(0, "tests/frozen/m69b")
import boost_histogram as bh
import hist
import subprocess
from graphed.core.execution import SequentialRunner
from graphed.services import bind_services, resolve_services
from histserv_harness import events, histserv_api, servers, write_events

import graphed_histogram as gh

MiB = 1 << 20


def rss(pid):
    time.sleep(0.6)
    return int(subprocess.check_output(["ps", "-o", "rss=", "-p", str(pid)])) * 1024


path = write_events(tempfile.mkdtemp() + "/e.parquet")
with servers(2) as (a, b):
    print("fresh", rss(a.proc.pid) / MiB, rss(b.proc.pid) / MiB)
    import histserv

    with histserv.Client(a.address) as c:
        r = c.init(hist.Hist(hist.axis.Regular(64, 0, 1, name="x"), storage=hist.storage.Double()))
        r.fill(x=[0.5])
        r.snapshot(delete_from_server=True)
    print("raw-client warm", rss(a.proc.pid) / MiB)
    _s, ev = events(path, 1)
    h = gh.boost.Histogram(bh.axis.Regular(6, 0.0, 1.0), storage=bh.storage.Double())
    h.fill(ev.x)
    hs = histserv_api()
    hs.backed(h, hs.Context(memory_mb=1024, workers=1, name="warm-probe"))
    plan = gh.plan({"warm": h}, steps_per_file=1)
    bound = bind_services(plan, {s.name: b.endpoint for s in plan.services})
    resolve_services(bound, SequentialRunner().run(bound).value)
    print("harness warm", rss(b.proc.pid) / MiB, "counts", {k: b.count(k) for k in ("Init", "FillMany", "Snapshot", "Delete")})
