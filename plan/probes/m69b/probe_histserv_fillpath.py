"""The fill path m69b plans, against real histserv 0.2.1 (graphed d0ad16b, graphed-histogram 4c4b79f).

Run: python probe_histserv_fillpath.py > probe_histserv_fillpath.txt  (a venv with those three + pyarrow)
P1 a template built from the slot's spec (dense axes renamed a0.., the fill-time "variation" axis as the chunk
   axis), inited EMPTY, needs no user axis names and sends no dense bytes;
P2 one FillMany per (slot, partition) with every chunk, unique_id=str(partition): a replay is ALREADY_EXISTS;
P3 the snapshot's chunks placed by label into zero_of(spec) equal the local plan bit-for-bit (flow included), for
   Weight/Double/Int64 on Regular+Variable+Integer axes, axis mode and sibling mode;
P4 a slot never filled snapshots to no chunks; P5 a user category axis's overflow is dropped by histserv.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time

import awkward as ak
import boost_histogram as bh
import graphed_histogram as gh
import grpc
import hist
import numpy as np
from graphed import Session, vary
from graphed.awkward import AwkwardBackend, from_parquet
from graphed.core.execution import LocalResources, SequentialRunner
from graphed_histogram._spec import zero_of
from histserv.chunked_hist import ChunkedHist
from histserv.client import Client
from histserv.protos import hist_pb2
from histserv.serialize import serialize_chunk_payload, serialize_unique_id


def template(spec: str) -> tuple[ChunkedHist, bool]:
    z = zero_of(spec)
    axes = list(z.axes)
    varied = axes and axes[-1].__dict__.get("name") == "variation" and isinstance(axes[-1], bh.axis.StrCategory)
    dense = axes[:-1] if varied else axes
    renamed = []
    for i, ax in enumerate(dense):
        ax = ax.__copy__()
        ax.__dict__["name"] = f"a{i}"
        renamed.append(ax)
    if varied:
        renamed.append(hist.axis.StrCategory(list(axes[-1]), name="variation"))
    return ChunkedHist(*renamed, storage=z.storage_type()), bool(varied)


def ship(stub, hist_id, t: ChunkedHist, varied: bool, partial: bh.Histogram, uid: str):
    view = partial.view(flow=True)
    if varied:
        labels = list(partial.axes[-1])
        chunks = [serialize_chunk_payload((lab,), np.ascontiguousarray(view[..., i]), shape=t.dense_view_shape,
                                          dtype=t.dense_view_dtype) for i, lab in enumerate(labels)]
    else:
        chunks = [serialize_chunk_payload((), view, shape=t.dense_view_shape, dtype=t.dense_view_dtype)]
    req = hist_pb2.FillManyRequest(hist_id=hist_id, chunks=chunks)
    req.unique_id = serialize_unique_id(uid)
    return stub.FillMany(req, timeout=30), req.ByteSize()


def resolve(snap: ChunkedHist, spec: str, varied: bool) -> bh.Histogram:
    out = zero_of(spec)
    view = out.view(flow=True)
    if varied:
        index = {lab: i for i, lab in enumerate(out.axes[-1])}
        for key, chunk in snap.items():
            view[..., index[key[0]]] = chunk
    else:
        for _key, chunk in snap.items():
            view[...] = chunk
    return out


def equal(a: bh.Histogram, b: bh.Histogram) -> bool:
    va, vb = a.view(flow=True), b.view(flow=True)
    if va.dtype.fields:
        return all(np.array_equal(va[f], vb[f]) for f in va.dtype.names)
    return va.dtype == vb.dtype and np.array_equal(va, vb)


d = tempfile.mkdtemp()
path = os.path.join(d, "e.parquet")
rng = np.random.default_rng(7)
x = rng.normal(2.0, 1.5, 4000)
ak.to_parquet(ak.Array({"x": x, "n": rng.integers(-1, 9, 4000), "w": rng.uniform(-0.5, 2.0, 4000)}), path)

s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
srv = subprocess.Popen([sys.executable, "-m", "histserv", "--port", str(port), "--log-level", "ERROR"])
try:
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close(); break
        except OSError:
            time.sleep(0.05)
    client = Client(f"127.0.0.1:{port}")
    for storage in (bh.storage.Weight(), bh.storage.Double(), bh.storage.Int64()):
        sess = Session(AwkwardBackend())
        ev = from_parquet(sess, "events", path, steps_per_file=3)
        axis_mode = gh.boost.Histogram(bh.axis.Regular(20, -2, 6), bh.axis.Integer(0, 5), storage=storage)
        sibling = gh.boost.Histogram(bh.axis.Variable([-1, 0, 0.5, 2, 5]), storage=storage)
        weighted = not isinstance(storage, bh.storage.Int64)
        w = vary(ev.w, "sf", up=ev.w * 1.25, down=ev.w * 0.75)
        if weighted:
            axis_mode.fill(ev.x, ev.n, weight=[w], variation_axis=True)
            sibling.fill(ev.x, weight=[w])
        else:
            axis_mode.fill(ev.x, ev.n, variation_axis=True)
            sibling.fill(ev.x)
        plan = gh.plan({"a": axis_mode, "s": sibling}, steps_per_file=3)
        local = SequentialRunner().run(plan).value
        res = LocalResources()
        partials = [plan.process(t.partition, res) for t in sorted(plan.tasks, key=lambda t: t.key)]
        name = type(storage).__name__
        for slot, spec in [(k, sp) for k, _i, sp in plan.process.reduce.layout]:
            t, varied = template(spec)
            init_req_bytes = len(ChunkedHist.metadata_json(t))
            remote = client.init(t)
            sizes = []
            for task, part in zip(sorted(plan.tasks, key=lambda t: t.key), partials, strict=True):
                _r, size = ship(client.stub, remote.hist_id, t, varied, part[slot], str(task.partition))
                sizes.append(size)
            try:
                ship(client.stub, remote.hist_id, t, varied, partials[0][slot], str(plan.tasks[0].partition))
                replay = "accepted (BAD)"
            except grpc.RpcError as e:
                replay = e.code().name
            snap = remote.snapshot(delete_from_server=True)
            got = resolve(snap, spec, varied)
            print(f"{name} slot={slot!r} chunk_axis={varied} chunks={len(list(snap.items()))} init_json_bytes={init_req_bytes}"
                  f" fillmany_bytes={sizes[0]} replay={replay} equal_to_local={equal(got, local[slot])}")
    # P4: never filled
    t, varied = template(json.dumps(json.loads(gh.spec_of(bh.Histogram(bh.axis.Regular(3, 0, 1))))))
    r = client.init(t)
    print(f"P4 never-filled slot: snapshot chunks={len(list(r.snapshot().items()))}")
    # P5: a user category axis as a chunk axis drops its overflow bin
    cat = hist.Hist(hist.axis.StrCategory(["a"], name="c"), hist.axis.Regular(2, 0, 1, name="x"))
    cat.fill(c=["a", "zzz"], x=[0.5, 0.5])
    r = client.init(cat)
    back = r.snapshot().to_hist()
    print(f"P5 user StrCategory: local total={cat.sum(flow=True)} after histserv round trip={back.sum(flow=True)}")
finally:
    srv.terminate(); srv.wait()
