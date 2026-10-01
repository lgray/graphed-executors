"""r6-B: scenario E (n FillMany of one 32 MiB histogram in flight) with each filler on its OWN connection, as
separate worker processes are, beside E's shared connection; (peak - static)/M against the model's a + b*n
(a=5.5, b=3.0: the maxima over every MODEL line). Run in python:3.1x-slim with histserv==0.2.1, psutil."""

from __future__ import annotations

import sys
import faulthandler
import threading

import grpc

sys.path.insert(0, "/p")
import probe_histserv_memory as P  # noqa: E402
from histserv.client import Client  # noqa: E402

A, B_ = 5.5, 3.0
_orig = grpc.insecure_channel


def own_connection(target, options=None, *a, **k):
    return _orig(target, [*(options or []), ("grpc.use_local_subchannel_pool", 1)], *a, **k)


def run(n: int, separate: bool) -> float:
    dense = 32 * P.MiB
    worst = 0
    for _rep in range(3):
        faulthandler.dump_traceback_later(120, exit=True)
        srv = P.Server()
        r = srv.client.init(P.dense_hist(dense, P.bh.storage.Double()))
        srv.client.stub.FillMany(P.fill_many(r, "seed"), timeout=P.TIMEOUT)
        reqs = [P.fill_many(r, f"c{i}") for i in range(n)]
        grpc.insecure_channel = own_connection if separate else _orig
        try:
            clients = [Client(f"127.0.0.1:{srv.port}") for _ in range(n)]
            for c in clients:
                c.channel  # the channel is a cached_property: build it while the patch is in place
        finally:
            grpc.insecure_channel = _orig
        for c in clients:
            grpc.channel_ready_future(c.channel).result(timeout=10)
        barrier = threading.Barrier(n)

        def send(i: int) -> None:
            barrier.wait()
            clients[i].stub.FillMany(reqs[i], timeout=P.TIMEOUT)

        ts = [threading.Thread(target=send, args=(i,)) for i in range(n)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        worst = max(worst, srv.above())
        conns = len([c for c in P.psutil.Process(srv.proc.pid).net_connections() if c.status == "ESTABLISHED"])
        srv.close()
    return (worst - 2 * dense) / dense, conns


if __name__ == "__main__":
    import faulthandler

    faulthandler.dump_traceback_later(120, exit=True)
    from importlib.metadata import version

    print(f"histserv {version('histserv')} grpcio {version('grpcio')} python {sys.version.split()[0]}")
    for n in (1, 2, 4, 8):
        for separate in (False, True):
            ratio, conns = run(n, separate)
            tag = "own connections" if separate else "shared connection"
            flag = "OVER" if ratio > A + B_ * n else "within"
            print(f"  {n} in flight, {tag:17s} ({conns} server conns): (peak-static)/M = {ratio:5.2f}"
                  f"  model a+b*n = {A + B_ * n:5.1f}  {flag}")
