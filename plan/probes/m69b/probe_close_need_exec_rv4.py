"""A need recorded while a first plan's server waits, then the run is stopped, over the frozen OrderSchedd recorder
(the server stays idle; no pilot ever starts). Does the server, ending because the run closes, submit the deferred
pilots? Frozen row 8 says Ctrl-C "removes a waiting server and submits no pilot". Cases: Ctrl-C (a real SIGINT) in
`fut.result()` and in the block's `close()`, each with and without a thread in `runner.wait_for_pilots()`; and a
direct `backend.close()` beside a waiting server and a waiting need.
PYTHONPATH=<tree>/src:<tree>/tests/frozen/m69b:<tree>/tests/frozen/m68a; argv[1] = a scratch dir."""

from __future__ import annotations

import os
import signal
import sys
import threading
import time
from pathlib import Path

import pytest
from m69b_order import OrderSchedd, order_bindings, order_plan
from services_harness import CountingHTTPServer, hosted_spec

from graphed_executors.htcondor_backend import HTCondorBackend, launch
from graphed_executors.htcondor_backend import backend as backend_mod
from graphed_executors.htcondor_backend import server as server_mod

signal.signal(signal.SIGINT, signal.default_int_handler)
root = Path(sys.argv[1])


def sigint_in(seconds: float) -> None:
    threading.Timer(seconds, os.kill, (os.getpid(), signal.SIGINT)).start()


def report(name: str, schedd: OrderSchedd, extra: str = "") -> None:
    t0 = schedd.events[0].t
    print(f"== {name} {extra}")
    for e in schedd.events:
        print(f"  {e.t - t0:6.2f}s {e.kind:15} {e.cluster or ''} {e.text[:90]}")
    pilots = {e.cluster for e in schedd.events if e.kind == "submit-pilots"}
    removed = {e.cluster for e in schedd.events if e.kind == "act" and e.text.startswith("Remove")}
    print(f"  pilot clusters submitted={sorted(pilots)} left in the queue={sorted(pilots - removed)}")


def runner_case(name: str, ctrl_c_in: str, need: bool) -> None:
    with CountingHTTPServer() as service, pytest.MonkeyPatch.context() as mp:
        mp.setattr(server_mod, "POLL_S", 0.5)
        schedd = OrderSchedd(service.port, announce_after_s=None, service_status=1)
        order_bindings(mp, schedd)
        runner = backend_mod.htcondor_runner(
            n_pilots=1, site="generic", service_hosts=("cluster",), log_dir=root / name, host="127.0.0.1"
        )
        try:
            with runner:
                fut = runner.submit(order_plan(f"rv4-{name}", "web"))
                deadline = time.monotonic() + 10
                while not schedd.service_dirs() and time.monotonic() < deadline:
                    time.sleep(0.05)
                if need:
                    threading.Thread(target=runner.wait_for_pilots, daemon=True).start()
                time.sleep(1.0)
                schedd.mark(f"Ctrl-C in {ctrl_c_in}")
                sigint_in(1.0)
                if ctrl_c_in == "result":
                    fut.result()
        except KeyboardInterrupt:
            schedd.mark("KeyboardInterrupt left the block")
        time.sleep(1.0)
        report(name, schedd)


def direct_case() -> None:
    with CountingHTTPServer() as service, pytest.MonkeyPatch.context() as mp:
        mp.setattr(server_mod, "POLL_S", 0.5)
        schedd = OrderSchedd(service.port, announce_after_s=None, service_status=1)
        order_bindings(mp, schedd)
        backend = HTCondorBackend(launch.CondorPilots("generic", log_dir=root / "direct"), 1, host="127.0.0.1")
        errs: list[str] = []

        def server() -> None:
            try:
                backend.host_service(hosted_spec("web"), "planB")
            except BaseException as exc:
                errs.append(f"{type(exc).__name__}: {exc}"[:100])

        s = threading.Thread(target=server, daemon=True)
        s.start()
        deadline = time.monotonic() + 10
        while not schedd.service_dirs() and time.monotonic() < deadline:
            time.sleep(0.05)
        n = threading.Thread(target=backend.wait_for_pilots, args=(1,), daemon=True)
        n.start()
        time.sleep(1.0)
        schedd.mark("backend.close()")
        backend.close()
        schedd.mark("close() returned")
        s.join(5.0)
        time.sleep(3.0)
        report("direct", schedd, f"server raised={errs} need thread alive 3s after close={n.is_alive()}")


which = sys.argv[2] if len(sys.argv) > 2 else "all"
for name, where, need in [
    ("result-control", "result", False),
    ("result-need", "result", True),
    ("close-control", "close", False),
    ("close-need", "close", True),
]:
    if which in ("all", name):
        runner_case(name, where, need)
if which in ("all", "direct"):
    direct_case()
sys.stdout.flush()
os._exit(0)  # the need threads wait on: do not join them
