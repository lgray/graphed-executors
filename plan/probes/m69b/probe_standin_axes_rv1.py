"""m69b-r1: the server-side template built from flow EXTENTS only (each dense axis a no-flow Regular of its flow
extent; the fill-time variation axis the chunk axis, as §5.1 P1) carries slots with category and
boolean axes bit for bit (flow included), so their refusal is not needed for correctness.

Run: ~/vibe-coding/cloud/graphed-histogram/.venv/bin/python probe_standin_axes_rv1.py > probe_standin_axes_rv1.txt
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time

import awkward as ak
import boost_histogram as bh
import graphed_histogram as gh
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


def standin(spec: str) -> tuple[ChunkedHist, bool]:
    z = zero_of(spec)
    axes = list(z.axes)
    varied = bool(axes) and axes[-1].__dict__.get("name") == "variation" and isinstance(axes[-1], bh.axis.StrCategory)
    dense = axes[:-1] if varied else axes
    out = [hist.axis.Regular(ax.extent, 0.0, 1.0, underflow=False, overflow=False, name=f"a{i}") for i, ax in enumerate(dense)]
    if varied:
        out.append(hist.axis.StrCategory(list(axes[-1]), name="variation"))
    return ChunkedHist(*out, storage=z.storage_type()), varied


def ship(stub, hist_id, t, varied, partial, uid):
    view = partial.view(flow=True)
    labels = list(partial.axes[-1]) if varied else [None]
    chunks = [serialize_chunk_payload((lab,) if varied else (), np.ascontiguousarray(view[..., i] if varied else view),
                                      shape=t.dense_view_shape, dtype=t.dense_view_dtype) for i, lab in enumerate(labels)]
    req = hist_pb2.FillManyRequest(hist_id=hist_id, chunks=chunks)
    req.unique_id = serialize_unique_id(uid)
    stub.FillMany(req, timeout=30)


def resolve(snap, spec, varied):
    out = zero_of(spec)
    view = out.view(flow=True)
    index = {lab: i for i, lab in enumerate(out.axes[-1])} if varied else None
    for key, chunk in snap.items():
        if varied:
            view[..., index[key[0]]] = chunk
        else:
            view[...] = chunk
    return out


def equal(a, b):
    va, vb = a.view(flow=True), b.view(flow=True)
    if va.dtype.fields:
        return all(np.array_equal(va[f], vb[f]) for f in va.dtype.names)
    return np.array_equal(va, vb)


d = tempfile.mkdtemp(); path = os.path.join(d, "e.parquet")
rng = np.random.default_rng(3)
n = 3000
ak.to_parquet(ak.Array({"x": rng.lognormal(3, 1, n), "c": rng.choice(["ee", "mm", "em", "tt"], n),
                        "k": rng.integers(-1, 5, n), "b": rng.integers(0, 2, n).astype(bool),
                        "w": rng.uniform(-0.5, 2, n)}), path)
s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
srv = subprocess.Popen([sys.executable, "-m", "histserv", "--port", str(port), "--log-level", "ERROR"])
try:
    for _ in range(200):
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close(); break
        except OSError:
            time.sleep(0.05)
    client = Client(f"127.0.0.1:{port}")
    sess = Session(AwkwardBackend())
    ev = from_parquet(sess, "events", path, steps_per_file=3)
    w = vary(ev.w, "sf", up=ev.w * 1.25, down=ev.w * 0.75)
    cats = {
        "strcat_reg": gh.boost.Histogram(bh.axis.StrCategory(["ee", "mm", "em"]), bh.axis.Regular(10, 1, 1000), storage=bh.storage.Weight()),
        "intcat_bool": gh.boost.Histogram(bh.axis.IntCategory([0, 1, 2]), bh.axis.Boolean(), storage=bh.storage.Double()),
    }
    cats["strcat_reg"].fill(ev.c, ev.x, weight=[w], variation_axis=True)
    cats["intcat_bool"].fill(ev.k, ev.b, weight=[w])
    plan = gh.plan(cats, steps_per_file=3)
    local = SequentialRunner().run(plan).value
    res = LocalResources()
    tasks = sorted(plan.tasks, key=lambda t: t.key)
    partials = [plan.process(t.partition, res) for t in tasks]
    for slot, _i, spec in plan.process.reduce.layout:
        t, varied = standin(spec)
        remote = client.init(t)
        for task, part in zip(tasks, partials, strict=True):
            ship(client.stub, remote.hist_id, t, varied, part[slot], str(task.partition))
        got = resolve(remote.snapshot(delete_from_server=True), spec, varied)
        axes = [type(a).__name__ + ("(log)" if getattr(a, "transform", None) is not None else "") for a in local[slot].axes]
        print(f"slot={slot!r} axes={axes} flow_total_local={local[slot].sum(flow=True)} equal_to_local={equal(got, local[slot])}")
finally:
    srv.terminate(); srv.wait()
