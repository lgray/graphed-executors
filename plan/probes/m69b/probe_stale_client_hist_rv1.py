"""Does histserv._call's per-(pid, endpoint) client cache survive a server restart on the same port?

A second run in one driver process (a notebook re-run, a kept worker pool) re-uses the port when the
executor's scan lands on it again. Leg A: a cached client after a restart. Leg B (control): a fresh client.
"""
import socket, subprocess, sys, time
from graphed_histogram import histserv as hs
from histserv import Client

def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]

def start(port):
    p = subprocess.Popen([sys.executable, "-m", "histserv", "--port", str(port), "--log-level", "ERROR"])
    for _ in range(200):
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close(); return p
        except OSError: time.sleep(0.05)
    raise SystemExit("no listen")

port = free_port(); ep = f"tcp://127.0.0.1:{port}"
p1 = start(port)
print("run1 stats:", hs._call(ep, lambda c: c.stats()["histogram_count"]))
p1.kill(); p1.wait()
p2 = start(port)
try:
    for i in range(3):
        t = time.monotonic()
        try:
            print(f"run2 cached call {i}:", hs._call(ep, lambda c: c.stats()["histogram_count"]), f"{time.monotonic()-t:.2f}s")
        except Exception as e:
            print(f"run2 cached call {i}: {type(e).__name__}: {e}"[:200], f"{time.monotonic()-t:.2f}s")
    with Client(f"127.0.0.1:{port}") as c:
        print("control fresh client:", c.stats()["histogram_count"])
finally:
    p2.kill(); p2.wait()
