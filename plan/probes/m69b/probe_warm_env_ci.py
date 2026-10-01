"""Warm histserv 0.2.1 server VmRSS (raw-client warm-up as probe_histserv_memory.py) and its loaded-module count."""

import socket
import subprocess
import sys
import time

import hist
from histserv import Client

port = 50551
proc = subprocess.Popen([sys.executable, "-m", "histserv", "--port", str(port), "--log-level", "ERROR"])
try:
    for _ in range(300):
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    with Client(f"127.0.0.1:{port}") as c:
        r = c.init(hist.Hist(hist.axis.Regular(64, 0, 1, name="x"), storage=hist.storage.Double()))
        r.fill(x=[0.5])
        r.snapshot(delete_from_server=True)
    time.sleep(0.6)
    status = dict(line.split(":", 1) for line in open(f"/proc/{proc.pid}/status"))
    maps = open(f"/proc/{proc.pid}/maps").read()
    sos = sorted({ln.split()[-1].rsplit("/", 1)[-1] for ln in maps.splitlines() if ".so" in ln})
    print("WARM", " ".join(f"{k}={status[k].strip()}" for k in ("VmRSS", "RssAnon", "RssFile")), "sofiles", len(sos))
    print("SOS", " ".join(s for s in sos if not s.startswith(("libc.", "ld-", "libm.", "libpthread"))))
finally:
    proc.kill()
