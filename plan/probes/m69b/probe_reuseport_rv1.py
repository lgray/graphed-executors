"""m69b-r1: can two `python -m histserv` processes (same uid) listen on ONE port at once? gRPC servers set
SO_REUSEPORT by default on Linux, so a second child on a port the scan found free need not fail to bind.

Run (Linux): python probe_reuseport_rv1.py   (histserv 0.2.1)
"""
import socket
import subprocess
import sys
import time

s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
argv = [sys.executable, "-m", "histserv", "--port", str(port), "--log-level", "ERROR"]
a = subprocess.Popen(argv)
b = subprocess.Popen(argv)
try:
    time.sleep(4)
    print(f"{sys.platform}: first alive={a.poll() is None} second alive={b.poll() is None} (returncode {b.poll()})")
    from histserv.client import Client
    import hist
    from histserv.chunked_hist import ChunkedHist
    ids = set()
    for _ in range(8):  # fresh channels: each new connection is placed by the kernel
        c = Client(f"127.0.0.1:{port}")
        r = c.init(ChunkedHist(hist.axis.Regular(2, 0, 1, name="a0")))
        ids.add(c.stats()["histogram_count"])
        c.channel.close()
    print(f"histogram_count seen by 8 fresh channels after one init each: {sorted(ids)}")
finally:
    for p in (a, b):
        p.terminate(); p.wait()
