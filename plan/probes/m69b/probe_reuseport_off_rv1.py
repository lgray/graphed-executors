"""m69b-r1 control for probe_reuseport_rv1: the same two children, each started through a 5-line launcher that
adds ("grpc.so_reuseport", 0) to histserv's grpc.aio.server options: the second child fails to bind and exits.

Run (Linux): python probe_reuseport_off_rv1.py   (histserv 0.2.1)
"""
import socket
import subprocess
import sys
import time

LAUNCH = (
    "import grpc.aio, runpy; _s = grpc.aio.server\n"
    "grpc.aio.server = lambda *a, options=(), **k: _s(*a, options=[*options, ('grpc.so_reuseport', 0)], **k)\n"
    "runpy.run_module('histserv', run_name='__main__')\n"
)
s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
argv = [sys.executable, "-c", LAUNCH, "--port", str(port), "--log-level", "ERROR"]
a = subprocess.Popen(argv)
time.sleep(3)
b = subprocess.Popen(argv, stderr=subprocess.PIPE, text=True)
try:
    time.sleep(4)
    err = "" if b.poll() is None else b.stderr.read().strip().splitlines()[-1]
    print(f"{sys.platform}: first alive={a.poll() is None} second alive={b.poll() is None} (returncode {b.poll()}: {err[:100]})")
finally:
    for p in (a, b):
        p.terminate(); p.wait()
