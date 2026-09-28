#!/bin/bash
echo "host=$(hostname -f) machine=$(grep -E '^Machine' ${_CONDOR_MACHINE_AD:-/dev/null} | head -1) date=$(date -u +%FT%TZ)"
python3 -m pip install -q --target "$PWD/pylib" "tritonclient[grpc]" grpcio-health-checking 2>&1 | tail -2
export PYTHONPATH=$PWD/pylib
echo "http-layer: $(curl -sS -m 10 -o /dev/null -w '%{http_code} ct=%{content_type}' https://triton.fnal.gov/v2/bogus-path 2>&1)"
python3 - <<'PY'
import time, grpc
from grpc_health.v1 import health_pb2, health_pb2_grpc
creds = grpc.ssl_channel_credentials()
for svc in ("", "inference.GRPCInferenceService"):
    try:
        t = time.time(); r = health_pb2_grpc.HealthStub(grpc.secure_channel("triton.fnal.gov:443", creds)).Check(health_pb2.HealthCheckRequest(service=svc), timeout=10)
        print("grpc.health.v1 service=%r -> %s %.3fs" % (svc, health_pb2.HealthCheckResponse.ServingStatus.Name(r.status), time.time() - t))
    except grpc.RpcError as e:
        print("grpc.health.v1 service=%r -> RpcError %s %s" % (svc, e.code(), (e.details() or "")[:200]))
try:
    health_pb2_grpc.HealthStub(grpc.secure_channel("www.fnal.gov:443", creds)).Check(health_pb2.HealthCheckRequest(service=""), timeout=10)
    print("control www.fnal.gov -> answered (unexpected)")
except grpc.RpcError as e:
    print("control www.fnal.gov -> RpcError", e.code())
import tritonclient.grpc as g
c = g.InferenceServerClient("triton.fnal.gov:443", ssl=True)
t = time.time(); print("tritonclient live=%s ready=%s %.3fs" % (c.is_server_live(), c.is_server_ready(), time.time() - t))
m = c.get_model_metadata("resnet50"); print("resnet50:", m.platform, [(i.name, i.datatype, list(i.shape)) for i in m.inputs])
PY
echo "rc=$?"
