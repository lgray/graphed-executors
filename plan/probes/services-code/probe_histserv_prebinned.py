"""Can a boost_histogram partial (already binned) be shipped to histserv as one Fill, and does the
snapshot equal it? Also: named-axis requirement, replayed unique_id, server-assigned hist_id."""
import socket, subprocess, sys, time
import numpy as np, boost_histogram as bh, hist, grpc
from histserv.client import Client
from histserv.protos import hist_pb2
from histserv.serialize import serialize_chunk_payload
from histserv.serialize import serialize_unique_id

s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
srv = subprocess.Popen([sys.executable, "-m", "histserv", "--port", str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    time.sleep(2.0)
    c = Client(f"127.0.0.1:{port}")
    # 1. unnamed bh axis -> init?
    unnamed = bh.Histogram(bh.axis.Regular(50, 0, 1), storage=bh.storage.Weight())
    try:
        c.init(hist.Hist(unnamed)); print("UNNAMED_INIT ok")
    except Exception as e:
        print("UNNAMED_INIT refused:", type(e).__name__, str(e)[:90])
    # 2. bh axis with metadata name -> hist named?
    named_bh = bh.Histogram(bh.axis.Regular(50, 0, 1, metadata={"name": "x"}), storage=bh.storage.Weight())
    hh = hist.Hist(named_bh)
    print("HIST_AXES_NAME_FROM_METADATA", hh.axes[0].name, "| via hist.axis:", hist.Hist(hist.axis.Regular(50, 0, 1, name="x"), storage=hist.storage.Weight()).axes[0].name)
    template = hist.Hist(hist.axis.Regular(50, 0, 1, name="x"), storage=hist.storage.Weight())
    r1 = c.init(template); r2 = c.init(template)
    print("HIST_ID_SERVER_ASSIGNED", r1.hist_id != r2.hist_id, len(r1.hist_id))
    # 3. control: public fill with raw values
    rng = np.random.default_rng(1); x = rng.random(10_000); w = rng.random(10_000)
    r1.fill(x=x, weight=w, unique_id="p0")
    # 4. pre-binned: a bh partial shipped as one FillRequest
    partial = bh.Histogram(bh.axis.Regular(50, 0, 1), storage=bh.storage.Weight()); partial.fill(x, weight=w)
    chunk = serialize_chunk_payload((), partial.view(flow=True), shape=r1._template.dense_view_shape, dtype=r1._template.dense_view_dtype, codec=None)
    req = hist_pb2.FillRequest(hist_id=r1.hist_id, chunk_key=chunk.chunk_key, dense_view=chunk.dense_view)
    req.unique_id = serialize_unique_id("p1")
    c.stub.Fill(req, timeout=10, metadata=r1._metadata()); print("PREBINNED_FILL ok bytes", len(chunk.dense_view))
    try:
        c.stub.Fill(req, timeout=10, metadata=r1._metadata()); print("REPLAY accepted (BAD)")
    except grpc.RpcError as e:
        print("REPLAY", e.code())
    snap = r1.snapshot(delete_from_server=True).to_hist()
    expect = partial.view(flow=True).copy(); expect["value"] *= 2; expect["variance"] *= 2
    print("SNAPSHOT_EQUALS_2x_PARTIAL", np.array_equal(snap.view(flow=True)["value"], expect["value"]) and np.array_equal(snap.view(flow=True)["variance"], expect["variance"]))
    print("SNAPSHOT_TYPE", type(snap).__name__, "isinstance bh", isinstance(snap, bh.Histogram))
    print("DELETED", not r1.exists())
finally:
    srv.terminate(); srv.wait()
