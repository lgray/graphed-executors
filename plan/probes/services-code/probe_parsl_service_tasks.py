import os, subprocess, time
from graphed_executors.common.http_plane import EscalatingHttpTransport
from graphed_executors.parsl_backend.transport_peer import DRIVER, HOST


def service_main(spec):
    proc = subprocess.Popen(["sleep", "60"])
    ep = EscalatingHttpTransport("svc", epoch=spec["epoch"], host=HOST)
    ep.set_registry({DRIVER: (spec["driver_host"], spec["driver_port"])})
    ep.send(DRIVER, ("announce", "svc", ep.host, ep.port, os.getpid(), proc.pid))
    t0 = time.monotonic()
    stopped = False
    while time.monotonic() - t0 < 30:
        got = ep.recv(timeout=0.2)
        if got is not None and got[1] == ("stop",):
            stopped = True
            break
    proc.kill(); proc.wait()
    ep.close()
    return {"stopped_by_message": stopped, "held_s": round(time.monotonic() - t0, 2), "pid": os.getpid()}


def other(i):
    time.sleep(0.2)
    return (i, os.getpid())


