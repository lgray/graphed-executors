"""Order of the pilots' submit vs each service job's submit over a recorded schedd, three plans of one runner (two run(), one submit()).

usage: PYTHONPATH=<executors>/src python probe_order_trace.py <executors checkout>
Real pilot processes connect when the pilots' submit is recorded; a service submit is answered by a local
HTTP server and a signed announce, so each run completes end to end.
"""

from __future__ import annotations

import http.server
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root / "tests/frozen/m68b"))
import m68b_harness as h  # noqa: E402

import graphed_executors  # noqa: E402

print("graphed_executors from", Path(graphed_executors.__file__).parent)
T0 = time.monotonic()
events: list[tuple[float, str]] = []
procs: list[subprocess.Popen[bytes]] = []
servers: list[http.server.HTTPServer] = []


def mark(what: str) -> None:
    events.append((round(time.monotonic() - T0, 2), what))


class Schedd(h.RecordingSchedd):
    def submit(self, description, count=0, spool=False, **kw):  # type: ignore[no-untyped-def]
        batch = str(description.get("JobBatchName", ""))
        mark(f"schedd.submit {batch.split('-')[1]} count={count}")
        res = super().submit(description, count, spool, **kw)
        initial = Path(description["initialdir"])
        if batch.startswith("graphed-pilots-"):
            url = description["arguments"].split()[0]
            env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(root / "src"), str(root / "tests/frozen/m68b")])}
            for _ in range(count):
                procs.append(
                    subprocess.Popen(
                        [sys.executable, "-m", "graphed_executors.htcondor_backend.pilot", url,
                         str(initial / "graphed-secret")],
                        env=env,
                    )
                )
        else:
            threading.Thread(target=announce, args=(initial,), daemon=True).start()
        return res


def announce(job_dir: Path) -> None:
    import json

    cfg = json.loads((job_dir / "service.json").read_text())
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), http.server.SimpleHTTPRequestHandler)
    servers.append(srv)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    secret = bytes.fromhex((job_dir / "graphed-secret").read_text().strip())
    body = h.announce_body(cfg["key"], f"127.0.0.1:{srv.server_address[1]}", "wn9.example")
    mark(f"announce {cfg['key']} posting")
    mark(f"announce {cfg['key']} -> {h.post_announce(cfg['url'], body, secret)}")


mp = pytest.MonkeyPatch()
schedd = Schedd(queue=[[{"JobStatus": 2}]])
h.record_bindings(mp, schedd)
backend_mod = h.backend_api()
for name in ("wait_for_pilots", "close"):
    orig = getattr(backend_mod.HTCondorRunner, name)

    def spy(self, *a, _o=orig, _n=name, **k):  # type: ignore[no-untyped-def]
        mark(f"HTCondorRunner.{_n}")
        return _o(self, *a, **k)

    mp.setattr(backend_mod.HTCondorRunner, name, spy)
try:
    with tempfile.TemporaryDirectory() as tmp:
        mark("htcondor_runner(...) called")
        runner = backend_mod.htcondor_runner(
            n_pilots=1, log_dir=Path(tmp) / "logs", host="127.0.0.1", service_hosts=("cluster",)
        )
        mark("htcondor_runner(...) returned")
        try:
            for i, how in ((1, "run"), (2, "run"), (3, "submit")):
                plan = h.service_plan(h.TimedGet(), 2, f"r{i}", (h.web_spec(timeout_s=20.0),))
                mark(f"plan {i}: runner.{how} called")
                call = runner.run if how == "run" else (lambda p: runner.submit(p).result(120.0))
                result = h.run_bounded(lambda p=plan: call(p), 120.0)
                mark(f"plan {i} returned {len(result.value)} parts")
        finally:
            runner.close()
finally:
    mp.undo()
    for p in procs:
        p.terminate()
        p.wait(10)
    for s in servers:
        s.shutdown()
for t, what in events:
    print(f"{t:7.2f}  {what}")
