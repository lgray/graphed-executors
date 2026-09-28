"""60 s live probe: server on localhost, 1-D init, fills from two processes, snapshot."""
import multiprocessing as mp, os, pickle, subprocess, sys, time
import numpy as np, hist
from histserv import Client
from histserv.client import RemoteHist

PORT = 50551


def worker(args):
    blob, info, seed, via = args
    remote = pickle.loads(blob) if via == "pickle" else RemoteHist.from_connection_info(info)
    sizes = []
    real = remote.client.stub.Fill
    def spy(req, **kw):
        sizes.append(req.ByteSize())
        return real(req, **kw)
    remote.client.stub.Fill = spy
    rng = np.random.default_rng(seed)
    for i in range(3):
        remote.fill(x=rng.uniform(0, 100, 10_000), dataset="ttbar", weight=np.ones(10_000), unique_id=f"{seed}-{i}")
    try:  # replay of an id
        remote.fill(x=rng.uniform(0, 100, 10_000), dataset="ttbar", weight=np.ones(10_000), unique_id=f"{seed}-0")
        replay = "accepted"
    except Exception as exc:
        replay = f"{exc.code()} {exc.details()}"
    return os.getpid(), sizes, replay


if __name__ == "__main__":
    srv = subprocess.Popen([sys.executable, "-m", "histserv", "--port", str(PORT), "--log-level", "WARNING"])
    try:
        time.sleep(3)
        c = Client(f"localhost:{PORT}")
        h = hist.Hist(hist.axis.Regular(50, 0, 100, name="x"), hist.axis.StrCategory([], name="dataset", growth=True), storage=hist.storage.Weight())
        remote = c.init(h, token="run-secret")
        print("REMOTE", remote)
        print("CHUNK_AXES", remote._template.chunk_axis_names, "DENSE_SHAPE", remote._template.dense_view_shape, remote._template.dense_view_dtype)
        blob = pickle.dumps(remote)
        print("PICKLED_REMOTEHIST_BYTES", len(blob))
        info = remote.get_connection_info()
        with mp.get_context("spawn").Pool(2) as pool:
            out = pool.map(worker, [(blob, info, 1, "pickle"), (blob, info, 2, "connection_info")])
        for pid, sizes, replay in out:
            print("WORKER_PID", pid, "FILL_REQUEST_BYTES", sizes, "REPLAYED_UNIQUE_ID", replay)
        snap = remote.snapshot()
        H = snap.to_hist()
        print("SNAPSHOT_TYPE", type(snap).__name__, "->", type(H).__module__ + "." + type(H).__name__)
        print("SNAPSHOT_SUM", H.sum(flow=True), "expected_6_fills", 6 * 10_000)
        print("WAS_FILLED_1-0", remote.was_filled_with_unique_id("1-0"), "WAS_FILLED_9-9", remote.was_filled_with_unique_id("9-9"))
        try:
            c.connect(remote.hist_id, token="wrong")
            print("WRONG_TOKEN accepted")
        except Exception as exc:
            print("WRONG_TOKEN refused:", type(exc).__name__, getattr(exc, "code", lambda: "")(), getattr(exc, "details", lambda: "")())
        try:
            c.connect(remote.hist_id)
            print("NO_TOKEN accepted")
        except Exception as exc:
            print("NO_TOKEN refused:", type(exc).__name__, exc.code(), exc.details())
        print("STATS", {k: v for k, v in c.stats().items() if k in ("histogram_count", "histogram_bytes", "version")})
    finally:
        srv.terminate(); srv.wait()
    out = subprocess.run(["lsof", "-nP", "-iTCP:%d" % PORT, "-sTCP:LISTEN"], capture_output=True, text=True).stdout
    print("LISTENER_AFTER_STOP", out.strip() or "none")
