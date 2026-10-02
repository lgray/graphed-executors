"""run_lpc's form (`with htcondor_runner(...) as runner: runner.run(plan)`) when the run's own pilots hold the room
its server needs (r1's self-starve sizes): close() cannot be called, so the user's way out is Ctrl-C. The
shell wrapper sends SIGINT after the first wait log; this prints what the interrupt left. As submituser in the
m68b-minicondor pool, cwd /work, PYTHONPATH=<tree>/src:tests/frozen/m69b:tests/frozen/m68a."""

import logging
import signal
import sys
import time

import htcondor2 as htc
from m69b_harness import HARNESS_FILE, histserv_api, served_plan, unique

from graphed_executors.htcondor_backend import htcondor_runner

signal.signal(signal.SIGINT, signal.default_int_handler)  # a background job starts with SIGINT ignored
logging.basicConfig(level=logging.INFO, format="%(relativeCreated)7.0fms %(name)s: %(message)s", stream=sys.stdout)
(slot,) = [a for a in htc.Collector().query(htc.AdType.Startd) if a.get("SlotType") == "Partitionable"]
pilot_mb = (int(slot["TotalSlotMemory"]) - 1024) // 2
ctx = histserv_api().Context(memory_mb=2048, workers=2, timeout_s=20.0, name=unique("rv2-sigint"))
t0 = time.monotonic()
try:
    with htcondor_runner(n_pilots=2, site="generic", log_dir="/tmp/rv2-sigint", user_modules=[HARNESS_FILE],
                         min_pilots=2, service_hosts=("cluster",), request_memory_mb=pilot_mb) as runner:
        print("run returned", runner.run(served_plan({"h": 8}, ctx)).value, flush=True)
except BaseException as exc:
    print(f"{time.monotonic() - t0:.1f}s: {type(exc).__name__} {exc}"[:240], flush=True)
    raise
