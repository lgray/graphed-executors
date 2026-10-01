"""A cluster server whose only slot room is held by the run's own idle pilots: does the run end (refusal or
timeout_s) or wait forever? Run as submituser in the m68b-minicondor pool, cwd /work, PYTHONPATH
tests/frozen/m69b:tests/frozen/m68a."""

import logging
import os
import time
import traceback

import htcondor2 as htc
from m69b_harness import HARNESS_FILE, histserv_api, served_plan, unique

from graphed_executors.htcondor_backend import htcondor_runner

SERVER_MB, TIMEOUT_S, WATCH_S = 2048, 20.0, 90.0
records: list[str] = []


class Keep(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        records.append(record.getMessage())


logging.getLogger("graphed_executors").addHandler(Keep())
logging.getLogger("graphed_executors").setLevel(logging.INFO)
(slot,) = [a for a in htc.Collector().query(htc.AdType.Startd) if a.get("SlotType") == "Partitionable"]
total = int(slot["TotalSlotMemory"])
pilot_mb = (total - SERVER_MB // 2) // 2  # two pilots leave half a server's memory free
print(f"TotalSlotMemory={total} TotalSlotCpus={slot['TotalSlotCpus']}; 2 pilots x {pilot_mb} MiB; server {SERVER_MB} MiB")
ctx = histserv_api().Context(memory_mb=SERVER_MB, workers=2, timeout_s=TIMEOUT_S, name=unique("rv-starve"))
plan = served_plan({"h": 8}, ctx)
runner = htcondor_runner(
    n_pilots=2, site="generic", log_dir="/tmp/rv-starve", user_modules=[HARNESS_FILE], min_pilots=2,
    service_hosts=("cluster",), request_memory_mb=pilot_mb,
)
schedd = htc.Schedd()
future = None
try:
    runner.wait_for_pilots()
    t0 = time.monotonic()
    future = runner.submit(plan)
    while time.monotonic() - t0 < WATCH_S and not future.done():
        time.sleep(15)
        jobs = [(int(a["ClusterId"]), str(a["JobBatchName"])[:24], int(a["JobStatus"]))
                for a in schedd.query(constraint="true", projection=["ClusterId", "JobBatchName", "JobStatus"])]
        print(f"t={time.monotonic() - t0:5.1f}s done={future.done()} queue={jobs}", flush=True)
    print(f"after {WATCH_S:.0f}s (timeout_s={TIMEOUT_S}): done={future.done()}; wait-log lines={sum('waits for a slot' in r for r in records)}")
    for line in [r for r in records if "waits for a slot" in r][:2]:
        print("  log:", line)
except Exception:
    traceback.print_exc()
finally:
    runner.close()
    try:
        assert future is not None, "no run was submitted"
        future.result(60)
        print("closed; the run then completed")
    except Exception as exc:  # the outcome after close, whatever it is
        print("closed; the run then raised", repr(exc)[:300])
    os._exit(0)  # a run thread still waiting would keep the interpreter alive
