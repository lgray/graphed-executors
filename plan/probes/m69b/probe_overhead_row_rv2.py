"""m69b-r2: the frozen memory row "≥ 2000 one-bin slots on one server filled once each: VmHWM − warm RSS ≤
prediction − B", run per storage against the plan's constants (O = 4000, I = 160: the maxima of the MODEL lines),
tasks = 1. Prints the margin (prediction − B) − (VmHWM − warm) and the smallest O that still passes.

Run: PYS="3.11 3.12 3.13 3.14" sh -c '...' (see probe_overhead_row_rv2.txt header); imports probe_histserv_memory.
"""
from __future__ import annotations

import sys

import boost_histogram as bh

import probe_histserv_memory as P

K, O, I = 2000, 4000, 160
for storage in (bh.storage.Weight(), bh.storage.Double()):
    item = 16 if isinstance(storage, bh.storage.Weight) else 8
    dense = 3 * item  # one bin plus its two flow bins
    srv = P.Server()
    try:
        remotes = [srv.client.init(P.dense_hist(dense, storage)) for _ in range(K)]
        for i, r in enumerate(remotes):
            srv.client.stub.FillMany(P.fill_many(r, f"p{i}"), timeout=P.TIMEOUT)
        srv.settle()
        grew = srv.above()
        predicted = K * (O + I * 1 + 2 * dense)
        o_min = grew / K - I - 2 * dense
        print(f"python {sys.version.split()[0]} {type(storage).__name__}: VmHWM-warm {grew} B, prediction-B {predicted} B,"
              f" margin {predicted - grew} B ({(predicted - grew) / predicted:.1%}); smallest passing O = {o_min:.0f} B")
    finally:
        srv.close()
