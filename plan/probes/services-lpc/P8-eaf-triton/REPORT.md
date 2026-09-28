# P8 — EAF Triton from an LPC batch worker (2026-09-25 15:23–15:24Z, lpcschedd5, cluster 30434471)

Evidence: `transcript.txt`. Job ran on cmswn2181 inside coffea-almalinux9-noml:2026.9.0-py3.12 (apptainer --contain).

| check (worker → triton.fnal.gov:443) | result |
|---|---|
| HTTP GET /v2/bogus-path | 200, content-type application/grpc (any path answers: not a readiness signal) |
| grpc.health.v1 Check service="" | SERVING, 0.041 s |
| grpc.health.v1 Check service="inference.GRPCInferenceService" | SERVING, 0.018 s |
| control: grpc.health.v1 against www.fnal.gov:443 | PERMISSION_DENIED |
| tritonclient.grpc(ssl=True) is_server_live / is_server_ready | True / True, 0.027 s |
| get_model_metadata("resnet50") | NOT_FOUND "has no available versions" — listed READY from the login node minutes earlier; the served model set changes under users |

So an LPC batch worker reaches the EAF Triton over gRPC+TLS. Cleanup: removed, `left: 0`, `~/graphed-probe-p8` removed.
