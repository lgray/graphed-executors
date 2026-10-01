"""r5-B: server RSS per open client connection (one per worker process in a run), histserv 0.2.1.
Each channel uses a local subchannel pool, so it holds its own TCP connection as a separate process would.
Run (Linux, /proc RSS): docker run --rm -e GRPC_VERBOSITY=NONE -v "$PWD:/p" python:3.12-slim sh -c
  'pip install -q "histserv==0.2.1" && uname -m && python /p/probe_connections_rv5b.py' > probe_connections_rv5b.linux.txt
probe_connections_rv5b.txt is the same scenario on macOS arm64 (graphed-histogram/.venv), RSS read with
`ps -o rss= -p <pid>` in place of /proc."""
import socket
import subprocess
import sys
import time

import grpc
from histserv.protos import hist_pb2, hist_pb2_grpc


def rss(pid: int) -> int:
    with open(f"/proc/{pid}/status") as f:
        return next(int(l.split()[1]) for l in f if l.startswith("VmRSS:")) * 1024


s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
srv = subprocess.Popen([sys.executable, "-m", "histserv", "--port", str(port), "--log-level", "WARNING"])
channels = []
try:
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close(); break
        except OSError:
            time.sleep(0.05)
    opts = [("grpc.use_local_subchannel_pool", 1), ("grpc.max_send_message_length", 1 << 29),
            ("grpc.max_receive_message_length", -1)]
    def open_n(n: int) -> None:
        for _ in range(n):
            ch = grpc.insecure_channel(f"127.0.0.1:{port}", options=opts)
            hist_pb2_grpc.HistogrammerServiceStub(ch).Stats(hist_pb2.StatsRequest(), timeout=10)
            channels.append(ch)
    open_n(4); time.sleep(1.0)
    base = rss(srv.pid)
    print(f"server rss with 4 connections: {base / 2**20:.1f} MiB")
    for total in (68, 260, 516):
        open_n(total - len(channels)); time.sleep(1.5)
        now = rss(srv.pid)
        print(f"{len(channels)} connections: rss {now / 2**20:.1f} MiB, per extra connection {(now - base) / (len(channels) - 4) / 1024:.1f} KiB")
finally:
    for ch in channels:
        ch.close()
    srv.terminate(); srv.wait()
