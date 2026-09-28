"""Premises for the endpoint-protocol revision of plan-services.md (D1/D4/D7).

Run: <venv with tritonclient[grpc,http] grpcio grpcio-health-checking>/bin/python probe_endpoint_protocol.py
"""

import http.server
import inspect
import socket
import threading
import time
import urllib.request
from concurrent import futures

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc


def varint(n: int) -> bytes:
    out = b""
    while True:
        b, n = n & 0x7F, n >> 7
        out += bytes([b | (0x80 if n else 0)])
        if not n:
            return out


def raw_health(hostport: str, service: str, tls: bool, timeout: float = 5.0) -> bytes:
    """grpc.health.v1.Health/Check with grpcio only: request/response as raw protobuf bytes."""
    s = service.encode()
    req = (b"\x0a" + varint(len(s)) + s) if s else b""
    ch = grpc.secure_channel(hostport, grpc.ssl_channel_credentials()) if tls else grpc.insecure_channel(hostport)
    with ch:
        return ch.unary_unary("/grpc.health.v1.Health/Check")(req, timeout=timeout)


def outcome(fn):
    try:
        return repr(fn())
    except grpc.RpcError as e:
        return f"RpcError {e.code().name}"
    except Exception as e:  # noqa: BLE001
        return f"{type(e).__name__}: {str(e)[:120]}"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# 1. a gRPC server with the reference health servicer (grpcio-health-checking)
srv1 = grpc.server(futures.ThreadPoolExecutor(2))
hs = health.HealthServicer()
health_pb2_grpc.add_HealthServicer_to_server(hs, srv1)
hs.set("", health_pb2.HealthCheckResponse.SERVING)
hs.set("svc.A", health_pb2.HealthCheckResponse.SERVING)
hs.set("svc.B", health_pb2.HealthCheckResponse.NOT_SERVING)
p1 = srv1.add_insecure_port("127.0.0.1:0")
srv1.start()
# 2. a gRPC server without any health service
srv2 = grpc.server(futures.ThreadPoolExecutor(2))
p2 = srv2.add_insecure_port("127.0.0.1:0")
srv2.start()


# 3. a plain HTTP/1 server; 4. an HTTP/1 server answering 200 application/grpc on every path (EAF shape)
class Grpcish(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("content-type", "application/grpc")
        self.end_headers()

    def log_message(self, *a):
        pass


class Plain(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


h3 = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Plain)
h4 = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Grpcish)
for h in (h3, h4):
    threading.Thread(target=h.serve_forever, daemon=True).start()
p3, p4 = h3.server_address[1], h4.server_address[1]

print("== P-a raw-bytes grpc.health.v1 client (grpcio only) vs the reference servicer / stub")
for svc in ("", "svc.A", "svc.B", "svc.unknown"):
    stub = health_pb2_grpc.HealthStub(grpc.insecure_channel(f"127.0.0.1:{p1}"))
    ref = outcome(lambda: health_pb2.HealthCheckResponse.ServingStatus.Name(
        stub.Check(health_pb2.HealthCheckRequest(service=svc), timeout=5).status))
    print(f"service={svc!r:14} raw={outcome(lambda: raw_health(f'127.0.0.1:{p1}', svc, False)):22} stub={ref}")
print("SERVING bytes == b'\\x08\\x01':", raw_health(f"127.0.0.1:{p1}", "", False) == b"\x08\x01")
print("grpc server without health  :", outcome(lambda: raw_health(f"127.0.0.1:{p2}", "", False)))
print("plain HTTP/1 server          :", outcome(lambda: raw_health(f"127.0.0.1:{p3}", "", False)))
print("HTTP/1 200 application/grpc  :", outcome(lambda: raw_health(f"127.0.0.1:{p4}", "", False)))
print("closed port                  :", outcome(lambda: raw_health(f"127.0.0.1:{free_port()}", "", False, 2)))
print("TLS channel to a plaintext gRPC server:", outcome(lambda: raw_health(f"127.0.0.1:{p1}", "", True, 3)))

print("== P-a' the http check's false pass and its guard (EAF shape reproduced locally)")
for port, what in ((p4, "grpc-ish"), (p3, "plain")):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/v2/bogus-path", timeout=5) as r:
            ct = r.headers.get("content-type", "")
            print(f"{what:9} GET /v2/bogus-path -> {r.status} ct={ct!r} guarded_pass={200 <= r.status < 300 and not ct.startswith('application/grpc')}")
    except Exception as e:  # noqa: BLE001
        print(f"{what:9} GET /v2/bogus-path -> {type(e).__name__} {e}")

print("== P-b tritonclient constructors: signature, laziness, scheme in url")
import tritonclient  # noqa: E402
import tritonclient.grpc as tg  # noqa: E402
import tritonclient.http as th  # noqa: E402

print("tritonclient", getattr(tritonclient, "__version__", "?"))
print("grpc sig:", inspect.signature(tg.InferenceServerClient.__init__))
print("http sig:", inspect.signature(th.InferenceServerClient.__init__))
dead = free_port()
for mod, url, kw in ((tg, f"127.0.0.1:{dead}", {"ssl": True}), (th, f"127.0.0.1:{dead}", {"ssl": True}),
                     (tg, f"127.0.0.1:{dead}", {}), (th, f"127.0.0.1:{dead}", {})):
    t = time.time()
    c = mod.InferenceServerClient(url=url, **kw)
    print(f"{mod.__name__:18} {kw} constructed against a closed port in {time.time()-t:.3f}s; is_server_live ->",
          outcome(c.is_server_live)[:90])
print("http client given 'http://host:port' against a live HTTP server:",
      outcome(lambda: th.InferenceServerClient(url=f"http://127.0.0.1:{p3}").is_server_live())[:140])
print("http client given 'host:port' against the same server:",
      outcome(lambda: th.InferenceServerClient(url=f"127.0.0.1:{p3}").is_server_live())[:140])
print("grpc client given 'grpc://host:port' (reference health server):",
      outcome(lambda: tg.InferenceServerClient(url=f"grpc://127.0.0.1:{p1}").is_server_live())[:140])
print("same request classes on both modules:",
      all(hasattr(m, n) for m in (tg, th) for n in ("InferInput", "InferRequestedOutput")),
      [str(inspect.signature(m.InferInput.__init__)) for m in (tg, th)])

print("== P-c EAF Triton from this machine (TLS, public roots)")
print("raw health '' :", outcome(lambda: raw_health("triton.fnal.gov:443", "", True, 8)))
print("raw health inference.GRPCInferenceService :",
      outcome(lambda: raw_health("triton.fnal.gov:443", "inference.GRPCInferenceService", True, 8)))
print("tritonclient.grpc ssl=True live :", outcome(lambda: tg.InferenceServerClient("triton.fnal.gov:443", ssl=True).is_server_live()))
srv1.stop(0)
srv2.stop(0)
