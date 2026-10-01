"""r5-B: does the grpc.RpcError a FillMany to a dead server raises survive pickling (a pool/pilot task's
exception crosses a process boundary)?  Run: graphed-histogram/.venv/bin/python probe_rpcerror_pickle_rv5b.py"""
import pickle
import socket

import cloudpickle
import grpc
from histserv.client import Client
from histserv.protos import hist_pb2

s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()  # nothing listens
try:
    Client(f"127.0.0.1:{port}").stub.FillMany(hist_pb2.FillManyRequest(hist_id="x"), timeout=5)
except grpc.RpcError as exc:
    print(f"raised {type(exc).__module__}.{type(exc).__qualname__} code={exc.code().name}")
    for name, dumps in (("pickle", pickle.dumps), ("cloudpickle", cloudpickle.dumps)):
        try:
            back = pickle.loads(dumps(exc))
            print(f"{name}: round-trips as {type(back).__qualname__}")
        except Exception as err:  # noqa: BLE001
            print(f"{name}: {type(err).__name__}: {err}")
