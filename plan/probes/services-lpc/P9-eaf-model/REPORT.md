# P9 — graphed_identity served by the EAF Triton (2026-09-25 15:57–15:59Z)

Model: `graphed_identity/` (this dir; ONNX Identity, opset 13, IR 8, INPUT0→OUTPUT0 FP32 [-1,-1], `onnxruntime_onnx`),
uploaded by the owner to `triton-models` on https://s3-eaf.fnal.gov. Check: `check.py` (gRPC+TLS to triton.fnal.gov:443).

| where | is_model_ready | metadata | infer (randn 5×3 / 1×4096 / NaN,±inf,−0,denormal,max,min) | evidence |
|---|---|---|---|---|
| LPC login cmslpc305 | READY at first poll | onnxruntime_onnx v1, INPUT0/OUTPUT0 FP32 [-1,-1] | bit-for-bit ×3, 1.8–3.6 ms | `login-transcript.txt` |
| LPC batch worker cmswn2186 (coffea image, lpcschedd5 cluster 30436084) | READY | same | bit-for-bit ×3, 2.3–3.6 ms | `batch-transcript.txt` |

Control: a one-ulp perturbation compares unequal. Bucket → server load latency is bounded only by the time between
the owner's upload and the first poll (already READY). Cleanup: job removed, `left: 0`, scratch dirs removed.
