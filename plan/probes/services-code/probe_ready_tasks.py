import os, socket, subprocess, sys, time, urllib.request
from graphed_executors.common.http_plane import EscalatingHttpTransport
from graphed_executors.parsl_backend.transport_peer import DRIVER, HOST


def _free():
    with socket.socket() as s:
        s.bind((HOST, 0)); return s.getsockname()[1]


def _ready(port):
    try:
        with urllib.request.urlopen(f"http://{HOST}:{port}/", timeout=1) as r:
            return 200 <= r.status < 300
    except OSError:
        return False


def service_main(spec):
    port = _free()
    proc = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", HOST],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    polls = 0
    if spec["wait"]:
        while not _ready(port):
            polls += 1; time.sleep(0.005)
    ep = EscalatingHttpTransport("svc", epoch=spec["epoch"], host=HOST)
    ep.set_registry({DRIVER: (spec["driver_host"], spec["driver_port"])})
    ep.send(DRIVER, ("announce", "svc", HOST, port, os.getpid(), proc.pid, polls))
    t0 = time.monotonic()
    while time.monotonic() - t0 < 1.5:
        got = ep.recv(timeout=0.2)
        if got is not None and got[1] == ("stop",):
            break
    proc.kill(); proc.wait(); ep.close()
    return polls


def get(url):
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            return r.status
    except OSError as e:
        return f"{type(e).__name__}"


def identity():
    ad = os.environ.get("_CONDOR_MACHINE_AD")
    if ad:
        for line in open(ad):
            if line.startswith("Machine"):
                return line.split("=", 1)[1].strip().strip('"')
    return socket.getfqdn()
