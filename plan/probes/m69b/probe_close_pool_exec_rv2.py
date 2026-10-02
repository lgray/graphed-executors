"""close() in the m68b-minicondor pool (10 CPUs, 15 973 MiB), as submituser, cwd /work,
PYTHONPATH=<tree>/src:tests/frozen/m68b. argv[1]:
  free [POLL_S]  a free pool: submit a one-server plan, then close() at once. Does the plan finish?
  queue [GATE_S] (b) plan R (gated tasks, its server up) submitted; plan W (a server that fits the slot whole but not
                 its free room) run directly on a thread and waiting; close(); R's gate opens GATE_S (5) s later.
  direct [GATE_S] (b') plan R run directly on a thread (gated, server up); plan W submitted and waiting; close().
Every case prints how long close() took, each plan's outcome, and the queue afterwards."""

from __future__ import annotations

import dataclasses
import logging
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

import htcondor2 as htc
from m68b_harness import HARNESS_FILE, GatedGet, TimedGet, recipes_api, service_plan

from graphed_executors.htcondor_backend import htcondor_runner
from graphed_executors.htcondor_backend import server as server_mod
from graphed_executors.local._transport import LookupFreeHTTPServer

logs: list[str] = []
T0 = time.monotonic()


class Keep(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        logs.append(f"{time.monotonic() - T0:6.1f}s {record.getMessage()}")


logging.getLogger("graphed_executors").addHandler(Keep())
logging.getLogger("graphed_executors").setLevel(logging.INFO)


class Gate(LookupFreeHTTPServer):
    daemon_threads = True
    state = "closed"
    polls = 0


class GateHandler(BaseHTTPRequestHandler):
    server: Gate

    def do_GET(self) -> None:
        self.server.polls += 1
        body = self.server.state.encode()
        self.send_response(200)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return None


def web(memory_mb: int) -> Any:
    spec = recipes_api().http_server("web")
    return dataclasses.replace(
        spec, launch=dataclasses.replace(spec.launch, resources={"memory_mb": memory_mb}), timeout_s=300.0
    )


def queue() -> list[tuple[int, str, int]]:
    ads = htc.Schedd().query(constraint="true", projection=["ClusterId", "JobBatchName", "JobStatus"])
    return [(int(a["ClusterId"]), str(a.get("JobBatchName", ""))[:28], int(a["JobStatus"])) for a in ads]


def services_history(since: int) -> list[tuple[Any, ...]]:
    attrs = ["ClusterId", "JobBatchName", "QDate", "JobCurrentStartDate", "NumJobStarts", "JobStatus"]
    ads = htc.Schedd().history(f'regexp("^graphed-service-", JobBatchName) && QDate >= {since}', attrs, match=20)
    return [(a["ClusterId"], a.get("QDate"), a.get("JobCurrentStartDate"), a.get("NumJobStarts"), a["JobStatus"])
            for a in ads]


def outcome(get: Any) -> str:
    try:
        return f"VALUE {get()!r}"[:160]
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"[:240]


def timed_close(runner: Any, bound: float = 300.0) -> str:
    t = time.monotonic()
    closer = threading.Thread(target=runner.close, daemon=True)
    closer.start()
    closer.join(bound)
    return "HUNG" if closer.is_alive() else f"{time.monotonic() - t:.1f}s"


def wait_until(pred: Any, bound: float) -> bool:
    end = time.monotonic() + bound
    while not pred() and time.monotonic() < end:
        time.sleep(0.5)
    return bool(pred())


def free(poll_s: float) -> None:
    server_mod.POLL_S = poll_s
    since = int(time.time())
    runner = htcondor_runner(n_pilots=1, site="generic", service_hosts=("cluster",), log_dir="/tmp/rv2-free",
                             user_modules=[HARNESS_FILE], min_pilots=1)
    runner.wait_for_pilots()
    fut = runner.submit(service_plan(TimedGet(), 1, "rv2-free", (web(512),)))
    took = timed_close(runner)
    print(f"free pool, POLL_S={poll_s}: close() {took}; plan: {outcome(lambda: len(fut.result(0).value))}")
    time.sleep(2)
    print("  service history (ClusterId, QDate, JobCurrentStartDate, NumJobStarts, JobStatus):", services_history(since))


def both(direct_r: bool, gate_s: float) -> None:
    gate = Gate(("", 0), GateHandler)
    threading.Thread(target=gate.serve_forever, daemon=True).start()
    runner = htcondor_runner(n_pilots=2, site="generic", service_hosts=("cluster",), log_dir="/tmp/rv2-both",
                             user_modules=[HARNESS_FILE], min_pilots=2, request_memory_mb=2048)
    runner.wait_for_pilots()
    url = f"http://{runner.backend.advertise_host}:{gate.server_address[1]}/"
    r_plan = service_plan(GatedGet(url), 1, "rv2-running", (web(1024),))
    w_plan = service_plan(TimedGet(), 1, "rv2-waiting", (web(12000),))
    got: dict[str, Any] = {}

    def run_direct(name: str, plan: Any) -> threading.Thread:
        def body() -> None:
            try:
                got[name] = ("value", len(runner.run(plan).value))
            except Exception as exc:
                got[name] = ("raised", f"{type(exc).__name__}: {exc}"[:240])

        th = threading.Thread(target=body, daemon=True)
        th.start()
        return th

    if direct_r:
        r_thread = run_direct("R", r_plan)
        assert wait_until(lambda: gate.polls > 0, 300), "R's task never started"
        w_fut = runner.submit(w_plan)
    else:
        r_fut = runner.submit(r_plan)
        assert wait_until(lambda: gate.polls > 0, 300), "R's task never started"
        w_thread = run_direct("W", w_plan)
    assert wait_until(lambda: any("waits for a slot" in line for line in logs), 60), "W never waited"
    print("before close:", queue())
    threading.Timer(gate_s, lambda: setattr(gate, "state", "open")).start()
    took = timed_close(runner)
    print(f"{'direct R, submitted W' if direct_r else 'submitted R, direct W'}, gate opens {gate_s:.0f} s after close(): close() {took}")
    if direct_r:
        r_thread.join(gate_s + 120)
        print("  R (running, direct):", got.get("R", f"HUNG (no outcome {gate_s + 120:.0f} s after close)"))
        print("  W (waiting, submitted):", outcome(lambda: w_fut.result(0)))
    else:
        w_thread.join(60)
        print("  R (running, submitted):", outcome(lambda: len(r_fut.result(0).value)))
        print("  W (waiting, direct):", got.get("W", "HUNG (no outcome after 60 s)"))
    gate.shutdown()


if __name__ == "__main__":
    import graphed_executors

    print("graphed_executors:", graphed_executors.__file__, "| stop_waiting:",
          hasattr(__import__("graphed_executors.htcondor_backend.backend", fromlist=["x"]).HTCondorBackend,
                  "stop_waiting"))
    case = sys.argv[1]
    try:
        if case == "free":
            free(float(sys.argv[2]) if len(sys.argv) > 2 else server_mod.POLL_S)
        else:
            both(direct_r=case == "direct", gate_s=float(sys.argv[2]) if len(sys.argv) > 2 else 5.0)
    finally:
        time.sleep(3)
        print("queue after:", queue())
        for line in logs:
            if "waits for a slot" in line or "closed" in line or "managed leg" in line:
                print("  log:", line[:200])
        import os

        os._exit(0)
