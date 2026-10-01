"""Warm idle histserv 0.2.1 server RSS with and without pandas importable (hist.basehist imports pandas,
and pandas pyarrow, when installed). Warm-up = the model probe's (Init, one FillMany with a unique_id,
Snapshot with delete); server argv = the frozen harness's."""
import socket, subprocess, sys, time
import boost_histogram as bh, hist, numpy as np
from histserv import Client
from histserv.chunked_hist import ChunkedHist
from histserv.protos import hist_pb2
from histserv.serialize import serialize_chunk_payload, serialize_unique_id

def status(pid, field):
    for line in open(f"/proc/{pid}/status"):
        if line.startswith(field + ":"):
            return int(line.split()[1]) * 1024

s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
p = subprocess.Popen([sys.executable, "-m", "histserv", "--port", str(port), "--log-level", "ERROR"])
try:
    for _ in range(600):
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close(); break
        except OSError: time.sleep(0.05)
    c = Client(f"127.0.0.1:{port}")
    r = c.init(ChunkedHist(hist.axis.Regular(6, 0.0, 1.0, name="a0"), storage=bh.storage.Double()))
    t = r._template; v = np.ones(t.dense_view_shape, dtype=t.dense_view_dtype)
    req = hist_pb2.FillManyRequest(hist_id=r.hist_id, chunks=[serialize_chunk_payload((), v, shape=t.dense_view_shape, dtype=t.dense_view_dtype)])
    req.unique_id = serialize_unique_id("w"); c.stub.FillMany(req, timeout=60)
    r.snapshot(delete_from_server=True)
    time.sleep(0.6)
    mods = open(f"/proc/{p.pid}/maps").read()
    print(f"warm VmRSS {status(p.pid, 'VmRSS') / 2**20:.1f} MiB; pandas mapped: {'pandas' in mods}; pyarrow mapped: {'pyarrow' in mods}; B = 129 MiB")
finally:
    p.kill(); p.wait()
