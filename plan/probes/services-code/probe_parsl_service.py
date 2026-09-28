"""m70 premise probe (parsl): a long-running service task holds one HTEX worker slot while other
tasks run on the remaining slot, announces (host, port, pid) to the driver's rendezvous plane
(EscalatingHttpTransport on HOST), and stops on a driver message (cancel_running=False on HTEX)."""
import os, subprocess, sys, time, uuid, tempfile
from graphed_executors.common.http_plane import EscalatingHttpTransport
from graphed_executors.parsl_backend.transport_peer import DRIVER, HOST, _open_driver_endpoint
from graphed_executors.parsl_backend.launch import start_htex, stop_htex
from probe_parsl_service_tasks import service_main, other  # by-reference pickling on HTEX


if __name__ == "__main__":
    nonce = uuid.uuid4().hex
    run_dir = tempfile.mkdtemp(prefix="parsl-svc-")
    ex = start_htex(workers=2, run_dir=run_dir)
    try:
        driver = _open_driver_endpoint(nonce)
        spec = {"epoch": nonce, "driver_host": driver.host, "driver_port": driver.port}
        svc = ex.submit(service_main, {}, spec)
        got = None
        t0 = time.monotonic()
        while got is None and time.monotonic() - t0 < 30:
            got = driver.recv(timeout=0.5)
        print("ANNOUNCE_REACHED_DRIVER", got is not None, got, f"after {time.monotonic()-t0:.1f}s")
        others = [ex.submit(other, {}, i) for i in range(4)]
        res = [f.result(timeout=30) for f in others]
        pids = {p for _, p in res}
        print("OTHER_TASKS_RAN_WHILE_SERVICE_HELD", len(res) == 4 and not svc.done(), res, "svc done?", svc.done())
        print("OTHERS_AVOIDED_SERVICE_PID", got[1][4] not in pids, "svc_pid", got[1][4], "other_pids", pids)
        def alive(pid):
            try:
                os.kill(pid, 0); return True
            except ProcessLookupError:
                return False
        child = got[1][5]
        c = svc.cancel(); time.sleep(1.0)
        print("CANCEL_IS_LOCAL_ONLY", c and alive(child), "cancel()->", c, "child alive after cancel:", alive(child))
        driver.set_registry({"svc": (got[1][2], got[1][3])})
        driver.send("svc", ("stop",))
        t1 = time.monotonic()
        while alive(child) and time.monotonic() - t1 < 10:
            time.sleep(0.1)
        print("SERVICE_STOPPED_BY_MESSAGE", not alive(child), f"child gone after {time.monotonic()-t1:.1f}s")
        driver.close()
    finally:
        stop_htex(ex)
