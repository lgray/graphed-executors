"""A DAG driver job with pilots="condor" (driver.main over the frozen OrderSchedd recorder): are its pilots
submitted before or after its SERVICE node announces? §5.2 "Ordering", Driverless: "the driver job's
backend (announced) defers its pilots as above, so they follow the SERVICE nodes' announces". The SERVICE
node's announce is posted ANNOUNCE_AFTER_S after the driver publishes its url, as a node still idle would.
PYTHONPATH=<tree>/src:<tree>/tests/frozen/m69b:<tree>/tests/frozen/m68a; argv[1] = a scratch dir."""

from __future__ import annotations

import json
import pickle
import sys
import threading
import time
from pathlib import Path

import pytest
from m69b_order import OrderSchedd, order_bindings, order_plan
from services_harness import FAKE_POOL, FAKE_SCHEDD, CountingHTTPServer

from graphed_executors.htcondor_backend import backend as backend_mod
from graphed_executors.htcondor_backend import driver
from graphed_executors.htcondor_backend.driver import SECRET_FILE, URL_FILE

ANNOUNCE_AFTER_S = 3.0
root = Path(sys.argv[1])
job, dag = root / "job", root / "dag"
job.mkdir(parents=True)
dag.mkdir()
run = {
    "pilots": "condor", "n_pilots": 1, "site": "generic", "image": None, "log_dir": str(root / "pilots"),
    "request_memory_mb": 1024, "min_pilots": 1, "retries": 0, "max_in_flight": 1,
    "schedd_locate": [FAKE_POOL, FAKE_SCHEDD], "user_modules": [], "endpoints": None,
    "announce_only": {"web": "svc0"}, "dag_dir": str(dag), "extra_submit": None,
}
(job / "run.json").write_text(json.dumps(run))
(job / "plan.pkl").write_bytes(pickle.dumps(order_plan("rv3-dag", "web")))

with CountingHTTPServer() as service, pytest.MonkeyPatch.context() as mp:
    schedd = OrderSchedd(service.port, pilots=True)
    order_bindings(mp, schedd)
    real = backend_mod.HTCondorBackend._host_announced

    def host_announced(self, spec, scope):  # type: ignore[no-untyped-def]
        schedd.mark("ServiceSet asks for the SERVICE node's announce")
        return real(self, spec, scope)

    mp.setattr(backend_mod.HTCondorBackend, "_host_announced", host_announced)

    def service_node() -> None:  # the SERVICE node: idle a while, then it announces
        while not (dag / URL_FILE).exists():
            time.sleep(0.05)
        schedd.mark("driver published its url")
        time.sleep(ANNOUNCE_AFTER_S)
        node = root / "svc0"
        node.mkdir()
        url = (dag / URL_FILE).read_text().strip()
        (node / "service.json").write_text(json.dumps({"key": "svc0", "url": url}))
        (node / "graphed-secret").write_text((dag / SECRET_FILE).read_text().strip())
        print("SERVICE node announce answered", schedd.announce(node), flush=True)

    threading.Thread(target=service_node, daemon=True).start()
    try:
        code = driver.main([str(job)])
    finally:
        schedd.finish_pilots()
        schedd.stop_pilots()
    t0 = schedd.events[0].t
    print("driver exit", code)
    for e in schedd.events:
        if e.kind in ("submit-pilots", "pilot-start", "announce", "mark"):
            print(f"  {e.t - t0:6.2f}s {e.kind:14} {e.text}")
    order = [e.kind if e.kind != "mark" else e.text for e in schedd.events]
    first_pilots = order.index("submit-pilots")
    announce = order.index("announce")
    print("pilots submitted", "BEFORE" if first_pilots < announce else "after", "the SERVICE node's announce")
    print((job / "driver.log").read_text()[-600:])
